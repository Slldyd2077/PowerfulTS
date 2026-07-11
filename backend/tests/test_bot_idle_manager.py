import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.bot_idle_manager import BotIdleManager, bot_channel_map, channel_human_count


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeTSMusic:
    def __init__(self, *, timeout: int = 1) -> None:
        self.timeout = timeout
        self.settings_calls = 0
        self.stop_calls: list[str] = []
        self.pause_calls: list[str] = []
        self.resume_calls: list[str] = []
        self.bots = [
            {
                "id": "bot-1",
                "name": "Test Bot",
                "status": "connected",
                "playing": False,
                "paused": False,
            }
        ]

    async def get_bot_settings_checked(self) -> dict:
        self.settings_calls += 1
        return {"idleTimeoutMinutes": self.timeout, "autoPauseOnEmpty": False}

    async def list_bots_checked(self) -> list[dict]:
        return self.bots

    async def get_bot_nickname(self, bot_id: str) -> str:
        return "MusicBot"

    async def stop_bot_checked(self, bot_id: str) -> dict:
        self.stop_calls.append(bot_id)
        return {"success": True}

    async def pause(self, bot_id: str) -> dict:
        self.pause_calls.append(bot_id)
        return {"success": True}

    async def resume(self, bot_id: str) -> dict:
        self.resume_calls.append(bot_id)
        return {"success": True}


def test_settings() -> SimpleNamespace:
    return SimpleNamespace(
        ts3_host="127.0.0.1",
        ts3_query_port=10011,
        ts3_query_user="query-user",
        ts3_query_password="query-password",
        ts3_sid=1,
    )


class BotIdleManagerTests(unittest.TestCase):
    def test_bots_in_same_channel_do_not_count_as_humans(self) -> None:
        clients = [
            {"client_type": "0", "client_nickname": "MusicBot A", "cid": "10"},
            {"client_type": "0", "client_nickname": "MusicBot B", "cid": "10"},
            {"client_type": "1", "client_nickname": "serveradmin", "cid": "10"},
        ]

        self.assertEqual(channel_human_count(clients, 10, {"MusicBot A", "MusicBot B"}), 0)

    def test_human_in_bot_channel_keeps_channel_active(self) -> None:
        clients = [
            {"client_type": "0", "client_nickname": "MusicBot A", "cid": "10"},
            {"client_type": "0", "client_nickname": "Alice", "cid": "10"},
            {"client_type": "0", "client_nickname": "Bob", "cid": "11"},
        ]

        self.assertEqual(channel_human_count(clients, 10, {"MusicBot A"}), 1)

    def test_bot_channel_map_returns_visible_bot_channels(self) -> None:
        clients = [
            {"client_type": "0", "client_nickname": "MusicBot A", "cid": "10"},
            {"client_type": "0", "client_nickname": "Alice", "cid": "10"},
            {"client_type": "0", "client_nickname": "MusicBot B", "cid": "12"},
        ]

        self.assertEqual(
            bot_channel_map(clients, {"MusicBot A", "MusicBot B"}),
            {"MusicBot A": 10, "MusicBot B": 12},
        )


class BotIdleManagerAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_channel_reaches_checked_stop_after_timeout(self) -> None:
        clock = FakeClock()
        tsmusic = FakeTSMusic(timeout=1)
        manager = BotIdleManager(test_settings(), tsmusic, clock=clock)
        clients = [{"client_type": "0", "client_nickname": "MusicBot", "cid": "10"}]

        with patch("app.services.bot_idle_manager.fetch_ts_clients", return_value=clients):
            await manager.poll_once()
            clock.now = 59
            await manager.poll_once()
            self.assertEqual(tsmusic.stop_calls, [])
            clock.now = 60
            await manager.poll_once()

        self.assertEqual(tsmusic.stop_calls, ["bot-1"])
        self.assertEqual(manager.snapshot()["bots"][0]["state"], "disconnected")

    async def test_human_return_cancels_idle_timer(self) -> None:
        clock = FakeClock()
        tsmusic = FakeTSMusic(timeout=1)
        manager = BotIdleManager(test_settings(), tsmusic, clock=clock)
        empty = [{"client_type": "0", "client_nickname": "MusicBot", "cid": "10"}]
        occupied = empty + [{"client_type": "0", "client_nickname": "Alice", "cid": "10"}]

        with patch("app.services.bot_idle_manager.fetch_ts_clients", return_value=empty):
            await manager.poll_once()
        clock.now = 30
        with patch("app.services.bot_idle_manager.fetch_ts_clients", return_value=occupied):
            await manager.poll_once()
        clock.now = 90
        with patch("app.services.bot_idle_manager.fetch_ts_clients", return_value=empty):
            await manager.poll_once()

        self.assertEqual(tsmusic.stop_calls, [])
        self.assertEqual(manager.snapshot()["bots"][0]["idleSeconds"], 0)

    async def test_unknown_location_preserves_timer_but_never_disconnects(self) -> None:
        clock = FakeClock()
        tsmusic = FakeTSMusic(timeout=1)
        manager = BotIdleManager(test_settings(), tsmusic, clock=clock)
        empty = [{"client_type": "0", "client_nickname": "MusicBot", "cid": "10"}]

        with patch("app.services.bot_idle_manager.fetch_ts_clients", return_value=empty):
            await manager.poll_once()
        clock.now = 90
        with patch("app.services.bot_idle_manager.fetch_ts_clients", return_value=[]):
            await manager.poll_once()

        status = manager.snapshot()["bots"][0]
        self.assertEqual(status["state"], "unknown")
        self.assertEqual(status["idleSeconds"], 90)
        self.assertEqual(tsmusic.stop_calls, [])

    async def test_unknown_duration_is_not_counted_after_recovery(self) -> None:
        clock = FakeClock()
        tsmusic = FakeTSMusic(timeout=1)
        manager = BotIdleManager(test_settings(), tsmusic, clock=clock)
        empty = [{"client_type": "0", "client_nickname": "MusicBot", "cid": "10"}]

        with patch("app.services.bot_idle_manager.fetch_ts_clients", return_value=empty):
            await manager.poll_once()
        clock.now = 30
        with patch("app.services.bot_idle_manager.fetch_ts_clients", return_value=[]):
            await manager.poll_once()
        clock.now = 90
        with patch("app.services.bot_idle_manager.fetch_ts_clients", return_value=empty):
            await manager.poll_once()

        self.assertEqual(tsmusic.stop_calls, [])
        self.assertEqual(manager.snapshot()["bots"][0]["idleSeconds"], 30)
        clock.now = 120
        with patch("app.services.bot_idle_manager.fetch_ts_clients", return_value=empty):
            await manager.poll_once()
        self.assertEqual(tsmusic.stop_calls, ["bot-1"])

    async def test_client_provider_follows_hot_reload(self) -> None:
        clock = FakeClock()
        old_client = FakeTSMusic(timeout=1)
        new_client = FakeTSMusic(timeout=1)
        holder = {"client": old_client}
        manager = BotIdleManager(test_settings(), lambda: holder["client"], clock=clock)
        clients = [{"client_type": "0", "client_nickname": "MusicBot", "cid": "10"}]

        with patch("app.services.bot_idle_manager.fetch_ts_clients", return_value=clients):
            await manager.poll_once()
            holder["client"] = new_client
            clock.now = 60
            await manager.poll_once()

        self.assertEqual(old_client.settings_calls, 1)
        self.assertEqual(new_client.settings_calls, 1)
        self.assertEqual(old_client.stop_calls, [])
        self.assertEqual(new_client.stop_calls, ["bot-1"])


if __name__ == "__main__":
    unittest.main()
