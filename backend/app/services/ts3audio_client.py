"""TS3AudioBot HTTP 适配客户端。

将 TS3AudioBot 的 REST API（全 GET、BASIC auth、/api/bot/use/{id}/{cmd}）
封装为语义化的异步方法，并统一处理响应解包与错误翻译。

端点依据 TS3AudioBot 0.12.0 实测 OpenAPI（GET /api/json/api, 共 164 个端点）。
"""
from __future__ import annotations

import base64
import logging
from typing import Any
from urllib.parse import quote

import httpx

from ..core.config import Settings

logger = logging.getLogger(__name__)


class TS3AudioBotError(Exception):
    """TS3AudioBot 返回的 JsonError 翻译后的异常。"""

    def __init__(self, code: int, name: str, message: str) -> None:
        self.code = code
        self.name = name
        self.message = message
        super().__init__(f"[{code} {name}] {message}")


# ErrorCode(CommandExceptionReason) → HTTP 状态映射
_ERROR_HTTP = {
    0: 502,   # Unknown / 连接错误
    2: 401,   # Unauthorized
    10: 422,  # CommandError
    11: 403,  # MissingRights
    12: 400,  # AmbiguousCall
    13: 400,  # MissingParameter
    15: 404,  # FunctionNotFound
    17: 409,  # MissingContext
}


class TS3AudioBotClient:
    """单个 TS3AudioBot 实例的异步客户端。"""

    def __init__(self, settings: Settings) -> None:
        if not settings.ts3ab_bot_uid or not settings.ts3ab_api_token:
            logger.warning(
                "TS3AB_BOT_UID / TS3AB_API_TOKEN 未配置，音乐通道将无法认证。"
                "请在 .env 中填入（TS3 私聊 bot 发 !api token）后重启。"
            )
        credential = f"{settings.ts3ab_bot_uid}:{settings.ts3ab_api_token}"
        token = base64.b64encode(credential.encode("utf-8")).decode("ascii")
        self._http = httpx.AsyncClient(
            base_url=settings.ts3ab_url,
            headers={"Authorization": f"Basic {token}"},
            timeout=httpx.Timeout(10.0),
        )
        self._bot_id = settings.ts3ab_default_bot_id

    async def close(self) -> None:
        await self._http.aclose()

    # ───────────────────────── 内部 ─────────────────────────

    @staticmethod
    def _encode(resource: str) -> str:
        """URL 编码音源字符串，斜杠/空格等全部转义。"""
        return quote(resource, safe="")

    async def _call(self, cmd: str) -> Any:
        """执行 bot context 命令：GET /api/bot/use/{bot_id}/{cmd}。

        自动解包 JsonValue，翻译 JsonError。
        """
        # 0.12.0 bot 上下文前缀含子命令起始符 /(
        # 完整 URL: /api/bot/use/{id}/(/{cmd}  例 /api/bot/use/0/(/song
        url = f"/api/bot/use/{self._bot_id}/(/{cmd}"
        try:
            resp = await self._http.get(url)
        except httpx.HTTPError as exc:
            raise TS3AudioBotError(0, "ConnectError", f"无法连接 TS3AudioBot: {exc}") from exc
        return self._parse(resp)

    @staticmethod
    def _parse(resp: httpx.Response) -> Any:
        if resp.status_code == 204 or not resp.content:
            return None
        try:
            data = resp.json()
        except ValueError:
            # 非预期响应（如 HTML），不当致命错误
            return None
        if isinstance(data, dict):
            if "ErrorCode" in data:
                raise TS3AudioBotError(
                    int(data.get("ErrorCode", 0)),
                    str(data.get("ErrorName", "")),
                    str(data.get("ErrorMessage", "")),
                )
            # JsonValue<T> 包装：{"Value": x}
            if set(data.keys()) == {"Value"}:
                return data["Value"]
        return data

    # ─────────────────────── bot 管理 ───────────────────────

    async def bot_list(self) -> list[dict]:
        """列出所有 bot 实例（不在 bot context 下）。"""
        try:
            resp = await self._http.get("/api/bot/list")
        except httpx.HTTPError as exc:
            raise TS3AudioBotError(0, "ConnectError", f"无法连接 TS3AudioBot: {exc}") from exc
        data = self._parse(resp)
        return data if isinstance(data, list) else []

    # ─────────────────────── 播放控制 ───────────────────────

    async def play(self, resource: str) -> None:
        """立即播放（清空当前队列）。"""
        await self._call(f"play/{self._encode(resource)}")

    async def add(self, resource: str) -> None:
        """加入队列末尾（共享 bot 推荐用法）。"""
        await self._call(f"add/{self._encode(resource)}")

    async def pause(self) -> bool:
        """切换暂停/恢复，返回切换后是否处于暂停。"""
        value = await self._call("pause")
        return bool(value)

    async def resume(self) -> None:
        """恢复播放（play 无参数）。"""
        await self._call("play")

    async def stop(self) -> None:
        await self._call("stop")

    async def next_song(self) -> None:
        await self._call("next")

    async def previous(self) -> None:
        await self._call("previous")

    async def seek(self, position: str) -> None:
        """跳转播放位置，position 如 '1:30' 或 '90s'。"""
        await self._call(f"seek/{self._encode(position)}")

    async def clear(self) -> None:
        await self._call("clear")

    # ─────────────────────── 状态查询 ───────────────────────

    async def get_song(self) -> dict | None:
        """当前播放歌曲信息（CurrentSongInfo），未播放时返回 None。"""
        try:
            return await self._call("song")
        except TS3AudioBotError as exc:
            # CommandError(10) / MissingContext(17) 视为空闲而非错误
            if exc.code in (10, 17):
                return None
            raise

    async def get_volume(self) -> float:
        """查询当前音量。"""
        value = await self._call("volume")
        return float(value) if value is not None else 0.0

    async def set_volume(self, level: int) -> float:
        value = await self._call(f"volume/{int(level)}")
        return float(value) if value is not None else float(level)

    async def get_queue(self) -> dict | None:
        """当前播放队列（.mix）。"""
        return await self._call("list/queue/.mix")

    async def get_history(self, amount: int = 20) -> Any:
        return await self._call(f"history/last/{int(amount)}")
