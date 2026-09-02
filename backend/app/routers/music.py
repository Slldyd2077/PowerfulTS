"""音乐路由 — 代理 TSMusicBot API。

用户只与 PowerfulTS 交互（统一认证 X-Session-Token，由 get_current_account 校验），
后端代理到 TSMusicBot (:3000)，用户看不到 TSMusicBot WebUI。
"""
from __future__ import annotations

from typing import Annotated, Literal

import asyncio
import logging
import re
from datetime import datetime
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request, Response, WebSocket, WebSocketDisconnect
from websockets.exceptions import InvalidHandshake
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.database import get_db
from ..deps import AccountDep, AdminDep, TsmusicDep, VoiceAccountDep, get_current_account
from ..models import Account, BotOwnership, BotShare, EntrySound, Friend
from ..services import bot_mover
from ..services.auth_service import AuthService
from ..services.entry_sound import (
    EntrySoundValidationError,
    inspect_audio,
    read_limited_upload,
)
from ..services.tsmusic_client import TSMusicClient, TSMusicUnavailable
from ..services.voice_bot import VoiceBotError
from ..services.voice_exclusivity import NATIVE_TS_PREEMPTED_CLOSE_CODE

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/music", tags=["music"])
settings = get_settings()
VOICE_DIAGNOSTICS_UPSTREAM_TIMEOUT_SECONDS = 0.8
ENTRY_SOUND_EFFECT_TIMEOUT_SECONDS = 3.0


# ───────────────────────── 依赖 ─────────────────────────

# TsmusicDep / AccountDep 由 ..deps 统一提供（按当前用户路由到其专属容器 client）。

# 前端按 JS 惯例用 query 参数 botId（camelCase）传当前 bot；此处用 alias 对齐，
# 否则 FastAPI 只认 snake_case 的 bot_id，前端传的真实 bot id 会被丢弃、回退默认 bot
# （曾因此静默打到不存在的默认 bot → 上游 404 → UI 假显示"正在播放"）。
BotIdQuery = Annotated[str | None, Query(alias="botId")]


async def _owned_bot_id(
    bot_id: BotIdQuery = None,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
) -> str | None:
    """解析 botId 并校验可访问性：非空时必须是当前 account **拥有或被共享**的 bot，否则 403。

    放宽以支持好友共享 bot（接受方可播放/点播/启停）。管理类操作（delete/配置/平台账号）
    用 _strict_owned_bot_id（仅 owner）。
    """
    if bot_id:
        accessible = await _accessible_bot_ids(db, account.id)
        if bot_id not in accessible:
            raise HTTPException(status_code=403, detail="无权操作该 Bot（不属于你，也未共享给你）")
    return bot_id


async def _strict_owned_bot_id(
    bot_id: BotIdQuery = None,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
) -> str | None:
    """严格 owner 校验：仅 bot 的 owner 可用（delete/配置/profile/avatar/平台账号 auth）。"""
    if bot_id:
        owned = await _owned_bot_ids(db, account.id)
        if bot_id not in owned:
            raise HTTPException(status_code=403, detail="仅 Bot 主人可执行此操作")
    return bot_id


# 播放/点播/启停类：owner 或被共享者可用
OwnedBotId = Annotated[str | None, Depends(_owned_bot_id)]
# 管理类（delete/配置/平台账号）：仅 owner
StrictOwnedBotId = Annotated[str | None, Depends(_strict_owned_bot_id)]


async def _library_bot_id(
    bot_id: BotIdQuery = None,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
) -> str:
    """解析曲库身份：自己的 Bot，或明确附带歌单权限的共享 Bot。"""
    owned = await _owned_bot_ids(db, account.id)
    if bot_id:
        if bot_id in owned:
            return bot_id
        playlist_share = (
            await db.execute(
                select(BotShare.id).where(
                    BotShare.bot_id == bot_id,
                    BotShare.shared_to_account_id == account.id,
                    BotShare.share_playlists.is_(True),
                )
            )
        ).first()
        if playlist_share:
            return bot_id
        raise HTTPException(status_code=403, detail="该共享 Bot 未授予歌单访问权限")
    if not owned:
        raise HTTPException(status_code=409, detail="请先创建自己的 Bot 并登录音乐平台账号")
    if settings.tsmusic_bot_id in owned:
        return settings.tsmusic_bot_id
    return sorted(owned)[0]


LibraryBotId = Annotated[str, Depends(_library_bot_id)]


# ───────────────────────── 请求模型 ─────────────────────────

class SearchRequest(BaseModel):
    q: str = Field(description="搜索关键词")


class PlayRequest(BaseModel):
    query: str = Field(description="歌名或 'id:xxx' 精确播放")
    queue: bool = Field(default=False, description="True=加入队列, False=立即播放")
    platform: str | None = Field(default=None, description="音源平台 netease/qq/bilibili")
    # 前端传入的歌曲元数据；上游 TSMusicBot 入队 QQ 音乐时会丢失 name/coverUrl，
    # 用它在后端缓存并回填队列 / 当前播放。
    meta: dict | None = Field(default=None, description="歌曲元数据 {id,name,artist,album,duration,coverUrl,platform}")


class LiveAudioStartRequest(BaseModel):
    mime_type: str = Field(alias="mimeType", min_length=1, max_length=128)
    source: Literal["computer", "microphone"] = "computer"


class SeekRequest(BaseModel):
    position: int = Field(ge=0, description="跳转到的播放位置（秒）")


class MoveRequest(BaseModel):
    to: int = Field(ge=0, description="队列项移动到的目标位置（0-based）")


class ShareRequest(BaseModel):
    friendTsNickname: str = Field(min_length=1, max_length=64, description="被共享好友的 TS 昵称")
    includePlaylists: bool = Field(default=False, description="是否同时允许好友浏览该 Bot 账号的私人歌单")


class VolumeRequest(BaseModel):
    volume: int = Field(ge=0, le=100)


class ModeRequest(BaseModel):
    mode: str = Field(description="seq | loop | random | rloop")


class VoiceDuckingRequest(BaseModel):
    """语音闪避（人说话时自动压低音乐音量），字段均可选、部分更新。"""
    enabled: bool | None = Field(default=None, description="是否启用闪避")
    volumePercent: float | None = Field(default=None, ge=0, le=100, description="有人说话时音乐保留的音量百分比")


class BotSettingsRequest(BaseModel):
    """全局 bot 行为设置（各项均可选，未传项上游保持不变）。"""
    idleTimeoutMinutes: int | None = Field(default=None, ge=0, description="频道无人多少分钟后自动断开，0=禁用")
    autoPauseOnEmpty: bool | None = Field(default=None, description="频道无人时自动暂停")
    voiceDucking: VoiceDuckingRequest | None = Field(default=None, description="语音闪避设置")


class BotProfileRequest(BaseModel):
    """per-bot profile 开关（6 字段均可选）。"""
    avatarEnabled: bool | None = None
    descriptionEnabled: bool | None = None
    nicknameEnabled: bool | None = None
    awayStatusEnabled: bool | None = None
    channelDescEnabled: bool | None = None
    nowPlayingMsgEnabled: bool | None = None


class BotAvatarRequest(BaseModel):
    # 200KB 图片 base64 ≈ 273KB + 前缀，留余量到 300KB，防超大 base64 撑爆内存后才被上游拒
    dataUrl: str = Field(max_length=300_000, description="data:image/(png|jpeg|webp);base64,...")


# ───────────────────────── 端点 ─────────────────────────


