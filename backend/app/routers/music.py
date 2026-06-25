"""音乐控制路由。

对前端暴露语义化的 POST/GET，内部转调 TS3AudioBot。
挂在 /api/music 前缀，在 main.py 的 catch-all 之前注册以优先匹配。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel, Field

from ..services.netease import NeteaseClient
from ..services.ts3audio_client import TS3AudioBotClient, TS3AudioBotError

router = APIRouter(prefix="/music", tags=["music"])

# 普通用户音量上限；TS3AB 支持到 200，管理员可后续放开
MAX_VOLUME = 100


# ───────────────────────── 依赖 ─────────────────────────

def get_ts3ab(request: Request) -> TS3AudioBotClient:
    return request.app.state.ts3ab


async def require_session(
    x_session_token: Annotated[str | None, Header(alias="X-Session-Token")] = None,
) -> str:
    """校验登录态。

    MVP 阶段仅校验 X-Session-Token 存在；真正的有效性校验后续接入 S-QC-Bot。
    """
    if not x_session_token:
        raise HTTPException(status_code=401, detail="未登录")
    return x_session_token


def _handle_error(exc: TS3AudioBotError) -> HTTPException:
    status = {
        0: 502, 2: 401, 10: 422, 11: 403,
        12: 400, 13: 400, 15: 404, 17: 409,
    }.get(exc.code, 502)
    return HTTPException(status_code=status, detail=exc.message)


# ───────────────────────── 请求模型 ─────────────────────────

class PlayRequest(BaseModel):
    resource: str | None = Field(default=None, description="音源 URL 或搜索词")
    song_url: str | None = None  # 兼容前端旧字段
    queue: bool = Field(default=True, description="True=加队列(共享bot安全), False=立即播放")


class VolumeRequest(BaseModel):
    volume: int = Field(ge=0, le=MAX_VOLUME)


class SeekRequest(BaseModel):
    position: str


# ───────────────────────── 端点 ─────────────────────────

Ts3abDep = Annotated[TS3AudioBotClient, Depends(get_ts3ab)]
SessionDep = Annotated[str, Depends(require_session)]


@router.post("/play")
async def play(body: PlayRequest, client: Ts3abDep, _: SessionDep):
    resource = body.resource or body.song_url
    if not resource:
        raise HTTPException(status_code=422, detail="需要 resource 或 song_url")
    try:
        if body.queue:
            await client.add(resource)
        else:
            await client.play(resource)
    except TS3AudioBotError as exc:
        raise _handle_error(exc) from exc
    return {"success": True, "queued": body.queue}


@router.post("/pause")
async def pause(client: Ts3abDep, _: SessionDep):
    try:
        paused = await client.pause()
    except TS3AudioBotError as exc:
        raise _handle_error(exc) from exc
    return {"success": True, "paused": paused}


@router.post("/resume")
async def resume(client: Ts3abDep, _: SessionDep):
    try:
        await client.resume()
    except TS3AudioBotError as exc:
        raise _handle_error(exc) from exc
    return {"success": True}


@router.post("/stop")
async def stop(client: Ts3abDep, _: SessionDep):
    try:
        await client.stop()
    except TS3AudioBotError as exc:
        raise _handle_error(exc) from exc
    return {"success": True}


@router.post("/next")
async def next_track(client: Ts3abDep, _: SessionDep):
    try:
        await client.next_song()
    except TS3AudioBotError as exc:
        raise _handle_error(exc) from exc
    return {"success": True}


@router.post("/previous")
async def previous_track(client: Ts3abDep, _: SessionDep):
    try:
        await client.previous()
    except TS3AudioBotError as exc:
        raise _handle_error(exc) from exc
    return {"success": True}


@router.post("/clear")
async def clear(client: Ts3abDep, _: SessionDep):
    try:
        await client.clear()
    except TS3AudioBotError as exc:
        raise _handle_error(exc) from exc
    return {"success": True}


@router.post("/seek")
async def seek(body: SeekRequest, client: Ts3abDep, _: SessionDep):
    try:
        await client.seek(body.position)
    except TS3AudioBotError as exc:
        raise _handle_error(exc) from exc
    return {"success": True}


@router.get("/nowplaying")
async def now_playing(client: Ts3abDep, _: SessionDep):
    try:
        song = await client.get_song()
    except TS3AudioBotError as exc:
        raise _handle_error(exc) from exc
    if not song:
        return {"playing": False}
    return {
        "playing": not bool(song.get("Paused", False)),
        "title": song.get("Title"),
        "link": song.get("Link"),
        "audio_type": song.get("AudioType"),
        "position": song.get("Position"),
        "length": song.get("Length"),
    }


@router.get("/queue")
async def queue(client: Ts3abDep, _: SessionDep):
    try:
        data = await client.get_queue()
    except TS3AudioBotError as exc:
        raise _handle_error(exc) from exc
    if not data:
        return {"items": [], "index": None}
    return {
        "items": data.get("Items") or [],
        "index": data.get("PlaybackIndex"),
        "count": data.get("SongCount", 0),
    }


@router.get("/volume")
async def get_volume(client: Ts3abDep, _: SessionDep):
    try:
        value = await client.get_volume()
    except TS3AudioBotError as exc:
        raise _handle_error(exc) from exc
    return {"volume": int(value)}


@router.post("/volume")
async def set_volume(body: VolumeRequest, client: Ts3abDep, _: SessionDep):
    try:
        value = await client.set_volume(body.volume)
    except TS3AudioBotError as exc:
        raise _handle_error(exc) from exc
    return {"volume": int(value)}


# ───────────────────────── 网易云音源 (PowerfulTS 自研) ─────────────────────────
# 调本地 NeteaseCloudMusicApi (:3000) 搜歌取 URL，交 TS3AudioBot 标准 play 播放。
# 不依赖任何 TS3AudioBot 插件，绕开 .NET 兼容问题。

def get_netease(request: Request) -> NeteaseClient:
    return request.app.state.netease


NeteaseDep = Annotated[NeteaseClient, Depends(get_netease)]


@router.get("/netease/search")
async def netease_search(keyword: str, netease: NeteaseDep, _: SessionDep, limit: int = 10):
    """搜索网易云音乐，返回 [{song_id, name, artist, album}]。"""
    results = await netease.search(keyword, limit)
    return {"keyword": keyword, "count": len(results), "results": results}


class NeteasePlayRequest(BaseModel):
    song_id: str
    queue: bool = True


@router.post("/netease/play")
async def netease_play(body: NeteasePlayRequest, netease: NeteaseDep, client: Ts3abDep, _: SessionDep):
    """播放网易云歌曲：取可播放 URL → 交 TS3AudioBot 播放。"""
    url = await netease.song_url(body.song_id)
    if not url:
        raise HTTPException(status_code=404, detail="无法获取歌曲 URL（可能需 VIP 或版权限制）")
    try:
        if body.queue:
            await client.add(url)
        else:
            await client.play(url)
    except TS3AudioBotError as exc:
        raise _handle_error(exc) from exc
    return {"success": True, "queued": body.queue}
