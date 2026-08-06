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

# 网页通话身份在 TS 里的昵称前缀，由 TSMusicBot 的 BotProfileManager 加上。
# 昵称是 PowerfulTS 各处的身份键（上线提醒、好友在线状态、ServerQuery 私聊），
# 带着这个标记去精确匹配账号昵称会全线失配 —— 网页上线因此收不到 QQ 提醒。
# 所以快照里同时留两份：nickname 是 TS 里的原样（展示用），identity 去掉标记（匹配用）。
WEB_VOICE_MARKER = "<WEB通讯>"


def strip_web_voice_marker(nickname: str) -> str:
    """去掉 `<WEB通讯>` 前缀，得到账号本身的 TS 昵称；没有标记则原样返回。"""
    if nickname.startswith(WEB_VOICE_MARKER):
        return nickname[len(WEB_VOICE_MARKER):].lstrip()
    return nickname


def _safe_int(value: object, default: int = 0) -> int:
    """安全 int 转换，空/异常字段返回 default，避免 ValueError 杀线程。"""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _build_channel_tree(raw_channels: list[dict]) -> list[dict]:
    """Build TS display order from ``pid`` and ``channel_order``.

    ``channel_order`` is not a numeric rank. It contains the cid of the
    previous sibling (0 means first), so sorting by cid or by channel_order
    does not reproduce the TeamSpeak channel tree.
    """
    parsed: list[dict] = []
    seen_cids: set[int] = set()
    for raw in raw_channels:
        cid = _safe_int(raw.get("cid"))
        if cid <= 0 or cid in seen_cids:
            continue
        seen_cids.add(cid)
        parsed.append({
            "cid": cid,
            "pid": _safe_int(raw.get("pid")),
            "channel_order": _safe_int(raw.get("channel_order")),
            "name": str(raw.get("channel_name", "")),
        })

    children_by_parent: dict[int, list[dict]] = {}
    for channel in parsed:
        children_by_parent.setdefault(channel["pid"], []).append(channel)

    def ordered_siblings(parent_id: int) -> list[dict]:
        siblings = children_by_parent.get(parent_id, [])
        followers: dict[int, list[dict]] = {}
        for channel in siblings:
            followers.setdefault(channel["channel_order"], []).append(channel)

        ordered: list[dict] = []
        used: set[int] = set()
        previous_cid = 0
        while True:
            next_channel = next(
                (item for item in followers.get(previous_cid, []) if item["cid"] not in used),
                None,
            )
            if next_channel is None:
                break
            ordered.append(next_channel)
            used.add(next_channel["cid"])
            previous_cid = next_channel["cid"]

        # Broken or incomplete order links should not make a channel vanish.
        ordered.extend(channel for channel in siblings if channel["cid"] not in used)
        return ordered

    result: list[dict] = []
    visited: set[int] = set()

    def append_branch(parent_id: int, depth: int) -> None:
        for channel in ordered_siblings(parent_id):
            cid = channel["cid"]
            if cid in visited:
                continue
            visited.add(cid)
            result.append({
                "cid": cid,
                "pid": channel["pid"],
                "channel_order": channel["channel_order"],
                "name": channel["name"],
                "depth": depth,
            })
            append_branch(cid, depth + 1)

    append_branch(0, 0)

    # Keep orphaned/cyclic records visible, using query order as a safe fallback.
    for channel in parsed:
        if channel["cid"] in visited:
            continue
        visited.add(channel["cid"])
        result.append({
            "cid": channel["cid"],
            "pid": channel["pid"],
            "channel_order": channel["channel_order"],
            "name": channel["name"],
            "depth": 0,
        })
        append_branch(channel["cid"], 1)

    return result


