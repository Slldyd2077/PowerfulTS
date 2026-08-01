import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.routers.music import _ensure_follow
from app.services.bot_mover import move_bot_to_user


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        ts3_host="127.0.0.1",
        ts3_query_port=10011,
        ts3_query_user="query",
        ts3_query_password="secret",
        ts3_sid=1,
    )


def _user() -> SimpleNamespace:
    return SimpleNamespace(
        unique_identifier="user-uid",
        ts_nickname="Alice",
    )


class FakeQuery:
    def __init__(self, clients: list[dict]) -> None:
        self.clients = clients
        self.commands: list[tuple[str, dict]] = []

    def connect(self) -> None:
        pass

    def close(self) -> None:
        pass

    def send(self, command: str, **params):
        self.commands.append((command, params))
        if command == "clientlist":
            return self.clients
        return []


class BotMoverTests(unittest.TestCase):
    def test_moves_by_stable_client_id_when_playing_changed_nickname(self) -> None:
        query = FakeQuery(
            [
                {
                    "client_type": "0",
                    "clid": "42",
                    "cid": "3",
                    "client_nickname": "♪ 当前歌曲 - 点歌姬",
                    "client_unique_identifier": "bot-uid",
                },
                {
                    "client_type": "0",
                    "clid": "7",
                    "cid": "9",
                    "client_nickname": "Alice",
                    "client_unique_identifier": "user-uid",
                },
            ]
        )

        with patch("app.services.bot_mover.TS3QueryClient", return_value=query):
            result = move_bot_to_user(_settings(), 42, "MusicBot", _user())

        self.assertEqual(result["reason"], "moved")
        self.assertIn(("clientmove", {"clid": 42, "cid": 9}), query.commands)

    def test_falls_back_to_config_nickname_for_old_upstream(self) -> None:
        query = FakeQuery(
            [
                {
                    "client_type": "0",
                    "clid": "42",
                    "cid": "3",
                    "client_nickname": "MusicBot",
                },
                {
                    "client_type": "0",
                    "clid": "7",
                    "cid": "9",
                    "client_nickname": "Alice",
                    "client_unique_identifier": "user-uid",
                },
            ]
        )

        with patch("app.services.bot_mover.TS3QueryClient", return_value=query):
            result = move_bot_to_user(_settings(), None, "MusicBot", _user())

        self.assertEqual(result["reason"], "moved")
        self.assertIn(("clientmove", {"clid": 42, "cid": 9}), query.commands)


class FollowBeforePlaybackTests(unittest.IsolatedAsyncioTestCase):
    async def test_reconnects_auto_disconnected_bot_before_resolving_clid(self) -> None:
        class FakeTSMusic:
            follow_enabled = True

            def __init__(self) -> None:
                self.ready = False

            async def ensure_player_ready(self, bot_id: str) -> None:
                self.ready = True

            async def get_bot_client_id(self, bot_id: str) -> int:
                self.assert_ready()
                return 42

            async def get_bot_nickname(self, bot_id: str) -> str:
                return "MusicBot"

            def assert_ready(self) -> None:
                if not self.ready:
                    raise AssertionError("bot identity was queried before reconnect")

        tsmusic = FakeTSMusic()
        account = _user()
        moved_with: list[tuple[int | None, str | None]] = []

        def fake_move(_settings, client_id, nickname, _account):
            moved_with.append((client_id, nickname))
            return {"moved": True, "reason": "moved", "user_cid": 9, "bot_cid": 9}

        with patch("app.routers.music.bot_mover.move_bot_to_user", side_effect=fake_move):
            result = await _ensure_follow(SimpleNamespace(), tsmusic, account, "bot-1")

        self.assertTrue(tsmusic.ready)
        self.assertEqual(moved_with, [(42, "MusicBot")])
        self.assertEqual(result["reason"], "moved")


if __name__ == "__main__":
    unittest.main()
