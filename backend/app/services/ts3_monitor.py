"""原生 TS3 ServerQuery 监控。

后台线程维持一条 ServerQuery 长连接（自写 socket 客户端，无 telnetlib 依赖），
轮询 clientlist / channellist，在内存维护在线用户与频道映射。
/api/stats、/api/channels 从此读取快照。

关键设计：
  - client_data 以 unique_identifier 为 key（跨会话稳定），避免重连后 clid 变化
    导致同一用户重复计数。
  - 轮询在锁外解析、锁内一次性应用写操作（短临界区）。
  - _run 外层兜底 try/except，任何异常都不杀监控线程。

ts3_query 为同步阻塞，故轮询跑在独立线程；快照读取极快（内存），路由可直接调用。
未配置或连接失败时优雅降级（返回空数据 + monitor_running=False），不阻塞后端启动。
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime

from ..core.config import Settings
from .ts3_query import TS3QueryClient, TS3QueryError

logger = logging.getLogger(__name__)

# WebUI 额外过滤的昵称（点歌机器人等，不影响其功能）
WEBUI_FILTERED = ("统计点播姬", "点播姬")
ONLINE_WINDOW = 15  # 秒：last_seen 在此窗口内视为在线
POLL_INTERVAL = 3  # 秒：轮询间隔
INITIAL_BACKOFF = 2  # 秒：连接失败初始退避
MAX_BACKOFF = 30  # 秒：最大退避


def _safe_int(value: object, default: int = 0) -> int:
    """安全 int 转换，空/异常字段返回 default，避免 ValueError 杀线程。"""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


class TS3Monitor:
    """TS3 ServerQuery 监控器（单例，由 app.state 持有）。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.host = settings.ts3_host
        self.port = settings.ts3_query_port
        self._conn: TS3QueryClient | None = None
        self._lock = threading.Lock()
        # unique_identifier -> {nickname, cid, first_seen, last_seen}
        self.client_data: dict[str, dict] = {}
        # cid -> channel_name
        self.channel_map: dict[int, str] = {}
        # 累计 unique_identifier（本次运行；跨重启持久化留待后续）
        self._total_users: set[str] = set()
        self.start_time = datetime.now()
        self.running = False
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        # 上线提醒：主 event loop + notifier 由 app 启动时注入（同步线程 → async 主循环）
        self._loop = None
        self._notifier = None

    # ─────────────────────── 上线提醒注入 ───────────────────────

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """注入主 event loop（从同步轮询线程投递 async 通知任务用）。"""
        self._loop = loop

    def set_notifier(self, notifier) -> None:
        """注入上线提醒编排器（OnlineNotifier）。"""
        self._notifier = notifier

    # ─────────────────────── 连接 ───────────────────────

    def _connect(self) -> None:
        conn = TS3QueryClient(self.host, self.port)
        conn.connect()
        conn.send(
            "login",
            client_login_name=self.settings.ts3_query_user,
            client_login_password=self.settings.ts3_query_password,
        )
        conn.send("use", sid=self.settings.ts3_sid)
        self._conn = conn
        self.running = True
        logger.info(
            "TS3 ServerQuery 已连接 %s:%s sid=%s",
            self.host, self.port, self.settings.ts3_sid,
        )

    def _disconnect(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        self.running = False

    # ─────────────────────── 轮询 ───────────────────────

    def _refresh_channels(self) -> None:
        resp = self._conn.send("channellist")
        new_map: dict[int, str] = {}
        for ch in resp:
            cid = _safe_int(ch.get("cid"))
            new_map[cid] = str(ch.get("channel_name", ""))
        with self._lock:
            self.channel_map = new_map

    def _refresh_clients(self) -> tuple[list[tuple[str, str]], list[str]]:
        now = time.time()
        resp = self._conn.send("clientlist", uid=True)
        # 锁外完成解析（resp 已是纯数据）
        updates: dict[str, dict] = {}
        seen_uids: set[str] = set()
        for cl in resp:
            # client_type==1 为 ServerQuery 连接，跳过
            if str(cl.get("client_type", "0")) == "1":
                continue
            nickname = str(cl.get("client_nickname", ""))
            if any(f in nickname for f in WEBUI_FILTERED):
                continue
            uid = str(cl.get("client_unique_identifier", ""))
            if not uid:
                continue  # 无 uid 无法去重，跳过
            seen_uids.add(uid)
            updates[uid] = {"nickname": nickname, "cid": _safe_int(cl.get("cid"))}
        # 锁内一次性应用写 + 清理（短临界区，整个写原子）；同时收集上线/离线 nickname
        new_online: list[tuple[str, str]] = []
        went_offline: list[str] = []
        with self._lock:
            for uid, u in updates.items():
                entry = self.client_data.get(uid)
                if entry is None:
                    self.client_data[uid] = {
                        "nickname": u["nickname"],
                        "cid": u["cid"],
                        "first_seen": now,
                        "last_seen": now,
                    }
                    self._total_users.add(uid)
                    new_online.append((u["nickname"], uid))
                else:
                    entry.update(nickname=u["nickname"], cid=u["cid"], last_seen=now)
            for uid in list(self.client_data.keys()):
                if uid not in seen_uids and now - self.client_data[uid]["last_seen"] > ONLINE_WINDOW:
                    went_offline.append(self.client_data[uid]["nickname"])
                    del self.client_data[uid]
        return new_online, went_offline

    def _poll_once(self) -> None:
        assert self._conn is not None
        try:
            self._refresh_channels()
            new_online, went_offline = self._refresh_clients()
            # 锁外把上线/离线事件投递到主 loop（fire-and-forget，不阻塞轮询）
            if new_online:
                self._dispatch_online(new_online)
            if went_offline:
                self._dispatch_offline(went_offline)
        except (TS3QueryError, ConnectionError, OSError) as exc:
            # 连接/协议异常 → 标记断开，主循环走重连退避
            logger.warning("TS3 轮询失败，将重连: %s", exc)
            self._disconnect()

    def _dispatch_online(self, clients: list[tuple[str, str]]) -> None:
        """上线事件投递到主 loop（同步线程 → async 主循环），fire-and-forget。"""
        if self._loop is None or self._notifier is None or self._loop.is_closed():
            return
        for nick, uid in clients:
            fut = asyncio.run_coroutine_threadsafe(self._notifier.on_online(nick, uid), self._loop)
            fut.add_done_callback(self._on_dispatch_done)

    def _dispatch_offline(self, nicknames: list[str]) -> None:
        if self._loop is None or self._notifier is None or self._loop.is_closed():
            return
        for nick in nicknames:
            asyncio.run_coroutine_threadsafe(self._notifier.on_offline(nick), self._loop)

    @staticmethod
    def _on_dispatch_done(fut) -> None:
        """投递协程异常兜底，避免静默丢失。"""
        try:
            fut.result()
        except Exception:
            logger.exception("上线提醒投递异常")

    def _run(self) -> None:
        backoff = INITIAL_BACKOFF
        while not self._stop_event.is_set():
            try:
                if self._conn is None:
                    try:
                        self._connect()
                        backoff = INITIAL_BACKOFF
                    except Exception as exc:
                        logger.warning("TS3 连接失败（%ds 后重试）: %s", backoff, exc)
                        if self._stop_event.wait(backoff):
                            break
                        backoff = min(backoff * 2, MAX_BACKOFF)
                        continue
                self._poll_once()
                if self._conn is None:
                    # poll 失败已断开 → 走重连退避（backoff 增长）
                    if self._stop_event.wait(backoff):
                        break
                    backoff = min(backoff * 2, MAX_BACKOFF)
                    continue
                if self._stop_event.wait(POLL_INTERVAL):
                    break
            except Exception:
                # 兜底：任何未预期异常都不得杀掉监控线程
                logger.exception("TS3 监控线程未预期异常，将重连")
                self._disconnect()
                if self._stop_event.wait(backoff):
                    break
                backoff = min(backoff * 2, MAX_BACKOFF)

    # ─────────────────────── 生命周期 ───────────────────────

    def start(self) -> None:
        if not self.settings.ts3_query_user or not self.settings.ts3_query_password:
            logger.warning(
                "TS3 ServerQuery 凭据未配置 (TS3_QUERY_USER/PASSWORD)，监控不启动 "
                "— 在 .env 配置后重启即可启用（避免空凭据反复登录被 ban）"
            )
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="ts3-monitor", daemon=True)
        self._thread.start()
        logger.info("TS3 监控线程已启动")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        self._disconnect()
        logger.info("TS3 监控线程已停止")

    # ─────────────────────── 快照（供路由读取）───────────────────────

    def get_stats(self) -> dict:
        """返回兼容前端 StatsData 契约的统计快照。"""
        now = time.time()
        online_list: list[dict] = []
        games: dict[str, int] = {}
        with self._lock:
            for entry in self.client_data.values():
                if now - entry["last_seen"] > ONLINE_WINDOW:
                    continue
                channel_name = self.channel_map.get(entry["cid"], "未知频道")
                online_list.append({
                    "nickname": entry["nickname"],
                    "game": channel_name,  # P0: 频道名即游戏（后续可加 game_mapping 精炼）
                    "online_time": int(now - entry["first_seen"]),
                    "channel": channel_name,
                })
                games[channel_name] = games.get(channel_name, 0) + 1
        return {
            "running_time": int((datetime.now() - self.start_time).total_seconds()),
            "total_users": len(self._total_users),
            "online_users": len(online_list),
            "gaming_users": len(online_list),
            "games": games,
            "online_list": online_list,
            "server_host": self.host,
            "server_port": self.port,
            "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "monitor_running": self.running,
            "mining_users": [],
            "mining_pools": {},
        }

    def get_channels(self) -> dict:
        """返回兼容前端 ChannelData 契约的频道快照。"""
        with self._lock:
            channels = {str(cid): name for cid, name in self.channel_map.items()}
        return {"channels": channels, "count": len(channels)}

    def get_status(self, nickname: str) -> tuple[str, str | None]:
        """返回该昵称的 (online_status, game)。

        online_status: '游戏中' / '在线' / '离线'；game 为所在频道名（在线时）。
        供好友列表的在线状态展示复用。
        """
        now = time.time()
        with self._lock:
            for entry in self.client_data.values():
                if entry["nickname"] == nickname and now - entry["last_seen"] <= ONLINE_WINDOW:
                    game = self.channel_map.get(entry["cid"])
                    return ("游戏中" if game else "在线", game)
        return ("离线", None)
