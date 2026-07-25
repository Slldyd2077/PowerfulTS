"""In-memory relay for user-authorized browser audio capture sessions."""
from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from typing import AsyncIterator


_END = object()


@dataclass
class LiveAudioSession:
    id: str
    account_id: int
    bot_id: str
    mime_type: str
    created_at: float = field(default_factory=time.monotonic)
    queue: asyncio.Queue[bytes | object] = field(
        default_factory=lambda: asyncio.Queue(maxsize=48)
    )
    upload_connected: bool = False
    consumer_connected: bool = False
    closed: bool = False


class LiveAudioRelay:
    """Pairs one browser WebSocket producer with one TSMusicBot HTTP consumer."""

    def __init__(self) -> None:
        self._sessions: dict[str, LiveAudioSession] = {}
        self._by_bot: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def create(
        self, account_id: int, bot_id: str, mime_type: str
    ) -> LiveAudioSession:
        async with self._lock:
            previous_id = self._by_bot.get(bot_id)
            if previous_id:
                self._close_unlocked(previous_id)
            session = LiveAudioSession(
                id=secrets.token_urlsafe(32),
                account_id=account_id,
                bot_id=bot_id,
                mime_type=mime_type,
            )
            self._sessions[session.id] = session
            self._by_bot[bot_id] = session.id
            return session

    async def get(self, session_id: str) -> LiveAudioSession | None:
        async with self._lock:
            return self._sessions.get(session_id)

    async def attach_upload(self, session_id: str) -> LiveAudioSession | None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.closed or session.upload_connected:
                return None
            session.upload_connected = True
            return session

    async def push(self, session_id: str, chunk: bytes) -> bool:
        session = await self.get(session_id)
        if session is None or session.closed or not chunk:
            return False
        try:
            await asyncio.wait_for(session.queue.put(chunk), timeout=3)
            return True
        except TimeoutError:
            # A stalled consumer must not let an unbounded live upload exhaust RAM.
            await self.close(session_id)
            return False

    async def stream(self, session_id: str) -> AsyncIterator[bytes]:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.closed or session.consumer_connected:
                return
            session.consumer_connected = True
        try:
            while True:
                item = await session.queue.get()
                if item is _END:
                    break
                yield item  # type: ignore[misc]
        finally:
            await self.close(session_id)

    async def close(self, session_id: str) -> LiveAudioSession | None:
        async with self._lock:
            return self._close_unlocked(session_id)

    def _close_unlocked(self, session_id: str) -> LiveAudioSession | None:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return None
        session.closed = True
        if self._by_bot.get(session.bot_id) == session_id:
            self._by_bot.pop(session.bot_id, None)
        try:
            session.queue.put_nowait(_END)
        except asyncio.QueueFull:
            try:
                session.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            session.queue.put_nowait(_END)
        return session

