import unittest
from unittest.mock import patch
from app.services.watch_room import RoomPeer, WatchRooms
from app.services.watch_config import parse_ice_servers


class WatchRoomTests(unittest.TestCase):
    def setUp(self):
        self.rooms = WatchRooms()
        self.host = RoomPeer(1, "Alice", 10)
        self.viewer = RoomPeer(2, "Bob", 10)
        self.child = RoomPeer(3, "Child", 11)
        for peer in (self.host, self.viewer, self.child):
            self.rooms.join(peer)

    def start(self, peer=None, kind="sync"):
        peer = peer or self.host
        self.rooms.handle(peer, {"type": "start", "kind": kind, "source": "direct",
                                 "url": "https://example.com/video.mp4"})
        return self.rooms.rooms[peer.cid].share

    def test_first_publisher_is_host_not_first_viewer(self):
        share = self.start(self.viewer)
        self.assertEqual(self.rooms.rooms[10].host, self.viewer.id)
        self.assertEqual(share["owner"], self.viewer.id)

    def test_one_picture_per_channel_parent_and_child_independent(self):
        parent_share = self.start()
        child_share = self.start(self.child, "screen")
        with self.assertRaises(ValueError):
            self.start(self.viewer)
        self.assertEqual(self.rooms.snapshot(10)["share"]["id"], parent_share["id"])
        self.assertNotEqual(parent_share["id"], child_share["id"])
        self.assertEqual([p["nickname"] for p in self.rooms.snapshot(11)["peers"]], ["Child"])

    def test_late_joiner_receives_current_playback(self):
        share = self.start()
        self.rooms.handle(self.host, {"type": "playback", "shareId": share["id"],
                                     "position": 100.0, "paused": False, "rate": 1.5})
        late = RoomPeer(4, "Late", 10)
        self.rooms.join(late)
        self.assertEqual(late.queue.get_nowait()["type"], "welcome")
        snapshot = late.queue.get_nowait()
        self.assertEqual(snapshot["share"]["position"], 100)
        self.assertEqual(snapshot["host"], self.host.id)

    def test_viewer_cannot_control_or_transfer_host(self):
        share = self.start()
        for command in ({"type": "stop", "shareId": share["id"]},
                        {"type": "playback", "shareId": share["id"], "position": 30.0},
                        {"type": "transfer", "target": self.host.id}):
            with self.assertRaises(ValueError):
                self.rooms.handle(self.viewer, command)

    def test_transfer_sync_keeps_video_and_progress_and_revokes_old_host(self):
        share = self.start()
        self.rooms.handle(self.host, {"type": "playback", "shareId": share["id"], "position": 50.0})
        self.rooms.handle(self.host, {"type": "transfer", "target": self.viewer.id})
        snapshot = self.rooms.snapshot(10)
        self.assertEqual(snapshot["host"], self.viewer.id)
        self.assertEqual(snapshot["share"]["position"], 50)
        self.assertEqual(snapshot["share"]["owner"], self.viewer.id)
        self.assertEqual(snapshot["share"]["id"], share["id"])
        with self.assertRaises(ValueError):
            self.rooms.handle(self.host, {"type": "stop", "shareId": share["id"]})
        self.rooms.handle(self.viewer, {"type": "stop", "shareId": share["id"]})

    def test_transfer_screen_requires_new_host_to_capture_own_window(self):
        self.start(kind="screen")
        self.rooms.handle(self.host, {"type": "transfer", "target": self.viewer.id})
        self.assertIsNone(self.rooms.snapshot(10)["share"])
        with self.assertRaises(ValueError):
            self.start()
        self.start(self.viewer, "screen")

    def test_cannot_transfer_or_signal_to_child_channel(self):
        share = self.start(kind="screen")
        for command in ({"type": "transfer", "target": self.child.id},
                        {"type": "signal", "target": self.child.id, "shareId": share["id"],
                         "description": {"type": "offer", "sdp": "v=0"}}):
            with self.assertRaises(ValueError):
                self.rooms.handle(self.host, command)

    def test_signals_only_flow_between_current_screen_host_and_viewers(self):
        share = self.start(kind="screen")
        other = RoomPeer(4, "Other", 10)
        self.rooms.join(other)
        while not self.viewer.queue.empty():
            self.viewer.queue.get_nowait()
        self.rooms.handle(self.host, {"type": "signal", "target": self.viewer.id,
                                     "shareId": share["id"], "description": {"type": "offer", "sdp": "v=0"}})
        self.assertEqual(self.viewer.queue.get_nowait()["from"], self.host.id)
        for sender, target, share_id, desc in (
            (self.viewer, other, share["id"], "offer"),
            (self.host, self.viewer, "stale-share", "offer"),
            (self.viewer, self.host, share["id"], "offer"),
        ):
            with self.assertRaises(ValueError):
                self.rooms.handle(sender, {"type": "signal", "target": target.id,
                                          "shareId": share_id, "description": {"type": desc, "sdp": "v=0"}})

    def test_host_leaving_releases_screen_and_host_lease(self):
        self.start(kind="screen")
        self.rooms.remove_account(self.host.account_id)
        self.assertIsNone(self.rooms.snapshot(10)["host"])
        self.assertIsNone(self.rooms.snapshot(10)["share"])
        self.assertEqual(self.rooms.snapshot(11)["peers"][0]["nickname"], "Child")
        self.start(self.viewer)

    def test_stopping_keeps_host_until_transfer_or_departure(self):
        share = self.start()
        self.rooms.handle(self.host, {"type": "stop", "shareId": share["id"]})
        with self.assertRaises(ValueError):
            self.start(self.viewer)

    def test_invalid_urls_and_playback_values_rejected(self):
        for url in ("javascript:alert(1)", "file:///etc/passwd", "https://user:pass@example.com/v", "https://[bad"):
            with self.assertRaises(ValueError):
                self.rooms.handle(self.host, {"type": "start", "kind": "sync", "source": "direct", "url": url})
        share = self.start()
        for position in (-1, float("inf"), float("nan"), "2", True):
            with self.assertRaises(ValueError):
                self.rooms.handle(self.host, {"type": "playback", "shareId": share["id"], "position": position})

    def test_duplicate_account_capacity_and_slow_peer_are_bounded(self):
        with self.assertRaises(ValueError):
            self.rooms.join(RoomPeer(1, "Duplicate", 10))
        for i in range(4, 11):
            self.rooms.join(RoomPeer(i, str(i), 10))
        with self.assertRaises(ValueError):
            self.rooms.join(RoomPeer(11, "Overflow", 10))
        for _ in range(100):
            self.rooms.emit(self.viewer, {"type": "pong"})
        self.assertLessEqual(self.viewer.queue.qsize(), 64)
        self.assertEqual(self.viewer.queue.get_nowait()["type"], "overflow")

    def mark_ready(self, peer, share, ready=True):
        self.rooms.handle(peer, {"type": "ready", "shareId": share["id"], "ready": ready})

    def test_waiting_freezes_everyone_and_resumes_after_all_members_loaded(self):
        share = self.start()
        self.rooms.handle(self.host, {"type": "pause", "shareId": share["id"], "paused": False})
        self.mark_ready(self.host, share)
        self.assertTrue(self.rooms.snapshot(10)["share"]["paused"])
        self.mark_ready(self.viewer, share)
        self.assertFalse(self.rooms.snapshot(10)["share"]["paused"])
        self.mark_ready(self.viewer, share, False)
        snapshot = self.rooms.snapshot(10)["share"]
        self.assertTrue(snapshot["paused"])
        self.assertFalse(snapshot["requestedPaused"])
        self.assertEqual(snapshot["waiting"], [{"nickname": "Bob", "reason": "loading"}])
        self.mark_ready(self.viewer, share)
        self.assertFalse(self.rooms.snapshot(10)["share"]["paused"])

    def test_member_pause_is_default_but_resume_and_policy_require_host(self):
        share = self.start()
        for peer in (self.host, self.viewer):
            self.mark_ready(peer, share)
        self.rooms.handle(self.host, {"type": "pause", "shareId": share["id"], "paused": False})
        self.rooms.handle(self.viewer, {"type": "pause", "shareId": share["id"]})
        self.mark_ready(self.viewer, share)
        self.assertTrue(self.rooms.snapshot(10)["share"]["paused"])
        with self.assertRaises(ValueError):
            self.rooms.handle(self.viewer, {"type": "pause", "shareId": share["id"], "paused": False})
        self.rooms.handle(self.host, {"type": "settings", "shareId": share["id"], "allowMemberPause": False})
        with self.assertRaises(ValueError):
            self.rooms.handle(self.viewer, {"type": "pause", "shareId": share["id"]})

    def test_host_can_disable_waiting_and_live_does_not_wait(self):
        share = self.start()
        self.rooms.handle(self.host, {"type": "pause", "shareId": share["id"], "paused": False})
        self.rooms.handle(self.host, {"type": "settings", "shareId": share["id"], "waitForMembers": False})
        self.assertFalse(self.rooms.snapshot(10)["share"]["paused"])
        self.rooms.handle(self.host, {"type": "stop", "shareId": share["id"]})
        self.rooms.handle(self.host, {"type": "start", "kind": "sync", "source": "site",
                                     "url": "https://live.example.com/room", "live": True})
        live = self.rooms.snapshot(10)["share"]
        self.rooms.handle(self.host, {"type": "pause", "shareId": live["id"], "paused": False})
        self.assertFalse(self.rooms.snapshot(10)["share"]["paused"])
        self.assertEqual(self.rooms.snapshot(10)["share"]["waiting"], [])

    def test_dropouts_wait_then_reconnect_with_same_identity(self):
        share = self.start()
        self.rooms.disconnect(self.viewer)
        self.assertIn({"nickname": "Bob", "reason": "offline"}, self.rooms.snapshot(10)["share"]["waiting"])
        reconnect = RoomPeer(2, "Bob", 10)
        self.rooms.join(reconnect)
        self.assertEqual(reconnect.id, self.viewer.id)
        self.mark_ready(reconnect, share)
        self.mark_ready(self.host, share)
        self.assertEqual(self.rooms.snapshot(10)["share"]["waiting"], [])

    def test_offline_timeout_and_intentional_departure_do_not_block_forever(self):
        self.start()
        with patch('app.services.watch_room.time.monotonic', return_value=100):
            self.rooms.disconnect(self.viewer)
        with patch('app.services.watch_room.time.monotonic', return_value=121):
            self.rooms.tick(10)
        self.assertFalse(self.rooms.rooms[10].offline)
        self.rooms.handle(self.host, {"type": "leave"})
        self.assertNotIn(10, self.rooms.rooms)
        with self.assertRaises(ValueError):
            self.rooms.handle(self.host, {"type": "start", "kind": "screen"})

    def test_missing_readiness_heartbeat_pauses_without_cross_channel_effect(self):
        share = self.start()
        with patch('app.services.watch_room.time.monotonic', return_value=100):
            for peer in (self.host, self.viewer):
                self.mark_ready(peer, share)
            self.rooms.handle(self.host, {"type": "pause", "shareId": share["id"], "paused": False})
        self.start(self.child, 'screen')
        with patch('app.services.watch_room.time.monotonic', return_value=107):
            self.rooms.tick(10)
        self.assertTrue(self.rooms.snapshot(10)["share"]["paused"])
        self.assertEqual(self.rooms.snapshot(11)["share"]["kind"], 'screen')

    def test_ice_settings_validate_urls_without_exposing_credential_in_errors(self):
        self.assertEqual(parse_ice_servers('[]'), [])
        self.assertEqual(parse_ice_servers('[{"urls":"turn:example.com:3478","username":"u","credential":"secret"}]')[0]['username'], 'u')
        for raw in ('{}', 'invalid', '[{"urls": "https://example.com", "credential":"secret"}]', '[{"urls":[]}]'):
            with self.assertRaises(ValueError) as caught:
                parse_ice_servers(raw)
            self.assertNotIn('secret', str(caught.exception))


if __name__ == "__main__":
    unittest.main()
