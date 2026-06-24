"""好友关系服务 (SQLite)。"""
from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Account, Friend

logger = logging.getLogger(__name__)


class FriendService:
    """好友关系的数据库操作封装。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_nickname(self, nickname: str) -> Account | None:
        result = await self.db.execute(select(Account).where(Account.ts_nickname == nickname))
        return result.scalar_one_or_none()

    async def list_friend_nicknames(self, account: Account) -> list[str]:
        """返回当前账号的好友 ts_nickname 列表。"""
        result = await self.db.execute(
            select(Account.ts_nickname)
            .join(Friend, Friend.friend_account_id == Account.id)
            .where(Friend.account_id == account.id)
        )
        return list(result.scalars().all())

    async def add_relation(self, account_id: int, friend_account_id: int) -> None:
        self.db.add(Friend(account_id=account_id, friend_account_id=friend_account_id))
        await self.db.commit()

    async def remove_relation(self, account_id: int, friend_account_id: int) -> None:
        await self.db.execute(
            delete(Friend).where(
                Friend.account_id == account_id,
                Friend.friend_account_id == friend_account_id,
            )
        )
        await self.db.commit()
