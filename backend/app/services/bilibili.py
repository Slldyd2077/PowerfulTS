"""B 站 API 客户端：视频信息、DASH 音频流、搜索。

不依赖任何 TS3AudioBot 插件，PowerfulTS 后端直接调用 B 站公开 API。
搜索接口需要 Wbi 签名（2025 年起强制），此处自行实现签名算法。
"""
from __future__ import annotations

import hashlib
import time
import urllib.parse

import httpx

BILI_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
BILI_REFERER = "https://www.bilibili.com"

_VIEW = "https://api.bilibili.com/x/web-interface/view"
_PLAYURL = "https://api.bilibili.com/x/player/playurl"
_NAV = "https://api.bilibili.com/x/web-interface/nav"
_SEARCH = "https://api.bilibili.com/x/web-interface/wbi/search/type"

# Wbi 混淆表 (来自 bilibili-API-collect)
_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
    26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
    20, 34, 44, 52,
]


class BiliClient:
    """B 站公开 API 异步客户端。"""

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            headers={"User-Agent": BILI_UA},
        )
        self._wbi_keys: tuple[str, str] | None = None

    async def close(self) -> None:
        await self._http.aclose()

    async def get_video(self, bvid: str) -> dict:
        """取视频信息（cid、标题、UP 主等）。"""
        r = await self._http.get(_VIEW, params={"bvid": bvid})
        data = r.json()
        if data.get("code") != 0:
            raise ValueError(f"B站 view 失败 ({bvid}): {data.get('message')}")
        return data["data"]

    async def get_audio_url(self, bvid: str, cid: int) -> str:
        """取最高码率 DASH 音频流直链。"""
        r = await self._http.get(
            _PLAYURL, params={"bvid": bvid, "cid": cid, "fnval": 16, "fourk": 1}
        )
        data = r.json()
        if data.get("code") != 0:
            raise ValueError(f"B站 playurl 失败: {data.get('message')}")
        audios = (data.get("data", {}).get("dash") or {}).get("audio") or []
        if not audios:
            raise ValueError("该视频无 DASH 音频流")
        audios.sort(key=lambda x: -x.get("bandwidth", 0))
        return audios[0]["baseUrl"]

    # ─────────────────────── Wbi 签名 ───────────────────────

    async def _get_wbi_keys(self) -> tuple[str, str]:
        if self._wbi_keys is None:
            r = await self._http.get(_NAV)
            wbi = r.json().get("data", {}).get("wbi_img", {})
            img = (wbi.get("img_url") or "").rsplit("/", 1)[-1].split(".")[0]
            sub = (wbi.get("sub_url") or "").rsplit("/", 1)[-1].split(".")[0]
            self._wbi_keys = (img, sub)
        return self._wbi_keys

    @staticmethod
    def _mixin_key(orig: str) -> str:
        return "".join(orig[i] for i in _MIXIN_KEY_ENC_TAB)[:32]

    async def _wbi_sign(self, params: dict) -> dict:
        img, sub = await self._get_wbi_keys()
        mixin = self._mixin_key(img + sub)
        signed = {**params, "wts": int(time.time())}
        # 过滤值里的特殊字符 (Wbi 要求)
        signed = {
            k: "".join(c for c in str(v) if c not in "!'()*")
            for k, v in signed.items()
        }
        query = urllib.parse.urlencode(sorted(signed.items()))
        signed["w_rid"] = hashlib.md5((query + mixin).encode()).hexdigest()
        return signed

    # ─────────────────────── 搜索 ───────────────────────

    async def search(self, keyword: str, page: int = 1, page_size: int = 20) -> list[dict]:
        """Wbi 签名搜索视频。返回精简字段列表。"""
        params = await self._wbi_sign({
            "search_type": "video",
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
        })
        r = await self._http.get(_SEARCH, params=params)
        data = r.json()
        if data.get("code") != 0:
            raise ValueError(f"B站搜索失败: {data.get('message')}")
        results = data.get("data", {}).get("result", [])
        return [
            {
                "bvid": v.get("bvid"),
                "title": v.get("title"),
                "author": v.get("author"),
                "pic": v.get("pic"),
                "duration": v.get("duration"),
                "play": v.get("play"),
            }
            for v in results
            if v.get("bvid")
        ]
