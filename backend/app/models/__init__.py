"""ORM 模型集合。导入即注册到 Base.metadata (init_db 建表依赖)。"""
from __future__ import annotations

from ..core.database import Base
from .account import Account, BotOwnership, BotShare, ServerMember, Session, VerifyCode
from .app_setting import AppSetting
from .community import ChannelRental, Friend, FriendRequest
from .stats import VisitStat

__all__ = [
    "Base",
    "Account",
    "ServerMember",
    "BotOwnership",
    "BotShare",
    "Session",
    "VerifyCode",
    "AppSetting",
    "ChannelRental",
    "Friend",
    "FriendRequest",
    "VisitStat",
]
