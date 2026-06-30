"""B 站浏览与点播路由 — 代理 TSMusicBot 多平台引擎。

搜索 / 播放全部委托给 TSMusicBot（platform=bilibili），用户只与 PowerfulTS 交互，
看不到 TSMusicBot WebUI。仅保留图片代理（注入 Referer/UA 绕过 B 站防盗链）。
"""
from __future__ import annotations

from ipaddress import AddressValueError, ip_address
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..deps import AccountDep, TsmusicDep
from ..services.bilibili import BILI_REFERER, BILI_UA

router = APIRouter(prefix="/bili", tags=["bilibili"])

# B 站封面/视频 CDN 域名白名单（bili_pic 仅允许代理这些 host，防 SSRF）
_BILI_HOST_SUFFIXES = (
    ".hdslb.com",
    ".bilivideo.com",
    ".bilivideo.cn",
    ".akamaized.net",
)


def _to_bili_video(song: dict) -> dict:
    """把 TSMusicBot 歌曲对象映射为前端 BiliVideo {bvid, title, author, pic, duration}。"""
    duration = song.get("duration") or 0
    return {
        "bvid": str(song.get("id", "")),
        "title": str(song.get("name", "")),
        "author": str(song.get("artist", "")),
        "pic": str(song.get("coverUrl", "") or ""),
        "duration": str(duration),
    }


def _check_bili_url(url: str) -> str:
    """校验图片代理目标：仅允许 http/https + B 站 CDN 白名单 host，拒绝内网/回环字面量。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, "仅允许 http/https 图片地址")
    host = (parsed.hostname or "").lower()
    if not host or not host.endswith(_BILI_HOST_SUFFIXES):
        raise HTTPException(400, "仅允许 B 站图片域名")
    try:
        # host 为 IP 字面量时拒绝内网/回环；域名（正常情况）已在白名单后缀校验
        ip = ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise HTTPException(400, "禁止访问内网地址")
    except AddressValueError:
        pass
    return url


# ───────────────────────── 图片代理 ─────────────────────────


@router.get("/pic")
async def bili_pic(url: str):
    """代理 B 站图片（注入 Referer/UA 绕过防盗链；仅允许 B 站 CDN 域名，防 SSRF）。

    无 header 鉴权：该端点供 ``<img src>`` 使用，浏览器无法为 img 注入 X-Session-Token，
    故以 host 白名单 + 协议限制 + 禁止重定向作为安全边界。
    """
    target = _check_bili_url(url)
    client = httpx.AsyncClient(timeout=httpx.Timeout(10.0), follow_redirects=False)
    try:
        resp = await client.get(
            target, headers={"User-Agent": BILI_UA, "Referer": BILI_REFERER}
        )
        if resp.status_code != 200:
            raise HTTPException(502, "图片获取失败")
        return Response(
            content=resp.content,
            media_type=resp.headers.get("content-type", "image/jpeg"),
        )
    except httpx.HTTPError:
        raise HTTPException(502, "图片代理失败")
    finally:
        await client.aclose()


# ───────────────────────── 搜索 ─────────────────────────


@router.get("/search")
async def bili_search(
    keyword: str,
    tsmusic: TsmusicDep,
    _account: AccountDep,
    page: int = 1,  # 前端契约保留；TSMusicBot 暂不分页
):
    """搜索 B 站视频（委托 TSMusicBot platform=bilibili）。"""
    songs = await tsmusic.search(keyword, platform="bilibili")
    return {
        "keyword": keyword,
        "count": len(songs),
        "results": [_to_bili_video(s) for s in songs],
    }


# ───────────────────────── 播放控制 ─────────────────────────


class BiliPlayRequest(BaseModel):
    bvid: str = Field(pattern=r"^BV[0-9A-Za-z]{10}$", description="B 站视频 BV 号")
    queue: bool = Field(default=False, description="True=加队列, False=立即播放")


@router.post("/play")
async def bili_play(
    body: BiliPlayRequest,
    tsmusic: TsmusicDep,
    _account: AccountDep,
):
    """播放指定 BV 号的 B 站视频音频（委托 TSMusicBot 多平台引擎）。"""
    query = f"id:{body.bvid}"
    try:
        result = await (tsmusic.add(query) if body.queue else tsmusic.play(query))
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "TSMusicBot 播放失败")

    if not isinstance(result, dict) or result.get("error"):
        raise HTTPException(502, "TSMusicBot 播放失败")

    return {
        "success": True,
        "title": result.get("title") or body.bvid,
        "bvid": body.bvid,
        "owner": None,
    }
