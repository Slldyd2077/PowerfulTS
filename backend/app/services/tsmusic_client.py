"""TSMusicBot API 代理客户端。

PowerfulTS 后端登录 TSMusicBot（:3000），持有 session cookie，
代理所有音乐 API。用户只与 PowerfulTS 交互，看不到 TSMusicBot WebUI。
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import Settings
from . import app_setting

if TYPE_CHECKING:
    from .bot_player_state import BotPlayerStateStore

logger = logging.getLogger(__name__)

# TSMusicBot 需要 Origin header 才允许 API 调用（CSRF 防护）
_HEADERS = {
    "Origin": "http://127.0.0.1:3000",
    "Content-Type": "application/json",
}

_QUALITY_POLICY: dict[str, dict[str, bool]] = {
    "netease": {
        "standard": False,
        "higher": False,
        "exhigh": False,
        "lossless": True,
        "hires": True,
        "jymaster": True,
    },
    "qq": {"128": False, "320": False, "flac": True},
    "bilibili": {"high": False},
    "kugou": {"128": False, "320": False, "flac": True, "high": True},
}

_QUALITY_ALIASES: dict[str, dict[str, str]] = {
    "qq": {
        "standard": "128",
        "higher": "320",
        "exhigh": "320",
        "lossless": "flac",
    },
    "kugou": {
        "standard": "128",
        "higher": "320",
        "exhigh": "320",
        "lossless": "flac",
        "hires": "high",
    },
}


class TSMusicClient:
    """TSMusicBot REST API 代理客户端（per-user：每个用户连自己的专属容器）。"""

    def __init__(
        self,
        base_url: str,
        user: str,
        password: str,
        bot_id: str = "",
        state_store: BotPlayerStateStore | None = None,
    ) -> None:
        self._base = base_url
        self._user = user
        self._pass = password
        self._bot_id = bot_id
        self._state_store = state_store
        self._state_locks: dict[str, asyncio.Lock] = {}
        self._startup_locks: dict[str, asyncio.Lock] = {}
        self._restored_bot_ids: set[str] = set()
        # 启用 cookie 跟踪，以维持登录 session
        self._http = httpx.AsyncClient(
            base_url=self._base,
            timeout=httpx.Timeout(15.0),
            headers=_HEADERS,
            cookies=httpx.Cookies(),  # 启用 cookie 支持
        )
        self._logged_in = False
        # 歌曲元数据缓存：上游 TSMusicBot 入队 QQ 音乐时会丢失 name/coverUrl/duration，
        # 在搜索 / play / add 时缓存完整元数据，get_queue / 状态查询时回填缺失字段
        # （key="platform:id"）。per-user 实例，缓存随用户隔离。
        self._meta_cache: dict[str, dict] = {}
        # bot TS 昵称缓存：GET /api/bot/{id}/config 取 nickname（列表 name 是实例名≠TS 昵称）
        self._bot_nickname_cache: dict[str, str] = {}
        # 播放跟随开关（per-client 内存缓存；None=未加载，property 默认开）
        self._follow_enabled: bool | None = None

    async def _ensure_login(self) -> None:
        """确保已登录（幂等）。"""
        if self._logged_in:
            return
        try:
            resp = await self._http.post(
                "/api/session/login",
                json={"username": self._user, "password": self._pass},
            )
            if resp.status_code == 200:
                self._logged_in = True
                logger.info("TSMusicBot 登录成功: %s", self._user)
            else:
                logger.warning("TSMusicBot 登录失败: %s", resp.text[:100])
        except httpx.HTTPError as exc:
            logger.warning("TSMusicBot 连接失败: %s", exc)

    async def close(self) -> None:
        await self._http.aclose()

    @property
    def bot_id(self) -> str:
        return self._bot_id

    @property
    def state_store(self) -> BotPlayerStateStore | None:
        return self._state_store

    @staticmethod
    def _json(resp: httpx.Response) -> dict:
        """安全解析响应 JSON：非 JSON / 空响应返回 {}，避免向上抛 ValueError。"""
        try:
            data = resp.json()
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {"data": data}

    @staticmethod
    def _extract_list(data: dict, key: str) -> list[dict]:
        """兼容 {data:{key:[...]}} 包裹与裸 {key:[...]} 两种响应，提取列表。"""
        if not isinstance(data, dict):
            return []
        items = data.get("data", {}).get(key, data.get(key, []))
        return items if isinstance(items, list) else []

    def _bid(self, bot_id: str | None) -> str:
        """解析 bot_id：默认回退 + 格式校验（UUID hex+连字符；防路径注入，非法回退默认并告警）。"""
        raw = bot_id if bot_id else self._bot_id
        if not re.fullmatch(r"[0-9a-fA-F-]{1,64}", raw or ""):
            logger.warning("非法 bot_id 回退默认: %s", (raw or "")[:32])
            return self._bot_id
        return raw

    # ───────────────────────── 元数据缓存 ─────────────────────────

    # 应用级单例缓存上限（FIFO 淘汰）：搜索结果写入放大，需防止内存无界增长
    _META_CACHE_MAX = 1024

    @staticmethod
    def _norm_platform(platform: str | None) -> str:
        """归一化平台标识（小写），消除上游 / 前端大小写差异导致的 key 不匹配。"""
        return (platform or "").strip().lower()

    def _meta_key(self, platform: str | None, song_id: str) -> str:
        # platform 缺失时用 "unknown" 隔离，避免与真实平台命名空间混淆 / 跨平台污染
        plat = self._norm_platform(platform)
        return f"{plat or 'unknown'}:{song_id}"

    def _cache_meta(self, song: dict, platform: str | None) -> None:
        """缓存歌曲元数据，供 get_queue 回填上游丢失的字段（QQ 入队 name/coverUrl 为空）。"""
        if not isinstance(song, dict):
            return
        sid = str(song.get("id") or "")
        if not sid:
            return
        meta = {
            k: song[k]
            for k in ("name", "artist", "album", "duration", "coverUrl")
            if song.get(k)
        }
        # vip 单独处理：False 是合法值（明确「非 VIP」），不能用真值判断跳过，
        # 否则 vip=False 会被丢弃，队列 / 正在播放无法回填「非 VIP」标记
        if "vip" in song and song["vip"] is not None:
            meta["vip"] = bool(song["vip"])
        if not meta:
            return
        key = self._meta_key(song.get("platform") or platform, sid)
        if key not in self._meta_cache and len(self._meta_cache) >= self._META_CACHE_MAX:
            # FIFO 淘汰最早的（dict 按插入序保序）
            self._meta_cache.pop(next(iter(self._meta_cache)))
        self._meta_cache[key] = meta

    def _enrich(self, item: dict) -> dict:
        """用本地缓存回填队列 / 当前播放项缺失的元数据（仅补空字段，不覆盖已有值）。"""
        if not isinstance(item, dict) or not item:
            return item
        sid = str(item.get("id") or "")
        if not sid:
            return item
        cached = self._meta_cache.get(self._meta_key(item.get("platform"), sid))
        if not cached:
            return item
        enriched = dict(item)
        for k, v in cached.items():
            if k == "vip":
                # vip=False 是合法值：仅当目标缺失 vip 时回填，不覆盖已有 False/True
                if "vip" not in enriched:
                    enriched[k] = v
            elif not enriched.get(k):
                enriched[k] = v
        return enriched

    # ───────────────────────── 播放状态持久化 ─────────────────────────

    async def _checked_player_snapshot(self, bot_id: str) -> tuple[int, list[dict]]:
        """严格读取音量和队列；任一请求失败都不覆盖已有快照。"""
        status_resp = await self._http.get(f"/api/bot/{bot_id}")
        status_resp.raise_for_status()
        status = self._json(status_resp)
        if not status.get("id") or "volume" not in status:
            raise ValueError("invalid bot status response")

        queue_resp = await self._http.get(f"/api/player/{bot_id}/queue")
        queue_resp.raise_for_status()
        data = self._json(queue_resp)
        raw_queue = data.get("queue", data.get("data", {}).get("queue"))
        if not isinstance(raw_queue, list):
            raise ValueError("invalid bot queue response")
        queue = [self._enrich(item) for item in raw_queue if isinstance(item, dict)]
        return max(0, min(100, int(status["volume"]))), queue

    async def persist_player_state(self, bot_id: str | None = None) -> bool:
        """把当前 Bot 音量和队列写入 SQLite；失败不影响播放控制。"""
        if self._state_store is None:
            return False
        bid = self._bid(bot_id)
        if not bid:
            return False
        lock = self._state_locks.setdefault(bid, asyncio.Lock())
        try:
            async with lock:
                volume, queue = await self._checked_player_snapshot(bid)
                await self._state_store.save(bid, volume, queue)
            return True
        except Exception:
            logger.warning("Bot %s 播放状态持久化失败，保留上次快照", bid, exc_info=True)
            return False

    def mark_player_disconnected(self, bot_id: str) -> None:
        """让下一次启动/播放先执行持久化状态恢复。"""
        self._restored_bot_ids.discard(bot_id)

    async def ensure_player_ready(self, bot_id: str | None = None) -> None:
        """播放操作前确保离线 Bot 已启动，并且本轮连接只恢复一次状态。"""
        if self._state_store is None:
            return
        bid = self._bid(bot_id)
        if not bid:
            return
        lock = self._startup_locks.setdefault(bid, asyncio.Lock())
        async with lock:
            try:
                status_resp = await self._http.get(f"/api/bot/{bid}")
                status_resp.raise_for_status()
                status = self._json(status_resp)
                connected = bool(status.get("connected") or status.get("online"))
                if not connected:
                    self.mark_player_disconnected(bid)
                    start_resp = await self._http.post(f"/api/bot/{bid}/start")
                    start_resp.raise_for_status()
                    if self._json(start_resp).get("error"):
                        return
                if bid not in self._restored_bot_ids:
                    await self.restore_player_state(bid)
            except (httpx.HTTPError, ValueError):
                # 保持原有降级行为：预启动失败时仍让实际播放命令交给上游处理。
                logger.warning("Bot %s 播放前启动/恢复失败", bid, exc_info=True)

    async def restore_player_state(self, bot_id: str | None = None) -> dict:
        """Bot 上线后恢复持久化音量和队列，已有运行队列时不重复添加。"""
        if self._state_store is None:
            return {"restored": False, "reason": "store_disabled"}
        bid = self._bid(bot_id)
        if not bid:
            return {"restored": False, "reason": "bot_id_missing"}
        try:
            saved = await self._state_store.load(bid)
        except Exception:
            logger.warning("Bot %s 播放状态快照读取失败", bid, exc_info=True)
            return {"restored": False, "reason": "snapshot_read_failed"}
        if saved is None:
            self._restored_bot_ids.add(bid)
            return {"restored": False, "reason": "snapshot_missing"}

        lock = self._state_locks.setdefault(bid, asyncio.Lock())
        try:
            async with lock:
                # start API 可能在 TS client 完全就绪前返回，最多等待约 5 秒。
                for attempt in range(10):
                    resp = await self._http.get(f"/api/bot/{bid}")
                    resp.raise_for_status()
                    bot = self._json(resp)
                    if bot.get("connected") or bot.get("online"):
                        break
                    if attempt < 9:
                        await asyncio.sleep(0.5)
                else:
                    return {"restored": False, "reason": "bot_not_connected"}

                queue_resp = await self._http.get(f"/api/player/{bid}/queue")
                queue_resp.raise_for_status()
                queue_data = self._json(queue_resp)
                current_queue = queue_data.get(
                    "queue", queue_data.get("data", {}).get("queue")
                )
                if not isinstance(current_queue, list):
                    raise ValueError("invalid bot queue response")

                volume_resp = await self._http.post(
                    f"/api/player/{bid}/volume", json={"volume": saved["volume"]}
                )
                volume_resp.raise_for_status()

                restored_count = 0
                if not current_queue:
                    for song in saved["queue"]:
                        song_id = str(song.get("id") or "").strip()
                        if not song_id:
                            continue
                        payload: dict[str, str] = {"query": f"id:{song_id}"}
                        platform = str(song.get("platform") or "").strip()
                        if platform:
                            payload["platform"] = platform
                        add_resp = await self._http.post(
                            f"/api/player/{bid}/add", json=payload
                        )
                        add_resp.raise_for_status()
                        add_result = self._json(add_resp)
                        if add_result.get("error"):
                            logger.warning(
                                "Bot %s 恢复队列歌曲 %s 失败: %s",
                                bid,
                                song_id,
                                add_result.get("error"),
                            )
                            continue
                        self._cache_meta(song, platform or None)
                        restored_count += 1

                logger.info(
                    "Bot %s 播放状态恢复完成: volume=%s, queue=%s%s",
                    bid,
                    saved["volume"],
                    restored_count,
                    " (保留现有队列)" if current_queue else "",
                )
                self._restored_bot_ids.add(bid)
                return {
                    "restored": True,
                    "volume": saved["volume"],
                    "queue": restored_count,
                    "keptExistingQueue": bool(current_queue),
                }
        except Exception:
            logger.warning("Bot %s 播放状态恢复失败", bid, exc_info=True)
            return {"restored": False, "reason": "restore_failed"}

    async def _persist_after(self, result: dict, bot_id: str | None) -> dict:
        if not result.get("error"):
            await self.persist_player_state(bot_id)
        return result

    # ───────────────────────── 搜索 ─────────────────────────

    async def search(self, q: str, platform: str | None = None, bot_id: str | None = None) -> list[dict]:
        """搜索歌曲，返回 [{id, name, artist, album, duration, coverUrl, platform}]。

        platform 指定音源平台：netease（默认）/ qq / bilibili。
        bot_id 指定 bot 实例 → 上游用该 bot 的平台 cookie 搜索（per-bot 平台账号）。
        B 站结果的 id 即 BV 号，可直接用于 play("id:<BV号>")。
        """
        await self._ensure_login()
        try:
            params: dict[str, str] = {"q": q}
            if platform:
                params["platform"] = platform
            if bot_id:
                params["botId"] = bot_id
            resp = await self._http.get("/api/music/search", params=params)
            data = resp.json()
            songs = data.get("data", {}).get("songs", data.get("songs", []))
            if isinstance(songs, list):
                # 缓存搜索结果元数据，使后续入队 / 队列展示能回填（QQ 入队丢字段）
                for s in songs:
                    self._cache_meta(s, platform)
                return songs
            return []
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("TSMusicBot 搜索失败: %s", exc)
            return []

    # ───────────────────────── 播放控制 ─────────────────────────

    async def play(self, query: str, platform: str | None = None, meta: dict | None = None, bot_id: str | None = None) -> dict:
        """播放（query 可以是歌名或 'id:xxx'，platform 指定音源，bot_id 指定 bot 实例）。"""
        await self._ensure_login()
        bid = self._bid(bot_id)
        await self.ensure_player_ready(bid)
        payload: dict = {"query": query}
        if platform:
            payload["platform"] = platform
        resp = await self._http.post(
            f"/api/player/{bid}/play", json=payload
        )
        if meta:
            self._cache_meta(meta, platform)
        return await self._persist_after(self._json(resp), bid)

    async def add(self, query: str, platform: str | None = None, meta: dict | None = None, bot_id: str | None = None) -> dict:
        """加入队列。meta 为前端传入的元数据，缓存后回填上游丢失的字段。"""
        await self._ensure_login()
        bid = self._bid(bot_id)
        await self.ensure_player_ready(bid)
        payload: dict = {"query": query}
        if platform:
            payload["platform"] = platform
        resp = await self._http.post(
            f"/api/player/{bid}/add", json=payload
        )
        if meta:
            self._cache_meta(meta, platform)
        return await self._persist_after(self._json(resp), bid)

    async def pause(self, bot_id: str | None = None) -> dict:
        await self._ensure_login()
        resp = await self._http.post(f"/api/player/{self._bid(bot_id)}/pause")
        return self._json(resp)

    async def resume(self, bot_id: str | None = None) -> dict:
        await self._ensure_login()
        bid = self._bid(bot_id)
        await self.ensure_player_ready(bid)
        resp = await self._http.post(f"/api/player/{bid}/resume")
        return self._json(resp)

    async def next(self, bot_id: str | None = None) -> dict:
        await self._ensure_login()
        bid = self._bid(bot_id)
        await self.ensure_player_ready(bid)
        resp = await self._http.post(f"/api/player/{bid}/next")
        return await self._persist_after(self._json(resp), bid)

    async def stop(self, bot_id: str | None = None) -> dict:
        await self._ensure_login()
        bid = self._bid(bot_id)
        resp = await self._http.post(f"/api/player/{bid}/stop")
        return await self._persist_after(self._json(resp), bid)

    async def seek(self, position: int, bot_id: str | None = None) -> dict:
        await self._ensure_login()
        resp = await self._http.post(
            f"/api/player/{self._bid(bot_id)}/seek", json={"position": position}
        )
        return self._json(resp)

    async def set_volume(self, volume: int, bot_id: str | None = None) -> dict:
        await self._ensure_login()
        bid = self._bid(bot_id)
        resp = await self._http.post(
            f"/api/player/{bid}/volume", json={"volume": volume}
        )
        return await self._persist_after(self._json(resp), bid)

    async def set_mode(self, mode: str, bot_id: str | None = None) -> dict:
        """mode: seq | loop | random | rloop。"""
        await self._ensure_login()
        resp = await self._http.post(
            f"/api/player/{self._bid(bot_id)}/mode", json={"mode": mode}
        )
        return self._json(resp)

    async def clear(self, bot_id: str | None = None) -> dict:
        await self._ensure_login()
        bid = self._bid(bot_id)
        resp = await self._http.post(f"/api/player/{bid}/clear")
        return await self._persist_after(self._json(resp), bid)

    async def remove_from_queue(self, index: int, bot_id: str | None = None) -> dict:
        """按队列索引移除单曲。前端传 0-based 数组索引；上游 !remove 为 1-based（N=1 即第一首），故 +1。"""
        await self._ensure_login()
        bid = self._bid(bot_id)
        resp = await self._http.delete(f"/api/player/{bid}/queue/{index + 1}")
        return await self._persist_after(self._json(resp), bid)

    async def play_at(self, index: int, bot_id: str | None = None) -> dict:
        """跳转到队列指定位置播放（不清空队列）。上游 play-at 用 0-based 数组索引，与前端一致，无需转换。"""
        await self._ensure_login()
        bid = self._bid(bot_id)
        await self.ensure_player_ready(bid)
        resp = await self._http.post(f"/api/player/{bid}/play-at", json={"index": index})
        return await self._persist_after(self._json(resp), bid)

    async def move_queue_item(self, from_idx: int, to_idx: int, bot_id: str | None = None) -> dict:
        """拖动调序：移动队列项到新位置（上游 POST /queue/:from/move {to}）。"""
        await self._ensure_login()
        bid = self._bid(bot_id)
        resp = await self._http.post(
            f"/api/player/{bid}/queue/{from_idx}/move", json={"to": to_idx}
        )
        return await self._persist_after(self._json(resp), bid)

    # ───────────────────────── 状态 ─────────────────────────

    async def get_bot_status(self, bot_id: str | None = None) -> dict:
        """获取指定 bot 状态（含当前播放 + 音量）。

        用详情端点 /api/bot/{id} 而非列表 /api/bot —— 列表的 playing/queueSize 字段
        不实时（常驻 False/0），详情端点才反映真实播放状态。
        """
        await self._ensure_login()
        try:
            bid = self._bid(bot_id)
            resp = await self._http.get(f"/api/bot/{bid}")
            bot = resp.json()
            if not isinstance(bot, dict) or not bot.get("id"):
                return {}
            cs = self._enrich(bot.get("currentSong") or {})
            return {
                "playing": bot.get("playing", False),
                "paused": bot.get("paused", False),
                "volume": bot.get("volume", 50),
                "playMode": bot.get("playMode", "seq"),
                "elapsed": bot.get("elapsed", 0),
                "queueSize": bot.get("queueSize", 0),
                # 当前曲 id：前端用它 + platform 精确匹配队列中的当前项（歌名匹配会误判同名/翻唱）
                "songId": str(cs.get("id") or ""),
                "title": cs.get("name", ""),
                "artist": cs.get("artist", ""),
                "album": cs.get("album", ""),
                "duration": cs.get("duration", 0),
                # 实际播放时长：试听片段=试听秒数，完整=duration；上游未暴露时回退 duration
                "effectiveDuration": bot.get("effectiveDuration") or cs.get("duration", 0),
                "position": bot.get("elapsed", 0),
                "cover": cs.get("coverUrl", ""),
                "platform": cs.get("platform", ""),
                # vip 来自搜索 / 详情时缓存的元数据回填（currentSong 本身不带 vip）
                "vip": cs.get("vip"),
            }
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("TSMusicBot 状态获取失败: %s", exc)
        return {}

    async def get_queue(self, bot_id: str | None = None) -> list[dict]:
        """获取播放队列。"""
        await self._ensure_login()
        try:
            resp = await self._http.get(f"/api/player/{self._bid(bot_id)}/queue")
            data = resp.json()
            q = data.get("queue", data.get("data", {}).get("queue", []))
            if isinstance(q, list):
                return [self._enrich(item) for item in q]
            return []
        except (httpx.HTTPError, ValueError):
            return []

    # ───────────────────────── bot 实例管理 ─────────────────────────

    def _map_bot(self, b: dict) -> dict:
        """上游 bot dict → 前端 BotInfo {id,name,status,playing,paused,default}。"""
        connected = bool(b.get("connected") or b.get("online"))
        return {
            "id": str(b.get("id") or ""),
            "name": str(b.get("name") or ""),
            "status": "connected" if connected else "offline",
            "playing": bool(b.get("playing")),
            "paused": bool(b.get("paused")),
            "default": str(b.get("id") or "") == self._bot_id,
        }

    async def list_bots(self) -> list[dict]:
        """GET /api/bot → 归一化为 BotInfo 列表。"""
        await self._ensure_login()
        try:
            resp = await self._http.get("/api/bot")
            data = resp.json()
            raw = data.get("bots", data.get("data", {}).get("bots", []))
            return [self._map_bot(b) for b in raw if isinstance(b, dict)]
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("TSMusicBot list_bots 失败: %s", exc)
            return []

    async def list_bots_checked(self) -> list[dict]:
        """严格读取 bot 列表，供后台任务区分“确实为空”和“查询失败”。

        面向 UI 的 :meth:`list_bots` 为了优雅降级会在网络/解析失败时返回空
        列表；空闲管理器不能使用该语义，否则一次瞬时故障就会被误判为没有
        在线 bot，并清空所有正在进行的空闲计时。
        """
        await self._ensure_login()
        resp = await self._http.get("/api/bot")
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("TSMusicBot bot list response is not an object")
        raw = data.get("bots", data.get("data", {}).get("bots", []))
        if not isinstance(raw, list):
            raise ValueError("TSMusicBot bot list response has no bots array")
        return [self._map_bot(b) for b in raw if isinstance(b, dict)]

    async def create_bot(self, payload: dict) -> dict:
        """POST /api/bot → 创建 bot（identity 自动生成，不自动连接）。"""
        await self._ensure_login()
        resp = await self._http.post("/api/bot", json=payload)
        return self._json(resp)

    async def update_bot(self, bot_id: str, payload: dict) -> dict:
        """PUT /api/bot/:id → 更新 bot 配置（连接类字段需先停止 bot 再改才生效）。"""
        await self._ensure_login()
        resp = await self._http.put(f"/api/bot/{bot_id}", json=payload)
        if "nickname" in payload:
            self._bot_nickname_cache.pop(bot_id, None)
        return self._json(resp)

    async def start_bot(self, bot_id: str) -> dict:
        """POST /api/bot/:id/start → 连接 TS（首次生成并持久化 identity）。"""
        await self._ensure_login()
        resp = await self._http.post(f"/api/bot/{bot_id}/start")
        result = self._json(resp)
        if not result.get("error"):
            self.mark_player_disconnected(bot_id)
            result["playerState"] = await self.restore_player_state(bot_id)
        return result

    async def stop_bot(self, bot_id: str) -> dict:
        await self._ensure_login()
        await self.persist_player_state(bot_id)
        resp = await self._http.post(f"/api/bot/{bot_id}/stop")
        result = self._json(resp)
        if not result.get("error"):
            self.mark_player_disconnected(bot_id)
        return result

    async def stop_bot_checked(self, bot_id: str) -> dict:
        """停止 bot，且将上游非 2xx 响应视为失败。"""
        await self._ensure_login()
        await self.persist_player_state(bot_id)
        resp = await self._http.post(f"/api/bot/{bot_id}/stop")
        resp.raise_for_status()
        result = self._json(resp)
        self.mark_player_disconnected(bot_id)
        return result

    async def delete_bot(self, bot_id: str) -> dict:
        await self._ensure_login()
        resp = await self._http.delete(f"/api/bot/{bot_id}")
        result = self._json(resp)
        if self._state_store is not None and not result.get("error"):
            await self._state_store.delete(bot_id)
        return result

    # ───────────────────────── bot 行为 / 外观设置 ─────────────────────────

    # per-bot ProfileConfig 白名单字段（与上游 database.ts 一致；默认全开）
    _PROFILE_KEYS = (
        "avatarEnabled", "descriptionEnabled", "nicknameEnabled",
        "awayStatusEnabled", "channelDescEnabled", "nowPlayingMsgEnabled",
    )

    async def get_bot_settings(self) -> dict:
        """全局 bot 行为设置：空闲下线分钟 + 空频道自动暂停。

        仅回传这两项；guestMode / adminGroups 属上游自身权限体系，PowerfulTS 不代理。
        """
        await self._ensure_login()
        try:
            data = self._json(await self._http.get("/api/bot/settings"))
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("TSMusicBot 读取 bot 设置失败: %s", exc)
            return {"idleTimeoutMinutes": 0, "autoPauseOnEmpty": False}
        return {
            "idleTimeoutMinutes": data.get("idleTimeoutMinutes", 0),
            "autoPauseOnEmpty": bool(data.get("autoPauseOnEmpty", False)),
        }

    async def get_bot_settings_checked(self) -> dict:
        """严格读取空闲设置，避免读取失败被静默降级为“功能已关闭”。"""
        await self._ensure_login()
        resp = await self._http.get("/api/bot/settings")
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("TSMusicBot settings response is not an object")
        return {
            "idleTimeoutMinutes": data.get("idleTimeoutMinutes", 0),
            "autoPauseOnEmpty": bool(data.get("autoPauseOnEmpty", False)),
        }

    async def set_bot_settings(
        self,
        idle_timeout_minutes: int | None = None,
        auto_pause_on_empty: bool | None = None,
    ) -> dict:
        """更新全局 bot 行为设置（仅透传非 None 字段，未传项上游保持不变）。"""
        await self._ensure_login()
        payload: dict = {}
        if idle_timeout_minutes is not None:
            payload["idleTimeoutMinutes"] = idle_timeout_minutes
        if auto_pause_on_empty is not None:
            payload["autoPauseOnEmpty"] = auto_pause_on_empty
        if not payload:
            return await self.get_bot_settings()
        data = self._json(await self._http.post("/api/bot/settings", json=payload))
        return {
            "idleTimeoutMinutes": data.get("idleTimeoutMinutes", 0),
            "autoPauseOnEmpty": bool(data.get("autoPauseOnEmpty", False)),
        }

    async def get_bot_profile(self, bot_id: str | None = None) -> dict:
        """per-bot profile 开关（6 字段，缺失默认 True，对齐上游 DEFAULT_PROFILE_CONFIG）。"""
        await self._ensure_login()
        bid = self._bid(bot_id)
        try:
            data = self._json(await self._http.get(f"/api/bot/{bid}/profile"))
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("TSMusicBot 读取 profile 失败: %s", exc)
            return {k: True for k in self._PROFILE_KEYS}
        return {k: bool(data.get(k, True)) for k in self._PROFILE_KEYS}

    async def set_bot_profile(self, partial: dict, bot_id: str | None = None) -> dict:
        """更新 per-bot profile 开关（仅透传白名单内且为 bool 的字段）。"""
        await self._ensure_login()
        bid = self._bid(bot_id)
        payload = {
            k: bool(partial[k])
            for k in self._PROFILE_KEYS
            if isinstance(partial.get(k), bool)
        }
        data = self._json(await self._http.put(f"/api/bot/{bid}/profile", json=payload))
        return {k: bool(data.get(k, True)) for k in self._PROFILE_KEYS}

    async def get_bot_avatar(self, bot_id: str | None = None) -> httpx.Response:
        """获取 bot 固定头像（二进制）。返回原始 Response 供 router 透传字节与 Content-Type。"""
        await self._ensure_login()
        return await self._http.get(f"/api/bot/{self._bid(bot_id)}/avatar")

    async def set_bot_avatar(self, data_url: str, bot_id: str | None = None) -> dict:
        """上传/替换 bot 固定头像（data:image/(png|jpeg|webp);base64,...）。

        上游对超大/格式非法返回 413/400，_json 不抛；这里把 status 透出（_status），
        供 router 转成对应 HTTPException。
        """
        await self._ensure_login()
        resp = await self._http.put(
            f"/api/bot/{self._bid(bot_id)}/avatar", json={"dataUrl": data_url}
        )
        data = self._json(resp)
        if resp.status_code >= 400:
            data["_status"] = resp.status_code
        return data

    async def delete_bot_avatar(self, bot_id: str | None = None) -> None:
        """移除 bot 固定头像。"""
        await self._ensure_login()
        await self._http.delete(f"/api/bot/{self._bid(bot_id)}/avatar")

    # ───────────────────────── 平台账号登录 ─────────────────────────

    async def get_auth_status(self, platform: str, bot_id: str | None = None) -> dict:
        await self._ensure_login()
        try:
            params: dict[str, str] = {"platform": platform}
            if bot_id:
                params["botId"] = bot_id
            resp = await self._http.get("/api/auth/status", params=params)
            return resp.json()
        except (httpx.HTTPError, ValueError):
            return {"platform": platform, "loggedIn": False}

    async def get_qrcode_status(self, key: str, platform: str, bot_id: str | None = None) -> dict:
        """轮询二维码扫码状态。fork 在 confirmed 时自动持久化平台 cookie。
        返回 {status: waiting|scanned|confirmed|expired}。"""
        await self._ensure_login()
        try:
            params: dict[str, str] = {"key": key, "platform": platform}
            if bot_id:
                params["botId"] = bot_id
            resp = await self._http.get("/api/auth/qrcode/status", params=params)
            return resp.json()
        except (httpx.HTTPError, ValueError):
            return {"status": "waiting"}

    async def get_qrcode(self, platform: str, bot_id: str | None = None) -> dict:
        await self._ensure_login()
        payload: dict = {"platform": platform}
        if bot_id:
            payload["botId"] = bot_id
        resp = await self._http.post("/api/auth/qrcode", json=payload)
        return self._json(resp)

    async def set_cookie(self, platform: str, cookie: str, bot_id: str | None = None) -> dict:
        await self._ensure_login()
        payload: dict = {"platform": platform, "cookie": cookie}
        if bot_id:
            payload["botId"] = bot_id
        resp = await self._http.post("/api/auth/cookie", json=payload)
        return self._json(resp)

    async def delete_cookie(self, platform: str, bot_id: str | None = None) -> dict:
        """退出某平台登录：清除该 bot 的平台 cookie。"""
        await self._ensure_login()
        params: dict[str, str] = {"platform": platform}
        if bot_id:
            params["botId"] = bot_id
        resp = await self._http.delete("/api/auth/cookie", params=params)
        return self._json(resp)

    # ───────────────────────── 我的音乐 / 歌单 ─────────────────────────

    async def _fetch_list(
        self,
        path: str,
        key: str,
        platform: str | None = None,
        params: dict[str, str] | None = None,
        cache_meta: bool = False,
        bot_id: str | None = None,
    ) -> dict:
        """统一代理 TSMusicBot 列表端点，返回 {ok, unsupported, data, error}。

        - 上游 501 → unsupported=True（该平台不支持此功能，如 B 站的歌单 / 每日推荐）
        - 正常 → data 为列表；cache_meta 时缓存每项元数据供队列回填
        - bot_id → 上游用该 bot 的平台 cookie（per-bot 平台账号）
        - 异常 → ok=False
        """
        await self._ensure_login()
        try:
            q: dict[str, str] = dict(params or {})
            if platform:
                q["platform"] = platform
            if bot_id:
                q["botId"] = bot_id
            resp = await self._http.get(path, params=q)
            if resp.status_code == 501:
                return {"ok": False, "unsupported": True, "data": [], "error": "not supported"}
            if resp.status_code >= 400:
                return {"ok": False, "unsupported": False, "data": [], "error": f"upstream {resp.status_code}"}
            data = self._json(resp)
            items = self._extract_list(data, key)
            if cache_meta:
                for s in items:
                    self._cache_meta(s, platform)
            return {"ok": True, "unsupported": False, "data": items}
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("TSMusicBot %s 失败: %s", path, exc)
            return {"ok": False, "unsupported": False, "data": [], "error": str(exc)}

    async def user_playlists(self, platform: str, bot_id: str | None = None) -> dict:
        """用户歌单（自建 + 收藏，per-bot）。网易云/QQ 为歌单，B 站为收藏夹列表（需登录）。"""
        return await self._fetch_list("/api/music/user/playlists", "playlists", platform, bot_id=bot_id)

    async def playlist_songs(self, playlist_id: str, platform: str | None = None, bot_id: str | None = None) -> dict:
        """歌单内歌曲（per-bot；缓存元数据，供入队后队列回填）。B 站时 playlist_id 为收藏夹 id，返回夹内视频。"""
        return await self._fetch_list(
            f"/api/music/playlist/{playlist_id}", "songs", platform, cache_meta=True, bot_id=bot_id
        )

    async def recommend_songs(self, platform: str, bot_id: str | None = None) -> dict:
        """每日推荐（per-bot）。B 站上游不支持。"""
        return await self._fetch_list(
            "/api/music/recommend/songs", "songs", platform, cache_meta=True, bot_id=bot_id
        )

    async def personal_fm(self, platform: str, bot_id: str | None = None) -> dict:
        """私人 FM（per-bot）。B 站上游不支持。"""
        return await self._fetch_list(
            "/api/music/personal/fm", "songs", platform, cache_meta=True, bot_id=bot_id
        )

    async def bilibili_popular(self, limit: int = 20, bot_id: str | None = None) -> dict:
        """B 站热门视频（无需登录，per-bot）。"""
        return await self._fetch_list(
            "/api/music/bilibili/popular", "songs",
            params={"limit": str(limit)}, cache_meta=True, bot_id=bot_id,
        )

    async def enqueue_songs(self, songs: list[dict], platform: str | None = None, bot_id: str | None = None) -> dict:
        """批量入队（循环 add + 并发上限 + 失败容忍），供前端「整单播放」。"""
        await self._ensure_login()
        target = list(songs)[:50]  # 上限保护，避免超大歌单打爆队列
        if not target:
            return {"ok": True, "enqueued": 0, "failed": 0}

        bid = self._bid(bot_id)
        await self.ensure_player_ready(bid)
        sem = asyncio.Semaphore(4)  # 并发上限，避免打爆上游

        async def _one(song: dict) -> bool:
            sid = str(song.get("id") or "")
            if not sid:
                return False
            payload: dict = {"query": f"id:{sid}"}
            if platform:
                payload["platform"] = platform
            async with sem:
                try:
                    # 直接判定上游状态码（self.add 不抛异常，无法靠 except 判定业务失败）
                    resp = await self._http.post(
                        f"/api/player/{bid}/add", json=payload
                    )
                    if resp.status_code >= 400:
                        return False
                    self._cache_meta(song, platform)
                    return True
                except (httpx.HTTPError, ValueError):
                    return False

        results = await asyncio.gather(*(_one(s) for s in target))
        ok_count = sum(1 for r in results if r)
        if ok_count:
            await self.persist_player_state(bid)
        return {"ok": True, "enqueued": ok_count, "failed": len(target) - ok_count}

    # ───────────────────────── 播放跟随 ─────────────────────────

    @property
    def follow_enabled(self) -> bool:
        """播放跟随开关（未加载时默认开启）。"""
        return self._follow_enabled if self._follow_enabled is not None else True

    async def load_follow_setting(self, session: AsyncSession) -> bool:
        """从 KV 加载跟随开关到内存缓存（缺失默认开启）。"""
        raw = await app_setting.get_setting(session, "follow_enabled", "1")
        self._follow_enabled = raw.strip().lower() not in ("0", "false", "no", "off")
        return self._follow_enabled

    async def set_follow_setting(self, session: AsyncSession, enabled: bool) -> None:
        """持久化跟随开关并刷新内存缓存。"""
        await app_setting.set_setting(session, "follow_enabled", "1" if enabled else "0")
        self._follow_enabled = enabled

    async def get_bot_config(self, bot_id: str) -> dict:
        """GET /api/bot/:id/config → bot 配置（编辑表单预填用；上游已排除 identity/apiKey）。"""
        await self._ensure_login()
        resp = await self._http.get(f"/api/bot/{bot_id}/config")
        return self._json(resp)

    async def get_bot_nickname(self, bot_id: str | None = None, *, refresh: bool = False) -> str | None:
        """获取 bot 的 TS 昵称（供 bot_mover 在 clientlist 中定位 bot client）。

        GET /api/bot/{id}/config 返回移除 identity/apiKey 后的 bot 配置，含 nickname。
        默认使用缓存；refresh=True 时强制重新读取，供跟随失败后的自愈重试。
        """
        bid = self._bid(bot_id)
        cached = None if refresh else self._bot_nickname_cache.get(bid)
        if cached:
            return cached
        await self._ensure_login()
        try:
            resp = await self._http.get(f"/api/bot/{bid}/config")
            if resp.status_code >= 400:
                logger.warning("获取 bot 昵称失败: 上游 %s", resp.status_code)
                return None
            nick = str(self._json(resp).get("nickname") or "").strip()
        except httpx.HTTPError as exc:
            logger.warning("获取 bot 昵称异常: %s", exc)
            return None
        if nick:
            self._bot_nickname_cache[bid] = nick
        return nick or None

    # ───────────────────────── 音质设置 ─────────────────────────

    async def get_quality(self, bot_id: str | None = None) -> dict:
        """获取指定 bot 的当前音质配置。"""
        await self._ensure_login()
        try:
            resp = await self._http.get(
                "/api/music/quality",
                params={"botId": self._bid(bot_id)},
            )
            return self._json(resp)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("获取音质失败: %s", exc)
            return {}

    async def set_quality(
        self,
        quality: str,
        platform: str | None = None,
        bot_id: str | None = None,
    ) -> dict:
        """设置指定 bot 的音质（platform 指定平台，未传则所有平台）。

        Args:
            quality: 音质级别，如 standard/higher/exhigh/lossless/hires 等
            platform: 平台标识（netease/qq/bilibili/kugou），None 表示全局设置
            bot_id: bot 实例 ID
        """
        await self._ensure_login()
        try:
            # 各平台使用自己的原生音质值。保留旧版 UI 曾发送的通用别名，
            # 但转发给上游时必须归一化，否则 QQ 会静默回退 128k。
            if platform not in _QUALITY_POLICY:
                return {"error": "unsupported platform", "_status": 400}
            normalized = _QUALITY_ALIASES.get(platform, {}).get(quality, quality)
            if normalized not in _QUALITY_POLICY[platform]:
                return {
                    "error": f"unsupported quality for {platform}",
                    "_status": 400,
                }
            bid = self._bid(bot_id)
            if _QUALITY_POLICY[platform][normalized]:
                status = await self.get_auth_status(platform, bot_id=bid)
                if not status.get("loggedIn") or status.get("vip") is not True:
                    return {
                        "error": "该音质需要已验证且有效的 VIP 会员",
                        "_status": 403,
                    }
            payload = {"quality": normalized, "botId": bid, "platform": platform}
            resp = await self._http.post("/api/music/quality", json=payload)
            data = self._json(resp)
            if resp.status_code >= 400:
                data["_status"] = resp.status_code
            return data
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("设置音质失败: %s", exc)
            return {"error": str(exc)}
