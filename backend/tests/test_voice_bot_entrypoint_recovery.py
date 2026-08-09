import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.routers import music
from app.services.voice_bot import VoiceBotError, VoiceBotManager


@pytest.mark.parametrize("role", ["member", "guest"])
def test_existing_voice_entrypoint_revalidates_connection(role: str) -> None:
    async def scenario() -> None:
        voice_bots = SimpleNamespace(
            ensure_existing_connected=AsyncMock(return_value="voice-bot")
        )
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(voice_bots=voice_bots))
        )
        account = SimpleNamespace(id=17, role=role)
        db = object()

        assert await music._voice_bot_id(request, account, db) == "voice-bot"
        voice_bots.ensure_existing_connected.assert_awaited_once_with(db, 17)

    asyncio.run(scenario())


def test_existing_voice_entrypoint_maps_recovery_failure_to_conflict() -> None:
    async def scenario() -> None:
        voice_bots = SimpleNamespace(
            ensure_existing_connected=AsyncMock(
                side_effect=VoiceBotError("voice bot could not reconnect")
            )
        )
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(voice_bots=voice_bots))
        )

        with pytest.raises(HTTPException) as exc_info:
            await music._voice_bot_id(
                request,
                SimpleNamespace(id=17, role="member"),
                object(),
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "voice bot could not reconnect"

    asyncio.run(scenario())


def test_failed_existing_recovery_keeps_pending_release() -> None:
    async def scenario() -> None:
        tsmusic = SimpleNamespace(delete_bot=AsyncMock(return_value={}))
        manager = VoiceBotManager(lambda: tsmusic)
        manager.current_bot_id = AsyncMock(return_value="voice-bot")
        manager._ensure_connected = AsyncMock(
            side_effect=VoiceBotError("voice bot could not reconnect")
        )
        with patch("app.services.voice_bot.RELEASE_GRACE_SECONDS", 0.02):
            manager.schedule_release(17, "voice-bot", destroy=True)
            with pytest.raises(VoiceBotError):
                await manager.ensure_existing_connected(object(), 17)
            await asyncio.sleep(0.04)

        tsmusic.delete_bot.assert_awaited_once_with("voice-bot")

    asyncio.run(scenario())


def test_successful_existing_recovery_refreshes_release_grace() -> None:
    async def scenario() -> None:
        tsmusic = SimpleNamespace(delete_bot=AsyncMock(return_value={}))
        manager = VoiceBotManager(lambda: tsmusic)
        manager.current_bot_id = AsyncMock(return_value="voice-bot")
        manager._ensure_connected = AsyncMock(return_value=None)
        with patch("app.services.voice_bot.RELEASE_GRACE_SECONDS", 0.05):
            manager.schedule_release(17, "voice-bot", destroy=True)
            await asyncio.sleep(0.04)
            assert await manager.ensure_existing_connected(object(), 17) == "voice-bot"
            await asyncio.sleep(0.02)
            tsmusic.delete_bot.assert_not_awaited()
            await asyncio.sleep(0.05)

        tsmusic.delete_bot.assert_awaited_once_with("voice-bot")

    asyncio.run(scenario())
