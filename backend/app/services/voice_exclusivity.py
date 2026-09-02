"""Mutual exclusion between a real TS client and an account's web voice bot."""
from __future__ import annotations

import logging
import asyncio
from typing import Protocol

from sqlalchemy import select

from ..core.config import Settings
from ..models import Account
from .ts3_monitor import WEB_VOICE_MARKER
from .ts3_query import TS3QueryClient

logger = logging.getLogger(__name__)

_INTERNAL_UID_PREFIXES = ("guest:", "invite:")
NATIVE_TS_PREEMPTED_CLOSE_CODE = 4412
NATIVE_TS_PREEMPTED_REASON = "TeamSpeak 客户端已上线，网页通话已断开"
WEB_TS_KICK_REASON = "网页通话已接管，同一账号只能保留一个语音端"


class VoiceExclusivityError(RuntimeError):
    """The server cannot safely establish the requested exclusive voice owner."""


class _VoiceBots(Protocol):
    async def current_bot_id(self, db, account_id: int) -> str | None: ...

    async def preempt_if_native_present(
        self, account_id: int, bot_id: str, *, is_present, close_downlink
    ) -> bool: ...


class _Downlinks(Protocol):
    async def close_active(
        self, account_id: int, *, code: int, reason: str
    ) -> bool: ...


def _has_registered_ts_identity(account: object) -> bool:
    uid = str(getattr(account, "unique_identifier", "") or "").strip()
    return bool(uid) and not uid.startswith(_INTERNAL_UID_PREFIXES)


def _is_web_voice_nickname(nickname: str) -> bool:
    return nickname.startswith(WEB_VOICE_MARKER)


def _safe_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _login(conn: TS3QueryClient, settings: Settings) -> None:
    conn.connect()
    conn.send(
        "login",
        client_login_name=settings.ts3_query_user,
        client_login_password=settings.ts3_query_password,
    )
    conn.send("use", sid=settings.ts3_sid)


def kick_real_ts_client_for_account(
    settings: Settings,
    account: object,
    *,
    exclude_clid: int | None,
    reason: str = WEB_TS_KICK_REASON,
) -> bool:
    """Kick a verified native identity before the web voice bot connects.

    Invitation and guest accounts only own an internal UID. A same-nickname
    native client therefore blocks their web join instead of being kicked
    without proof of ownership.
    """
    expected_uid = str(getattr(account, "unique_identifier", "") or "").strip()
    expected_nickname = str(getattr(account, "ts_nickname", "") or "").strip()
    verified_identity = _has_registered_ts_identity(account)
    conn = TS3QueryClient(settings.ts3_host, settings.ts3_query_port)
    try:
        _login(conn, settings)
        kick_clids: list[int] = []
        unverified_conflict = False
        for client in conn.send("clientlist", uid=True):
            if str(client.get("client_type", "0")) == "1":
                continue
            clid = _safe_int(client.get("clid"))
            if clid is None or clid == exclude_clid:
                continue
            nickname = str(client.get("client_nickname", ""))
            if _is_web_voice_nickname(nickname):
                continue
            uid = str(client.get("client_unique_identifier", ""))
            if verified_identity and uid == expected_uid:
                kick_clids.append(clid)
            elif not verified_identity and nickname == expected_nickname:
                unverified_conflict = True

        if unverified_conflict:
            raise VoiceExclusivityError(
                "该账号尚未绑定真实 TS 身份，检测到同名 TS 客户端，无法安全强制下线"
            )
        for clid in kick_clids:
            conn.send(
                "clientkick",
                clid=clid,
                reasonid=5,
                reasonmsg=reason,
            )
            logger.info(
                "网页通话接管: 已踢出真实 TS 客户端 account=%s clid=%s",
                getattr(account, "id", "?"),
                clid,
            )
        return bool(kick_clids)
    except VoiceExclusivityError:
        raise
    except Exception as exc:
        logger.warning(
            "网页通话互斥检查失败 account=%s",
            getattr(account, "id", "?"),
            exc_info=True,
        )
        raise VoiceExclusivityError(
            "无法确认 TeamSpeak 客户端状态，请稍后重试"
        ) from exc
    finally:
        conn.close()


def is_ts_client_connection_present(
    settings: Settings,
    unique_identifier: str,
    clid: int,
) -> bool:
    """Revalidate a monitor arrival against a fresh ServerQuery snapshot."""
    conn = TS3QueryClient(settings.ts3_host, settings.ts3_query_port)
    try:
        _login(conn, settings)
        for client in conn.send("clientlist", uid=True):
            if str(client.get("client_type", "0")) == "1":
                continue
            if str(client.get("client_unique_identifier", "")) != unique_identifier:
                continue
            return _safe_int(client.get("clid")) == clid
        return False
    except Exception as exc:
        raise VoiceExclusivityError(
            "无法复核 TeamSpeak 客户端连接状态"
        ) from exc
    finally:
        conn.close()


class VoiceExclusivityCoordinator:
    """Make the most recently connected native TS client the active owner."""

    def __init__(
        self,
        session_factory,
        voice_bots_provider,
        tsmusic_provider,
        downlinks_provider,
        settings: Settings,
        presence_checker=is_ts_client_connection_present,
    ) -> None:
        self._session_factory = session_factory
        self._voice_bots_provider = voice_bots_provider
        self._tsmusic_provider = tsmusic_provider
        self._downlinks_provider = downlinks_provider
        self._settings = settings
        self._presence_checker = presence_checker

    async def on_visible(
        self,
        identity: str,
        unique_identifier: str,
        *,
        clid: int | None,
        web_voice: bool,
    ) -> None:
        if not identity or not unique_identifier or clid is None:
            return
        async with self._session_factory() as db:
            account = await db.scalar(
                select(Account).where(
                    Account.unique_identifier == unique_identifier
                )
            )
            if account is None or not _has_registered_ts_identity(account):
                return

            voice_bots: _VoiceBots = self._voice_bots_provider()
            bot_id = await voice_bots.current_bot_id(db, account.id)
            if not bot_id:
                return
            try:
                bot_clid = await self._tsmusic_provider().get_bot_client_id(bot_id)
            except Exception:
                logger.warning(
                    "读取网页通话 bot clid 失败 account=%s bot=%s",
                    account.id,
                    bot_id,
                    exc_info=True,
                )
                bot_clid = None
            if clid == bot_clid:
                return
            async def native_is_still_present() -> bool:
                try:
                    return await asyncio.to_thread(
                        self._presence_checker,
                        self._settings,
                        unique_identifier,
                        clid,
                    )
                except VoiceExclusivityError:
                    logger.warning(
                        "放弃过期或无法复核的 TS 接管事件 account=%s clid=%s",
                        account.id,
                        clid,
                        exc_info=True,
                    )
                    return False

            async def close_downlink() -> None:
                await self._downlinks_provider().close_active(
                    account.id,
                    code=NATIVE_TS_PREEMPTED_CLOSE_CODE,
                    reason=NATIVE_TS_PREEMPTED_REASON,
                )
            preempted = await voice_bots.preempt_if_native_present(
                account.id,
                bot_id,
                is_present=native_is_still_present,
                close_downlink=close_downlink,
            )
            if not preempted:
                return
            logger.info(
                "真实 TS 客户端接管: 已断开网页通话 account=%s bot=%s clid=%s",
                account.id,
                bot_id,
                clid,
            )
