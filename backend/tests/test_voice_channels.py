"""网页通话的频道选择器：成员分组、bot 定位、切频道错误分类。"""
import asyncio
import json
import time
import unittest
from types import SimpleNamespace

import httpx

from app.services.ts3_monitor import TS3Monitor, strip_web_voice_marker
from app.services.tsmusic_client import TSMusicClient

_SETTINGS = SimpleNamespace(
    ts3_host="127.0.0.1",
    ts3_query_port=10011,
    ts3_query_user="query",
    ts3_query_password="secret",
    ts3_sid=1,
)


def _monitor_with(clients: list[dict], channels: list[dict]) -> TS3Monitor:
    monitor = TS3Monitor(_SETTINGS)  # type: ignore[arg-type]
    now = time.time()
    monitor.channel_tree = channels
    monitor.channel_password = {ch["cid"]: ch.pop("_locked", False) for ch in channels}
    monitor.client_data = {
        f"uid-{c['clid']}": {
            "identity": strip_web_voice_marker(c["nickname"]),
            **c,
            "first_seen": now,
            "last_seen": now,
        }
        for c in clients
    }
    return monitor


class VoiceOverviewTests(unittest.TestCase):
    def _overview(self, bot_clid):
        monitor = _monitor_with(
            clients=[
                {"nickname": "Alice", "clid": 11, "cid": 1},
                {"nickname": "♪ 某首歌 - 点歌姬", "clid": 12, "cid": 2},
                {"nickname": "Bob", "clid": 13, "cid": 2},
            ],
            channels=[
                {"cid": 1, "pid": 0, "depth": 0, "name": "大厅", "_locked": False},
                {"cid": 2, "pid": 0, "depth": 0, "name": "小黑屋", "_locked": True},
                {"cid": 3, "pid": 0, "depth": 0, "name": "空频道", "_locked": False},
            ],
        )
        return monitor.get_voice_overview(bot_clid)

    def test_groups_members_by_channel_and_flags_password(self) -> None:
        overview = self._overview(bot_clid=12)
        by_cid = {c["cid"]: c for c in overview["channels"]}

        self.assertEqual([c["nickname"] for c in by_cid[1]["clients"]], ["Alice"])
        self.assertEqual(
            sorted(c["nickname"] for c in by_cid[2]["clients"]),
            sorted(["Bob", "♪ 某首歌 - 点歌姬"]),
        )
        self.assertEqual(by_cid[3]["clients"], [])
        self.assertFalse(by_cid[1]["hasPassword"])
        self.assertTrue(by_cid[2]["hasPassword"])

    def test_locates_the_bot_by_clid_not_nickname(self) -> None:
        # The bot renamed itself to the current song; a nickname match would miss
        # it, and adding the <WEB通讯> marker would break it a second way.
        overview = self._overview(bot_clid=12)
        self.assertEqual(overview["botCid"], 2)
        bot_entries = [
            client
            for channel in overview["channels"]
            for client in channel["clients"]
            if client["isBot"]
        ]
        self.assertEqual([c["nickname"] for c in bot_entries], ["♪ 某首歌 - 点歌姬"])

    def test_offline_bot_reports_no_channel_and_marks_nobody(self) -> None:
        overview = self._overview(bot_clid=None)
        self.assertIsNone(overview["botCid"])
        self.assertFalse(
            any(c["isBot"] for ch in overview["channels"] for c in ch["clients"])
        )

    def test_stale_clients_are_not_listed(self) -> None:
        monitor = _monitor_with(
            clients=[{"nickname": "Ghost", "clid": 11, "cid": 1}],
            channels=[{"cid": 1, "pid": 0, "depth": 0, "name": "大厅"}],
        )
        monitor.client_data["uid-11"]["last_seen"] = time.time() - 3600
        overview = monitor.get_voice_overview(bot_clid=None)
        self.assertEqual(overview["channels"][0]["clients"], [])


class JoinChannelTests(unittest.TestCase):
    """The join goes through the bot's own TS client on purpose.

    A ServerQuery clientmove would look identical here but silently bypass the
    channel password, because query admins hold b_channel_join_ignore_password.
    """

    def _run(self, password: str, responder):
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/api/session/login":
                return httpx.Response(200, json={"ok": True})
            return responder(request)

        async def scenario():
            client = TSMusicClient("http://bot.example", "u", "p", bot_id="bot-a")
            await client._http.aclose()
            client._http = httpx.AsyncClient(
                base_url="http://bot.example", transport=httpx.MockTransport(handler)
            )
            try:
                return await client.join_channel(7, password)
            finally:
                await client.close()

        result = asyncio.run(scenario())
        join = next(r for r in requests if r.url.path.endswith("/channel"))
        return result, join

    def test_posts_cid_and_password_to_the_bots_own_join_endpoint(self) -> None:
        result, join = self._run("hunter2", lambda _r: httpx.Response(200, json={"success": True}))
        self.assertTrue(result["ok"])
        self.assertEqual(join.url.path, "/api/bot/bot-a/channel")
        self.assertEqual(json.loads(join.content), {"cid": 7, "password": "hunter2"})

    def test_wrong_password_is_flagged_as_a_correctable_input_error(self) -> None:
        result, _ = self._run(
            "nope",
            lambda _r: httpx.Response(409, json={"error": "invalid channel password", "tsErrorId": 781}),
        )
        self.assertFalse(result["ok"])
        self.assertTrue(result["invalid_password"])
        self.assertEqual(result["detail"], "频道密码不正确")

    def test_other_teamspeak_errors_get_a_readable_reason(self) -> None:
        result, _ = self._run(
            "", lambda _r: httpx.Response(409, json={"error": "channel is full", "tsErrorId": 777})
        )
        self.assertFalse(result["ok"])
        self.assertNotIn("invalid_password", result)
        self.assertEqual(result["detail"], "频道已满")

    def test_unknown_error_falls_back_to_the_upstream_message(self) -> None:
        result, _ = self._run(
            "", lambda _r: httpx.Response(500, json={"error": "not connected to TeamSpeak"})
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["detail"], "not connected to TeamSpeak")


if __name__ == "__main__":
    unittest.main()
