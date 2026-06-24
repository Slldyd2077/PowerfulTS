"""原生数据层 — SQLAlchemy 2.0 async + SQLite。

默认零依赖文件库 (data/powerfults.db)；改 DATABASE_URL 可平滑切换 PostgreSQL/MySQL。
SQLite 开启 WAL 模式以支持并发读 + 单写。
"""
from __future__ import annotations

import logging
import os
from typing import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class Base(DeclarativeBase):
    """所有 ORM 模型的声明基类。"""


def _ensure_sqlite_dir() -> None:
    """SQLite 文件库：确保目录存在。"""
    url = settings.database_url
    if not url.startswith("sqlite"):
        return
    path = url.split("///")[-1]  # sqlite+aiosqlite:///./data/x.db → ./data/x.db
    db_dir = os.path.dirname(path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)


_ensure_sqlite_dir()

engine = create_async_engine(settings.database_url, echo=False, future=True)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
    """SQLite 专用：连接建立时开启 WAL + 外键约束。"""
    if not settings.database_url.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：提供一个异步数据库会话。"""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """启动时建表（幂等）。需在导入所有模型后调用。"""
    from .. import models  # noqa: F401  触发模型注册到 Base.metadata

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # 日志只输出驱动名，避免切换 PG/MySQL 后连接串(含密码)落盘
    driver = settings.database_url.split("://")[0]
    logger.info("数据库初始化完成 (driver=%s)", driver)


async def dispose_db() -> None:
    """关闭连接池。"""
    await engine.dispose()
