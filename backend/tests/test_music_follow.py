from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.routers import music


class MusicFollowTests(IsolatedAsyncioTestCase):
    async def test_play_command_runs_before_channel_follow(self) -> None:
        events: list[str] = []

        class FakeClient:
            async def play(self, *_args, **_kwargs):
                events.append("play")
                return {"success": True}

        async def fake_follow(*_args, **_kwargs):
            events.append("follow")
            return {"moved": True, "reason": "moved"}

        with patch("app.routers.music._ensure_follow", new=fake_follow):
            result = await music.play(
                music.PlayRequest(query="id:1"),
                SimpleNamespace(),
                FakeClient(),
                SimpleNamespace(ts_nickname="listener"),
                "bot-id",
            )

        self.assertEqual(events, ["play", "follow"])
        self.assertEqual(result["follow"], {"moved": True, "reason": "moved"})

    async def test_follow_retries_while_reconnecting_and_refreshes_nickname(self) -> None:
        client = SimpleNamespace(
            follow_enabled=True,
            get_bot_nickname=AsyncMock(side_effect=["OldNick", "NewNick"]),
        )
        missing = {"moved": False, "reason": "bot_not_found"}
        moved = {"moved": True, "reason": "moved", "user_cid": 7}
        stable = {"moved": False, "reason": "already_together", "user_cid": 7}

        with (
            patch(
                "app.routers.music.asyncio.to_thread",
                new=AsyncMock(side_effect=[missing, moved, stable, stable]),
            ) as mover,
            patch("app.routers.music.asyncio.sleep", new=AsyncMock()) as sleep,
        ):
            result = await music._ensure_follow(
                SimpleNamespace(),
                client,
                SimpleNamespace(ts_nickname="listener"),
                "bot-id",
            )

        self.assertTrue(result["moved"])
        client.get_bot_nickname.assert_any_await("bot-id", refresh=True)
        self.assertEqual(mover.await_count, 4)
        self.assertEqual(sleep.await_count, 3)

    async def test_follow_rechecks_after_move_to_prevent_default_channel_race(self) -> None:
        client = SimpleNamespace(
            follow_enabled=True,
            get_bot_nickname=AsyncMock(return_value="BotNick"),
        )
        moved = {"moved": True, "reason": "moved", "user_cid": 9}
        moved_back = {"moved": True, "reason": "moved", "user_cid": 9}
        stable = {"moved": False, "reason": "already_together", "user_cid": 9}

        with (
            patch(
                "app.routers.music.asyncio.to_thread",
                new=AsyncMock(side_effect=[moved, stable, moved_back, stable, stable]),
            ) as mover,
            patch("app.routers.music.asyncio.sleep", new=AsyncMock()),
        ):
            result = await music._ensure_follow(
                SimpleNamespace(),
                client,
                SimpleNamespace(ts_nickname="listener"),
                "bot-id",
            )

        self.assertEqual(mover.await_count, 5)
        self.assertEqual(result["reason"], "moved")
        self.assertTrue(result["moved"])
