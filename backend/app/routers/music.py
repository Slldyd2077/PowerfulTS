"""音乐路由 — 代理 TSMusicBot API。

用户只与 PowerfulTS 交互（统一认证 X-Session-Token，由 get_current_account 校验），
后端代理到 TSMusicBot (:3000)，用户看不到 TSMusicBot WebUI。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..deps import get_current_account
from ..models import Account
from ..services.tsmusic_client import TSMusicClient

router = APIRouter(prefix="/music", tags=["music"])


# ───────────────────────── 依赖 ─────────────────────────

def get_tsmusic(request: Request) -> TSMusicClient:
    return request.app.state.tsmusic


TsmusicDep = Annotated[TSMusicClient, Depends(get_tsmusic)]
AccountDep = Annotated[Account, Depends(get_current_account)]


# ───────────────────────── 请求模型 ─────────────────────────

class SearchRequest(BaseModel):
    q: str = Field(description="搜索关键词")


class PlayRequest(BaseModel):
    query: str = Field(description="歌名或 'id:xxx' 精确播放")
    queue: bool = Field(default=False, description="True=加入队列, False=立即播放")
    platform: str | None = Field(default=None, description="音源平台 netease/qq/bilibili")


class VolumeRequest(BaseModel):
    volume: int = Field(ge=0, le=100)


class ModeRequest(BaseModel):
    mode: str = Field(description="seq | loop | random | rloop")


# ───────────────────────── 端点 ─────────────────────────

@router.get("/search")
async def search(
    q: str,
    tsmusic: TsmusicDep,
    _account: AccountDep,
    platform: str | None = None,
):
    """搜索歌曲（可指定平台 netease/qq/bilibili）。"""
    results = await tsmusic.search(q, platform=platform)
    return {"count": len(results), "results": results}


@router.post("/play")
async def play(body: PlayRequest, tsmusic: TsmusicDep, _account: AccountDep):
    """播放（query 可以是歌名或 'id:xxx'，platform 指定音源）。"""
    if body.queue:
        result = await tsmusic.add(body.query, platform=body.platform)
    else:
        result = await tsmusic.play(body.query, platform=body.platform)
    return result


@router.post("/pause")
async def pause(tsmusic: TsmusicDep, _account: AccountDep):
    return await tsmusic.pause()


@router.post("/resume")
async def resume(tsmusic: TsmusicDep, _account: AccountDep):
    return await tsmusic.resume()


@router.post("/next")
async def next_track(tsmusic: TsmusicDep, _account: AccountDep):
    return await tsmusic.next()


@router.post("/stop")
async def stop(tsmusic: TsmusicDep, _account: AccountDep):
    return await tsmusic.stop()


@router.post("/seek")
async def seek(body: SeekRequest, tsmusic: TsmusicDep, _account: AccountDep):
    return await tsmusic.seek(body.position)


@router.post("/volume")
async def set_volume(body: VolumeRequest, tsmusic: TsmusicDep, _account: AccountDep):
    return await tsmusic.set_volume(body.volume)


@router.post("/mode")
async def set_mode(body: ModeRequest, tsmusic: TsmusicDep, _account: AccountDep):
    return await tsmusic.set_mode(body.mode)


@router.post("/clear")
async def clear(tsmusic: TsmusicDep, _account: AccountDep):
    return await tsmusic.clear()


@router.get("/nowplaying")
async def now_playing(tsmusic: TsmusicDep, _account: AccountDep):
    """当前播放状态（歌名/歌手/进度/封面/音量）。"""
    return await tsmusic.get_bot_status()


@router.get("/queue")
async def queue(tsmusic: TsmusicDep, _account: AccountDep):
    """播放队列。"""
    items = await tsmusic.get_queue()
    return {"count": len(items), "items": items}


# ───────────────────────── 平台账号登录 ─────────────────────────


@router.get("/auth/status")
async def auth_status(platform: str, tsmusic: TsmusicDep, _account: AccountDep):
    """获取某平台登录状态。"""
    return await tsmusic.get_auth_status(platform)


@router.post("/auth/qrcode")
async def auth_qrcode(body: dict, tsmusic: TsmusicDep, _account: AccountDep):
    """获取某平台登录二维码。"""
    platform = body.get("platform", "netease")
    return await tsmusic.get_qrcode(platform)


class CookieRequest(BaseModel):
    platform: str
    cookie: str


@router.post("/auth/cookie")
async def auth_cookie(body: CookieRequest, tsmusic: TsmusicDep, _account: AccountDep):
    """手动设置某平台 cookie。"""
    return await tsmusic.set_cookie(body.platform, body.cookie)
