from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.routers.friends import _deliver_or_queue_friend_notice


class FriendNotificationDeliveryTests(IsolatedAsyncioTestCase):
    async def test_bound_qq_is_preferred_even_when_ts_is_online(self) -> None:
        napcat = SimpleNamespace(send_private_msg=AsyncMock(return_value=True))
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            napcat=napcat,
            ts3_monitor=SimpleNamespace(get_status=lambda _nick: ("在线", None)),
        )))
        db = SimpleNamespace(add=lambda _item: None, commit=AsyncMock())
        recipient = SimpleNamespace(id=2, ts_nickname="friend", qq_number="10001")

        with patch("app.routers.friends.asyncio.to_thread", new=AsyncMock()) as ts_send:
            result = await _deliver_or_queue_friend_notice(request, db, recipient, "hello")

        self.assertEqual(result, "qq")
        napcat.send_private_msg.assert_awaited_once_with("10001", "hello")
        ts_send.assert_not_awaited()
        db.commit.assert_not_awaited()

    async def test_online_recipient_without_qq_uses_ts(self) -> None:
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            napcat=SimpleNamespace(send_private_msg=AsyncMock()),
            ts3_monitor=SimpleNamespace(get_status=lambda _nick: ("在线", None)),
        )))
        db = SimpleNamespace(add=lambda _item: None, commit=AsyncMock())
        recipient = SimpleNamespace(id=2, ts_nickname="friend", qq_number=None)

        with patch("app.routers.friends.asyncio.to_thread", new=AsyncMock(return_value=True)) as ts_send:
            result = await _deliver_or_queue_friend_notice(request, db, recipient, "hello")

        self.assertEqual(result, "ts")
        ts_send.assert_awaited_once()
        db.commit.assert_not_awaited()

    async def test_offline_recipient_without_qq_is_persisted(self) -> None:
        added = []
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            napcat=SimpleNamespace(send_private_msg=AsyncMock()),
            ts3_monitor=SimpleNamespace(get_status=lambda _nick: ("离线", None)),
        )))
        db = SimpleNamespace(add=added.append, commit=AsyncMock())
        recipient = SimpleNamespace(id=2, ts_nickname="friend", qq_number=None)

        result = await _deliver_or_queue_friend_notice(request, db, recipient, "hello")

        self.assertEqual(result, "pending")
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0].recipient_account_id, 2)
        self.assertEqual(added[0].message, "hello")
        db.commit.assert_awaited_once()
