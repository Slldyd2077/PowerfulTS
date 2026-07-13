"""账号 / 会话 / 验证码 — 认证域 ORM 模型。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class Account(Base):
    """用户账号。以 TS3 unique_identifier 为身份锚点（不可伪造）。"""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts_nickname: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    unique_identifier: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="member", server_default="member")
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    netease_cookie: Mapped[str | None] = mapped_column(Text, nullable=True)
    netease_uid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # QQ 绑定 + 好友上线提醒开关（NapCat 推送用）
    qq_number: Mapped[str | None] = mapped_column(String(16), nullable=True)
    notify_friends_online: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    # 管理员可为每位成员配置的服务器动态通知（发送至该成员绑定的 QQ）。
    notify_server_online: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    notify_server_first_join: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    # 成员动态的投递渠道：默认 TS 私聊；NapCat 已启用时管理员可切换为 QQ。
    notification_channel: Mapped[str] = mapped_column(String(8), default="ts", server_default="ts", nullable=False)
    # ── 专属 TSMusicBot 容器归属（per-user 隔离：每用户独立容器 → 独立 bot + 平台账号）──
    tsmusic_container_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tsmusic_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tsmusic_user: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tsmusic_password: Mapped[str | None] = mapped_column(String(128), nullable=True)
    container_status: Mapped[str] = mapped_column(String(16), default="none", server_default="none")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ServerMember(Base):
    """已被监测到的 TS3 成员；用于跨重启识别首次进入服务器事件。"""

    __tablename__ = "server_members"

    unique_identifier: Mapped[str] = mapped_column(String(128), primary_key=True)
    first_nickname: Mapped[str] = mapped_column(String(64))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BotOwnership(Base):
    """bot 实例归属：哪个 account 拥有哪个 TSMusicBot bot（软隔离，list/start/stop/delete 按 owner 过滤）。"""

    __tablename__ = "bot_ownerships"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    bot_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("account_id", "bot_id", name="uq_account_bot"),)


class BotShare(Base):
    """bot 共享：owner 把一个 bot 共享给好友 account。
    接受方可播放/点播/启停（用 owner 的 VIP 平台账号），不能 delete/配置/改平台账号。
    """

    __tablename__ = "bot_shares"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    bot_id: Mapped[str] = mapped_column(String(64), index=True)
    shared_to_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    # False: 仅借用 VIP 播放能力；True: 接受方还可浏览 owner 的私人歌单/推荐/FM。
    share_playlists: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    shared_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "owner_account_id", "bot_id", "shared_to_account_id", name="uq_bot_share"
        ),
    )


class Session(Base):
    """登录会话。TTL 由 expires_at 字段 + 惰性清理实现（替代 Redis EXPIRE）。"""

    __tablename__ = "sessions"

    token: Mapped[str] = mapped_column(String(128), primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class VerifyCode(Base):
    """注册验证码（TS 身份认证）。

    expected_uid: 发码目标的 unique_identifier（防注册时昵称换人冒名）。
    attempts: 校验失败累计，达上限即失效（防暴力枚举）。
    """

    __tablename__ = "verify_codes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), index=True)
    code: Mapped[str] = mapped_column(String(16))
    expected_uid: Mapped[str] = mapped_column(String(128), default="", server_default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
