"""Bot 音量与队列的 SQLite 持久化读写。"""
from __future__ import annotations

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..models.bot_player_state import BotPlayerState

logger = logging.getLogger(__name__)


class BotPlayerStateStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, bot_id: str, volume: int, queue: list[dict]) -> None:
        payload = json.dumps(queue, ensure_ascii=False, separators=(",", ":"), default=str)
        async with self._session_factory() as session:
            row = await session.get(BotPlayerState, bot_id)
            if row is None:
                row = BotPlayerState(bot_id=bot_id)
                session.add(row)
            row.volume = max(0, min(100, int(volume)))
            row.queue_json = payload
            await session.commit()

    async def load(self, bot_id: str) -> dict | None:
        async with self._session_factory() as session:
            row = await session.get(BotPlayerState, bot_id)
            if row is None:
                return None
            try:
                queue = json.loads(row.queue_json)
            except (TypeError, ValueError):
                logger.warning("Bot %s 的持久化队列损坏，按空队列处理", bot_id)
                queue = []
            return {
                "volume": max(0, min(100, int(row.volume))),
                "queue": [item for item in queue if isinstance(item, dict)]
                if isinstance(queue, list)
                else [],
            }

    async def delete(self, bot_id: str) -> None:
        async with self._session_factory() as session:
            row = await session.get(BotPlayerState, bot_id)
            if row is not None:
                await session.delete(row)
                await session.commit()
