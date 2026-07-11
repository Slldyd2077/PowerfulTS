"""好友关系服务 (SQLite)。"""
from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Account, Friend, FriendRequest

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

    async def check_is_friend(self, account_id: int, friend_account_id: int) -> bool:
        """检查是否已经是好友关系。"""
        result = await self.db.execute(
            select(Friend).where(
                Friend.account_id == account_id,
                Friend.friend_account_id == friend_account_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def check_mutual_friends(self, account_id: int, friend_account_id: int) -> bool:
        """检查是否是双向好友关系。"""
        result1 = await self.db.execute(
            select(Friend).where(
                Friend.account_id == account_id,
                Friend.friend_account_id == friend_account_id,
            )
        )
        result2 = await self.db.execute(
            select(Friend).where(
                Friend.account_id == friend_account_id,
                Friend.friend_account_id == account_id,
            )
        )
        return result1.scalar_one_or_none() is not None and result2.scalar_one_or_none() is not None

    async def create_friend_request(self, requester_id: int, recipient_id: int) -> FriendRequest | None:
        """创建好友申请。如果已存在待处理申请则返回 None。"""
        # 检查是否已存在待处理申请
        existing = await self.db.execute(
            select(FriendRequest).where(
                FriendRequest.requester_id == requester_id,
                FriendRequest.recipient_id == recipient_id,
                FriendRequest.status == "pending"
            )
        )
        if existing.scalar_one_or_none():
            return None

        request = FriendRequest(requester_id=requester_id, recipient_id=recipient_id, status="pending")
        self.db.add(request)
        await self.db.commit()
        await self.db.refresh(request)
        return request

    async def get_pending_requests(self, account_id: int) -> list[FriendRequest]:
        """获取待处理的好友申请列表。"""
        result = await self.db.execute(
            select(FriendRequest).where(
                FriendRequest.recipient_id == account_id,
                FriendRequest.status == "pending"
            )
        )
        return list(result.scalars().all())

    async def accept_friend_request(self, request_id: int) -> bool:
        """接受好友申请，建立双向好友关系。"""
        request = await self.db.get(FriendRequest, request_id)
        if not request or request.status != "pending":
            return False

        # 建立双向好友关系
        self.db.add(Friend(account_id=request.requester_id, friend_account_id=request.recipient_id))
        self.db.add(Friend(account_id=request.recipient_id, friend_account_id=request.requester_id))

        # 更新申请状态
        request.status = "accepted"
        await self.db.commit()
        return True

    async def reject_friend_request(self, request_id: int) -> bool:
        """拒绝好友申请。"""
        request = await self.db.get(FriendRequest, request_id)
        if not request or request.status != "pending":
            return False

        request.status = "rejected"
        await self.db.commit()
        return True
