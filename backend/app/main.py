"""
PowerfulTS 后端 — FastAPI 双桥接代理

两条通道并存：
  /api/music/*  → TS3AudioBot (:58913)  音乐引擎
  /api/*        → S-QC-Bot (:8080)      监控/用户/频道 (透传)
"""
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .core.config import get_settings
from .services.ts3audio_client import TS3AudioBotClient
from .services.bilibili import BiliClient
from .routers import music, bilibili

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：创建/销毁两个桥接客户端。"""
    # 通道 1: S-QC-Bot 透传客户端
    app.state.sqc_client = httpx.AsyncClient(
        base_url=settings.sqc_bot_url,
        timeout=httpx.Timeout(15.0),
    )
    # 通道 2: TS3AudioBot 音乐引擎客户端
    app.state.ts3ab = TS3AudioBotClient(settings)
    # B 站 API 客户端 (方案 D: 后端自取音频流)
    app.state.bili = BiliClient()
    try:
        yield
    finally:
        await app.state.sqc_client.aclose()
        await app.state.ts3ab.close()
        await app.state.bili.close()


app = FastAPI(
    title="PowerfulTS Backend",
    version="1.1.0",
    description="TS3 监控面板后端 — 双桥接 (S-QC-Bot 监控 + TS3AudioBot 音乐)",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 音乐通道：具体路由，必须在 catch-all 之前注册以优先匹配
app.include_router(music.router, prefix="/api")
# B 站通道：浏览与播放 (方案 D, 不依赖 TS3AudioBot 插件)
app.include_router(bilibili.router, prefix="/api")


# ─────────────────────────────────────────────────────
#  通用代理：其余 /api/* 请求转发到 S-QC-Bot
# ─────────────────────────────────────────────────────

@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_api(path: str, request: Request):
    """
    通用 API 代理：将非音乐请求转发到 S-QC-Bot。

    /api/music/* 已由上方 music router 拦截，不会进入这里。
    """
    client: httpx.AsyncClient = request.app.state.sqc_client

    target_path = f"/api/{path}"
    if request.url.query:
        target_path += f"?{request.url.query}"

    body = await request.body()

    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)
    headers.pop("transfer-encoding", None)

    try:
        upstream_resp = await client.request(
            method=request.method,
            url=target_path,
            content=body if body else None,
            headers=headers,
        )

        response_headers = dict(upstream_resp.headers)
        for h in ["content-encoding", "transfer-encoding", "content-length"]:
            response_headers.pop(h, None)

        return Response(
            content=upstream_resp.content,
            status_code=upstream_resp.status_code,
            headers=response_headers,
        )
    except httpx.ConnectError:
        return Response(
            content='{"error": "无法连接到 S-QC-Bot 服务，请确保 bot_main_v2.py 已启动"}',
            status_code=502,
            media_type="application/json",
        )
    except httpx.TimeoutException:
        return Response(
            content='{"error": "S-QC-Bot 服务响应超时"}',
            status_code=504,
            media_type="application/json",
        )


# ─────────────────────────────────────────────────────
#  健康检查
# ─────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "ok",
        "mode": "dual-bridge",
        "sqc_bot": settings.sqc_bot_url,
        "ts3ab": settings.ts3ab_url,
    }
