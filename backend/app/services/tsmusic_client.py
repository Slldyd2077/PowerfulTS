"""TSMusicBot API 代理客户端。

PowerfulTS 后端登录 TSMusicBot（:3000），持有 session cookie，
代理所有音乐 API。用户只与 PowerfulTS 交互，看不到 TSMusicBot WebUI。
"""
from __future__ import annotations

import logging

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
            return songs if isinstance(songs, list) else []
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("TSMusicBot 搜索失败: %s", exc)
            return []

    # ───────────────────────── 播放控制 ─────────────────────────

    async def play(self, query: str, platform: str | None = None) -> dict:
        """播放（query 可以是歌名或 'id:xxx'，platform 指定音源）。"""
        await self._ensure_login()
        payload: dict = {"query": query}
        if platform:
            payload["platform"] = platform
        resp = await self._http.post(
            f"/api/player/{self._bot_id}/play", json=payload
        )
        return self._json(resp)

    async def add(self, query: str, platform: str | None = None) -> dict:
        """加入队列。"""
        await self._ensure_login()
        payload: dict = {"query": query}
        if platform:
            payload["platform"] = platform
        resp = await self._http.post(
            f"/api/player/{self._bot_id}/add", json=payload
        )
        return self._json(resp)

    async def pause(self) -> dict:
        await self._ensure_login()
        resp = await self._http.post(f"/api/player/{self._bot_id}/pause")
        return self._json(resp)

    async def resume(self) -> dict:
        await self._ensure_login()
        resp = await self._http.post(f"/api/player/{self._bot_id}/resume")
        return self._json(resp)

    async def next(self) -> dict:
        await self._ensure_login()
        resp = await self._http.post(f"/api/player/{self._bot_id}/next")
        return self._json(resp)

    async def stop(self) -> dict:
        await self._ensure_login()
        resp = await self._http.post(f"/api/player/{self._bot_id}/stop")
        return self._json(resp)

    async def seek(self, position: int) -> dict:
        await self._ensure_login()
        resp = await self._http.post(
            f"/api/player/{self._bot_id}/seek", json={"position": position}
        )
        return self._json(resp)

    async def set_volume(self, volume: int) -> dict:
        await self._ensure_login()
        resp = await self._http.post(
            f"/api/player/{self._bot_id}/volume", json={"volume": volume}
        )
        return self._json(resp)

    async def set_mode(self, mode: str) -> dict:
        """mode: seq | loop | random | rloop。"""
        await self._ensure_login()
        resp = await self._http.post(
            f"/api/player/{self._bot_id}/mode", json={"mode": mode}
        )
        return self._json(resp)

    async def clear(self) -> dict:
        await self._ensure_login()
        resp = await self._http.post(f"/api/player/{self._bot_id}/clear")
        return self._json(resp)

    # ───────────────────────── 状态 ─────────────────────────

    async def get_bot_status(self) -> dict:
        """获取 bot 状态（含当前播放 + 音量）。"""
        await self._ensure_login()
        try:
            resp = await self._http.get("/api/bot")
            data = resp.json()
            bots = data.get("bots", data.get("data", {}).get("bots", []))
            if bots and isinstance(bots, list):
                bot = bots[0]
                cs = bot.get("currentSong") or {}
                return {
                    "playing": bot.get("playing", False),
                    "paused": bot.get("paused", False),
                    "volume": bot.get("volume", 50),
                    "playMode": bot.get("playMode", "seq"),
                    "elapsed": bot.get("elapsed", 0),
                    "queueSize": bot.get("queueSize", 0),
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

    async def get_queue(self) -> list[dict]:
        """获取播放队列。"""
        await self._ensure_login()
        try:
            resp = await self._http.get(f"/api/player/{self._bot_id}/queue")
            data = resp.json()
            q = data.get("queue", data.get("data", {}).get("queue", []))
            return q if isinstance(q, list) else []
        except (httpx.HTTPError, ValueError):
            return []

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
