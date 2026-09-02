from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.services.voice_bot import VoiceBotError, VoiceBotManager
from app.services.voice_exclusivity import (
    VoiceExclusivityCoordinator,
    VoiceExclusivityError,
)


class _SessionContext:
    def __init__(self, scalar_results) -> None:
        self.db = SimpleNamespace(scalar=AsyncMock(side_effect=scalar_results))

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_args):
        return False


class _SessionFactory:
    def __init__(self, scalar_results) -> None:
        self.context = _SessionContext(scalar_results)

    def __call__(self):
        return self.context


class VoiceExclusivityCoordinatorTests(IsolatedAsyncioTestCase):
    async def test_verified_real_ts_arrival_preempts_web_session(self) -> None:
        account = SimpleNamespace(
            id=7,
            ts_nickname="Alice",
            unique_identifier="real-uid",
            role="member",
        )
        async def preempt(*_args, is_present, close_downlink):
            if not await is_present():
                return False
            await close_downlink()
            return True

        manager = SimpleNamespace(
            current_bot_id=AsyncMock(return_value="web-bot"),
            preempt_if_native_present=AsyncMock(side_effect=preempt),
        )
        tsmusic = SimpleNamespace(get_bot_client_id=AsyncMock(return_value=42))
        downlinks = SimpleNamespace(close_active=AsyncMock(return_value=True))
        coordinator = VoiceExclusivityCoordinator(
            _SessionFactory([account]),
            lambda: manager,
            lambda: tsmusic,
            lambda: downlinks,
            SimpleNamespace(),
            presence_checker=lambda *_args: True,
        )

        await coordinator.on_visible(
            "Alice", "real-uid", clid=11, web_voice=False
        )

        downlinks.close_active.assert_awaited_once()
        args = downlinks.close_active.await_args
        self.assertEqual(args.args[0], 7)
        self.assertEqual(args.kwargs["code"], 4412)
        manager.preempt_if_native_present.assert_awaited_once()

    async def test_web_bot_arrival_never_preempts_itself(self) -> None:
        account = SimpleNamespace(
            id=7,
            ts_nickname="Alice",
            unique_identifier="invite:internal",
            role="member",
        )
        manager = SimpleNamespace(
            current_bot_id=AsyncMock(return_value="web-bot"),
            preempt_if_native_present=AsyncMock(),
        )
        tsmusic = SimpleNamespace(get_bot_client_id=AsyncMock(return_value=42))
        downlinks = SimpleNamespace(close_active=AsyncMock())
        coordinator = VoiceExclusivityCoordinator(
            _SessionFactory([None]),
            lambda: manager,
            lambda: tsmusic,
            lambda: downlinks,
            SimpleNamespace(),
            presence_checker=lambda *_args: True,
        )

        await coordinator.on_visible(
            "Alice", "web-bot-uid", clid=42, web_voice=False
        )

        manager.preempt_if_native_present.assert_not_awaited()

    async def test_unverified_invited_nickname_cannot_preempt_web(self) -> None:
        account = SimpleNamespace(
            id=9,
            ts_nickname="Invitee",
            unique_identifier="invite:internal",
            role="member",
        )
        manager = SimpleNamespace(
            current_bot_id=AsyncMock(return_value="invite-web-bot"),
            preempt_if_native_present=AsyncMock(),
        )
        tsmusic = SimpleNamespace(get_bot_client_id=AsyncMock(return_value=55))
        downlinks = SimpleNamespace(close_active=AsyncMock(return_value=True))
        coordinator = VoiceExclusivityCoordinator(
            _SessionFactory([None]),
            lambda: manager,
            lambda: tsmusic,
            lambda: downlinks,
            SimpleNamespace(),
            presence_checker=lambda *_args: True,
        )

        await coordinator.on_visible(
            "Invitee", "native-unbound-uid", clid=21, web_voice=False
        )

        manager.preempt_if_native_present.assert_not_awaited()


