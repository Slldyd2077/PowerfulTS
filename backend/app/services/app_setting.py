"""应用级 KV 设置读写（SQLite + SQLAlchemy async）。

纯函数风格（同 ts3_auth），供 TSMusicClient 单例在加载/保存「播放跟随」开关时调用。
通用 get/update-or-insert 写法，不绑定 SQLite 方言，平滑兼容 PG/MySQL。
"""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.app_setting import AppSetting


async def get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    """读取某 key 的值，缺失返回 default。"""
    row = await session.get(AppSetting, key)
    return row.value if row is not None else default


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    """UPSERT 写入 key=value（先查再 update/insert，跨库通用）。

    并发首次写时 INSERT 可能撞 PK（IntegrityError），回滚后按已存在行 update 重试。
    """
    existing = await session.get(AppSetting, key)
    if existing is None:
        session.add(AppSetting(key=key, value=value))
        try:
            await session.commit()
            return
        except IntegrityError:
            await session.rollback()
            existing = await session.get(AppSetting, key)
    if existing is not None:
        existing.value = value
        await session.commit()