async def _ensure_follow(
    request: Request,
    tsmusic: TSMusicClient,
    account: Account,
    bot_id: str | None,
) -> dict:
    """播放前移动 bot 到当前用户所在 TS 频道。

    开关关闭 / 失败均不阻断播放，仅返回结果 dict（{moved, reason, ...}）。
    同步 SQ 调用经 asyncio.to_thread 放线程池，异常外层兜底。
    """
    try:
        if not tsmusic.follow_enabled:
            return {"moved": False, "reason": "disabled"}
        # 播放、实时推流等入口都可能遇到被空闲管理器断开的 Bot；先确保其已上线。
        await tsmusic.ensure_player_ready(bot_id)
        bot_client_id = await tsmusic.get_bot_client_id(bot_id)
        bot_nick = await tsmusic.get_bot_nickname(bot_id)
        if bot_client_id is None and not bot_nick:
            logger.warning("跟随跳过: 未能解析 bot clid 或昵称 (bot_id=%s)", bot_id)
            return {"moved": False, "reason": "bot_identity_unknown"}
        # 自动空闲断开后，播放命令会触发 Bot 重连；上游返回时 TS client 可能尚未
        # 出现在 clientlist。短暂重试，重新获取 clid，并刷新昵称兼容旧版上游。
        result: dict = {"moved": False, "reason": "bot_not_found"}
        moved_once = False
        stable_checks = 0
        for attempt in range(10):
            result = await asyncio.to_thread(
                bot_mover.move_bot_to_user,
                settings,
                bot_client_id,
                bot_nick,
                account,
            )
            reason = result.get("reason")
            if reason == "already_together":
                if not moved_once:
                    break
                stable_checks += 1
                if stable_checks >= 2:
                    result = {**result, "moved": True, "reason": "moved"}
                    break
            elif reason == "moved":
                moved_once = True
                stable_checks = 0
                # TSMusicBot 重连初始化可能随后进入 defaultChannel，覆盖本次移动；
                # 连续复查两次，确认初始化完成后仍与点歌者处于同一频道。
            elif reason == "bot_not_found":
                bot_client_id = await tsmusic.get_bot_client_id(bot_id)
                if attempt == 0:
                    bot_nick = await tsmusic.get_bot_nickname(bot_id, refresh=True) or bot_nick
            else:
                break
            if attempt < 9:
                delay = 1.0 if moved_once else min(0.25 * (2**attempt), 1.0)
                await asyncio.sleep(delay)
        if moved_once and result.get("reason") == "already_together":
            result = {**result, "moved": True, "reason": "moved"}
        reason = result.get("reason")
        if result.get("moved"):
            logger.info("跟随完成: bot→cid=%s (用户=%s)", result.get("user_cid"), account.ts_nickname)
        elif reason not in ("disabled", "already_together"):
            logger.warning("跟随未生效: %s (用户=%s)", reason, account.ts_nickname)
        return result
    except Exception:
        logger.warning("跟随异常 (用户=%s)", account.ts_nickname, exc_info=True)
        return {"moved": False, "reason": "exception"}


@router.get("/search")
async def search(
    q: str,
    tsmusic: TsmusicDep,
    _account: AccountDep,
    platform: str | None = None,
    bot_id: OwnedBotId = None,
):
    """搜索歌曲（per-bot：带 botId 用该 bot 的平台 cookie 搜索）。"""
    results = await tsmusic.search(q, platform=platform, bot_id=bot_id)
    return {"count": len(results), "results": results}


@router.post("/play")
async def play(body: PlayRequest, request: Request, tsmusic: TsmusicDep, account: AccountDep, bot_id: OwnedBotId = None):
    """播放（query 可以是歌名或 'id:xxx'，platform 指定音源）。"""
    if body.queue:
        result = await tsmusic.add(body.query, platform=body.platform, meta=body.meta, bot_id=bot_id)
    else:
        result = await tsmusic.play(body.query, platform=body.platform, meta=body.meta, bot_id=bot_id)
    # 先让播放动作唤醒可能被空闲管理器断开的 Bot，再执行频道跟随。
    follow = await _ensure_follow(request, tsmusic, account, bot_id)
    if isinstance(result, dict):
        # 仅回传 moved/reason 给前端，剥离内部 cid/clid（最小信息原则）
        result["follow"] = {"moved": follow.get("moved", False), "reason": follow.get("reason")}
    return result


async def _open_live_relay(
    request: Request,
    tsmusic: TSMusicClient,
    account: Account,
    bid: str,
    mime_type: str,
    title: str,
    follow: dict,
) -> dict:
    """Wire a browser capture session to a bot's live input. Shared by 电脑音频 and 网页通话。"""
    if not mime_type.lower().startswith(("audio/", "video/webm")):
        raise HTTPException(status_code=400, detail="不支持的实时音频格式")

    relay = request.app.state.live_audio
    session = await relay.create(account.id, bid, mime_type)
    configured_base = settings.live_audio_public_url.strip().rstrip("/")
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    proto = forwarded_proto if forwarded_proto in {"http", "https"} else request.url.scheme
    request_host = request.headers.get("host", request.url.netloc)
    base = configured_base or f"{proto}://{request_host}".rstrip("/")
    stream_url = f"{base}/api/music/live/stream/{session.id}"
    try:
        result = await tsmusic.start_live_audio(
            stream_url, mime_type, bot_id=bid, title=title,
        )
    except httpx.HTTPStatusError as exc:
        await relay.close(session.id)
        if exc.response.status_code == 404:
            raise HTTPException(
                status_code=501,
                detail="当前 TSMusicBot 不支持实时输入，请更新到带 /api/player/:botId/live 接口的版本",
            ) from exc
        raise HTTPException(status_code=502, detail="音乐机器人未能启动实时播放") from exc
    except httpx.HTTPError as exc:
        await relay.close(session.id)
        raise HTTPException(status_code=502, detail="无法连接音乐机器人") from exc
    return {
        "ok": True,
        "sessionId": session.id,
        "uploadPath": f"/api/music/live/{session.id}/upload",
        "follow": {"moved": follow.get("moved", False), "reason": follow.get("reason")},
        "upstream": result,
    }


@router.post("/live/start")
async def start_live_audio(
    body: LiveAudioStartRequest,
    request: Request,
    tsmusic: TsmusicDep,
    account: AccountDep,
    bot_id: OwnedBotId = None,
):
    """Create a one-use live relay after the browser has granted capture access."""
    bid = bot_id or tsmusic.bot_id
    if not bid:
        raise HTTPException(status_code=400, detail="请先选择音乐机器人")
    title = (
        f"{account.ts_nickname} 的麦克风"
        if body.source == "microphone"
        else f"{account.ts_nickname} 的电脑音频"
    )
    follow = await _ensure_follow(request, tsmusic, account, bid)
    return await _open_live_relay(
        request, tsmusic, account, bid, body.mime_type, title, follow,
    )


class VoiceMicRequest(BaseModel):
    mime_type: str = Field(alias="mimeType", min_length=1, max_length=128)


@router.post("/voice/mic/start")
async def start_voice_microphone(
    body: VoiceMicRequest,
    request: Request,
    tsmusic: TsmusicDep,
    account: VoiceAccountDep,
    db: AsyncSession = Depends(get_db),
):
    """网页通话的麦克风上行。

    没有复用 /live/start：那条路要 OwnedBotId，而通话 bot 刻意不写 bot_ownerships
    （否则会混进音乐实例列表），会被自己的权限检查判 403。这里直接按账号解析通话 bot。

    也刻意不做「跟随」：跟随会把 bot 拽到用户 TS 客户端所在频道，把网页上刚选好的
    频道覆盖掉——网页通话里用户的选择才是准的。
    """
    await _limit_guest_voice(request, account, "microphone")
    bid = await _voice_bot_id(request, account, db)
    return await _open_live_relay(
        request,
        tsmusic,
        account,
        bid,
        body.mime_type,
        f"{account.ts_nickname} 的网页麦克风",
        {"moved": False, "reason": "voice_call"},
    )


