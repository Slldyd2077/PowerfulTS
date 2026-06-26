"""TSMusicBot API 代理客户端。

PowerfulTS 后端登录 TSMusicBot（:3000），持有 session cookie，
代理所有音乐 API。用户只与 PowerfulTS 交互，看不到 TSMusicBot WebUI。
"""
from __future__ import annotations

import asyncio
import logging
import re

import httpx

from ..core.config import Settings

logger = logging.getLogger(__name__)

# TSMusicBot 需要 Origin header 才允许 API 调用（CSRF 防护）
_HEADERS = {
    "Origin": "http://127.0.0.1:3000",
    "Content-Type": "application/json",
}


class TSMusicClient:
    """TSMusicBot REST API 代理客户端。"""

    def __init__(self, settings: Settings) -> None:
        self._base = settings.tsmusic_url
        self._user = settings.tsmusic_user
        self._pass = settings.tsmusic_password
        self._bot_id = settings.tsmusic_bot_id
        self._http = httpx.AsyncClient(
            base_url=self._base,
            timeout=httpx.Timeout(15.0),
            headers=_HEADERS,
        )
        self._logged_in = False
        # 歌曲元数据缓存：上游 TSMusicBot 入队 QQ 音乐时会丢失 name/coverUrl/duration，
        # 在搜索 / play / add 时缓存完整元数据，get_queue / 状态查询时回填缺失字段
        # （key="platform:id"）。TSMusicClient 为应用级单例，缓存跨请求有效。
        self._meta_cache: dict[str, dict] = {}

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
            if not enriched.get(k):
                enriched[k] = v
        return enriched

    # ───────────────────────── 搜索 ─────────────────────────

    async def search(self, q: str, platform: str | None = None) -> list[dict]:
        """搜索歌曲，返回 [{id, name, artist, album, duration, coverUrl, platform}]。

        platform 指定音源平台：netease（默认）/ qq / bilibili。
        B 站结果的 id 即 BV 号，可直接用于 play("id:<BV号>")。
        """
        await self._ensure_login()
        try:
            params: dict[str, str] = {"q": q}
            if platform:
                params["platform"] = platform
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
        payload: dict = {"query": query}
        if platform:
            payload["platform"] = platform
        resp = await self._http.post(
            f"/api/player/{bid}/play", json=payload
        )
        if meta:
            self._cache_meta(meta, platform)
        return self._json(resp)

    async def add(self, query: str, platform: str | None = None, meta: dict | None = None, bot_id: str | None = None) -> dict:
        """加入队列。meta 为前端传入的元数据，缓存后回填上游丢失的字段。"""
        await self._ensure_login()
        bid = self._bid(bot_id)
        payload: dict = {"query": query}
        if platform:
            payload["platform"] = platform
        resp = await self._http.post(
            f"/api/player/{bid}/add", json=payload
        )
        if meta:
            self._cache_meta(meta, platform)
        return self._json(resp)

    async def pause(self, bot_id: str | None = None) -> dict:
        await self._ensure_login()
        resp = await self._http.post(f"/api/player/{self._bid(bot_id)}/pause")
        return self._json(resp)

    async def resume(self, bot_id: str | None = None) -> dict:
        await self._ensure_login()
        resp = await self._http.post(f"/api/player/{self._bid(bot_id)}/resume")
        return self._json(resp)

    async def next(self, bot_id: str | None = None) -> dict:
        await self._ensure_login()
        resp = await self._http.post(f"/api/player/{self._bid(bot_id)}/next")
        return self._json(resp)

    async def stop(self, bot_id: str | None = None) -> dict:
        await self._ensure_login()
        resp = await self._http.post(f"/api/player/{self._bid(bot_id)}/stop")
        return self._json(resp)

    async def seek(self, position: int, bot_id: str | None = None) -> dict:
        await self._ensure_login()
        resp = await self._http.post(
            f"/api/player/{self._bid(bot_id)}/seek", json={"position": position}
        )
        return self._json(resp)

    async def set_volume(self, volume: int, bot_id: str | None = None) -> dict:
        await self._ensure_login()
        resp = await self._http.post(
            f"/api/player/{self._bid(bot_id)}/volume", json={"volume": volume}
        )
        return self._json(resp)

    async def set_mode(self, mode: str, bot_id: str | None = None) -> dict:
        """mode: seq | loop | random | rloop。"""
        await self._ensure_login()
        resp = await self._http.post(
            f"/api/player/{self._bid(bot_id)}/mode", json={"mode": mode}
        )
        return self._json(resp)

    async def clear(self, bot_id: str | None = None) -> dict:
        await self._ensure_login()
        resp = await self._http.post(f"/api/player/{self._bid(bot_id)}/clear")
        return self._json(resp)

    async def remove_from_queue(self, index: int, bot_id: str | None = None) -> dict:
        """按队列索引移除单曲。前端传 0-based 数组索引；上游 !remove 为 1-based（N=1 即第一首），故 +1。"""
        await self._ensure_login()
        resp = await self._http.delete(f"/api/player/{self._bid(bot_id)}/queue/{index + 1}")
        return self._json(resp)

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
                "position": bot.get("elapsed", 0),
                "cover": cs.get("coverUrl", ""),
                "platform": cs.get("platform", ""),
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

    async def create_bot(self, payload: dict) -> dict:
        """POST /api/bot → 创建 bot（identity 自动生成，不自动连接）。"""
        await self._ensure_login()
        resp = await self._http.post("/api/bot", json=payload)
        return self._json(resp)

    async def start_bot(self, bot_id: str) -> dict:
        """POST /api/bot/:id/start → 连接 TS（首次生成并持久化 identity）。"""
        await self._ensure_login()
        resp = await self._http.post(f"/api/bot/{bot_id}/start")
        return self._json(resp)

    async def stop_bot(self, bot_id: str) -> dict:
        await self._ensure_login()
        resp = await self._http.post(f"/api/bot/{bot_id}/stop")
        return self._json(resp)

    async def delete_bot(self, bot_id: str) -> dict:
        await self._ensure_login()
        resp = await self._http.delete(f"/api/bot/{bot_id}")
        return self._json(resp)

    # ───────────────────────── 平台账号登录 ─────────────────────────

    async def get_auth_status(self, platform: str) -> dict:
        await self._ensure_login()
        try:
            resp = await self._http.get("/api/auth/status", params={"platform": platform})
            return resp.json()
        except (httpx.HTTPError, ValueError):
            return {"platform": platform, "loggedIn": False}

    async def get_qrcode(self, platform: str) -> dict:
        await self._ensure_login()
        resp = await self._http.post("/api/auth/qrcode", json={"platform": platform})
        return self._json(resp)

    async def set_cookie(self, platform: str, cookie: str) -> dict:
        await self._ensure_login()
        resp = await self._http.post("/api/auth/cookie", json={"platform": platform, "cookie": cookie})
        return self._json(resp)

    # ───────────────────────── 我的音乐 / 歌单 ─────────────────────────

    async def _fetch_list(
        self,
        path: str,
        key: str,
        platform: str | None = None,
        params: dict[str, str] | None = None,
        cache_meta: bool = False,
    ) -> dict:
        """统一代理 TSMusicBot 列表端点，返回 {ok, unsupported, data, error}。

        - 上游 501 → unsupported=True（该平台不支持此功能，如 B 站的歌单 / 每日推荐）
        - 正常 → data 为列表；cache_meta 时缓存每项元数据供队列回填
        - 异常 → ok=False
        """
        await self._ensure_login()
        try:
            q: dict[str, str] = dict(params or {})
            if platform:
                q["platform"] = platform
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

    async def user_playlists(self, platform: str) -> dict:
        """用户歌单（自建 + 收藏）。B 站上游不支持 → unsupported=True。"""
        return await self._fetch_list("/api/music/user/playlists", "playlists", platform)

    async def playlist_songs(self, playlist_id: str, platform: str | None = None) -> dict:
        """歌单内歌曲（缓存元数据，供入队后队列回填）。"""
        return await self._fetch_list(
            f"/api/music/playlist/{playlist_id}", "songs", platform, cache_meta=True
        )

    async def recommend_songs(self, platform: str) -> dict:
        """每日推荐。B 站上游不支持。"""
        return await self._fetch_list(
            "/api/music/recommend/songs", "songs", platform, cache_meta=True
        )

    async def personal_fm(self, platform: str) -> dict:
        """私人 FM。B 站上游不支持。"""
        return await self._fetch_list(
            "/api/music/personal/fm", "songs", platform, cache_meta=True
        )

    async def bilibili_popular(self, limit: int = 20) -> dict:
        """B 站热门视频（无需 platform 查询参数 / 无需登录）。"""
        return await self._fetch_list(
            "/api/music/bilibili/popular", "songs",
            params={"limit": str(limit)}, cache_meta=True,
        )

    async def enqueue_songs(self, songs: list[dict], platform: str | None = None, bot_id: str | None = None) -> dict:
        """批量入队（循环 add + 并发上限 + 失败容忍），供前端「整单播放」。"""
        await self._ensure_login()
        target = list(songs)[:50]  # 上限保护，避免超大歌单打爆队列
        if not target:
            return {"ok": True, "enqueued": 0, "failed": 0}

        bid = self._bid(bot_id)
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
        return {"ok": True, "enqueued": ok_count, "failed": len(target) - ok_count}
