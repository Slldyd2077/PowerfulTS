"""网易云音乐客户端。

调用本地部署的 NeteaseCloudMusicApi 服务 (Node.js, 默认 :3000)。
搜索 (/search) + 取播放 URL (/song/url)。URL 交给 TS3AudioBot 标准 play 播放。
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