@router.websocket("/live/{session_id}/upload")
async def upload_live_audio(websocket: WebSocket, session_id: str):
    """Receive MediaRecorder chunks; the random short-lived id is the capability."""
    relay = websocket.app.state.live_audio
    session = await relay.attach_upload(session_id)
    if session is None:
        await websocket.close(code=4404, reason="直播会话不存在或已连接")
        return
    await websocket.accept()
    try:
        while True:
            chunk = await websocket.receive_bytes()
            if len(chunk) > 2 * 1024 * 1024:
                await websocket.close(code=4400, reason="音频分片过大")
                break
            if not await relay.push(session_id, chunk):
                await websocket.close(code=4410, reason="实时音频消费者已断开")
                break
    except WebSocketDisconnect:
        pass
    finally:
        closed = await relay.close(session_id)
        if closed is not None:
            try:
                await websocket.app.state.tsmusic.stop(bot_id=closed.bot_id)
            except Exception:
                logger.warning("停止实时音频 bot 失败: %s", closed.bot_id, exc_info=True)


@router.get("/live/stream/{session_id}")
async def consume_live_audio(request: Request, session_id: str):
    """Private, single-consumer capability URL used by TSMusicBot/FFmpeg."""
    session = await request.app.state.live_audio.get(session_id)
    if session is None or session.closed:
        raise HTTPException(status_code=404, detail="直播会话不存在")
    return StreamingResponse(
        request.app.state.live_audio.stream(session_id),
        media_type=session.mime_type,
        headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/live/{session_id}/stop")
async def stop_live_audio(
    session_id: str,
    request: Request,
    tsmusic: TsmusicDep,
    account: VoiceAccountDep,
):
    session = await request.app.state.live_audio.get(session_id)
    if session is None:
        return {"ok": True, "stopped": False}
    if session.account_id != account.id:
        raise HTTPException(status_code=403, detail="无权停止此直播")
    closed = await request.app.state.live_audio.close(session_id)
    if closed is not None:
        await tsmusic.stop(bot_id=closed.bot_id)
    return {"ok": True, "stopped": closed is not None}


async def _voice_bot_id(request: Request, account: Account, db: AsyncSession) -> str:
    """当前账号已开通的通话 bot；没有则 409（提示先加入通话）。"""
    try:
        return await request.app.state.voice_bots.ensure_existing_connected(
            db, account.id
        )
    except VoiceBotError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/voice/diagnostics")
async def voice_diagnostics(
    request: Request,
    tsmusic: TsmusicDep,
    account: VoiceAccountDep,
    db: AsyncSession = Depends(get_db),
):
    """Account-scoped latency telemetry for the active web-voice bot."""
    # Diagnostics is observational: polling it must not restart or extend the
    # lifetime of a voice bot. Interactive voice operations use _voice_bot_id.
    bid = await request.app.state.voice_bots.current_bot_id(db, account.id)
    if not bid:
        raise HTTPException(status_code=409, detail="请先加入通话")
    relay = await request.app.state.live_audio.status_for_bot(bid)
    try:
        upstream = await asyncio.wait_for(
            tsmusic.get_bot_status(bot_id=bid),
            timeout=VOICE_DIAGNOSTICS_UPSTREAM_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.debug("TSMusicBot voice diagnostics timed out", extra={"bot_id": bid})
        upstream = {}
    return {
        "relay": relay,
        "audioPipeline": upstream.get("audioPipeline"),
        "liveVoice": upstream.get("liveVoice"),
    }


async def _limit_guest_voice(request: Request, account: Account, action: str) -> None:
    if account.role != "guest":
        return
    allowed = await request.app.state.guest_voice_limiter.allow(
        f"{account.id}:{action}"
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="游客通话操作过于频繁，请稍后再试")


# 等一次强制轮询的上限。TS 在同机/同网时一轮 channellist+clientlist 只要几十毫秒；
# 真超时了就退回原来的行为（下一个 3 秒周期补上），不把动作本身拖失败。
_SNAPSHOT_SYNC_TIMEOUT = 2.0


async def _sync_ts3_snapshot(request: Request) -> None:
    """让 TS 监控立刻重跑一轮，别让刚做完的动作等下一个轮询周期才在页面上出现。

    /voice/channels 读的是监控的内存快照（3 秒一轮）。加入通话、切频道之后马上去读，
    拿到的还是动作之前的状态 —— 表现就是「点了没反应，过一会儿才更新」。
    """
    monitor = request.app.state.ts3_monitor
    if not monitor.running:
        return
    token = monitor.request_refresh()
    await asyncio.to_thread(monitor.wait_for_refresh, token, _SNAPSHOT_SYNC_TIMEOUT)


@router.post("/voice/session")
async def open_voice_session(
    request: Request,
    account: VoiceAccountDep,
    db: AsyncSession = Depends(get_db),
):
    """按需开通本账号的通话 bot（以自己的昵称进入服务器）并等它连上。"""
    await _limit_guest_voice(request, account, "session")
    try:
        session = await request.app.state.voice_bots.acquire(db, account)
    except VoiceBotError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if account.role == "guest":
        # If the browser never claims a downlink, do not leave an anonymous TS
        # client connected indefinitely. A claimed stream cancels this lease.
        request.app.state.voice_bots.schedule_release(
            account.id, session["botId"], destroy=True
        )
    # 刚进服务器的通话身份要立刻能在频道列表里看到，前端才不用等轮询。
    await _sync_ts3_snapshot(request)
    return {"ok": True, **session}


@router.post("/voice/session/stop")
async def close_voice_session(
    request: Request,
    account: VoiceAccountDep,
    db: AsyncSession = Depends(get_db),
):
    """挂断：让通话 bot 立刻离开服务器。"""
    bid = await request.app.state.voice_bots.current_bot_id(db, account.id)
    if bid:
        await request.app.state.voice_bots.release_now(
            account.id, bid, destroy=account.role == "guest"
        )
        await _sync_ts3_snapshot(request)
    return {"ok": True, "stopped": bool(bid)}


@router.post("/voice/start")
async def start_voice_downlink(
    request: Request,
    account: VoiceAccountDep,
    db: AsyncSession = Depends(get_db),
):
    """Issue a one-use capability for an authenticated browser listener."""
    await _limit_guest_voice(request, account, "downlink")
    bid = await _voice_bot_id(request, account, db)
    connection_ttl_seconds = None
    if account.role == "guest":
        session_expiry = await AuthService(db).get_active_session_expiry(account.id)
        if session_expiry is None:
            raise HTTPException(status_code=401, detail="游客会话已过期")
        connection_ttl_seconds = (session_expiry - datetime.now()).total_seconds()
    ticket = await request.app.state.voice_downlink.create(
        account.id,
        bid,
        ephemeral=account.role == "guest",
        connection_ttl_seconds=connection_ttl_seconds,
    )
    return {
        "ok": True,
        "sessionId": ticket.id,
        "streamPath": f"/api/music/voice/{ticket.id}/stream",
        "expiresIn": 30,
    }


class VoiceChannelRequest(BaseModel):
    cid: int = Field(ge=1)
    password: str = Field(default="", max_length=128)


def _entry_sound_response(row: EntrySound | None) -> dict:
    if row is None:
        return {"enabled": False}
    return {
        "enabled": True,
        "filename": row.original_filename,
        "mimeType": row.mime_type,
        "sizeBytes": row.size_bytes,
        "durationMs": row.duration_ms,
        "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/voice/entry-sound")
async def get_entry_sound(
    _account: AccountDep,
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(EntrySound, _account.id)
    return _entry_sound_response(row)


@router.put("/voice/entry-sound")
async def put_entry_sound(
    request: Request,
    account: AccountDep,
    filename: str = Query(min_length=1, max_length=255),
    db: AsyncSession = Depends(get_db),
):
    """Replace the member's entry sound from a raw browser request body."""
    allowed = await request.app.state.entry_sound_upload_limiter.allow(
        f"account:{account.id}"
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="入场音效上传过于频繁，请稍后再试")
    content = await read_limited_upload(request)
    try:
        inspected = await asyncio.to_thread(inspect_audio, content, filename)
    except EntrySoundValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    storage = request.app.state.entry_sound_storage
    new_storage_filename = await asyncio.to_thread(
        storage.write_atomic, content, inspected.extension
    )
    old_row = await db.get(EntrySound, account.id)
    old_storage_filename = old_row.storage_filename if old_row else None
    if old_row is None:
        row = EntrySound(
            account_id=account.id,
            storage_filename=new_storage_filename,
            original_filename=inspected.original_filename,
            mime_type=inspected.mime_type,
            size_bytes=len(content),
            duration_ms=inspected.duration_ms,
        )
        db.add(row)
    else:
        old_row.storage_filename = new_storage_filename
        old_row.original_filename = inspected.original_filename
        old_row.mime_type = inspected.mime_type
        old_row.size_bytes = len(content)
        old_row.duration_ms = inspected.duration_ms
        row = old_row
    try:
        await db.commit()
        await db.refresh(row)
    except Exception:
        await db.rollback()
        await asyncio.to_thread(storage.delete, new_storage_filename)
        raise
    if old_storage_filename:
        try:
            await asyncio.to_thread(storage.delete, old_storage_filename)
        except OSError:
            logger.warning("清理旧入场音效失败", exc_info=True)
    return _entry_sound_response(row)


@router.delete("/voice/entry-sound")
async def delete_entry_sound(
    request: Request,
    account: AccountDep,
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(EntrySound, account.id)
    if row is None:
        return {"enabled": False}
    storage_filename = row.storage_filename
    await db.delete(row)
    await db.commit()
    try:
        await asyncio.to_thread(
            request.app.state.entry_sound_storage.delete, storage_filename
        )
    except OSError:
        logger.warning("删除入场音效文件失败", exc_info=True)
    return {"enabled": False}


@router.get("/voice/entry-sound/stream/{token}")
async def stream_entry_sound(request: Request, token: str):
    """Bearer-capability stream for TSMusicBot; intentionally has no account auth."""
    capability = request.app.state.entry_sound_capabilities.resolve(token)
    if capability is None:
        raise HTTPException(status_code=404, detail="音效链接无效或已过期")
    try:
        path = request.app.state.entry_sound_storage.path_for(
            capability.storage_filename
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="音效不存在") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="音效不存在")
    return FileResponse(
        path,
        media_type=capability.mime_type,
        headers={"Cache-Control": "private, no-store"},
    )


def _entry_sound_public_base(request: Request) -> str:
    configured = settings.live_audio_public_url.strip().rstrip("/")
    if configured:
        parsed = urlsplit(configured)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise RuntimeError("LIVE_AUDIO_PUBLIC_URL is not a safe absolute http(s) URL")
        return configured
    inferred = urlsplit(str(request.url))
    hostname = inferred.hostname
    loopback_hosts = {"localhost", "127.0.0.1", "::1"}
    client_host = request.client.host if request.client is not None else ""
    came_through_proxy = any(
        request.headers.get(name)
        for name in (
            "forwarded",
            "x-forwarded-for",
            "x-forwarded-host",
            "x-forwarded-proto",
            "x-real-ip",
        )
    )
    if (
        hostname in loopback_hosts
        and client_host in loopback_hosts
        and not came_through_proxy
    ):
        if inferred.scheme not in {"http", "https"}:
            raise RuntimeError("local entry-sound URL must use http(s)")
        return f"{inferred.scheme}://{inferred.netloc}".rstrip("/")
    raise RuntimeError(
        "LIVE_AUDIO_PUBLIC_URL must be configured for non-loopback entry-sound playback"
    )


async def _deliver_entry_sound(
    tsmusic: TSMusicClient,
    url: str,
    *,
    account_id: int,
    bot_id: str,
) -> None:
    try:
        await asyncio.wait_for(
            tsmusic.play_sound_effect(url, bot_id=bot_id),
            timeout=ENTRY_SOUND_EFFECT_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.warning(
            "播放入场音效失败，不影响频道切换 (account_id=%s, bot_id=%s)",
            account_id,
            bot_id,
            exc_info=True,
        )


async def _trigger_entry_sound(
    request: Request,
    tsmusic: TSMusicClient,
    account: Account,
    bot_id: str,
    db: AsyncSession,
) -> None:
    """Best effort only: a playback problem must never undo a successful TS move."""
    if account.role == "guest":
        return
    try:
        row = await db.get(EntrySound, account.id)
        if row is None:
            return
        public_base = _entry_sound_public_base(request)
        token = request.app.state.entry_sound_capabilities.create(
            row.storage_filename, row.mime_type
        )
        url = (
            f"{public_base}"
            f"/api/music/voice/entry-sound/stream/{token}"
        )
        task = asyncio.create_task(
            _deliver_entry_sound(
                tsmusic,
                url,
                account_id=account.id,
                bot_id=bot_id,
            )
        )
        tasks = getattr(request.app.state, "entry_sound_tasks", None)
        if tasks is None:
            tasks = set()
            request.app.state.entry_sound_tasks = tasks
        tasks.add(task)
        task.add_done_callback(tasks.discard)
    except Exception:
        logger.warning(
            "准备入场音效失败，不影响频道切换 (account_id=%s, bot_id=%s)",
            account.id,
            bot_id,
            exc_info=True,
        )


@router.get("/voice/channels")
async def voice_channels(
    request: Request,
    tsmusic: TsmusicDep,
    account: VoiceAccountDep,
    fresh: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    """频道树 + 各频道在场成员 + 自己的通话 bot 当前所在频道。

    还没加入通话时不该报错——频道列表本身是可以先看的，只是没有「当前频道」。
    fresh=1 表示用户主动点了刷新：先催一轮轮询再读，别让他看着旧快照再点一次。
    """
    if fresh:
        await _sync_ts3_snapshot(request)
    bid = await request.app.state.voice_bots.current_bot_id(db, account.id)
    bot_clid = await tsmusic.get_bot_client_id(bid) if bid else None
    overview = request.app.state.ts3_monitor.get_voice_overview(bot_clid)
    overview["botOnline"] = bot_clid is not None
    return overview


@router.post("/voice/channel")
async def move_voice_channel(
    body: VoiceChannelRequest,
    request: Request,
    tsmusic: TsmusicDep,
    account: VoiceAccountDep,
    db: AsyncSession = Depends(get_db),
):
    """把自己的通话 bot 移到目标频道；频道有密码时由 body.password 提供。"""
    await _limit_guest_voice(request, account, "channel")
    bid = await _voice_bot_id(request, account, db)
    if await tsmusic.get_bot_client_id(bid) is None:
        raise HTTPException(status_code=409, detail="通话机器人不在线，请重新加入通话")
    result = await tsmusic.join_channel(body.cid, body.password, bot_id=bid)
    if not result["ok"]:
        # 密码错误是用户能自己纠正的输入问题，其余归为上游/权限问题。
        status = 403 if result.get("invalid_password") else 502
        raise HTTPException(status_code=status, detail=result["detail"])
    await _trigger_entry_sound(request, tsmusic, account, bid, db)
    # 人已经过去了，快照得跟上：否则前端紧接着的刷新会把你「弹回」原频道。
    await _sync_ts3_snapshot(request)
    return {"ok": True, "cid": body.cid}


# 4000-4999 是 WebSocket 应用自定义关闭码，code 与 reason 都会原样送达浏览器。
VOICE_CLOSE_TICKET_INVALID = 4404
VOICE_CLOSE_GUEST_EXPIRED = 4401
VOICE_CLOSE_UPSTREAM_UNSUPPORTED = 4502
VOICE_CLOSE_UPSTREAM_UNREACHABLE = 4503
VOICE_CLOSE_UPSTREAM_ERROR = 1011
VOICE_CLOSE_NATIVE_TS_PREEMPTED = NATIVE_TS_PREEMPTED_CLOSE_CODE


def voice_close_for(error: BaseException) -> tuple[int, str]:
    """把上游异常翻译成浏览器可直接展示的关闭码 + 原因。

    分三档是因为前端的应对方式不同：
    - 4502 升级被拒 = TSMusicBot 没有 /api/voice/downlink，重连多少次都一样，直接收手；
    - 4503 连不上（登录就失败/连接被拒）= 通常是没起来或在重启，值得有限次重连；
    - 1011 其它 = 流中途出错，退避重连。
    """
    if isinstance(error, InvalidHandshake):
        return VOICE_CLOSE_UPSTREAM_UNSUPPORTED, "音乐机器人未提供频道语音下行（版本过旧）"
    if isinstance(error, (TSMusicUnavailable, httpx.HTTPError, OSError)):
        return VOICE_CLOSE_UPSTREAM_UNREACHABLE, "连不上音乐机器人（未运行或地址不通）"
    return VOICE_CLOSE_UPSTREAM_ERROR, "上游语音连接中断"


async def _pump_voice_downlink(websocket: WebSocket, bot_id: str) -> None:
    async for packet in websocket.app.state.tsmusic.voice_packets(bot_id):
        if len(packet) <= 64 * 1024:
            await websocket.send_bytes(packet)


async def _await_client_gone(websocket: WebSocket) -> None:
    """纯粹为了观察浏览器断开。

    下行是单向的，一个字节都不用收；但只要不 receive()，Starlette 就永远看不到
    websocket.disconnect，上游那条 TSMusicBot WS 会随着每个关掉的标签页越积越多。
    """
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return


@router.websocket("/voice/{ticket_id}/stream")
async def stream_voice_downlink(websocket: WebSocket, ticket_id: str):
    """Proxy authenticated TSMusicBot Opus packets to one browser socket."""
    ticket = await websocket.app.state.voice_downlink.claim(ticket_id)
    if ticket is None:
        await websocket.close(code=VOICE_CLOSE_TICKET_INVALID, reason="语音订阅不存在或已过期")
        return
    try:
        try:
            await websocket.app.state.voice_bots.keep_alive(ticket.account_id)
        except VoiceBotError:
            await websocket.close(
                code=VOICE_CLOSE_NATIVE_TS_PREEMPTED,
                reason="TeamSpeak 客户端已上线，网页通话已断开",
            )
            return
        await websocket.accept()

        async def close_for_preemption(code: int, reason: str) -> None:
            try:
                await websocket.close(code=code, reason=reason)
            except RuntimeError:
                pass

        await websocket.app.state.voice_downlink.register_active(
            ticket, close_for_preemption
        )
        try:
            # Close the claim/register race: if native TS won between the first
            # lease check and socket registration, return the permanent code now.
            await websocket.app.state.voice_bots.keep_alive(ticket.account_id)
        except VoiceBotError:
            await close_for_preemption(
                VOICE_CLOSE_NATIVE_TS_PREEMPTED,
                "TeamSpeak 客户端已上线，网页通话已断开",
            )
            return

        pump = asyncio.create_task(_pump_voice_downlink(websocket, ticket.bot_id))
        watchdog = asyncio.create_task(_await_client_gone(websocket))
        tasks = {pump, watchdog}
        expiry = None
        if ticket.connection_expires_at is not None:
            expiry = asyncio.create_task(
                asyncio.sleep(max(0.0, ticket.connection_expires_at - asyncio.get_running_loop().time()))
            )
            tasks = {*tasks, expiry}
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        # 取消 pump 会把 CancelledError 抛回 voice_packets 的 async with，上游 WS 随之关闭。
        await asyncio.gather(*pending, return_exceptions=True)

        if expiry is not None and expiry in done:
            try:
                await websocket.close(
                    code=VOICE_CLOSE_GUEST_EXPIRED, reason="游客通话身份已过期"
                )
            except RuntimeError:
                pass
            return
        if watchdog in done:
            return
        error = pump.exception()
        if error is None or isinstance(error, WebSocketDisconnect):
            return
        code, reason = voice_close_for(error)
        logger.warning("Bot %s 语音下行中断：%s", ticket.bot_id, reason, exc_info=error)
        try:
            await websocket.close(code=code, reason=reason)
        except RuntimeError:
            pass
    finally:
        await websocket.app.state.voice_downlink.release(ticket)
        # 浏览器没了就把通话 bot 收回去（带宽限期：刷新页面会立刻重新接上）。
        websocket.app.state.voice_bots.schedule_release(
            ticket.account_id, ticket.bot_id, destroy=ticket.ephemeral
        )


@router.post("/pause")
async def pause(tsmusic: TsmusicDep, _account: AccountDep, bot_id: OwnedBotId = None):
    return await tsmusic.pause(bot_id=bot_id)


@router.post("/resume")
async def resume(request: Request, tsmusic: TsmusicDep, account: AccountDep, bot_id: OwnedBotId = None):
    result = await tsmusic.resume(bot_id=bot_id)
    await _ensure_follow(request, tsmusic, account, bot_id)
    return result


@router.post("/next")
async def next_track(request: Request, tsmusic: TsmusicDep, account: AccountDep, bot_id: OwnedBotId = None):
    result = await tsmusic.next(bot_id=bot_id)
    await _ensure_follow(request, tsmusic, account, bot_id)
    return result


@router.post("/stop")
async def stop(tsmusic: TsmusicDep, _account: AccountDep, bot_id: OwnedBotId = None):
    return await tsmusic.stop(bot_id=bot_id)


@router.post("/seek")
async def seek(body: SeekRequest, tsmusic: TsmusicDep, _account: AccountDep, bot_id: OwnedBotId = None):
    return await tsmusic.seek(body.position, bot_id=bot_id)


@router.post("/volume")
async def set_volume(body: VolumeRequest, tsmusic: TsmusicDep, _account: AccountDep, bot_id: OwnedBotId = None):
    return await tsmusic.set_volume(body.volume, bot_id=bot_id)


@router.post("/mode")
async def set_mode(body: ModeRequest, tsmusic: TsmusicDep, _account: AccountDep, bot_id: OwnedBotId = None):
    return await tsmusic.set_mode(body.mode, bot_id=bot_id)


@router.post("/clear")
async def clear(tsmusic: TsmusicDep, _account: AccountDep, bot_id: OwnedBotId = None):
    return await tsmusic.clear(bot_id=bot_id)


@router.get("/nowplaying")
async def now_playing(tsmusic: TsmusicDep, _account: AccountDep, bot_id: OwnedBotId = None):
    """当前播放状态（歌名/歌手/进度/封面/音量）。"""
    return await tsmusic.get_bot_status(bot_id=bot_id)


@router.get("/queue")
async def queue(tsmusic: TsmusicDep, _account: AccountDep, bot_id: OwnedBotId = None):
    """播放队列。"""
    items = await tsmusic.get_queue(bot_id=bot_id)
    return {"count": len(items), "items": items}


@router.delete("/queue/{index}")
async def remove_from_queue(
    index: Annotated[int, Path(ge=0)],
    tsmusic: TsmusicDep,
    _account: AccountDep,
    bot_id: OwnedBotId = None,
):
    """移除队列中指定位置的单曲（前端传 0-based 索引，内部转上游 1-based !remove）。"""
    return await tsmusic.remove_from_queue(index, bot_id=bot_id)


@router.post("/queue/{index}/play")
async def play_at(
    index: Annotated[int, Path(ge=0)],
    request: Request,
    tsmusic: TsmusicDep,
    account: AccountDep,
    bot_id: OwnedBotId = None,
):
    """跳转到队列中指定位置播放（点击队列项切歌；index 越界或不可播时 400）。"""
    result = await tsmusic.play_at(index, bot_id=bot_id)
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(status_code=400, detail=str(result["error"]))
    await _ensure_follow(request, tsmusic, account, bot_id)
    return result


@router.post("/queue/{index}/move")
async def move_queue_item(
    index: Annotated[int, Path(ge=0)],
    body: MoveRequest,
    tsmusic: TsmusicDep,
    _account: AccountDep,
    bot_id: OwnedBotId = None,
):
    """拖动调序：移动队列项到新位置（index=from，body.to=目标）。"""
    result = await tsmusic.move_queue_item(index, body.to, bot_id=bot_id)
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(status_code=400, detail=str(result["error"]))
    return result


# ───────────────────────── 音质设置 ─────────────────────────


@router.get("/quality")
async def get_quality(tsmusic: TsmusicDep, _account: AccountDep, bot_id: OwnedBotId = None):
    """获取当前 bot 的音质配置（各平台独立）。"""
    return await tsmusic.get_quality(bot_id=bot_id)


@router.post("/quality")
async def set_quality(
    body: Annotated[dict, Body(description="音质设置 {quality, platform?}")],
    tsmusic: TsmusicDep,
    _account: AccountDep,
    bot_id: OwnedBotId = None,
):
    """设置音质（quality 必填，platform 可选）。"""
    quality = body.get("quality")
    if not quality:
        raise HTTPException(status_code=400, detail="quality is required")
    platform = body.get("platform")
    result = await tsmusic.set_quality(quality, platform, bot_id=bot_id)
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(
            status_code=int(result.get("_status") or 400),
            detail=str(result["error"]),
        )
    return result


# ───────────────────────── 我的音乐 / 歌单 ─────────────────────────


@router.get("/my/playlists")
async def my_playlists(platform: str, tsmusic: TsmusicDep, _account: AccountDep, bot_id: LibraryBotId):
    """当前用户的歌单；共享 Bot 不会暴露其主人的私人曲库。"""
    return await tsmusic.user_playlists(platform, bot_id=bot_id)


_PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@router.get("/my/playlist/{playlist_id}/songs")
async def my_playlist_songs(
    playlist_id: str,
    platform: str,
    tsmusic: TsmusicDep,
    _account: AccountDep,
    bot_id: LibraryBotId,
):
    """歌单内歌曲（per-bot；playlist_id 限定字母/数字/下划线/短横，防路径注入）。"""
    if not _PLAYLIST_ID_RE.fullmatch(playlist_id):
        raise HTTPException(status_code=400, detail="invalid playlist_id")
    return await tsmusic.playlist_songs(playlist_id, platform, bot_id=bot_id)


@router.get("/my/recommend/songs")
async def my_recommend_songs(platform: str, tsmusic: TsmusicDep, _account: AccountDep, bot_id: LibraryBotId):
    """每日推荐（per-bot）。"""
    return await tsmusic.recommend_songs(platform, bot_id=bot_id)


@router.get("/my/personal-fm")
async def my_personal_fm(platform: str, tsmusic: TsmusicDep, _account: AccountDep, bot_id: LibraryBotId):
    """私人 FM（per-bot）。"""
    return await tsmusic.personal_fm(platform, bot_id=bot_id)


@router.get("/my/bilibili-popular")
async def my_bilibili_popular(
    tsmusic: TsmusicDep,
    _account: AccountDep,
    limit: int = 20,
    bot_id: OwnedBotId = None,
):
    """B 站热门视频（无需登录，per-bot）。"""
    return await tsmusic.bilibili_popular(limit, bot_id=bot_id)


class EnqueueRequest(BaseModel):
    platform: str | None = Field(default=None, description="音源平台 netease/qq/bilibili")
    songs: list[dict] = Field(description="歌曲列表 [{id,...}]，最多取前 50 首")


@router.post("/my/enqueue")
async def my_enqueue(body: EnqueueRequest, request: Request, tsmusic: TsmusicDep, account: AccountDep, bot_id: OwnedBotId = None):
    """批量入队（整单播放）：后端循环 add，并发上限 4，上限 50 首，单首失败容忍。整批只跟随一次。"""
    result = await tsmusic.enqueue_songs(body.songs, platform=body.platform, bot_id=bot_id)
    await _ensure_follow(request, tsmusic, account, bot_id)
    return result


# ───────────────────────── 播放跟随开关 ─────────────────────────


class FollowSettingRequest(BaseModel):
    enabled: bool


@router.get("/follow-setting")
async def get_follow_setting(tsmusic: TsmusicDep, _account: AccountDep, db: AsyncSession = Depends(get_db)):
    """播放跟随开关（默认开启）。"""
    return {"enabled": await tsmusic.load_follow_setting(db)}


@router.put("/follow-setting")
async def put_follow_setting(body: FollowSettingRequest, tsmusic: TsmusicDep, _account: AccountDep, db: AsyncSession = Depends(get_db)):
    """更新播放跟随开关（持久化 + 刷新单例缓存）。"""
    await tsmusic.set_follow_setting(db, body.enabled)
    return {"enabled": body.enabled}


# ───────────────────────── bot 实例管理 ─────────────────────────


_BOT_ID_RE = re.compile(r"^[0-9a-fA-F-]{1,64}$")


def _check_bot_id(bot_id: str) -> None:
    """校验 bot_id 格式（UUID hex+连字符），防路径注入。Path(pattern) 对 path 参数不生效，显式补。"""
    if not _BOT_ID_RE.fullmatch(bot_id):
        raise HTTPException(status_code=400, detail="invalid bot_id")


class BotCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    nickname: str = Field(min_length=1, max_length=64)
    serverAddress: str = Field(min_length=1, description="TS 服务器地址（TSMusicBot 在 docker 时用 host.docker.internal）")
    serverPort: int = Field(default=9987, ge=1, le=65535)
    defaultChannel: str = ""
    channelPassword: str = ""
    serverPassword: str = ""


async def _owned_bot_ids(db: AsyncSession, account_id: int) -> set[str]:
    """当前 account **拥有**的 bot_id 集合（严格 owner，管理操作用）。"""
    rows = await db.execute(
        select(BotOwnership.bot_id).where(BotOwnership.account_id == account_id)
    )
    return {r[0] for r in rows.all()}


async def _accessible_bot_ids(db: AsyncSession, account_id: int) -> set[str]:
    """当前 account 可访问的 bot_id 集合 = 拥有的 ∪ 别人共享给我的（播放/点播/启停用）。"""
    owned = await _owned_bot_ids(db, account_id)
    shared_rows = await db.execute(
        select(BotShare.bot_id).where(BotShare.shared_to_account_id == account_id)
    )
    return owned | {r[0] for r in shared_rows.all()}


async def _check_bot_owner(db: AsyncSession, account_id: int, bot_id: str) -> None:
    """严格校验当前 account **拥有**该 bot，否则 403（delete/配置等管理操作用）。"""
    owned = await _owned_bot_ids(db, account_id)
    if bot_id not in owned:
        raise HTTPException(status_code=403, detail="无权操作该 Bot（不属于你）")


async def _check_bot_accessible(db: AsyncSession, account_id: int, bot_id: str) -> None:
    """校验当前 account 可访问该 bot（拥有或被共享），否则 403（start/stop 用）。"""
    accessible = await _accessible_bot_ids(db, account_id)
    if bot_id not in accessible:
        raise HTTPException(status_code=403, detail="无权操作该 Bot（不属于你，也未共享给你）")


@router.get("/bots")
async def list_bots(tsmusic: TsmusicDep, account: AccountDep, db: AsyncSession = Depends(get_db)):
    """bot 实例列表（自己拥有的 + 好友共享给我的；含连接 / 播放状态）。"""
    all_bots = await tsmusic.list_bots()
    owned = await _owned_bot_ids(db, account.id)
    # 共享给我的：bot_id -> (owner_account_id, 是否附带歌单权限)
    shared_rows = (
        await db.execute(
            select(BotShare.bot_id, BotShare.owner_account_id, BotShare.share_playlists).where(
                BotShare.shared_to_account_id == account.id
            )
        )
    ).all()
    shared_map = {r[0]: (r[1], bool(r[2])) for r in shared_rows}
    # 共享 bot 的 owner 昵称
    owner_ids = {value[0] for value in shared_map.values() if value[0] is not None}
    owner_nicks: dict[int, str] = {}
    if owner_ids:
        nick_rows = (
            await db.execute(
                select(Account.id, Account.ts_nickname).where(Account.id.in_(owner_ids))
            )
        ).all()
        owner_nicks = {r[0]: r[1] for r in nick_rows}

    out = []
    for b in all_bots:
        bid = b.get("id")
        if bid in owned:
            out.append(b)
        elif bid in shared_map:
            owner_id, share_playlists = shared_map[bid]
            out.append({
                **b,
                "shared": True,
                "ownerNickname": owner_nicks.get(owner_id, "好友"),
                "sharePlaylists": share_playlists,
            })
    return {"bots": out}


@router.post("/bots")
async def create_bot(body: BotCreate, tsmusic: TsmusicDep, account: AccountDep, db: AsyncSession = Depends(get_db)):
    """创建 bot 并记录 owner（identity 自动生成，不自动连接）。"""
    try:
        result = await tsmusic.create_bot(body.model_dump())
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="TSMusicBot 不可达，请确认其 Docker 容器在运行")
    bot_id = str(result.get("id") or "")
    if bot_id:
        db.add(BotOwnership(account_id=account.id, bot_id=bot_id))
        await db.commit()
    return result


class BotUpdateRequest(BaseModel):
    name: str | None = None
    serverAddress: str | None = None
    serverPort: int | None = None
    nickname: str | None = None
    defaultChannel: str | None = None
    channelPassword: str | None = None
    serverPassword: str | None = None


@router.put("/bots/{bot_id}")
async def update_bot(
    bot_id: str,
    body: BotUpdateRequest,
    tsmusic: TsmusicDep,
    account: AccountDep,
    db: AsyncSession = Depends(get_db),
):
    """更新 bot 配置（仅 owner；连接类字段需先停止 bot 再改才生效）。"""
    _check_bot_id(bot_id)
    await _check_bot_owner(db, account.id, bot_id)
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    if not payload:
        raise HTTPException(status_code=400, detail="没有要更新的字段")
    result = await tsmusic.update_bot(bot_id, payload)
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(status_code=400, detail=str(result["error"]))
    return {"success": True}


@router.get("/bots/{bot_id}/config")
async def get_bot_config_endpoint(
    bot_id: str,
    tsmusic: TsmusicDep,
    account: AccountDep,
    db: AsyncSession = Depends(get_db),
):
    """获取 bot 配置（仅 owner；编辑表单预填用，上游已排除 identity/apiKey）。"""
    _check_bot_id(bot_id)
    await _check_bot_owner(db, account.id, bot_id)
    return await tsmusic.get_bot_config(bot_id)


@router.post("/bots/{bot_id}/share")
async def share_bot(
    bot_id: str,
    body: ShareRequest,
    _tsmusic: TsmusicDep,
    account: AccountDep,
    db: AsyncSession = Depends(get_db),
):
    """把 bot 共享给好友（仅 owner；需双方为好友；即时生效、持久）。"""
    try:
        _check_bot_id(bot_id)
        await _check_bot_owner(db, account.id, bot_id)
        friend = (
            await db.execute(
                select(Account).where(Account.ts_nickname == body.friendTsNickname)
            )
        ).scalars().first()
        if not friend:
            raise HTTPException(status_code=400, detail="用户不存在")
        friend_id = friend.id
        if friend_id == account.id:
            raise HTTPException(status_code=400, detail="不能共享给自己")
        is_friend = (
            await db.execute(
                select(Friend.id).where(
                    Friend.account_id == account.id,
                    Friend.friend_account_id == friend_id,
                )
            )
        ).first()
        if not is_friend:
            raise HTTPException(status_code=400, detail="对方不是你的好友")
        existing = (
            await db.execute(
                select(BotShare).where(
                    BotShare.owner_account_id == account.id,
                    BotShare.bot_id == bot_id,
                    BotShare.shared_to_account_id == friend_id,
                )
            )
        ).scalars().first()
        if existing:
            existing.share_playlists = body.includePlaylists
        else:
            db.add(BotShare(
                owner_account_id=account.id,
                bot_id=bot_id,
                shared_to_account_id=friend_id,
                share_playlists=body.includePlaylists,
            ))
        await db.commit()
        return {"success": True, "includePlaylists": body.includePlaylists}
    except HTTPException:
        raise
    except Exception:
        logger.exception("share_bot 500 异常")
        raise HTTPException(status_code=500, detail="共享失败，请查看后端日志")


@router.delete("/bots/{bot_id}/share/{friend_account_id}")
async def unshare_bot(
    bot_id: str,
    friend_account_id: int,
    _tsmusic: TsmusicDep,
    account: AccountDep,
    db: AsyncSession = Depends(get_db),
):
    """撤销共享（仅 owner）。"""
    _check_bot_id(bot_id)
    await _check_bot_owner(db, account.id, bot_id)
    rows = (
        await db.execute(
            select(BotShare).where(
                BotShare.owner_account_id == account.id,
                BotShare.bot_id == bot_id,
                BotShare.shared_to_account_id == friend_account_id,
            )
        )
    ).scalars().all()
    for r in rows:
        await db.delete(r)
    await db.commit()
    return {"success": True}


@router.get("/bots/my-shares")
async def my_shares(_tsmusic: TsmusicDep, account: AccountDep, db: AsyncSession = Depends(get_db)):
    """我共享出去的 bot（按 bot 聚合，含共享给谁）。"""
    rows = (
        await db.execute(
            select(
                BotShare.bot_id,
                BotShare.shared_to_account_id,
                Account.ts_nickname,
                BotShare.share_playlists,
            )
            .join(Account, Account.id == BotShare.shared_to_account_id)
            .where(BotShare.owner_account_id == account.id)
        )
    ).all()
    shares: dict[str, list[dict]] = {}
    for bid, fid, nick, share_playlists in rows:
        shares.setdefault(bid, []).append({
            "accountId": fid,
            "nickname": nick,
            "includePlaylists": bool(share_playlists),
        })
    return {"shares": [{"botId": bid, "sharedTo": lst} for bid, lst in shares.items()]}


@router.post("/bots/{bot_id}/start")
async def start_bot(bot_id: str, tsmusic: TsmusicDep, account: AccountDep, db: AsyncSession = Depends(get_db)):
    """启动 bot 连接 TS。"""
    _check_bot_id(bot_id)
    await _check_bot_accessible(db, account.id, bot_id)
    try:
        return await tsmusic.start_bot(bot_id)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="TSMusicBot 不可达，请确认其 Docker 容器在运行")


@router.post("/bots/{bot_id}/stop")
async def stop_bot(bot_id: str, tsmusic: TsmusicDep, account: AccountDep, db: AsyncSession = Depends(get_db)):
    """停止 bot（断开 TS）。"""
    _check_bot_id(bot_id)
    await _check_bot_accessible(db, account.id, bot_id)
    try:
        return await tsmusic.stop_bot(bot_id)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="TSMusicBot 不可达，请确认其 Docker 容器在运行")


@router.delete("/bots/{bot_id}")
async def delete_bot(bot_id: str, tsmusic: TsmusicDep, account: AccountDep, db: AsyncSession = Depends(get_db)):
    """删除 bot 实例（同步删 owner 记录）。"""
    _check_bot_id(bot_id)
    await _check_bot_owner(db, account.id, bot_id)
    try:
        result = await tsmusic.delete_bot(bot_id)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="TSMusicBot 不可达，请确认其 Docker 容器在运行")
    # 删除该 bot 的 owner 记录
    objs = (
        await db.execute(select(BotOwnership).where(BotOwnership.bot_id == bot_id))
    ).scalars().all()
    for o in objs:
        await db.delete(o)
    await db.commit()
    return result


# ───────────────────────── bot 行为 / 外观设置 ─────────────────────────


@router.get("/bot-settings")
async def get_bot_settings(tsmusic: TsmusicDep, _account: AccountDep):
    """全局 bot 行为设置（空闲下线分钟 + 空频道自动暂停）。"""
    return await tsmusic.get_bot_settings()


@router.get("/bot-idle-status")
async def get_bot_idle_status(request: Request, _account: AdminDep):
    """空闲下线管理器诊断状态（管理员）。"""
    return request.app.state.bot_idle_manager.snapshot()


@router.put("/bot-settings")
async def put_bot_settings(body: BotSettingsRequest, tsmusic: TsmusicDep, _account: AccountDep):
    """更新全局 bot 行为设置（仅透传非 None 字段）。"""
    try:
        return await tsmusic.set_bot_settings(
            body.idleTimeoutMinutes,
            body.autoPauseOnEmpty,
            body.voiceDucking.model_dump(exclude_none=True) if body.voiceDucking else None,
        )
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="TSMusicBot 不可达，请确认其 Docker 容器在运行")


