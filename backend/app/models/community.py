"""频道租赁 / 好友 — 社区域 ORM 模型。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class ChannelRental(Base):
    """频道租赁记录。account 拥有的 TS3 子频道。"""

    __tablename__ = "channel_rentals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    channel_name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ts3_cid: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Friend(Base):
    """好友关系（单向：account → friend_account）。"""

    __tablename__ = "friends"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    friend_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    notify_online: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("account_id", "friend_account_id", name="uq_friend_pair"),
    )


class FriendRequest(Base):
    """好友申请（待接受的好友请求）。"""

    __tablename__ = "friend_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    requester_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("requester_id", "recipient_id", name="uq_friend_request"),
    )


class PendingNotification(Base):
    """当前无可用通知渠道时留存，收件人下次 TS 上线后补发。"""

    __tablename__ = "pending_notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipient_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32), default="friend_request", server_default="friend_request")
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
