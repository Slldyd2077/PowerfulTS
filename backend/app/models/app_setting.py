"""应用级 KV 设置 — 持久化开关类配置（如「播放跟随」开关）。"""
from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class AppSetting(Base):
    """键值对设置。key 为主键（如 ``follow_enabled``），value 为字符串值。"""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), default="", server_default="")