@router.get("/bots/{bot_id}/profile")
async def get_bot_profile(bot_id: str, tsmusic: TsmusicDep, _account: AccountDep):
    """per-bot profile 开关（头像/昵称/描述等 6 字段）。"""
    _check_bot_id(bot_id)
    try:
        return await tsmusic.get_bot_profile(bot_id)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="TSMusicBot 不可达，请确认其 Docker 容器在运行")


@router.put("/bots/{bot_id}/profile")
async def put_bot_profile(bot_id: str, body: BotProfileRequest, tsmusic: TsmusicDep, _account: AccountDep, db: AsyncSession = Depends(get_db)):
    """更新 per-bot profile 开关（仅 owner；仅透传非 None 字段；上游立即生效）。"""
    _check_bot_id(bot_id)
    await _check_bot_owner(db, _account.id, bot_id)
    try:
        return await tsmusic.set_bot_profile(body.model_dump(exclude_none=True), bot_id)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="TSMusicBot 不可达，请确认其 Docker 容器在运行")


@router.get("/bots/{bot_id}/avatar")
async def get_bot_avatar(bot_id: str, tsmusic: TsmusicDep, _account: AccountDep):
    """获取 bot 固定头像（二进制透传）。无自定义头像时上游返回 404。"""
    _check_bot_id(bot_id)
    try:
        resp = await tsmusic.get_bot_avatar(bot_id)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="TSMusicBot 不可达，请确认其 Docker 容器在运行")
    if resp.status_code >= 400:
        raise HTTPException(status_code=404, detail="该 Bot 未设置固定头像")
    # 白名单 content-type，防上游返回非图片头被原样透传（类型伪造）
    ct = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    if not ct.startswith("image/"):
        ct = "image/png"
    return Response(content=resp.content, media_type=ct)


