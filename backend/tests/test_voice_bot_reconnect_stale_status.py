import asyncio
import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

import pytest

try:
    import sqlite3  # noqa: F401
except ImportError as exc:
    if "_sqlite3" not in str(exc):
        raise
    models = types.ModuleType("app.models")

    class _Model:
        pass

    models.Account = _Model
    models.BotOwnership = _Model
    models.Session = _Model
    models.VoiceBot = _Model
    sys.modules["app.models"] = models

    tsmusic_client = types.ModuleType("app.services.tsmusic_client")
    tsmusic_client.TSMusicClient = _Model
    sys.modules["app.services.tsmusic_client"] = tsmusic_client

from app.services.voice_bot import VoiceBotError, VoiceBotManager


class FakeTsmusic:
    """A TSMusicBot facade whose bot list can be stale while TS socket health is not."""

    def __init__(self, client_ids: list[int | None]) -> None:
        self.client_ids = client_ids
        self.started: list[str] = []
        self.list_calls = 0
        self.client_id_checks = 0

    async def list_bots(self) -> list[dict]:
        self.list_calls += 1
        return [{"id": "voice-bot", "status": "connected"}]

    async def get_bot_client_id(self, bot_id: str) -> int | None:
        assert bot_id == "voice-bot"
        self.client_id_checks += 1
        if not self.client_ids:
            return None
        return self.client_ids.pop(0)

    async def start_bot(self, bot_id: str) -> dict:
        self.started.append(bot_id)
        return {"ok": True}


class ProbeManager(VoiceBotManager):
    def __init__(self, tsmusic: FakeTsmusic) -> None:
        super().__init__(lambda: tsmusic)
        self.capacity_checked_for: list[int] = []

    async def _ensure_bot(self, _db, _tsmusic, _account) -> str:
        return "voice-bot"

    async def _ensure_guest_capacity(self, _db, account) -> None:
        self.capacity_checked_for.append(account.id)


async def _acquire_with_probe(role: str, client_ids: list[int | None]):
    tsmusic = FakeTsmusic(client_ids)
    manager = ProbeManager(tsmusic)
    account = SimpleNamespace(id=7, role=role, ts_nickname=f"{role}-user")
    with (
        patch("app.services.voice_bot.CONNECT_TIMEOUT_SECONDS", 0.05),
        patch("app.services.voice_bot._CONNECT_POLL_SECONDS", 0.01),
    ):
        session = await manager.acquire(None, account)
    return session, tsmusic, manager


@pytest.mark.parametrize("role", ["member", "guest"])
def test_stale_connected_status_restarts_once_before_returning_session(role: str) -> None:
    async def scenario():
        return await _acquire_with_probe(role, [None, 42])

    session, tsmusic, manager = asyncio.run(scenario())

    assert session == {"botId": "voice-bot", "nickname": f"{role}-user"}
    assert tsmusic.started == ["voice-bot"]
    assert tsmusic.client_id_checks >= 2
    if role == "guest":
        assert manager.capacity_checked_for == [7]
    else:
        assert manager.capacity_checked_for == []


@pytest.mark.parametrize("role", ["member", "guest"])
def test_healthy_connected_voice_identity_does_not_restart(role: str) -> None:
    async def scenario():
        return await _acquire_with_probe(role, [42])

    session, tsmusic, _manager = asyncio.run(scenario())

    assert session == {"botId": "voice-bot", "nickname": f"{role}-user"}
    assert tsmusic.started == []
    assert tsmusic.client_id_checks == 1


@pytest.mark.parametrize("role", ["member", "guest"])
def test_reconnect_failure_returns_a_clear_session_error(role: str) -> None:
    async def scenario():
        return await _acquire_with_probe(role, [None, None, None])

    with pytest.raises(VoiceBotError, match="连接|重连|语音"):
        asyncio.run(scenario())
