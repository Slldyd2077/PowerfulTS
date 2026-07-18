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
from .routers import admin, auth, bilibili, friends, intro_music, monitor, music, steam
from .services.netease import NeteaseClient
from .services.napcat_client import NapCatClient
from .services.steam_client import SteamClient
from .services.bot_idle_manager import BotIdleManager
from .services.bot_player_state import BotPlayerStateStore
from .services.online_notifier import OnlineNotifier
from .services.tsmusic_client import TSMusicClient
from .services.ts3_monitor import TS3Monitor

settings = get_settings()
logger = logging.getLogger(__name__)


async def _migrate_bot_ownership() -> None:
    """把现有默认 bot（env TSMUSIC_BOT_ID）归属首个 account。

    owner 软隔离表是新增的，历史 bot（单租户时期创建）无 owner 记录，
    会被 list_bots 过滤。这里一次性把现有默认 bot 归给首个 account（你的号）。
    """
    bot_id = settings.tsmusic_bot_id
    if not bot_id:
        return
    from sqlalchemy import select

    from .models import Account, BotOwnership

    async with AsyncSessionLocal() as session:
        existing = await session.scalar(
            select(BotOwnership).where(BotOwnership.bot_id == bot_id)
        )
        if existing is not None:
            return  # 已有 owner 记录，不重复迁移
        acc = await session.scalar(select(Account).order_by(Account.id))
        if acc is None:
            return
        session.add(BotOwnership(account_id=acc.id, bot_id=bot_id))
        await session.commit()
        logger.info(
            "迁移: 现有 bot %s 归属 account %s (%s)", bot_id, acc.id, acc.ts_nickname
        )


async def _refresh_steam_games_loop(app: FastAPI) -> None:
    """后台定期拉取所有绑定 Steam 用户的当前游戏，刷新 SteamClient 快照供 TS 监控联动。

    未配置 Steam 或查询失败时优雅降级（warning 不抛），不影响主循环与监控线程。
    """
    from sqlalchemy import select

    from .models import Account

    while True:
        try:
            steam = app.state.steam
            if steam.configured:
                async with AsyncSessionLocal() as session:
                    rows = (
                        await session.execute(
                            select(Account.ts_nickname, Account.steamid64).where(
                                Account.steamid64.is_not(None)
                            )
                        )
                    ).all()
                if rows:
                    nick_to_sid = {r.ts_nickname: r.steamid64 for r in rows}
                    summaries = await steam.get_player_summaries(list(nick_to_sid.values()))
                    sid_to_game = {
                        sid: summary.get("gameextrainfo")
                        for sid, summary in summaries.items()
                        if summary and summary.get("gameextrainfo")
                    }
                    game_by_nick = {nick: sid_to_game.get(sid) for nick, sid in nick_to_sid.items()}
                    steam.update_status_snapshot(game_by_nick)
        except Exception:
            logger.warning("Steam 当前游戏快照刷新失败", exc_info=True)
        await asyncio.sleep(120)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：原生数据层 + TS3 监控 + 多媒体代理客户端 + NapCat 推送。"""
    # 原生数据层: 建表 (SQLite + SQLAlchemy async)
    await init_db()
    # 迁移：现有默认 bot（env TSMUSIC_BOT_ID）归属首个 account（兼容历史单租户数据）
    try:
        await _migrate_bot_ownership()
    except Exception:
        logger.warning("bot owner 迁移失败", exc_info=True)
    # NapCat QQ 推送客户端 (好友上线提醒; 未配置则发送时优雅降级)
    app.state.napcat = NapCatClient(settings.napcat_url, settings.napcat_token)
    # 上线提醒编排器 (反查订阅者 → NapCat 发私聊)
    app.state.online_notifier = OnlineNotifier(app.state.napcat, AsyncSessionLocal, settings)
    # 原生 TS3 监控 (后台线程 ServerQuery 轮询; 未配置则优雅降级)
    # 注入主 event loop + notifier，使监控线程能把上线事件投递回 async 主循环
    app.state.ts3_monitor = TS3Monitor(settings)
    app.state.ts3_monitor.set_loop(asyncio.get_running_loop())
    app.state.ts3_monitor.set_notifier(app.state.online_notifier)
    app.state.ts3_monitor.start()
    # Steam 集成（OpenID 绑定 + 游戏查询；未配置 API Key 则功能降级）
    app.state.steam = SteamClient(
        settings.steam_api_key,
        settings.steam_openid_return_url,
        settings.steam_openid_realm,
        settings.steam_openid_state_secret,
    )
    # TS 监控线程通过此回调读取 Steam 当前游戏（延迟求值 app.state.steam，兼容 admin 热重载）
    app.state.ts3_monitor.set_steam_lookup(
        lambda nick: app.state.steam.get_current_game_sync(nick)
    )
    # 后台定期刷新所有绑定用户的 Steam 当前游戏到内存快照（供 TS 联动）
    steam_refresh_task = asyncio.create_task(_refresh_steam_games_loop(app))
    # 网易云音乐 API 客户端 (本地 NeteaseCloudMusicApi 服务, 账号/歌单)
    app.state.netease = NeteaseClient(settings.netease_api_url)
    # TSMusicBot 音乐引擎代理客户端（单例：连接单一共享 TSMusicBot 容器）
    app.state.tsmusic = TSMusicClient(
        settings.tsmusic_url, settings.tsmusic_user, settings.tsmusic_password,
        bot_id=settings.tsmusic_bot_id,
        state_store=BotPlayerStateStore(AsyncSessionLocal),
    )
    # Resolve the client lazily: admin hot reload replaces app.state.tsmusic.
    # Capturing the object here would leave the idle manager using a closed client.
    app.state.bot_idle_manager = BotIdleManager(settings, lambda: app.state.tsmusic)
    app.state.bot_idle_manager.start()
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
        await app.state.bot_idle_manager.stop()
        await app.state.netease.close()
        await app.state.tsmusic.close()
        await app.state.napcat.close()
        steam_refresh_task.cancel()
        try:
            await steam_refresh_task
        except (asyncio.CancelledError, Exception):
            pass
        await app.state.steam.close()
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
# Steam 集成：/api/steam/*（OpenID 绑定 + 好友在线状态 + 共同游戏 + 时长排行）
app.include_router(steam.router, prefix="/api")
# 管理后台：/api/admin/*（RBAC：仅 admin）
app.include_router(admin.router, prefix="/api")


# ─────────────────────────────────────────────────────
#  健康检查
# ─────────────────────────────────────────────────────


@app.get("/health")
async def health():
    """健康检查（仅返回状态，不泄露内部地址 / 连接串 / 数据库 URL）。"""
    return {"status": "ok", "mode": "native-transition"}