@router.put("/bots/{bot_id}/avatar")
async def put_bot_avatar(bot_id: str, body: BotAvatarRequest, tsmusic: TsmusicDep, _account: AccountDep, db: AsyncSession = Depends(get_db)):
    """上传/替换 bot 固定头像（仅 owner；png/jpeg/webp，≤200KB）。"""
    _check_bot_id(bot_id)
    await _check_bot_owner(db, _account.id, bot_id)
    # 前置校验：仅放行 image/* data URL，避免任意大 payload 转发到上游
    if not body.dataUrl.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="仅支持 image/* data URL")
    try:
        result = await tsmusic.set_bot_avatar(body.dataUrl, bot_id)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="TSMusicBot 不可达，请确认其 Docker 容器在运行")
    status = result.pop("_status", 200)
    if status >= 400:
        raise HTTPException(status_code=status, detail=result.get("error", "头像上传失败"))
    return result


@router.delete("/bots/{bot_id}/avatar")
async def delete_bot_avatar(bot_id: str, tsmusic: TsmusicDep, _account: AccountDep, db: AsyncSession = Depends(get_db)):
    """移除 bot 固定头像（仅 owner）。"""
    _check_bot_id(bot_id)
    await _check_bot_owner(db, _account.id, bot_id)
    try:
        await tsmusic.delete_bot_avatar(bot_id)
        return {"success": True}
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="TSMusicBot 不可达，请确认其 Docker 容器在运行")


