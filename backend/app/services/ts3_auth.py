"""TS 身份认证：ServerQuery 在线查询 + 私聊下发验证码。

发码使用独立临时连接（不共享 monitor 长连接，避免并发污染其命令流）。
send_verify_code 返回发码目标的 unique_identifier（注册时校验一致，防昵称换人冒名）。
target_mode=1 表示向 target=clid 的客户端发私聊消息。
"""
from __future__ import annotations

import logging
import time

from ..core.config import Settings
from .ts3_monitor import ONLINE_WINDOW, TS3Monitor
from .ts3_query import TS3QueryClient

logger = logging.getLogger(__name__)


def _find_online_entry(monitor: TS3Monitor, nickname: str) -> dict | None:
    """在 monitor 内存中查找该昵称的在线 entry（未过 ONLINE_WINDOW）。"""
    now = time.time()
    with monitor._lock:
        for entry in monitor.client_data.values():
            if entry["nickname"] == nickname and now - entry["last_seen"] <= ONLINE_WINDOW:
                return entry
    return None


def is_online(monitor: TS3Monitor, nickname: str) -> bool:
    """该 TS 昵称当前是否在线。"""
    return _find_online_entry(monitor, nickname) is not None


def get_online_uid(monitor: TS3Monitor, nickname: str) -> str | None:
    """在线则返回其 unique_identifier（不可伪造的身份锚点）。"""
    entry = _find_online_entry(monitor, nickname)
    return entry.get("unique_identifier") if entry else None


def send_verify_code(settings: Settings, nickname: str, code: str) -> str | None:
    """独立连接：查 clid + 私聊下发验证码。

    返回发码目标的 unique_identifier（在线）；不在线返回 None。
    """
    conn = TS3QueryClient(settings.ts3_host, settings.ts3_query_port)
    try:
        conn.connect()
        conn.send(
            "login",
            client_login_name=settings.ts3_query_user,
            client_login_password=settings.ts3_query_password,
        )
        conn.send("use", sid=settings.ts3_sid)
        clients = conn.send("clientlist", uid=True)
        for cl in clients:
            if str(cl.get("client_type", "0")) == "1":
                continue
            if str(cl.get("client_nickname", "")) == nickname:
                clid = cl.get("clid")
                uid = str(cl.get("client_unique_identifier", ""))
                conn.send(
                    "sendtextmessage",
                    targetmode=1,
                    target=clid,
                    msg=f"【PowerfulTS】你的验证码是: {code} (5 分钟内有效)",
                )
                return uid
        return None  # 不在线
    finally:
        conn.close()
