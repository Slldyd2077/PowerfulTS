"""Bot 播放器持久化状态。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class BotPlayerState(Base):
    """跨 Bot 下线保存音量和播放队列。"""

    __tablename__ = "bot_player_states"

    bot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    volume: Mapped[int] = mapped_column(Integer, default=50, server_default="50")
    queue_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
