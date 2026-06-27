"""NapCat (OneBot 11) QQ 消息客户端。

用于好友上线提醒推送，通过 OneBot HTTP API 发私聊。
未配置或不可达时优雅降级（warning 不抛），避免拖垮调用方（尤其 TS3 监控线程）。
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class NapCatClient:
    """OneBot 11 HTTP 私聊客户端。"""

    def __init__(self, base_url: str, token: str = "", timeout: float = 8.0) -> None:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.AsyncClient(base_url=base_url.rstrip("/"), headers=headers, timeout=timeout)

    async def send_private_msg(self, qq: str, message: str) -> bool:
        """发送 QQ 私聊。成功 True；任何失败 warning + False，绝不向上抛。"""
        try:
            resp = await self._http.post("/send_private_msg", json={"user_id": int(qq), "message": message})
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("NapCat 发送失败 (qq=%s): %s", qq, exc)
            return False
        if resp.status_code != 200:
            logger.warning("NapCat 非 200 (qq=%s): %s %s", qq, resp.status_code, resp.text[:120])
            return False
        try:
            body = resp.json()
        except ValueError:
            return True  # HTTP 200 但非 JSON，视作已发送
        if body.get("retcode") not in (0, None):
            logger.warning("NapCat retcode!=0 (qq=%s): %s", qq, body)
            return False
        return True

    async def close(self) -> None:
        await self._http.aclose()
