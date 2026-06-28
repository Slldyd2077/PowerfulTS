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
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ._version import __version__
from .core.config import get_settings
from .core.database import AsyncSessionLocal, dispose_db, init_db
from .routers import auth, bilibili, friends, intro_music, monitor, music
from .services.netease import NeteaseClient
from .services.napcat_client import NapCatClient
from .services.online_notifier import OnlineNotifier
from .services.tsmusic_client import TSMusicClient
from .services.ts3_monitor import TS3Monitor

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：原生数据层 + TS3 监控 + 多媒体代理客户端 + NapCat 推送。"""
    # 原生数据层: 建表 (SQLite + SQLAlchemy async)
    await init_db()
    # NapCat QQ 推送客户端 (好友上线提醒; 未配置则发送时优雅降级)
    app.state.napcat = NapCatClient(settings.napcat_url, settings.napcat_token)
    # 上线提醒编排器 (反查订阅者 → NapCat 发私聊)
    app.state.online_notifier = OnlineNotifier(app.state.napcat, AsyncSessionLocal)
    # 原生 TS3 监控 (后台线程 ServerQuery 轮询; 未配置则优雅降级)
    # 注入主 event loop + notifier，使监控线程能把上线事件投递回 async 主循环
    app.state.ts3_monitor = TS3Monitor(settings)
    app.state.ts3_monitor.set_loop(asyncio.get_running_loop())
    app.state.ts3_monitor.set_notifier(app.state.online_notifier)
    app.state.ts3_monitor.start()
    # 网易云音乐 API 客户端 (本地 NeteaseCloudMusicApi 服务, 账号/歌单)
    app.state.netease = NeteaseClient(settings.netease_api_url)
    # TSMusicBot 音乐引擎代理客户端 (网易云 / QQ / B 站 多平台)
    app.state.tsmusic = TSMusicClient(settings)
    # 预加载播放跟随开关到单例（保证重启后关闭态生效；失败不阻断启动）
    try:
        async with AsyncSessionLocal() as session:
            await app.state.tsmusic.load_follow_setting(session)
    except Exception:
        logger.warning("预加载播放跟随开关失败（将惰性使用默认值）", exc_info=True)
    try:
        yield
    finally:
        app.state.ts3_monitor.stop()
        await app.state.netease.close()
        await app.state.tsmusic.close()
        await app.state.napcat.close()
        await dispose_db()


app = FastAPI(
    title="PowerfulTS Backend",
    version=__version__,
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
# 开屏背景音乐：/api/intro-music/* (本地音乐目录扫描 + 流式, 登录页随机播放 + 真实频谱)
app.include_router(intro_music.router, prefix="/api")


# ─────────────────────────────────────────────────────
#  健康检查
# ─────────────────────────────────────────────────────


@app.get("/health")
async def health():
    """健康检查（仅返回状态，不泄露内部地址 / 连接串 / 数据库 URL）。"""
    return {"status": "ok", "mode": "native-transition"}
