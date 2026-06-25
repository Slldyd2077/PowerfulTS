"""网易云音乐客户端。

调用本地部署的 NeteaseCloudMusicApi 服务 (Node.js, 默认 :3000)。
搜索 (/search) + 取播放 URL (/song/url)。播放交由 TSMusicBot（网易云平台）代理。
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class NeteaseClient:
    """网易云音乐 API 客户端。"""

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self.base_url = base_url
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def search(self, keyword: str, limit: int = 10) -> list[dict]:
        """搜索歌曲，返回 [{song_id, name, artist}]。"""
        try:
            resp = await self._http.get(
                "/search", params={"keywords": keyword, "limit": limit}
            )
            resp.raise_for_status()
            songs = resp.json().get("result", {}).get("songs", [])
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("网易云搜索失败: %s", exc)
            return []
        return [
            {
                "song_id": str(s.get("id", "")),
                "name": str(s.get("name", "")),
                "artist": "/".join(a.get("name", "") for a in s.get("artists", [])),
                "album": (s.get("album") or {}).get("name", ""),
            }
            for s in songs
        ]

    async def song_url(self, song_id: str) -> str | None:
        """获取歌曲可播放 URL；无版权/VIP 限制时返回 None。"""
        try:
            resp = await self._http.get("/song/url", params={"id": song_id})
            resp.raise_for_status()
            data = resp.json().get("data", [])
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("网易云取 URL 失败: %s", exc)
            return None
        if not data:
            return None
        url = data[0].get("url")
        return url if url else None

    async def close(self) -> None:
        await self._http.aclose()

    # ───────────────────────── 账号登录 + 个人数据 ─────────────────────────

    async def qr_key(self) -> str | None:
        """生成扫码登录 unikey。"""
        try:
            resp = await self._http.get("/login/qr/key")
            return resp.json().get("data", {}).get("unikey")
        except (httpx.HTTPError, ValueError):
            return None

    async def qr_create(self, unikey: str) -> str | None:
        """生成二维码图片 (base64 data uri)。"""
        try:
            resp = await self._http.get(
                "/login/qr/create", params={"key": unikey, "qrimg": "true"}
            )
            return resp.json().get("data", {}).get("qrimg")
        except (httpx.HTTPError, ValueError):
            return None

    async def qr_check(self, unikey: str) -> dict:
        """轮询扫码状态。code: 801待扫码 / 802已扫待确认 / 803已登录(带cookie)。"""
        try:
            resp = await self._http.get("/login/qr/check", params={"key": unikey})
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return {"code": -1, "message": "查询失败"}
        cookie = data.get("cookie", "")
        if data.get("code") == 803:
            # 803 的 cookie 可能在 message 字段里（网易云 API 的小坑）
            if not cookie:
                msg = data.get("message", "")
                if ";" in msg or "=" in msg:
                    cookie = msg
            # 清洗 Set-Cookie 属性（Max-Age/Expires/Path 等），只留纯 name=value
            cookie = self._clean_cookie(cookie)
        return {"code": data.get("code"), "message": data.get("message"), "cookie": cookie}

    @staticmethod
    def _clean_cookie(raw: str) -> str:
        """从 Set-Cookie 格式字符串提取纯请求 cookie（name=value; name=value）。

        网易云 qr/check 返回的 cookie 带 Max-Age/Expires/Path 等 Set-Cookie 属性，
        直接当请求 Cookie 头发会被服务端判无效，需清洗。
        """
        if not raw:
            return ""
        skip = {"max-age", "expires", "path", "domain", "httponly", "secure", "samesite"}
        parts = []
        for item in raw.split(";"):
            item = item.strip()
            if "=" not in item:
                continue
            key = item.split("=", 1)[0].strip().lower()
            if key in skip:
                continue
            parts.append(item)
        return "; ".join(parts)

    async def account_info(self, cookie: str) -> dict | None:
        """用 cookie 取当前登录账号信息 (uid / 昵称)。"""
        try:
            resp = await self._http.get("/user/account", headers={"Cookie": cookie})
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return None
        profile = data.get("profile") or {}
        if not profile.get("userId"):
            return None
        return {
            "uid": str(profile.get("userId", "")),
            "nickname": profile.get("nickname", ""),
        }

    async def user_playlists(self, uid: str, cookie: str, limit: int = 30) -> list[dict]:
        """取用户歌单（自建 + 收藏的）。"""
        try:
            resp = await self._http.get(
                "/user/playlist", params={"uid": uid, "limit": limit},
                headers={"Cookie": cookie},
            )
            playlists = resp.json().get("playlist", [])
        except (httpx.HTTPError, ValueError):
            return []
        return [
            {
                "id": str(p.get("id", "")),
                "name": p.get("name", ""),
                "track_count": p.get("trackCount", 0),
                "cover": (p.get("coverImgUrl") or "")[:120],
            }
            for p in playlists
        ]

    async def playlist_tracks(self, playlist_id: str, cookie: str, limit: int = 100) -> list[dict]:
        """取歌单内歌曲（song_id/name/artist），交给 play 播放。"""
        try:
            resp = await self._http.get(
                "/playlist/detail", params={"id": playlist_id},
                headers={"Cookie": cookie},
            )
            tracks = (resp.json().get("playlist") or {}).get("tracks", [])
        except (httpx.HTTPError, ValueError):
            return []
        return [
            {
                "song_id": str(t.get("id", "")),
                "name": t.get("name", ""),
                "artist": "/".join(a.get("name", "") for a in t.get("ar", [])),
            }
            for t in tracks[:limit]
        ]
