"""Short-lived, one-use capabilities for browser voice downlink sockets."""
from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceDownlinkTicket:
    id: str
    account_id: int
    bot_id: str
    expires_at: float


class VoiceDownlinkTickets:
    """Issues capabilities without exposing the user's login token in a WS URL."""

    def __init__(self, ttl_seconds: float = 30.0) -> None:
        self._ttl = ttl_seconds
        self._tickets: dict[str, VoiceDownlinkTicket] = {}
        self._lock = asyncio.Lock()

    async def create(self, account_id: int, bot_id: str) -> VoiceDownlinkTicket:
        async with self._lock:
            self._prune_unlocked()
            ticket = VoiceDownlinkTicket(
                id=secrets.token_urlsafe(32),
                account_id=account_id,
                bot_id=bot_id,
                expires_at=time.monotonic() + self._ttl,
            )
            self._tickets[ticket.id] = ticket
            return ticket

    async def claim(self, ticket_id: str) -> VoiceDownlinkTicket | None:
        """Atomically consume a ticket. A reconnect must request a new one."""
        async with self._lock:
            self._prune_unlocked()
            ticket = self._tickets.pop(ticket_id, None)
            if ticket is None or ticket.expires_at <= time.monotonic():
                return None
            return ticket

    def _prune_unlocked(self) -> None:
        now = time.monotonic()
        for ticket_id, ticket in list(self._tickets.items()):
            if ticket.expires_at <= now:
                self._tickets.pop(ticket_id, None)