# ───────────────────────── 平台账号登录 ─────────────────────────


@router.get("/auth/status")
async def auth_status(platform: str, tsmusic: TsmusicDep, _account: AccountDep, bot_id: LibraryBotId):
    """获取当前用户自己平台账号的登录状态，不披露共享 Bot 主人的账号信息。"""
    return await tsmusic.get_auth_status(platform, bot_id=bot_id)


@router.get("/auth/qrcode/status")
async def auth_qrcode_status(key: str, platform: str, tsmusic: TsmusicDep, _account: AccountDep, bot_id: StrictOwnedBotId = None):
    """轮询二维码扫码状态（per-bot；fork 在 confirmed 时自动持久化 cookie）。"""
    return await tsmusic.get_qrcode_status(key, platform, bot_id=bot_id)


@router.post("/auth/qrcode")
async def auth_qrcode(body: dict, tsmusic: TsmusicDep, _account: AccountDep, bot_id: StrictOwnedBotId = None):
    """获取某平台登录二维码（per-bot）。"""
    platform = body.get("platform", "netease")
    return await tsmusic.get_qrcode(platform, bot_id=bot_id)


class CookieRequest(BaseModel):
    platform: str
    cookie: str


@router.post("/auth/cookie")
async def auth_cookie(body: CookieRequest, tsmusic: TsmusicDep, _account: AccountDep, bot_id: StrictOwnedBotId = None):
    """手动设置某平台 cookie（per-bot：绑定到该 bot）。"""
    return await tsmusic.set_cookie(body.platform, body.cookie, bot_id=bot_id)


