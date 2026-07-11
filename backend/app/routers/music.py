"""音乐路由 — 代理 TSMusicBot API。

用户只与 PowerfulTS 交互（统一认证 X-Session-Token，由 get_current_account 校验），
后端代理到 TSMusicBot (:3000)，用户看不到 TSMusicBot WebUI。
"""
from __future__ import annotations

from typing import Annotated

import asyncio
import logging
import re

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.database import get_db
from ..deps import AccountDep, AdminDep, TsmusicDep, get_current_account
from ..models import Account, BotOwnership, BotShare, Friend
from ..services import bot_mover
from ..services.tsmusic_client import TSMusicClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/music", tags=["music"])
settings = get_settings()


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


class SeekRequest(BaseModel):
    position: int = Field(ge=0, description="跳转到的播放位置（秒）")


class MoveRequest(BaseModel):
    to: int = Field(ge=0, description="队列项移动到的目标位置（0-based）")


class ShareRequest(BaseModel):
    friendTsNickname: str = Field(min_length=1, max_length=64, description="被共享好友的 TS 昵称")


class VolumeRequest(BaseModel):
    volume: int = Field(ge=0, le=100)


class ModeRequest(BaseModel):
    mode: str = Field(description="seq | loop | random | rloop")


class BotSettingsRequest(BaseModel):
    """全局 bot 行为设置（两项均可选，未传项上游保持不变）。"""
    idleTimeoutMinutes: int | None = Field(default=None, ge=0, description="频道无人多少分钟后自动断开，0=禁用")
    autoPauseOnEmpty: bool | None = Field(default=None, description="频道无人时自动暂停")


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
        bot_nick = await tsmusic.get_bot_nickname(bot_id)
        if not bot_nick:
            logger.warning("跟随跳过: 未能解析 bot 昵称 (bot_id=%s)", bot_id)
            return {"moved": False, "reason": "bot_nickname_unknown"}
        result = await asyncio.to_thread(bot_mover.move_bot_to_user, settings, bot_nick, account)
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
    follow = await _ensure_follow(request, tsmusic, account, bot_id)
    if body.queue:
        result = await tsmusic.add(body.query, platform=body.platform, meta=body.meta, bot_id=bot_id)
    else:
        result = await tsmusic.play(body.query, platform=body.platform, meta=body.meta, bot_id=bot_id)
    if isinstance(result, dict):
        # 仅回传 moved/reason 给前端，剥离内部 cid/clid（最小信息原则）
        result["follow"] = {"moved": follow.get("moved", False), "reason": follow.get("reason")}
    return result


@router.post("/pause")
async def pause(tsmusic: TsmusicDep, _account: AccountDep, bot_id: OwnedBotId = None):
    return await tsmusic.pause(bot_id=bot_id)


@router.post("/resume")
async def resume(request: Request, tsmusic: TsmusicDep, account: AccountDep, bot_id: OwnedBotId = None):
    await _ensure_follow(request, tsmusic, account, bot_id)
    return await tsmusic.resume(bot_id=bot_id)


@router.post("/next")
async def next_track(request: Request, tsmusic: TsmusicDep, account: AccountDep, bot_id: OwnedBotId = None):
    await _ensure_follow(request, tsmusic, account, bot_id)
    return await tsmusic.next(bot_id=bot_id)


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
    await _ensure_follow(request, tsmusic, account, bot_id)
    result = await tsmusic.play_at(index, bot_id=bot_id)
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(status_code=400, detail=str(result["error"]))
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
async def get_quality(tsmusic: TsmusicDep, _account: AccountDep):
    """获取当前音质配置（各平台独立）。"""
    return await tsmusic.get_quality()


@router.post("/quality")
async def set_quality(
    body: Annotated[dict, Body(description="音质设置 {quality, platform?}")],
    tsmusic: TsmusicDep,
    _account: AccountDep,
):
    """设置音质（quality 必填，platform 可选）。"""
    quality = body.get("quality")
    if not quality:
        raise HTTPException(status_code=400, detail="quality is required")
    platform = body.get("platform")
    return await tsmusic.set_quality(quality, platform)


# ───────────────────────── 我的音乐 / 歌单 ─────────────────────────


@router.get("/my/playlists")
async def my_playlists(platform: str, tsmusic: TsmusicDep, _account: AccountDep, bot_id: OwnedBotId = None):
    """用户歌单（自建+收藏，per-bot：用该 bot 的平台 cookie）。"""
    return await tsmusic.user_playlists(platform, bot_id=bot_id)


_PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@router.get("/my/playlist/{playlist_id}/songs")
async def my_playlist_songs(
    playlist_id: str,
    platform: str,
    tsmusic: TsmusicDep,
    _account: AccountDep,
    bot_id: OwnedBotId = None,
):
    """歌单内歌曲（per-bot；playlist_id 限定字母/数字/下划线/短横，防路径注入）。"""
    if not _PLAYLIST_ID_RE.fullmatch(playlist_id):
        raise HTTPException(status_code=400, detail="invalid playlist_id")
    return await tsmusic.playlist_songs(playlist_id, platform, bot_id=bot_id)


@router.get("/my/recommend/songs")
async def my_recommend_songs(platform: str, tsmusic: TsmusicDep, _account: AccountDep, bot_id: OwnedBotId = None):
    """每日推荐（per-bot）。"""
    return await tsmusic.recommend_songs(platform, bot_id=bot_id)


@router.get("/my/personal-fm")
async def my_personal_fm(platform: str, tsmusic: TsmusicDep, _account: AccountDep, bot_id: OwnedBotId = None):
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
    await _ensure_follow(request, tsmusic, account, bot_id)
    return await tsmusic.enqueue_songs(body.songs, platform=body.platform, bot_id=bot_id)


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
    # 共享给我的：bot_id -> owner_account_id
    shared_rows = (
        await db.execute(
            select(BotShare.bot_id, BotShare.owner_account_id).where(
                BotShare.shared_to_account_id == account.id
            )
        )
    ).all()
    shared_map = {r[0]: r[1] for r in shared_rows}
    # 共享 bot 的 owner 昵称
    owner_ids = {oid for oid in shared_map.values() if oid is not None}
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
            out.append({**b, "shared": True, "ownerNickname": owner_nicks.get(shared_map[bid], "好友")})
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
        db.add(BotShare(owner_account_id=account.id, bot_id=bot_id, shared_to_account_id=friend_id))
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status_code=400, detail="已经共享给该好友了")
        return {"success": True}
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
            select(BotShare.bot_id, BotShare.shared_to_account_id, Account.ts_nickname)
            .join(Account, Account.id == BotShare.shared_to_account_id)
            .where(BotShare.owner_account_id == account.id)
        )
    ).all()
    shares: dict[str, list[dict]] = {}
    for bid, fid, nick in rows:
        shares.setdefault(bid, []).append({"accountId": fid, "nickname": nick})
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
        return await tsmusic.set_bot_settings(body.idleTimeoutMinutes, body.autoPauseOnEmpty)
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
async def auth_status(platform: str, tsmusic: TsmusicDep, _account: AccountDep, bot_id: OwnedBotId = None):
    """获取某平台登录状态（per-bot：该 bot 的平台登录态）。"""
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
    """退出某平台登录（清除该 bot 的平台 cookie）。"""
    return await tsmusic.delete_cookie(platform, bot_id=bot_id)
