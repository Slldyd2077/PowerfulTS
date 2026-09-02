"""网页通话身份的在线识别，以及「动作做完立刻能看到」的强制轮询握手。

两个原始 bug：
  1. 从网页加入通话后好友收不到 QQ 上线提醒 —— TS 里的昵称带 `<WEB通讯>` 前缀，
     而上线提醒/好友在线状态都按账号昵称精确匹配，全部失配。
  2. 加入通话 / 切频道后页面要等一两拍才更新 —— 频道数据读的是监控 3 秒一轮的快照。
"""
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from app.services import ts3_auth
from app.services.online_notifier import OnlineNotifier
from app.services.ts3_monitor import TS3Monitor, strip_web_voice_marker
from app.services.voice_exclusivity import (
    VoiceExclusivityError,
    kick_real_ts_client_for_account,
)

_SETTINGS = SimpleNamespace(
    ts3_host="127.0.0.1",
    ts3_query_port=10011,
    ts3_query_user="query",
    ts3_query_password="secret",
    ts3_sid=1,
)


def _client(
    nickname: str,
    clid: int,
    cid: int = 1,
    *,
    last_connected: int | None = None,
) -> dict:
    return {
        "clid": clid,
        "cid": cid,
        "client_type": "0",
        "client_nickname": nickname,
        "client_unique_identifier": f"uid-{clid}",
        "client_lastconnected": last_connected if last_connected is not None else clid,
    }


def _client_with_uid(nickname: str, clid: int, uid: str, cid: int = 1) -> dict:
    client = _client(nickname, clid, cid)
    client["client_unique_identifier"] = uid
    return client


def _monitor_seeing(clients: list[dict]) -> tuple[TS3Monitor, list, list]:
    monitor = TS3Monitor(_SETTINGS)  # type: ignore[arg-type]
    monitor._conn = SimpleNamespace(send=lambda command, **_kw: clients if command == "clientlist" else [])
    new_online, went_offline, _visible = monitor._refresh_clients()
    return monitor, new_online, went_offline


class WebVoiceNicknameTests(unittest.TestCase):
    def test_strip_marker_handles_the_upstream_format(self) -> None:
        # TSMusicBot 写的是 "<WEB通讯> " 带尾空格；容错一下没有空格的情况。
        self.assertEqual(strip_web_voice_marker("<WEB通讯> Alice"), "Alice")
        self.assertEqual(strip_web_voice_marker("<WEB通讯>Alice"), "Alice")
        self.assertEqual(strip_web_voice_marker("Alice"), "Alice")
        self.assertEqual(strip_web_voice_marker("Alice <WEB通讯>"), "Alice <WEB通讯>")

    def test_online_event_carries_the_account_nickname_not_the_marked_one(self) -> None:
        _monitor, new_online, _offline = _monitor_seeing([_client("<WEB通讯> Alice", 11)])

        # 上线提醒按账号昵称查订阅者，带前缀就查不到人 —— 这正是 QQ 通知不触发的原因。
        self.assertEqual(new_online, [("Alice", "uid-11", True)])

    def test_a_plain_client_is_not_flagged_as_web_voice(self) -> None:
        _monitor, new_online, _offline = _monitor_seeing([_client("Alice", 11)])
        self.assertEqual(new_online, [("Alice", "uid-11", False)])

    def test_snapshot_keeps_the_marked_nickname_for_display(self) -> None:
        monitor, _online, _offline = _monitor_seeing([_client("<WEB通讯> Alice", 11)])
        entry = monitor.client_data["uid-11"]

        # 频道里别人看到的就是带标记的名字，展示不能被抹掉。
        self.assertEqual(entry["nickname"], "<WEB通讯> Alice")
        self.assertEqual(entry["identity"], "Alice")

    def test_web_only_presence_counts_as_online(self) -> None:
        monitor, _online, _offline = _monitor_seeing([_client("<WEB通讯> Alice", 11)])
        monitor.channel_map = {1: "大厅"}

        self.assertTrue(ts3_auth.is_online(monitor, "Alice"))
        self.assertEqual(ts3_auth.get_online_uid(monitor, "Alice"), "uid-11")
        self.assertEqual(monitor.get_status("Alice"), ("游戏中", "大厅"))

    def test_rename_into_the_marker_keeps_the_same_identity(self) -> None:
        """标记是通话中途加上的（浏览器接上下行才加），不能因此当成新的人上线。"""
        clients = [_client("Alice", 11)]
        monitor = TS3Monitor(_SETTINGS)  # type: ignore[arg-type]
        monitor._conn = SimpleNamespace(
            send=lambda command, **_kw: clients if command == "clientlist" else []
        )
        monitor._refresh_clients()

        clients[0]["client_nickname"] = "<WEB通讯> Alice"
        new_online, went_offline, _visible = monitor._refresh_clients()

        self.assertEqual(new_online, [])
        self.assertEqual(went_offline, [])
        self.assertEqual(_visible, [])
        self.assertEqual(monitor.client_data["uid-11"]["identity"], "Alice")

    def test_reappearing_real_client_is_reported_even_inside_online_window(self) -> None:
        """网页踢掉 TS 后，用户很快重连也必须触发“真实 TS 后上线”处理。"""
        clients = [_client_with_uid("Alice", 11, "real-uid")]
        monitor = TS3Monitor(_SETTINGS)  # type: ignore[arg-type]
        monitor._conn = SimpleNamespace(
            send=lambda command, **_kw: clients if command == "clientlist" else []
        )
        _new_online, _went_offline, visible = monitor._refresh_clients()
        self.assertEqual(visible, [("Alice", "real-uid", False, 11)])

        clients.clear()
        monitor._refresh_clients()
        self.assertIn("real-uid", monitor.client_data)

        clients.append(_client_with_uid("Alice", 12, "real-uid"))
        new_online, went_offline, visible = monitor._refresh_clients()

        self.assertEqual(new_online, [])
        self.assertEqual(went_offline, [])
        self.assertEqual(visible, [("Alice", "real-uid", False, 12)])

    def test_same_clid_with_new_connection_timestamp_is_an_arrival(self) -> None:
        clients = [_client_with_uid("Alice", 11, "real-uid")]
        clients[0]["client_lastconnected"] = 100
        monitor = TS3Monitor(_SETTINGS)  # type: ignore[arg-type]
        monitor._conn = SimpleNamespace(
            send=lambda command, **_kw: clients if command == "clientlist" else []
        )
        monitor._refresh_clients()

        clients[0]["client_lastconnected"] = 200
        _new_online, _went_offline, arrivals = monitor._refresh_clients()

        self.assertEqual(arrivals, [("Alice", "real-uid", False, 11)])


