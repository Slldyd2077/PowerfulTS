"""
PowerfulTS 后端 — FastAPI

架构（原生直连 + TSMusicBot 多媒体代理）：
  /api/music/*        → TSMusicBot (:3000)      音乐引擎（网易云 / QQ / B 站 多平台）
  /api/bili/*         → TSMusicBot (:3000)      B 站搜索/点播（多平台）+ 图片代理
  /api/stats|channels → 原生 TS3 ServerQuery    监控 / 频道（直读）
  /api/auth|friends   → 原生 TS3 ServerQuery    认证 / 好友 + SQLite

原生数据层: SQLite + SQLAlchemy async (core.database)
原生 TS3 监控: services.ts3_monitor (ServerQuery 长连接轮询)
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import get_settings
from .core.database import dispose_db, init_db
from .routers import auth, bilibili, friends, monitor, music
from .services.netease import NeteaseClient
from .services.tsmusic_client import TSMusicClient
from .services.ts3_monitor import TS3Monitor

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：原生数据层 + TS3 监控 + 多媒体代理客户端。"""
    # 原生数据层: 建表 (SQLite + SQLAlchemy async)
    await init_db()
    # 原生 TS3 监控 (后台线程 ServerQuery 轮询; 未配置则优雅降级)
    app.state.ts3_monitor = TS3Monitor(settings)
    app.state.ts3_monitor.start()
    # 网易云音乐 API 客户端 (本地 NeteaseCloudMusicApi 服务, 账号/歌单)
    app.state.netease = NeteaseClient(settings.netease_api_url)
    # TSMusicBot 音乐引擎代理客户端 (网易云 / QQ / B 站 多平台)
    app.state.tsmusic = TSMusicClient(settings)
    try:
        yield
    finally:
        app.state.ts3_monitor.stop()
        await app.state.netease.close()
        await app.state.tsmusic.close()
        await dispose_db()


app = FastAPI(
    title="PowerfulTS Backend",
    version="2.0.0",
    description="TS3 监控面板后端 — 原生 TS3 直连 + TSMusicBot 多媒体代理",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["X-Session-Token", "Content-Type"],
)

# 音乐通道：TSMusicBot 多平台音乐引擎（网易云 / QQ / B 站）
app.include_router(music.router, prefix="/api")
# B 站通道：搜索/点播 (TSMusicBot 多平台) + 图片代理
app.include_router(bilibili.router, prefix="/api")
# 原生监控：/api/stats、/api/channels (从 TS3 ServerQuery 直读)
app.include_router(monitor.router, prefix="/api")
# 原生认证：/api/auth/* (TS 身份认证)
app.include_router(auth.router, prefix="/api")
# 原生好友：/api/friends/*
app.include_router(friends.router, prefix="/api")


# ─────────────────────────────────────────────────────
#  健康检查
# ─────────────────────────────────────────────────────


@app.get("/health")
async def health():
    """健康检查（仅返回状态，不泄露内部地址 / 连接串 / 数据库 URL）。"""
    return {"status": "ok", "mode": "native-transition"}
