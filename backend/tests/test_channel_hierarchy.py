import unittest

from app.services.ts3_monitor import _build_channel_tree


class ChannelHierarchyTests(unittest.TestCase):
    def test_uses_ts_parent_and_previous_sibling_order(self) -> None:
        channels = [
            {"cid": "5", "pid": "10", "channel_order": "30", "channel_name": "Child B"},
            {"cid": "2", "pid": "0", "channel_order": "10", "channel_name": "Root B"},
            {"cid": "30", "pid": "10", "channel_order": "0", "channel_name": "Child A"},
            {"cid": "10", "pid": "0", "channel_order": "0", "channel_name": "Root A"},
        ]

        result = _build_channel_tree(channels)

        self.assertEqual([channel["cid"] for channel in result], [10, 30, 5, 2])
        self.assertEqual([channel["depth"] for channel in result], [0, 1, 1, 0])

    def test_keeps_orphaned_channels_visible(self) -> None:
        channels = [
            {"cid": "8", "pid": "999", "channel_order": "0", "channel_name": "Orphan"},
        ]

        self.assertEqual(
            _build_channel_tree(channels),
            [{
                "cid": 8,
                "pid": 999,
                "channel_order": 0,
                "name": "Orphan",
                "depth": 0,
            }],
        )


if __name__ == "__main__":
    unittest.main()
