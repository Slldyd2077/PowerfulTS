"""访问统计 — 面板自身访问计数。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class VisitStat(Base):
    """访客 IP 计数。"""

    __tablename__ = "visit_stats"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ip: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    visit_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    last_seen: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