class VoiceBotPreemptionTests(IsolatedAsyncioTestCase):
    async def test_real_ts_kick_happens_before_web_bot_connects(self) -> None:
        events: list[str] = []

        async def get_client_id(_bot_id):
            events.append("get-client-id")
            return 42

        async def ensure_bot(_db, _tsmusic, _account):
            events.append("ensure-bot")
            return "web-bot"

        async def ensure_connected(_tsmusic, _bot_id):
            events.append("connect-web")

        def kick(*_args, **_kwargs):
            events.append("kick-native")
            return True

        tsmusic = SimpleNamespace(get_bot_client_id=get_client_id)
        manager = VoiceBotManager(lambda: tsmusic, settings=SimpleNamespace())
        manager.current_bot_id = AsyncMock(return_value="web-bot")  # type: ignore[method-assign]
        manager._ensure_bot = ensure_bot  # type: ignore[method-assign]
        manager._ensure_connected = ensure_connected  # type: ignore[method-assign]
        account = SimpleNamespace(
            id=17,
            role="member",
            ts_nickname="Alice",
            unique_identifier="real-uid",
        )

        with patch(
            "app.services.voice_bot.kick_real_ts_client_for_account",
            side_effect=kick,
        ):
            await manager.acquire(SimpleNamespace(), account)

        self.assertLess(events.index("kick-native"), events.index("connect-web"))
        self.assertEqual(events.count("kick-native"), 2)

    async def test_stale_record_client_id_error_falls_through_to_recovery(self) -> None:
        tsmusic = SimpleNamespace(
            get_bot_client_id=AsyncMock(side_effect=[RuntimeError("missing"), 42])
        )
        manager = VoiceBotManager(lambda: tsmusic, settings=SimpleNamespace())
        manager.current_bot_id = AsyncMock(return_value="stale-bot")  # type: ignore[method-assign]
        manager._ensure_bot = AsyncMock(return_value="rebuilt-bot")  # type: ignore[method-assign]
        manager._ensure_connected = AsyncMock()  # type: ignore[method-assign]
        account = SimpleNamespace(
            id=17,
            role="member",
            ts_nickname="Alice",
            unique_identifier="real-uid",
        )

        with patch(
            "app.services.voice_bot.kick_real_ts_client_for_account",
            return_value=False,
        ):
            result = await manager.acquire(SimpleNamespace(), account)

        self.assertEqual(result["botId"], "rebuilt-bot")
        manager._ensure_connected.assert_awaited_once_with(tsmusic, "rebuilt-bot")

    async def test_failed_post_connect_exclusivity_check_discards_web_bot(self) -> None:
        tsmusic = SimpleNamespace(get_bot_client_id=AsyncMock(return_value=42))
        manager = VoiceBotManager(
            lambda: tsmusic,
            settings=SimpleNamespace(),
        )
        manager._ensure_bot = AsyncMock(return_value="web-bot")  # type: ignore[method-assign]
        manager._ensure_connected = AsyncMock()  # type: ignore[method-assign]
        manager._discard_web_bot = AsyncMock()  # type: ignore[method-assign]
        manager.current_bot_id = AsyncMock(return_value=None)  # type: ignore[method-assign]
        account = SimpleNamespace(id=17, role="member", ts_nickname="Alice")

        with patch(
            "app.services.voice_bot.kick_real_ts_client_for_account",
            side_effect=[
                False,
                VoiceExclusivityError("无法确认 TeamSpeak 客户端状态"),
            ],
        ):
            with self.assertRaisesRegex(VoiceBotError, "无法确认"):
                await manager.acquire(SimpleNamespace(), account)

        manager._ensure_connected.assert_awaited_once_with(tsmusic, "web-bot")
        manager._discard_web_bot.assert_awaited_once_with(17, "web-bot")

    async def test_atomic_native_preemption_fences_reconnect_and_disconnects(self) -> None:
        tsmusic = SimpleNamespace(
            delete_bot=AsyncMock(),
            stop_bot=AsyncMock(),
        )
        manager = VoiceBotManager(lambda: tsmusic)
        manager._delete_voice_bot_record = AsyncMock()  # type: ignore[method-assign]

        close_downlink = AsyncMock()
        self.assertTrue(
            await manager.preempt_if_native_present(
                17,
                "web-bot",
                is_present=AsyncMock(return_value=True),
                close_downlink=close_downlink,
            )
        )

        close_downlink.assert_awaited_once()
        manager._delete_voice_bot_record.assert_awaited_once_with(17, "web-bot")
        tsmusic.delete_bot.assert_awaited_once_with("web-bot")
        with self.assertRaisesRegex(VoiceBotError, "TeamSpeak 客户端已上线"):
            await manager.ensure_existing_connected(SimpleNamespace(), 17)
        with self.assertRaisesRegex(VoiceBotError, "TeamSpeak 客户端已上线"):
            await manager.keep_alive(17)
        manager.schedule_release(17, "web-bot")
        self.assertNotIn(17, manager._release_tasks)

    async def test_stale_native_event_does_not_preempt_web(self) -> None:
        tsmusic = SimpleNamespace(delete_bot=AsyncMock(), stop_bot=AsyncMock())
        manager = VoiceBotManager(lambda: tsmusic)
        manager._delete_voice_bot_record = AsyncMock()  # type: ignore[method-assign]

        self.assertFalse(
            await manager.preempt_if_native_present(
                17,
                "web-bot",
                is_present=AsyncMock(return_value=False),
                close_downlink=AsyncMock(),
            )
        )

        manager._delete_voice_bot_record.assert_not_awaited()
        tsmusic.delete_bot.assert_not_awaited()