class WebVoiceNotificationTests(IsolatedAsyncioTestCase):
    def _notifier(self) -> OnlineNotifier:
        notifier = OnlineNotifier(napcat=None, sessionmaker=None, settings=_SETTINGS)  # type: ignore[arg-type]
        notifier._get_notice_templates = AsyncMock(return_value=("好友 {nick} 上线", "动态 {nick}", "新人 {nick}"))
        notifier._flush_pending_notifications = AsyncMock(return_value=0)
        notifier._resolve_friend_subscribers = AsyncMock(return_value=["10001"])
        notifier._resolve_server_subscribers = AsyncMock(return_value=[])
        notifier._send_qq = AsyncMock(return_value=1)
        notifier._send_server_notice = AsyncMock(return_value=0)
        notifier._mark_first_seen = AsyncMock(return_value=True)
        return notifier

    async def test_web_voice_online_still_pushes_the_friend_qq_notice(self) -> None:
        notifier = self._notifier()

        await notifier.on_online("Alice", "uid-11", web_voice=True)

        notifier._resolve_friend_subscribers.assert_awaited_once_with("Alice")
        notifier._send_qq.assert_awaited_once_with(["10001"], "好友 Alice 上线")

    async def test_web_voice_identity_is_not_reported_as_a_brand_new_member(self) -> None:
        # 通话 bot 每个账号一个、自带全新的 TS unique_identifier，
        # 登记成「首次进入服务器的新成员」是误报。
        notifier = self._notifier()

        await notifier.on_online("Alice", "uid-11", web_voice=True)

        notifier._mark_first_seen.assert_not_awaited()

    async def test_a_real_client_still_triggers_the_first_join_notice(self) -> None:
        notifier = self._notifier()

        await notifier.on_online("Alice", "uid-11")

        notifier._mark_first_seen.assert_awaited_once_with("uid-11", "Alice")


