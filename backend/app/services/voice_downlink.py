"""Short-lived, one-use capabilities for browser voice downlink sockets."""
from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass
from typing import Awaitable, Callable


@dataclass(frozen=True)
class VoiceDownlinkTicket:
    id: str
    account_id: int
    bot_id: str
    ephemeral: bool
    expires_at: float
    connection_expires_at: float | None


class VoiceDownlinkTickets:
    """Issues capabilities without exposing the user's login token in a WS URL."""

    def __init__(self, ttl_seconds: float = 30.0) -> None:
        self._ttl = ttl_seconds
        self._tickets: dict[str, VoiceDownlinkTicket] = {}
        self._active_accounts: frozenset[int] = frozenset()
        self._active_closers: dict[
            int, tuple[str, Callable[[int, str], Awaitable[None]]]
        ] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        account_id: int,
        bot_id: str,
        *,
        ephemeral: bool = False,
        connection_ttl_seconds: float | None = None,
    ) -> VoiceDownlinkTicket:
        async with self._lock:
            self._prune_unlocked()
            self._tickets = {
                ticket_id: existing
                for ticket_id, existing in self._tickets.items()
                if existing.account_id != account_id
            }
            ticket = VoiceDownlinkTicket(
                id=secrets.token_urlsafe(32),
                account_id=account_id,
                bot_id=bot_id,
                ephemeral=ephemeral,
                expires_at=time.monotonic() + self._ttl,
                connection_expires_at=(
                    time.monotonic() + max(0.0, connection_ttl_seconds)
                    if connection_ttl_seconds is not None
                    else None
                ),
            )
            self._tickets = {**self._tickets, ticket.id: ticket}
            return ticket

    async def claim(self, ticket_id: str) -> VoiceDownlinkTicket | None:
        """Atomically consume a ticket. A reconnect must request a new one."""
        async with self._lock:
            self._prune_unlocked()
            ticket = self._tickets.pop(ticket_id, None)
            if ticket is None or ticket.expires_at <= time.monotonic():
                return None
            if ticket.account_id in self._active_accounts:
                return None
            self._active_accounts = self._active_accounts | {ticket.account_id}
            return ticket

    async def release(self, ticket: VoiceDownlinkTicket) -> None:
        """Release the per-account stream lease after the socket closes."""
        async with self._lock:
            self._active_accounts = self._active_accounts - {ticket.account_id}
            registered = self._active_closers.get(ticket.account_id)
            if registered is not None and registered[0] == ticket.id:
                self._active_closers.pop(ticket.account_id, None)

    async def register_active(
        self,
        ticket: VoiceDownlinkTicket,
        closer: Callable[[int, str], Awaitable[None]],
    ) -> None:
        """Attach the claimed browser socket so a native TS login can close it."""
        async with self._lock:
            if ticket.account_id not in self._active_accounts:
                return
            self._active_closers = {
                **self._active_closers,
                ticket.account_id: (ticket.id, closer),
            }

    async def close_active(self, account_id: int, *, code: int, reason: str) -> bool:
        """Close one active browser downlink without exposing its capability."""
        async with self._lock:
            registered = self._active_closers.pop(account_id, None)
        if registered is None:
            return False
        await registered[1](code, reason)
        return True

    def _prune_unlocked(self) -> None:
        now = time.monotonic()
        self._tickets = {
            ticket_id: ticket
            for ticket_id, ticket in self._tickets.items()
            if ticket.expires_at > now
        }
