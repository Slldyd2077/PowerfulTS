import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.voice_bot import VoiceBotError, VoiceBotManager, _resolve_server_target


@pytest.mark.parametrize("password", ["", "fake-ts6-server-password", " password with spaces "])
def test_voice_bot_inherits_server_password_without_exposing_it(password, caplog):
    async def scenario():
        tsmusic = SimpleNamespace(
            list_bots_checked=AsyncMock(return_value=[]),
            get_bot_config=AsyncMock(return_value={
                "serverAddress": "ts6.test.invalid",
                "serverPort": 9999,
                "serverPassword": password,
                "identity": "fake-private-identity",
                "ts6ApiKey": "fake-query-secret",
            }),
            create_bot=AsyncMock(return_value={"id": "new-voice-bot"}),
            get_bot_client_id=AsyncMock(return_value=42),
        )
        owned_rows = Mock()
        owned_rows.all.return_value = [("existing-music-bot",)]
        db = SimpleNamespace(
            execute=AsyncMock(return_value=owned_rows),
            add=Mock(),
            commit=AsyncMock(),
        )
        manager = VoiceBotManager(lambda: tsmusic)
        manager.current_bot_id = AsyncMock(return_value=None)
        manager._ensure_connected = AsyncMock()
        account = SimpleNamespace(id=17, role="member", ts_nickname="test-user")

        result = await manager.acquire(db, account)
        payload = tsmusic.create_bot.call_args.args[0]
        assert payload["serverPassword"] == password
        assert payload["serverAddress"] == "ts6.test.invalid"
        assert payload["serverPort"] == 9999
        assert "identity" not in payload
        assert "ts6ApiKey" not in payload
        assert result == {"botId": "new-voice-bot", "nickname": "test-user"}

        target = await _resolve_server_target(tsmusic, db)
        if password:
            assert password not in repr(target)

    with caplog.at_level(logging.INFO, logger="app.services.voice_bot"):
        asyncio.run(scenario())
    if password:
        assert password not in caplog.text


def test_voice_bot_does_not_invent_password_when_upstream_config_omits_it():
    async def scenario():
        tsmusic = SimpleNamespace(get_bot_config=AsyncMock(return_value={
            "serverAddress": "ts3.test.invalid",
        }))
        owned_rows = Mock()
        owned_rows.all.return_value = [("existing-music-bot",)]
        db = SimpleNamespace(execute=AsyncMock(return_value=owned_rows))
        target = await _resolve_server_target(tsmusic, db)
        assert target.server_port == 9987
        assert target.server_password == ""

    asyncio.run(scenario())


@pytest.mark.parametrize("password", [None, 123, {"masked": True}])
def test_invalid_upstream_password_is_not_forwarded_or_exposed(password):
    async def scenario():
        tsmusic = SimpleNamespace(get_bot_config=AsyncMock(return_value={
            "serverAddress": "ts6.test.invalid",
            "serverPassword": password,
        }))
        owned_rows = Mock()
        owned_rows.all.return_value = [("existing-music-bot",)]
        db = SimpleNamespace(execute=AsyncMock(return_value=owned_rows))
        with pytest.raises(VoiceBotError, match="服务器密码"):
            await _resolve_server_target(tsmusic, db)

    asyncio.run(scenario())