class VoiceExclusivityKickTests(unittest.TestCase):
    def test_web_session_kicks_the_registered_real_ts_identity(self) -> None:
        account = SimpleNamespace(
            ts_nickname="Alice",
            unique_identifier="real-uid",
            role="member",
        )
        conn = Mock()
        conn.send.side_effect = [
            [],
            [],
            [
                _client_with_uid("Alice", 11, "real-uid"),
                _client_with_uid("<WEB通讯> Alice", 12, "web-uid"),
            ],
            [],
        ]

        with patch("app.services.voice_exclusivity.TS3QueryClient", return_value=conn):
            self.assertTrue(
                kick_real_ts_client_for_account(
                    _SETTINGS,  # type: ignore[arg-type]
                    account,
                    exclude_clid=12,
                    reason="网页通话已接管，同一账号只能保留一个语音端",
                )
            )

        conn.send.assert_any_call(
            "clientkick",
            clid=11,
            reasonid=5,
            reasonmsg="网页通话已接管，同一账号只能保留一个语音端",
        )

    def test_web_session_does_not_kick_a_spoofed_matching_nickname(self) -> None:
        account = SimpleNamespace(
            ts_nickname="Alice",
            unique_identifier="real-uid",
            role="member",
        )
        conn = Mock()
        conn.send.side_effect = [
            [],
            [],
            [_client_with_uid("Alice", 11, "someone-else")],
        ]

        with patch("app.services.voice_exclusivity.TS3QueryClient", return_value=conn):
            self.assertFalse(
                kick_real_ts_client_for_account(
                    _SETTINGS,  # type: ignore[arg-type]
                    account,
                    exclude_clid=None,
                    reason="网页通话已接管，同一账号只能保留一个语音端",
                )
            )

        self.assertNotIn(
            "clientkick",
            [call.args[0] for call in conn.send.call_args_list],
        )

    def test_unverified_invitation_account_never_kicks_by_nickname(self) -> None:
        account = SimpleNamespace(
            ts_nickname="Alice",
            unique_identifier="invite:internal",
            role="member",
        )
        conn = Mock()
        conn.send.side_effect = [
            [],
            [],
            [_client_with_uid("Alice", 11, "someone-else")],
        ]

        with patch("app.services.voice_exclusivity.TS3QueryClient", return_value=conn):
            with self.assertRaisesRegex(VoiceExclusivityError, "尚未绑定"):
                kick_real_ts_client_for_account(
                    _SETTINGS,  # type: ignore[arg-type]
                    account,
                    exclude_clid=None,
                    reason="网页通话已接管，同一账号只能保留一个语音端",
                )

        self.assertNotIn(
            "clientkick",
            [call.args[0] for call in conn.send.call_args_list],
        )

    def test_query_failure_blocks_web_join_instead_of_allowing_overlap(self) -> None:
        account = SimpleNamespace(
            id=7,
            ts_nickname="Alice",
            unique_identifier="real-uid",
            role="member",
        )
        conn = Mock()
        conn.connect.side_effect = OSError("query unavailable")

        with patch("app.services.voice_exclusivity.TS3QueryClient", return_value=conn):
            with self.assertRaisesRegex(VoiceExclusivityError, "无法确认"):
                kick_real_ts_client_for_account(
                    _SETTINGS,  # type: ignore[arg-type]
                    account,
                    exclude_clid=None,
                )


class ForcedRefreshTests(unittest.TestCase):
    def test_request_refresh_cuts_the_poll_interval_short(self) -> None:
        monitor = TS3Monitor(_SETTINGS)  # type: ignore[arg-type]
        threading.Timer(0.05, monitor.request_refresh).start()

        started = time.monotonic()
        should_stop = monitor._sleep_between_polls(30.0)

        self.assertFalse(should_stop)
        self.assertLess(time.monotonic() - started, 5.0)

    def test_stop_also_wakes_the_sleeping_loop(self) -> None:
        monitor = TS3Monitor(_SETTINGS)  # type: ignore[arg-type]
        monitor._stop_event.set()
        monitor._wake.set()

        self.assertTrue(monitor._sleep_between_polls(30.0))

    def test_waits_for_a_poll_that_started_after_the_request(self) -> None:
        monitor = TS3Monitor(_SETTINGS)  # type: ignore[arg-type]
        polls: list[int] = []
        monitor._poll_once = lambda: polls.append(1)  # type: ignore[method-assign]

        # 请求刷新时正好有一轮在飞：它读到的是动作之前的状态，等它没意义。
        with monitor._poll_cv:
            monitor._polls_started = 1
        token = monitor.request_refresh()
        with monitor._poll_cv:
            monitor._polls_done = 1
            monitor._poll_cv.notify_all()

        self.assertFalse(monitor.wait_for_refresh(token, timeout=0.05))

        threading.Thread(target=monitor._poll_and_publish, daemon=True).start()
        self.assertTrue(monitor.wait_for_refresh(token, timeout=5.0))
        self.assertEqual(len(polls), 1)

    def test_a_failed_poll_still_releases_the_waiter(self) -> None:
        monitor = TS3Monitor(_SETTINGS)  # type: ignore[arg-type]

        def boom() -> None:
            raise RuntimeError("connection died")

        monitor._poll_once = boom  # type: ignore[method-assign]
        token = monitor.request_refresh()

        with self.assertRaises(RuntimeError):
            monitor._poll_and_publish()
        self.assertTrue(monitor.wait_for_refresh(token, timeout=0.05))


if __name__ == "__main__":
    unittest.main()
