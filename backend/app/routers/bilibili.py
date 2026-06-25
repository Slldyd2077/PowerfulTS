"""B 站浏览与播放路由（方案 D，不依赖 TS3AudioBot 插件）。

PowerfulTS 后端自取 B 站 DASH 音频流，经自带 stream proxy（支持 Range/流式，
替代坏掉的 xxmod Proxy.exe）喂给 TS3AudioBot 播放。
"""
from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from ..services.bilibili import BILI_REFERER, BILI_UA, BiliClient
from ..services.ts3audio_client import TS3AudioBotClient, TS3AudioBotError
from .music import require_session

router = APIRouter(prefix="/bili", tags=["bilibili"])

# 需要透传给 ffmpeg 的响应头（尤其 content-range / accept-ranges，决定能否 seek）
_PASS_HEADERS = (
    "content-type",
    "content-length",
    "content-range",
    "accept-ranges",
    "cache-control",
    "etag",
)


def _get_ts3ab(request: Request) -> TS3AudioBotClient:
    return request.app.state.ts3ab


def _get_bili(request: Request) -> BiliClient:
    return request.app.state.bili


def _bili_err(exc: TS3AudioBotError) -> HTTPException:
    status = {
        0: 502, 2: 401, 10: 422, 11: 403,
        12: 400, 13: 400, 15: 404, 17: 409,
    }.get(exc.code, 502)
    return HTTPException(status_code=status, detail=exc.message)


# ───────────────────────── stream proxy ─────────────────────────


@router.get("/stream")
async def bili_stream(url: str, request: Request):
    """流式转发 B 站音频流：注入 Referer/UA，透传 Range 与分片响应头。

    这是替代 xxmod Proxy.exe 的关键——它支持 Range，ffmpeg 才能正常探测与播放。
    """
    fwd = {"User-Agent": BILI_UA, "Referer": BILI_REFERER}
    if rng := request.headers.get("range"):
        fwd["Range"] = rng

    client = httpx.AsyncClient(timeout=httpx.Timeout(None), follow_redirects=True)
    try:
        upstream = await client.send(
            client.build_request("GET", url, headers=fwd), stream=True
        )
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(502, f"无法获取 B 站音频流: {exc}") from exc

    resp_headers = {k: upstream.headers[k] for k in _PASS_HEADERS if k in upstream.headers}

    async def body():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        body(), status_code=upstream.status_code, headers=resp_headers
    )


@router.get("/pic")
async def bili_pic(url: str):
    """代理 B 站图片（注入 Referer/UA 绕过防盗链，缩略图才能显示）。"""
    client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
    try:
        resp = await client.get(url, headers={"User-Agent": BILI_UA, "Referer": BILI_REFERER})
        if resp.status_code != 200:
            raise HTTPException(502, "图片获取失败")
        return Response(
            content=resp.content,
            media_type=resp.headers.get("content-type", "image/jpeg"),
        )
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"图片代理失败: {exc}") from exc
    finally:
        await client.aclose()


# ───────────────────────── 播放控制 ─────────────────────────


class BiliPlayRequest(BaseModel):
    bvid: str = Field(description="B 站视频 BV 号")
    queue: bool = Field(default=False, description="True=加队列, False=立即播放")


@router.post("/play")
async def bili_play(
    body: BiliPlayRequest,
    request: Request,
    ts3ab: Annotated[TS3AudioBotClient, Depends(_get_ts3ab)],
    bili: Annotated[BiliClient, Depends(_get_bili)],
    _: Annotated[str, Depends(require_session)],
):
    """播放指定 BV 号的 B 站视频音频。"""
    try:
        info = await bili.get_video(body.bvid)
        audio = await bili.get_audio_url(info["bvid"], info["cid"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    stream_url = f"{request.base_url}api/bili/stream?url={quote(audio, safe='')}"
    try:
        if body.queue:
            await ts3ab.add(stream_url)
        else:
            await ts3ab.play(stream_url)
    except TS3AudioBotError as exc:
        raise _bili_err(exc) from exc

    return {
        "success": True,
        "title": info.get("title"),
        "bvid": info["bvid"],
        "owner": (info.get("owner") or {}).get("name"),
    }


# ───────────────────────── 搜索 ─────────────────────────


@router.get("/search")
async def bili_search(
    keyword: str,
    bili: Annotated[BiliClient, Depends(_get_bili)],
    _: Annotated[str, Depends(require_session)],
    page: int = 1,
):
    """Wbi 签名搜索 B 站视频。"""
    try:
        results = await bili.search(keyword, page)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"keyword": keyword, "count": len(results), "results": results}
