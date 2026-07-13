"""播放跟随：把 TSMusicBot 的 bot client 移动到当前用户所在 TS 频道。

独立临时 ServerQuery 连接（不共享 monitor 长连接，避免并发污染其命令流），
照搬 ts3_auth.send_verify_code 的 connect→login→use→clientlist→操作→close 范式。

背景：TSMusicBot 是 real TS3 client（client_type=0），上游 REST API 无「移动 bot」
端点（其 joinChannel/clientMove 仅内部方法 + TS 聊天命令）。故由 PowerfulTS 用
ServerQuery ``clientmove`` 自行把 bot 移到点播用户所在频道，用户才能听到。
"""
from __future__ import annotations

import logging

from ..core.config import Settings
from ..models import Account
from .ts3_query import TS3QueryClient, TS3QueryError

logger = logging.getLogger(__name__)


def bot_nickname_matches(actual: object, configured: object) -> bool:
    """匹配 Bot 的静态昵称或播放状态动态昵称。

    TSMusicBot 开启 ``nicknameEnabled`` 后会把 TS 昵称改成
    ``♪ 歌曲名 - 配置昵称``。配置 API 仍只返回基础昵称，因此不能只做精确匹配。
    """
    actual_nick = str(actual or "").strip()
    configured_nick = str(configured or "").strip()
    if not actual_nick or not configured_nick:
        return False
    return actual_nick == configured_nick or actual_nick.endswith(f" - {configured_nick}")


def _int_or_none(value: object) -> int | None:
    """安全 int 转换，空/异常返回 None（区分「字段缺失」与合法的 0 频道 cid）。"""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def move_bot_to_user(settings: Settings, bot_nickname: str, user: Account) -> dict:
    """临时 SQ 连接：把 bot 移到 user 所在频道。不抛异常。

    返回 ``{moved: bool, reason: str, user_cid: int|None, bot_cid: int|None}``。
    reason 取值：``user_offline`` / ``user_no_channel`` / ``bot_not_found`` /
    ``already_together`` / ``moved`` / ``move_failed`` / ``connect_failed``。
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

        user_uid = (user.unique_identifier or "").strip()
        user_nick = (user.ts_nickname or "").strip()

        # 一次遍历同时定位 user（cid）与 bot（clid/cid）
        user_found = False
        user_cid: int | None = None
        bot_clid: int | None = None
        bot_cid: int | None = None
        for cl in clients:
            if str(cl.get("client_type", "0")) == "1":
                continue  # 跳过 ServerQuery 连接
            nick = str(cl.get("client_nickname", ""))
            # 定位用户：优先 unique_identifier（不可伪造），回退昵称
            if not user_found:
                uid = str(cl.get("client_unique_identifier", ""))
                if (user_uid and uid == user_uid) or (user_nick and nick == user_nick):
                    user_found = True
                    user_cid = _int_or_none(cl.get("cid"))
            # 定位 bot：兼容基础昵称与“歌曲名 - 基础昵称”的动态昵称。
            if bot_clid is None and bot_nickname_matches(nick, bot_nickname):
                bot_clid = _int_or_none(cl.get("clid"))
                bot_cid = _int_or_none(cl.get("cid"))

        if not user_found:
            return {"moved": False, "reason": "user_offline", "user_cid": None, "bot_cid": bot_cid}
        if user_cid is None:
            return {"moved": False, "reason": "user_no_channel", "user_cid": None, "bot_cid": bot_cid}
        if bot_clid is None:
            return {"moved": False, "reason": "bot_not_found", "user_cid": user_cid, "bot_cid": None}
        if bot_cid is not None and bot_cid == user_cid:
            return {"moved": False, "reason": "already_together", "user_cid": user_cid, "bot_cid": bot_cid}

        conn.send("clientmove", clid=bot_clid, cid=user_cid)
        logger.info(
            "跟随: bot「%s」(clid=%s) → cid=%s（用户 %s 所在频道）",
            bot_nickname, bot_clid, user_cid, user.ts_nickname,
        )
        return {"moved": True, "reason": "moved", "user_cid": user_cid, "bot_cid": user_cid}
    except TS3QueryError as exc:
        logger.warning("跟随失败: clientmove 被拒 [%s] %s（用户 %s）", exc.error_id, exc.msg, user.ts_nickname)
        return {"moved": False, "reason": "move_failed", "user_cid": None, "bot_cid": None}
    except (ConnectionError, OSError) as exc:
        logger.warning("跟随失败: SQ 连接异常 %s（用户 %s）", exc, user.ts_nickname)
        return {"moved": False, "reason": "connect_failed", "user_cid": None, "bot_cid": None}
    finally:
        conn.close()
