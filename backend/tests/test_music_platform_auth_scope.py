import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI

from app.core.database import get_db
from app.deps import get_current_account, get_tsmusic
from app.routers import music


AUTH_ROUTES = [
    ("GET", "/music/auth/qrcode/status", {"key": "qr", "platform": "qq"}, None, "get_qrcode_status"),
    ("POST", "/music/auth/qrcode", {}, {"platform": "qq"}, "get_qrcode"),
    ("POST", "/music/auth/cookie", {}, {"platform": "qq", "cookie": "test-cookie"}, "set_cookie"),
    ("DELETE", "/music/auth/cookie", {"platform": "qq"}, None, "delete_cookie"),
    ("POST", "/music/auth/jellyfin/test", {}, {"serverUrl": "http://jellyfin:8096"}, "jellyfin_test"),
    ("POST", "/music/auth/jellyfin/login", {}, {"serverUrl": "http://jellyfin:8096"}, "jellyfin_login"),
]


@pytest.mark.parametrize("method,path,params,body,upstream_method", AUTH_ROUTES)
@pytest.mark.parametrize("bot_id,status", [(None, 400), ("def-456", 403), ("abc-123", 200)])
def test_platform_credentials_require_an_explicit_owned_bot(
    method, path, params, body, upstream_method, bot_id, status
):
    async def scenario():
        app = FastAPI()
        app.include_router(music.router)
        account = SimpleNamespace(id=7)
        upstream = SimpleNamespace(**{
            route[-1]: AsyncMock(return_value={"success": True}) for route in AUTH_ROUTES
        })
        app.dependency_overrides[get_current_account] = lambda: account
        app.dependency_overrides[get_db] = lambda: SimpleNamespace()
        app.dependency_overrides[get_tsmusic] = lambda: upstream
        query = {**params, **({"botId": bot_id} if bot_id is not None else {})}
        with patch("app.routers.music._owned_bot_ids", AsyncMock(return_value={"abc-123"})):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://powerfults.test"
            ) as client:
                response = await client.request(method, path, params=query, json=body)
        assert response.status_code == status, response.text
        if status == 200:
            called = getattr(upstream, upstream_method)
            called.assert_awaited_once()
            assert called.await_args.kwargs["bot_id"] == "abc-123"
        else:
            for handler in vars(upstream).values():
                handler.assert_not_awaited()

    asyncio.run(scenario())
