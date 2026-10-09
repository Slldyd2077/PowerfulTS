"""Persist cumulative monitor identities independently of member notifications."""
from __future__ import annotations

import asyncio
from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..models import MonitorUser, ServerMember


class MonitorUserStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions
        self._lock = asyncio.Lock()

    async def load(self) -> set[str]:
        """Restore counts, seeding existing history without consuming first-join events."""
        async with self._lock, self._sessions() as db:
            stored = set(await db.scalars(select(MonitorUser.unique_identifier)))
            legacy = set(await db.scalars(select(ServerMember.unique_identifier)))
            missing = legacy - stored
            if missing:
                db.add_all(MonitorUser(unique_identifier=uid) for uid in missing)
                await db.commit()
            return stored | legacy

    async def save(self, user_ids: Collection[str]) -> None:
        """Insert only new identities; counts never decrease when clients leave."""
        if not user_ids:
            return
        async with self._lock, self._sessions() as db:
            existing = set(await db.scalars(
                select(MonitorUser.unique_identifier).where(
                    MonitorUser.unique_identifier.in_(user_ids)
                )
            ))
            missing = set(user_ids) - existing
            if missing:
                db.add_all(MonitorUser(unique_identifier=uid) for uid in missing)
                await db.commit()
