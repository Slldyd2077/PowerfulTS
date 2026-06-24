"""
PowerfulTS 后端 — FastAPI

架构演进中（分阶段原生化）：
  /api/music/*        → TS3AudioBot (:58913)  音乐引擎 (原生)
  /api/bilibili/*     → Bilibili API           B 站浏览/播放 (原生)
  /api/stats|channels → 原生 TS3 ServerQuery   (P0 已接入)
  /api/* (其余)       → S-QC-Bot (:8080)       过渡期透传 (逐模块替换, 高危端点已拉黑)

原生数据层: SQLite + SQLAlchemy async (core.database)
原生 TS3 监控: services.ts3_monitor (ServerQuery 长连接轮询)
"""
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .core.config import get_settings
from .core.database import dispose_db, init_db
from .services.ts3audio_client import TS3AudioBotClient
from .services.bilibili import BiliClient
from .services.ts3_monitor import TS3Monitor
from .routers import music, bilibili, monitor

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：原生数据层 + TS3 监控 + 桥接客户端。"""
    # 原生数据层: 建表 (SQLite + SQLAlchemy async)
    await init_db()
    # 原生 TS3 监控 (后台线程 ServerQuery 轮询; 未配置则优雅降级)
    app.state.ts3_monitor = TS3Monitor(settings)
    app.state.ts3_monitor.start()
    # 通道 1: S-QC-Bot 透传客户端 (过渡期)
    app.state.sqc_client = httpx.AsyncClient(
        base_url=settings.sqc_bot_url,
        timeout=httpx.Timeout(15.0),
    )
    # 通道 2: TS3AudioBot 音乐引擎客户端
    app.state.ts3ab = TS3AudioBotClient(settings)
    # B 站 API 客户端 (后端自取音频流)
    app.state.bili = BiliClient()
    try:
        yield
    finally:
        app.state.ts3_monitor.stop()
        await app.state.sqc_client.aclose()
        await app.state.ts3ab.close()
        await app.state.bili.close()
        await dispose_db()


app = FastAPI(
    title="PowerfulTS Backend",
    version="2.0.0",
    description="TS3 监控面板后端 — 分阶段原生化 (TS3 直连 + SQLite)",
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
# B 站通道：浏览与播放 (后端自取音频流, 不依赖 TS3AudioBot 插件)
app.include_router(bilibili.router, prefix="/api")
# 原生监控：/api/stats、/api/channels (P0，从 TS3 ServerQuery 直读)
app.include_router(monitor.router, prefix="/api")


# ─────────────────────────────────────────────────────
#  通用代理：其余 /api/* 请求转发到 S-QC-Bot (过渡期)
# ─────────────────────────────────────────────────────

# 过渡期透传代理: 拉黑 S-QC-Bot 中的高危无鉴权端点
# (远程桌面控制等; 完整鉴权在 P1 接入账号体系时统一处理)
_PROXY_BLOCKLIST = ("desktop/exec", "desktop", "heart/tick")


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_api(path: str, request: Request):
    """通用 API 代理：将未原生化请求转发到 S-QC-Bot。

    随原生化推进，/api/stats、/api/channels 等已由原生路由接管，不再进入这里。
    """
    normalized = path.rstrip("/")
    if any(normalized == b or normalized.startswith(b + "/") for b in _PROXY_BLOCKLIST):
        return Response(
            content='{"error": "该端点已被安全策略禁用"}',
            status_code=403,
            media_type="application/json",
        )

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
    """健康检查（仅返回状态，不泄露内部地址 / 连接串 / 数据库 URL）。"""
    return {"status": "ok", "mode": "native-transition"}
