import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI

from app.core.database import get_db
from app.deps import get_current_account, get_tsmusic
from app.routers import music


@pytest.mark.parametrize("saved,expected", [("ts.example.com", "ts.example.com"), ("", "env-ts.example.com")])
def test_defaults_use_saved_host_then_environment_without_query_port(saved, expected):
    async def scenario():
        app = FastAPI()
        app.include_router(music.router)
        app.dependency_overrides[get_current_account] = lambda: SimpleNamespace(id=7)
        app.dependency_overrides[get_db] = lambda: SimpleNamespace()
        with patch.object(music, "settings", SimpleNamespace(ts3_host="env-ts.example.com", ts3_query_port=10022)), patch(
            "app.services.app_setting.get_setting", AsyncMock(return_value=saved)
        ) as read:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/music/bots/defaults")
        assert response.status_code == 200, response.text
        assert response.json() == {"serverAddress": expected, "serverPort": 9987}
        assert read.await_args.args[1] == "sys.ts3_host"
    asyncio.run(scenario())


@pytest.mark.parametrize("address,expected", [(None, "configured-ts.example.com"), ("custom.example.com", "custom.example.com")])
def test_create_resolves_missing_address_and_preserves_explicit_address(address, expected):
    async def scenario():
        upstream = SimpleNamespace(create_bot=AsyncMock(return_value={"id": "abc-123"}))
        db = SimpleNamespace(add=lambda row: None, commit=AsyncMock())
        body = music.BotCreate(name="Test Bot", **({"serverAddress": address} if address else {}))
        with patch("app.services.app_setting.get_setting", AsyncMock(return_value="configured-ts.example.com")):
            await music.create_bot(body, upstream, SimpleNamespace(id=7), db)
        payload = upstream.create_bot.await_args.args[0]
        assert payload["serverAddress"] == expected
        assert payload["serverPort"] == 9987
    asyncio.run(scenario())