@router.delete("/auth/cookie")
async def auth_logout(platform: str, tsmusic: TsmusicDep, _account: AccountDep, bot_id: StrictOwnedBotId = None):
    """退出某平台登录（清除该 bot 的平台 cookie；Jellyfin 清除该 bot 的凭据）。"""
    return await tsmusic.delete_cookie(platform, bot_id=bot_id)


# ───────────────────────── 音源开关 / Jellyfin ─────────────────────────


@router.get("/providers")
async def music_providers(tsmusic: TsmusicDep, _account: AccountDep):
    """音源开关 + 默认音源（配置级；前端据此隐藏未启用的音源 tab）。"""
    return await tsmusic.get_providers()


class JellyfinForm(BaseModel):
    serverUrl: str = ""
    authMode: str = "userpass"
    username: str = ""
    password: str = ""
    apiKey: str = ""
    userId: str = ""


@router.post("/auth/jellyfin/test")
async def auth_jellyfin_test(
    body: JellyfinForm, tsmusic: TsmusicDep, _account: AccountDep, bot_id: StrictOwnedBotId = None
):
    """测试该 bot 的 Jellyfin 连接（空凭据字段回落该 bot 已存值，不落盘）。"""
    return await tsmusic.jellyfin_test(body.model_dump(), bot_id=bot_id)


@router.post("/auth/jellyfin/login")
async def auth_jellyfin_login(
    body: JellyfinForm, tsmusic: TsmusicDep, _account: AccountDep, bot_id: StrictOwnedBotId = None
):
    """保存该 bot 的 Jellyfin 凭据（热重配 + 验证连接）。"""
    return await tsmusic.jellyfin_login(body.model_dump(), bot_id=bot_id)
