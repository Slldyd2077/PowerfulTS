import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from app.services.tsmusic_client import TSMusicClient
from app.services.voice_bot import VoiceBotError, VoiceBotManager


@pytest.mark.parametrize("error", [httpx.ReadTimeout("upstream timed out"), ValueError("bad list")])
def test_upstream_list_failure_preserves_existing_voice_identity(error):
    async def scenario():
        upstream = SimpleNamespace(
            list_bots=AsyncMock(return_value=[]),
            list_bots_checked=AsyncMock(side_effect=error),
            create_bot=AsyncMock(),
        )
        db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock(), add=Mock())
        manager = VoiceBotManager(lambda: upstream)
        manager.current_bot_id = AsyncMock(return_value="existing-voice-bot")
        account = SimpleNamespace(id=17, ts_nickname="test-user")
        with pytest.raises(VoiceBotError, match="读取.*机器人"):
            await manager._ensure_bot(db, upstream, account)
        db.execute.assert_not_awaited()
        db.commit.assert_not_awaited()
        upstream.create_bot.assert_not_awaited()

    asyncio.run(scenario())


def test_confirmed_missing_upstream_bot_is_recreated():
    async def scenario():
        upstream = SimpleNamespace(
            list_bots_checked=AsyncMock(return_value=[]),
            create_bot=AsyncMock(return_value={"id": "replacement"}),
        )
        db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock(), add=Mock())
        manager = VoiceBotManager(lambda: upstream)
        manager.current_bot_id = AsyncMock(return_value="deleted-voice-bot")
        account = SimpleNamespace(id=17, ts_nickname="test-user")
        target = SimpleNamespace(server_address="ts.test", server_port=9987, server_password="")
        with patch("app.services.voice_bot._resolve_server_target", AsyncMock(return_value=target)):
            assert await manager._ensure_bot(db, upstream, account) == "replacement"
        db.execute.assert_awaited_once()
        upstream.create_bot.assert_awaited_once()

    asyncio.run(scenario())


def test_existing_upstream_bot_is_reused_without_database_writes():
    async def scenario():
        upstream = SimpleNamespace(
            list_bots_checked=AsyncMock(return_value=[{"id": "existing-voice-bot"}]),
            create_bot=AsyncMock(),
        )
        db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
        manager = VoiceBotManager(lambda: upstream)
        manager.current_bot_id = AsyncMock(return_value="existing-voice-bot")
        assert await manager._ensure_bot(db, upstream, SimpleNamespace(id=17)) == "existing-voice-bot"
        db.execute.assert_not_awaited()
        db.commit.assert_not_awaited()
        upstream.create_bot.assert_not_awaited()

    asyncio.run(scenario())


def test_connect_deadline_includes_start_request():
    async def scenario():
        async def slow_start(_bot_id):
            await asyncio.sleep(0.08)

        upstream = SimpleNamespace(start_bot=AsyncMock(side_effect=slow_start))
        manager = VoiceBotManager(lambda: upstream)
        manager._is_connected = AsyncMock(side_effect=[False, True])
        with patch("app.services.voice_bot.CONNECT_TIMEOUT_SECONDS", 0.01):
            with pytest.raises(VoiceBotError, match="连接 TS 超时"):
                await manager._ensure_connected(upstream, "voice-bot")

    asyncio.run(scenario())


def test_start_error_payload_fails_without_polling_until_timeout():
    async def scenario():
        upstream = SimpleNamespace(start_bot=AsyncMock(return_value={"error": "handshake failed"}))
        manager = VoiceBotManager(lambda: upstream)
        manager._is_connected = AsyncMock(return_value=False)
        with pytest.raises(VoiceBotError, match="未能连接 TS"):
            await manager._ensure_connected(upstream, "voice-bot")
        manager._is_connected.assert_awaited_once()

    asyncio.run(scenario())


@pytest.mark.parametrize("payload", [{}, {"error": "upstream unavailable"}, {"data": {}}])
def test_checked_bot_list_rejects_missing_array(payload):
    async def scenario():
        client = TSMusicClient("http://tsmusic.test", "user", "password")
        client._logged_in = True
        client._request = AsyncMock(return_value=httpx.Response(
            200, json=payload, request=httpx.Request("GET", "http://tsmusic.test/api/bot"),
        ))
        try:
            with pytest.raises(ValueError, match="bots array"):
                await client.list_bots_checked()
        finally:
            await client.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("payload", [{"bots": []}, {"data": {"bots": []}}])
def test_checked_bot_list_accepts_an_explicit_empty_array(payload):
    async def scenario():
        client = TSMusicClient("http://tsmusic.test", "user", "password")
        client._logged_in = True
        client._request = AsyncMock(return_value=httpx.Response(
            200, json=payload, request=httpx.Request("GET", "http://tsmusic.test/api/bot"),
        ))
        try:
            assert await client.list_bots_checked() == []
        finally:
            await client.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("bots", [[None], [{"name": "voice"}], [{"id": "valid"}, None]])
def test_checked_bot_list_rejects_partial_or_invalid_records(bots):
    async def scenario():
        client = TSMusicClient("http://tsmusic.test", "user", "password")
        client._logged_in = True
        client._request = AsyncMock(return_value=httpx.Response(
            200, json={"bots": bots}, request=httpx.Request("GET", "http://tsmusic.test/api/bot"),
        ))
        try:
            with pytest.raises(ValueError, match="invalid bot"):
                await client.list_bots_checked()
        finally:
            await client.close()

    asyncio.run(scenario())


def test_upstream_start_failure_is_reported_without_restoring_player():
    async def scenario():
        client = TSMusicClient("http://tsmusic.test", "user", "password")
        client._logged_in = True
        client._request = AsyncMock(return_value=httpx.Response(
            500, json={"error": "connect timeout after 15000ms"},
            request=httpx.Request("POST", "http://tsmusic.test/api/bot/voice-bot/start"),
        ))
        client.restore_player_state = AsyncMock()
        try:
            with pytest.raises(httpx.HTTPStatusError):
                await client.start_bot("voice-bot")
            client.restore_player_state.assert_not_awaited()
        finally:
            await client.close()

    asyncio.run(scenario())