class TS3Monitor:
    """TS3 ServerQuery 监控器（单例，由 app.state 持有）。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.host = settings.ts3_host
        self.port = settings.ts3_query_port
        self._conn: TS3QueryClient | None = None
        self._lock = threading.Lock()
        # unique_identifier -> {nickname, identity, clid, cid, first_seen, last_seen}
        self.client_data: dict[str, dict] = {}
        # cid -> channel_name
        self.channel_map: dict[int, str] = {}
        # TS display order, including parent/child depth for the Web UI.
        self.channel_tree: list[dict] = []
        # cid -> 是否设了频道密码（网页通话切频道时决定要不要弹密码框）
        self.channel_password: dict[int, bool] = {}
        # 累计 unique_identifier（本次运行；跨重启持久化留待后续）
        self._total_users: set[str] = set()
        self.start_time = datetime.now()
        self.running = False
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        # 按需轮询：加入通话 / 切频道这类动作做完就该立刻看到新状态，
        # 不该等下一个 POLL_INTERVAL。_wake 提前唤醒轮询线程，
        # _polls_started/_polls_done 让调用方能等到「请求之后才开始」的那次轮询跑完。
        self._wake = threading.Event()
        self._poll_cv = threading.Condition()
        self._polls_started = 0
        self._polls_done = 0
        # 上线提醒：主 event loop + notifier 由 app 启动时注入（同步线程 → async 主循环）
        self._loop = None
        self._notifier = None
        # Steam 当前游戏查询回调（由 app 注入；TS 在线时优先显示 Steam 游戏）
        self._steam_lookup = None

    # ─────────────────────── 上线提醒注入 ───────────────────────

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """注入主 event loop（从同步轮询线程投递 async 通知任务用）。"""
        self._loop = loop

    def set_notifier(self, notifier) -> None:
        """注入上线提醒编排器（OnlineNotifier）。"""
        self._notifier = notifier

    def set_steam_lookup(self, lookup) -> None:
        """注入 Steam 当前游戏查询回调：lookup(nickname) -> game_name | None。

        get_status/get_stats 在 TS 在线时优先展示 Steam 当前游戏（无则回退频道名）。
        回调由后台 task 维护的内存快照支撑，本线程只读，任何异常降级为 None。
        """
        self._steam_lookup = lookup

    def _steam_game(self, nickname: str) -> str | None:
        """安全调用 Steam 查询回调；未注入/异常一律返回 None（优雅降级）。"""
        if not self._steam_lookup:
            return None
        try:
            return self._steam_lookup(nickname)
        except Exception:
            return None

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
        # -flags 额外带回 channel_flag_password，网页通话据此决定是否要密码。
        resp = self._conn.send("channellist", flags=True)
        new_map: dict[int, str] = {}
        new_password: dict[int, bool] = {}
        for ch in resp:
            cid = _safe_int(ch.get("cid"))
            new_map[cid] = str(ch.get("channel_name", ""))
            new_password[cid] = _safe_int(ch.get("channel_flag_password")) == 1
        new_tree = _build_channel_tree(resp)
        with self._lock:
            self.channel_map = new_map
            self.channel_tree = new_tree
            self.channel_password = new_password

    def _refresh_clients(self) -> tuple[list[tuple[str, str, bool]], list[str]]:
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
            updates[uid] = {
                "nickname": nickname,
                "identity": strip_web_voice_marker(nickname),
                "clid": _safe_int(cl.get("clid")),
                "cid": _safe_int(cl.get("cid")),
            }
        # 锁内一次性应用写 + 清理（短临界区，整个写原子）；同时收集上线/离线事件。
        # 上线事件带 identity（账号昵称）而不是原样昵称，网页身份才认得出是谁。
        new_online: list[tuple[str, str, bool]] = []
        went_offline: list[str] = []
        with self._lock:
            for uid, u in updates.items():
                entry = self.client_data.get(uid)
                if entry is None:
                    self.client_data[uid] = {
                        "nickname": u["nickname"],
                        "identity": u["identity"],
                        "clid": u["clid"],
                        "cid": u["cid"],
                        "first_seen": now,
                        "last_seen": now,
                    }
                    self._total_users.add(uid)
                    new_online.append((u["identity"], uid, u["identity"] != u["nickname"]))
                else:
                    entry.update(
                        nickname=u["nickname"],
                        identity=u["identity"],
                        clid=u["clid"],
                        cid=u["cid"],
                        last_seen=now,
                    )
            for uid in list(self.client_data.keys()):
                if uid not in seen_uids and now - self.client_data[uid]["last_seen"] > ONLINE_WINDOW:
                    went_offline.append(self.client_data[uid]["identity"])
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

    def _dispatch_online(self, clients: list[tuple[str, str, bool]]) -> None:
        """上线事件投递到主 loop（同步线程 → async 主循环），fire-and-forget。"""
        if self._loop is None or self._notifier is None or self._loop.is_closed():
            return
        for nick, uid, web_voice in clients:
            fut = asyncio.run_coroutine_threadsafe(
                self._notifier.on_online(nick, uid, web_voice=web_voice), self._loop
            )
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

    def _poll_and_publish(self) -> None:
        """轮询一次并推进代次，让 request_refresh 的等待者知道新快照已就绪。

        失败（连接断开）也要推进：等待方只是「等这一轮跑完」，不该被吊到超时。
        """
        with self._poll_cv:
            self._polls_started += 1
            started = self._polls_started
        try:
            self._poll_once()
        finally:
            with self._poll_cv:
                self._polls_done = started
                self._poll_cv.notify_all()

    def _sleep_between_polls(self, seconds: float) -> bool:
        """轮询间隔；request_refresh 与 stop 都能提前唤醒。True 表示该退出线程。"""
        self._wake.wait(seconds)
        self._wake.clear()
        return self._stop_event.is_set()

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
                self._poll_and_publish()
                if self._conn is None:
                    # poll 失败已断开 → 走重连退避（backoff 增长）
                    if self._stop_event.wait(backoff):
                        break
                    backoff = min(backoff * 2, MAX_BACKOFF)
                    continue
                if self._sleep_between_polls(POLL_INTERVAL):
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
        self._wake.set()  # 正在等轮询间隔的线程立刻醒来收工
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        self._disconnect()
        logger.info("TS3 监控线程已停止")

    # ─────────────────────── 按需刷新（供路由调用）───────────────────────

    def request_refresh(self) -> int:
        """请求轮询线程立刻跑一次，返回配合 wait_for_refresh 用的代次令牌。

        令牌取的是「已开始的轮询数」：若此刻正好有一轮在飞，它读到的是动作之前的
        状态，等它没意义，所以 wait_for_refresh 要求 _polls_done 严格大于令牌
        —— 即必须是本次请求之后才开始的那一轮。
        """
        with self._poll_cv:
            token = self._polls_started
        self._wake.set()
        return token

    def wait_for_refresh(self, token: int, timeout: float = 2.0) -> bool:
        """阻塞等到该轮轮询跑完（调用方应放线程池）。超时返回 False，不抛。"""
        with self._poll_cv:
            return self._poll_cv.wait_for(lambda: self._polls_done > token, timeout)

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
                nickname = entry["nickname"]
                # 显示用原样昵称（TS 里就是这个），查 Steam 用 identity：
                # 绑定按账号昵称记，带 <WEB通讯> 前缀查不到。
                display_game = self._steam_game(entry["identity"]) or channel_name
                online_list.append({
                    "nickname": nickname,
                    "game": display_game,
                    "online_time": int(now - entry["first_seen"]),
                    "channel": channel_name,
                })
                games[display_game] = games.get(display_game, 0) + 1
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
            channels = [dict(channel) for channel in self.channel_tree]
        return {"channels": channels, "count": len(channels)}

    def get_voice_overview(self, bot_clid: int | None) -> dict:
        """网页通话用：频道树 + 每个频道的在场成员 + bot 当前所在频道。

        bot 用 clid 定位而不是昵称：昵称会随「正在播放的歌」和 <WEB通讯> 标记变化，
        按昵称找会在这两种情况下失效。
        """
        now = time.time()
        with self._lock:
            tree = [dict(channel) for channel in self.channel_tree]
            needs_password = dict(self.channel_password)
            members: dict[int, list[dict]] = {}
            bot_cid: int | None = None
            for entry in self.client_data.values():
                if now - entry["last_seen"] > ONLINE_WINDOW:
                    continue
                is_bot = bot_clid is not None and entry.get("clid") == bot_clid
                if is_bot:
                    bot_cid = entry["cid"]
                # clid 要透出去：下行语音包按 clid 标记说话人，前端靠它把
                # 「谁在说话」和「这条音频流」对上，才能给每个人单独调音量。
                members.setdefault(entry["cid"], []).append(
                    {"clid": entry.get("clid", 0), "nickname": entry["nickname"], "isBot": is_bot}
                )
        channels = [
            {
                "cid": channel["cid"],
                "pid": channel["pid"],
                "depth": channel["depth"],
                "name": channel["name"],
                "hasPassword": needs_password.get(channel["cid"], False),
                "clients": sorted(
                    members.get(channel["cid"], []), key=lambda c: c["nickname"].lower()
                ),
            }
            for channel in tree
        ]
        return {"channels": channels, "botCid": bot_cid, "monitorRunning": self.running}

    def get_status(self, nickname: str) -> tuple[str, str | None]:
        """返回该昵称的 (online_status, game)。

        online_status: '游戏中' / '在线' / '离线'；game 为所在频道名（在线时）。
        供好友列表的在线状态展示复用。
        """
        now = time.time()
        with self._lock:
            for entry in self.client_data.values():
                # 按 identity 比：网页通话身份的昵称带 <WEB通讯> 前缀，按原样比会判成离线。
                if entry["identity"] == nickname and now - entry["last_seen"] <= ONLINE_WINDOW:
                    # 优先显示 Steam 当前游戏（后台 task 维护），无则回退 TS 频道名
                    steam_game = self._steam_game(nickname)
                    if steam_game:
                        return ("游戏中", steam_game)
                    game = self.channel_map.get(entry["cid"])
                    return ("游戏中" if game else "在线", game)
        return ("离线", None)
