import unittest

from app.services.bot_idle_manager import bot_channel_map, channel_human_count


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


if __name__ == "__main__":
    unittest.main()
