"""In-memory relay for user-authorized browser audio capture sessions."""
from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable


_END = object()


@dataclass(frozen=True)
class LiveAudioChunk:
    payload: bytes
    enqueued_at: float
    enqueued_wall_ms: int
    metrics_ready: asyncio.Event = field(default_factory=asyncio.Event, repr=False)


@dataclass
class LiveAudioSession:
    id: str
    account_id: int
    bot_id: str
    mime_type: str
    created_at: float = field(default_factory=time.monotonic)
    queue: asyncio.Queue[LiveAudioChunk | object] = field(
        default_factory=lambda: asyncio.Queue(maxsize=48)
    )
    upload_connected: bool = False
    consumer_connected: bool = False
    closed: bool = False
    queued_chunks: int = 0
    queued_bytes: int = 0
    peak_queued_chunks: int = 0
    peak_queued_bytes: int = 0
    chunks_pushed: int = 0
    bytes_pushed: int = 0
    chunks_streamed: int = 0
    bytes_streamed: int = 0
    last_enqueue_at: int | None = None
    last_dequeue_at: int | None = None
    last_queue_dwell_ms: int | None = None
    max_queue_dwell_ms: int = 0


class LiveAudioRelay:
    """Pairs one browser WebSocket producer with one TSMusicBot HTTP consumer."""

    def __init__(
        self,
        *,
        monotonic_fn: Callable[[], float] = time.monotonic,
        wall_time_fn: Callable[[], float] = lambda: time.time() * 1000,
    ) -> None:
        self._sessions: dict[str, LiveAudioSession] = {}
        self._by_bot: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._monotonic_fn = monotonic_fn
        self._wall_time_fn = wall_time_fn

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
                created_at=self._monotonic_fn(),
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
        item = LiveAudioChunk(
            payload=bytes(chunk),
            enqueued_at=self._monotonic_fn(),
            enqueued_wall_ms=round(self._wall_time_fn()),
        )
        try:
            await asyncio.wait_for(session.queue.put(item), timeout=3)
            size = len(item.payload)
            session.queued_chunks += 1
            session.queued_bytes += size
            session.peak_queued_chunks = max(
                session.peak_queued_chunks, session.queued_chunks
            )
            session.peak_queued_bytes = max(
                session.peak_queued_bytes, session.queued_bytes
            )
            session.chunks_pushed += 1
            session.bytes_pushed += size
            session.last_enqueue_at = item.enqueued_wall_ms
            item.metrics_ready.set()
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
                if not isinstance(item, LiveAudioChunk):
                    continue
                await item.metrics_ready.wait()
                size = len(item.payload)
                dwell_ms = max(
                    0, round((self._monotonic_fn() - item.enqueued_at) * 1000)
                )
                session.queued_chunks = max(0, session.queued_chunks - 1)
                session.queued_bytes = max(0, session.queued_bytes - size)
                session.chunks_streamed += 1
                session.bytes_streamed += size
                session.last_dequeue_at = round(self._wall_time_fn())
                session.last_queue_dwell_ms = dwell_ms
                session.max_queue_dwell_ms = max(
                    session.max_queue_dwell_ms, dwell_ms
                )
                yield item.payload
        finally:
            await self.close(session_id)

    async def status_for_bot(self, bot_id: str) -> dict:
        """Return bounded queue telemetry without exposing capability ids."""
        async with self._lock:
            session_id = self._by_bot.get(bot_id)
            session = self._sessions.get(session_id) if session_id else None
        if session is None:
            return self._inactive_status()
        if session.closed:
            return self._inactive_status()
        return {
            "active": True,
            "uploadConnected": session.upload_connected,
            "consumerConnected": session.consumer_connected,
            "queuedChunks": session.queued_chunks,
            "queuedBytes": session.queued_bytes,
            "peakQueuedChunks": session.peak_queued_chunks,
            "peakQueuedBytes": session.peak_queued_bytes,
            "chunksPushed": session.chunks_pushed,
            "bytesPushed": session.bytes_pushed,
            "chunksStreamed": session.chunks_streamed,
            "bytesStreamed": session.bytes_streamed,
            "lastEnqueueAt": session.last_enqueue_at,
            "lastDequeueAt": session.last_dequeue_at,
            "lastQueueDwellMs": session.last_queue_dwell_ms,
            "maxQueueDwellMs": session.max_queue_dwell_ms,
        }

    @staticmethod
    def _inactive_status() -> dict:
        return {
            "active": False,
            "uploadConnected": False,
            "consumerConnected": False,
            "queuedChunks": 0,
            "queuedBytes": 0,
            "peakQueuedChunks": 0,
            "peakQueuedBytes": 0,
            "chunksPushed": 0,
            "bytesPushed": 0,
            "chunksStreamed": 0,
            "bytesStreamed": 0,
            "lastEnqueueAt": None,
            "lastDequeueAt": None,
            "lastQueueDwellMs": None,
            "maxQueueDwellMs": 0,
        }

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

