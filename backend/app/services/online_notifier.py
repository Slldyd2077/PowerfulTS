"""TS3 上线与首次加入的成员动态通知编排器。"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import distinct, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from ..core.config import Settings
from ..models.account import Account, ServerMember
from ..models.community import Friend, PendingNotification
from ..services import app_setting
from . import ts3_auth
from .napcat_client import NapCatClient
from .notification_utils import unique_qq_numbers

logger = logging.getLogger(__name__)

# 默认消息模板
DEFAULT_FRIEND_ONLINE_NOTICE = "✅ 你的好友「{nick}」已上线 TeamSpeak"
DEFAULT_SERVER_ONLINE_NOTICE = "🟢 服务器动态：{nick} 已上线 TeamSpeak"
DEFAULT_SERVER_FIRST_JOIN_NOTICE = "👋 新成员提醒：{nick} 首次进入 TeamSpeak 服务器"


class OnlineNotifier:
    """好友提醒固定走 QQ；管理员配置的成员动态默认走 TS 私聊，可选 QQ。"""

    def __init__(self, napcat: NapCatClient, sessionmaker, settings: Settings) -> None:
        self._napcat = napcat
        self._sessions = sessionmaker
        self._settings = settings
        self._notified: set[str] = set()
        self._lock = asyncio.Lock()

    async def _resolve_friend_subscribers(self, nickname: str) -> list[str]:
        adder = aliased(Account)
        onlinee = aliased(Account)
        async with self._sessions() as db:
            result = await db.execute(
                select(distinct(adder.qq_number))
                .join(Friend, Friend.account_id == adder.id)
                .join(onlinee, Friend.friend_account_id == onlinee.id)
                .where(onlinee.ts_nickname == nickname)
                .where(Friend.notify_online.is_(True))
                .where(adder.qq_number.isnot(None))
                .where(adder.qq_number != "")
            )
            return unique_qq_numbers(result.scalars().all())

    async def _flush_pending_notifications(self, nickname: str) -> int:
        """收件人 TS 上线时补发之前无可用渠道而留存的消息。"""
        async with self._sessions() as db:
            account_id = await db.scalar(
                select(Account.id).where(Account.ts_nickname == nickname)
            )
            if account_id is None:
                return 0
            rows = list((await db.execute(
                select(PendingNotification)
                .where(PendingNotification.recipient_account_id == account_id)
                .order_by(PendingNotification.created_at, PendingNotification.id)
            )).scalars().all())
            sent = 0
            for item in rows:
                delivered = await asyncio.to_thread(
                    ts3_auth.send_private_message, self._settings, nickname, item.message
                )
                if not delivered:
                    break
                await db.delete(item)
                sent += 1
            if sent:
                await db.commit()
            return sent

    async def _resolve_server_subscribers(self, field: str) -> list[tuple[str, str, str | None]]:
        """返回 (TS 昵称、渠道、QQ)，字段仅来自内部固定列表。"""
        enabled = getattr(Account, field)
        async with self._sessions() as db:
            result = await db.execute(
                select(Account.ts_nickname, Account.notification_channel, Account.qq_number)
                .where(enabled.is_(True))
            )
            return list(result.all())

    async def _mark_first_seen(self, unique_identifier: str, nickname: str) -> bool:
        async with self._sessions() as db:
            db.add(ServerMember(unique_identifier=unique_identifier, first_nickname=nickname))
            try:
                await db.commit()
                return True
            except IntegrityError:
                await db.rollback()
                return False

    async def _send_server_notice(self, recipients: list[tuple[str, str, str | None]], message: str) -> int:
        """TS 为默认渠道；QQ 仅在该成员显式选中且已绑定 QQ 时发送。"""
        sent = 0
        qq_sent: set[str] = set()
        for nickname, channel, qq_number in recipients:
            if channel == "qq" and qq_number:
                qq = str(qq_number)
                if qq not in qq_sent and await self._napcat.send_private_msg(qq, message):
                    sent += 1
                    qq_sent.add(qq)
            elif channel != "qq":
                if await asyncio.to_thread(ts3_auth.send_private_message, self._settings, nickname, message):
                    sent += 1
        return sent

    async def _send_qq(self, recipients: list[str], message: str) -> int:
        sent = 0
        for qq in recipients:
            if await self._napcat.send_private_msg(qq, message):
                sent += 1
        return sent

    async def _get_notice_templates(self) -> tuple[str, str, str]:
        """获取通知消息模板，返回 (friend_online, server_online, server_first_join)。"""
        async with self._sessions() as db:
            friend_online = await app_setting.get_setting(
                db, "sys.friend_online_notice", DEFAULT_FRIEND_ONLINE_NOTICE
            )
            server_online = await app_setting.get_setting(
                db, "sys.server_online_notice", DEFAULT_SERVER_ONLINE_NOTICE
            )
            server_first_join = await app_setting.get_setting(
                db, "sys.server_first_join_notice", DEFAULT_SERVER_FIRST_JOIN_NOTICE
            )
            return friend_online, server_online, server_first_join

    async def on_online(self, nickname: str, unique_identifier: str | None = None) -> None:
        async with self._lock:
            if nickname in self._notified:
                return
            self._notified.add(nickname)

        # 获取自定义消息模板
        friend_online_msg, server_online_msg, server_first_join_msg = await self._get_notice_templates()

        await self._flush_pending_notifications(nickname)

        friend_subscribers = await self._resolve_friend_subscribers(nickname)
        if friend_subscribers:
            await self._send_qq(friend_subscribers, friend_online_msg.format(nick=nickname))

        online_subscribers = await self._resolve_server_subscribers("notify_server_online")
        if online_subscribers:
            await self._send_server_notice(online_subscribers, server_online_msg.format(nick=nickname))

        if unique_identifier and await self._mark_first_seen(unique_identifier, nickname):
            first_join_subscribers = await self._resolve_server_subscribers("notify_server_first_join")
            if first_join_subscribers:
                await self._send_server_notice(first_join_subscribers, server_first_join_msg.format(nick=nickname))

    async def on_offline(self, nickname: str) -> None:
        self._notified.discard(nickname)
