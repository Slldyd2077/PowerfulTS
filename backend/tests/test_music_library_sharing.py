from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.routers.music import _library_bot_id


class PersonalLibraryBotIdTests(IsolatedAsyncioTestCase):
    async def test_rejects_a_shared_bot_for_private_library_reads(self) -> None:
        account = SimpleNamespace(id=7)
        db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(first=lambda: None)))
        with patch("app.routers.music._owned_bot_ids", new=AsyncMock(return_value={"own-bot"})):
            with self.assertRaises(HTTPException) as raised:
                await _library_bot_id("shared-bot", account, db)

        self.assertEqual(raised.exception.status_code, 403)

    async def test_accepts_the_current_users_own_bot(self) -> None:
        account = SimpleNamespace(id=7)
        with patch("app.routers.music._owned_bot_ids", new=AsyncMock(return_value={"own-bot"})):
            result = await _library_bot_id("own-bot", account, AsyncMock())

        self.assertEqual(result, "own-bot")

    async def test_accepts_shared_bot_when_playlist_access_was_granted(self) -> None:
        account = SimpleNamespace(id=7)
        db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(first=lambda: (1,))))
        with patch("app.routers.music._owned_bot_ids", new=AsyncMock(return_value={"own-bot"})):
            result = await _library_bot_id("shared-bot", account, db)

        self.assertEqual(result, "shared-bot")

    async def test_resolves_an_owned_bot_when_shared_bot_is_active_client_side(self) -> None:
        account = SimpleNamespace(id=7)
        with patch("app.routers.music._owned_bot_ids", new=AsyncMock(return_value={"own-bot"})):
            result = await _library_bot_id(None, account, AsyncMock())

        self.assertEqual(result, "own-bot")
