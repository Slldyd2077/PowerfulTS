"""好友上线提醒编排器。

ts3_monitor 检测到上线 → on_online(nickname) → 反查「谁把这个昵称加为好友 + 开启了
提醒 + 绑了 QQ」→ NapCat 发私聊。nickname 级去重（一次上线只通知一次），离线清除。
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import distinct, select
from sqlalchemy.orm import aliased

from ..models.account import Account
from ..models.community import Friend
from .napcat_client import NapCatClient
from .notification_utils import unique_qq_numbers

logger = logging.getLogger(__name__)

ONLINE_NOTICE_TPL = "✨ 你的好友「{nick}」已上线 TeamSpeak"


class OnlineNotifier:
    """好友上线 → QQ 私聊提醒。"""

    def __init__(self, napcat: NapCatClient, sessionmaker) -> None:
        self._napcat = napcat
        self._sessions = sessionmaker
        self._notified: set[str] = set()
        self._lock = asyncio.Lock()

    async def _resolve_subscribers(self, nickname: str) -> list[str]:
        """反查：把 nickname 加为好友、开启提醒、且绑了 QQ 的「添加者」QQ 列表。"""
        adder = aliased(Account)
        onlinee = aliased(Account)
        async with self._sessions() as db:
            result = await db.execute(
                select(distinct(adder.qq_number))
                .join(Friend, Friend.account_id == adder.id)
                .join(onlinee, Friend.friend_account_id == onlinee.id)
                .where(onlinee.ts_nickname == nickname)
                .where(adder.notify_friends_online.is_(True))
                .where(adder.qq_number.isnot(None))
                .where(adder.qq_number != "")
            )
            return unique_qq_numbers(result.scalars().all())

    async def on_online(self, nickname: str) -> None:
        """某用户上线 → 反查订阅者 → 发 QQ 提醒（nickname 级去重）。"""
        async with self._lock:
            if nickname in self._notified:
                return
            # 先标记防并发风暴；即便发送失败也靠「离线→再上线」恢复
            self._notified.add(nickname)
        subscribers = await self._resolve_subscribers(nickname)
        if not subscribers:
            logger.debug("上线 %s：无 QQ 订阅者，跳过", nickname)
            return
        sent = 0
        for qq in subscribers:
            if await self._napcat.send_private_msg(qq, ONLINE_NOTICE_TPL.format(nick=nickname)):
                sent += 1
        logger.info("上线 %s：通知 %d/%d 位订阅者", nickname, sent, len(subscribers))

    async def on_offline(self, nickname: str) -> None:
        """某用户离线 → 清除去重标记，下次上线可再次通知。"""
        self._notified.discard(nickname)
