import asyncio
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient
from starlette.websockets import WebSocket
from websockets.exceptions import InvalidHandshake

from app.routers import music
from app.services.tsmusic_client import TSMusicClient, TSMusicUnavailable
from app.services.voice_downlink import VoiceDownlinkTickets


def test_voice_downlink_ticket_is_one_use():
    async def scenario():
        tickets = VoiceDownlinkTickets()
        issued = await tickets.create(7, "bot-a")
        assert await tickets.claim(issued.id) == issued
        assert await tickets.claim(issued.id) is None

    asyncio.run(scenario())


def test_expired_voice_downlink_ticket_is_rejected():
    async def scenario():
        tickets = VoiceDownlinkTickets(ttl_seconds=-1)
        issued = await tickets.create(7, "bot-a")
        assert await tickets.claim(issued.id) is None

    asyncio.run(scenario())


def test_upstream_failures_carry_a_close_code_the_browser_can_act_on():
    # A TSMusicBot without /api/voice/downlink refuses the upgrade; retrying that
    # forever just hides the real problem from the user.
    assert music.voice_close_for(InvalidHandshake("no such endpoint"))[0] == 4502
    # A bot that is simply down never yields a session cookie: _ensure_login logs
    # the connection error and returns, so this is the shape that actually reaches us.
    assert music.voice_close_for(TSMusicUnavailable("no session cookie"))[0] == 4503
    assert music.voice_close_for(httpx.ConnectError("connection refused"))[0] == 4503
    assert music.voice_close_for(ConnectionRefusedError())[0] == 4503
    # A mid-stream failure is worth reconnecting through.
    assert music.voice_close_for(RuntimeError("upstream died"))[0] == 1011
    # Every reason is short enough for the 123-byte WebSocket close-reason limit.
    for error in (InvalidHandshake(""), TSMusicUnavailable(""), RuntimeError("")):
        assert len(music.voice_close_for(error)[1].encode()) <= 123


def _voice_downlink_app(packets):
    """Minimal app exposing only the downlink route, with fake upstream state."""
    app = FastAPI()
    app.include_router(music.router, prefix="/api")
    app.state.voice_downlink = VoiceDownlinkTickets()

    class FakeVoiceBots:
        """Records voice lease activity when a browser connects and drops."""

        def __init__(self):
            self.released: list[tuple[int, str, bool]] = []
            self.kept_alive: list[int] = []

        async def keep_alive(self, account_id):
            self.kept_alive.append(account_id)

        def schedule_release(self, account_id, bot_id, *, destroy=False):
            self.released.append((account_id, bot_id, destroy))

    app.state.voice_bots = FakeVoiceBots()

    class FakeTsmusic:
        def __init__(self):
            self.upstream_closed = False

        async def voice_packets(self, bot_id):
            try:
                for packet in packets:
                    yield packet
                while True:  # Idle channel: the socket stays open with no audio.
                    await asyncio.sleep(0.05)
            finally:
                self.upstream_closed = True

    app.state.tsmusic = FakeTsmusic()
    return app


def test_browser_disconnect_closes_the_upstream_voice_socket():
    """Driven at the ASGI level on purpose.

    TestClient cancels the whole app task when its socket closes, so it passes
    with or without the fix. uvicorn does not: a websocket app only learns the
    browser is gone by calling receive(), which is what the watchdog is for.
    """
    app = _voice_downlink_app([b"\x01\x04\x00\x09\x03\xc0opus"])

    async def scenario():
        ticket = await app.state.voice_downlink.create(7, "bot-a")
        browser_gone = asyncio.Event()
        sent: list[dict] = []
        handshake_done = False

        async def receive():
            nonlocal handshake_done
            if not handshake_done:
                handshake_done = True
                return {"type": "websocket.connect"}
            await browser_gone.wait()
            return {"type": "websocket.disconnect", "code": 1001}

        async def send(message):
            sent.append(message)

        websocket = WebSocket({"type": "websocket", "app": app, "headers": []}, receive, send)
        handler = asyncio.create_task(music.stream_voice_downlink(websocket, ticket.id))

        for _ in range(100):  # Wait until audio is actually flowing.
            if any(m.get("bytes") for m in sent):
                break
            await asyncio.sleep(0.02)
        assert any(m.get("bytes") for m in sent), "no voice packet reached the browser"
        assert not app.state.tsmusic.upstream_closed

        browser_gone.set()
        await asyncio.wait_for(handler, timeout=5)
        assert app.state.tsmusic.upstream_closed
        # The browser leaving must also hand the caller's voice bot back, or it
        # would sit in the channel until something else happened to evict it.
        assert app.state.voice_bots.released == [(7, "bot-a", False)]
        # Before accept and again after registration: the second fence closes
        # the race where native TS wins while the browser socket is being wired.
        assert app.state.voice_bots.kept_alive == [7, 7]

    asyncio.run(scenario())


def test_new_ticket_replaces_an_unclaimed_ticket_for_the_same_account():
    async def scenario():
        tickets = VoiceDownlinkTickets()
        first = await tickets.create(7, "bot-a")
        second = await tickets.create(7, "bot-a")

        assert await tickets.claim(first.id) is None
        assert await tickets.claim(second.id) == second
        await tickets.release(second)

    asyncio.run(scenario())


def test_only_one_claimed_downlink_can_be_active_per_account():
    async def scenario():
        tickets = VoiceDownlinkTickets()
        first = await tickets.create(7, "bot-a")
        assert await tickets.claim(first.id) == first

        blocked = await tickets.create(7, "bot-a")
        assert await tickets.claim(blocked.id) is None

        await tickets.release(first)
        retry = await tickets.create(7, "bot-a")
        assert await tickets.claim(retry.id) == retry
        await tickets.release(retry)

    asyncio.run(scenario())


def test_native_ts_preemption_closes_the_active_browser_socket():
    async def scenario():
        tickets = VoiceDownlinkTickets()
        ticket = await tickets.create(7, "bot-a")
        claimed = await tickets.claim(ticket.id)
        assert claimed == ticket
        closer = AsyncMock()
        await tickets.register_active(ticket, closer)

        assert await tickets.close_active(
            7,
            code=music.VOICE_CLOSE_NATIVE_TS_PREEMPTED,
            reason="TeamSpeak 客户端已上线，网页通话已断开",
        )
        closer.assert_awaited_once_with(
            music.VOICE_CLOSE_NATIVE_TS_PREEMPTED,
            "TeamSpeak 客户端已上线，网页通话已断开",
        )

        await tickets.release(ticket)
        assert not await tickets.close_active(7, code=4412, reason="again")

    asyncio.run(scenario())


def test_guest_browser_disconnect_destroys_its_temporary_voice_identity():
    app = _voice_downlink_app([b"\x01\x04\x00\x09\x03\xc0opus"])

    async def scenario():
        ticket = await app.state.voice_downlink.create(7, "guest-bot", ephemeral=True)
        browser_gone = asyncio.Event()
        handshake_done = False

        async def receive():
            nonlocal handshake_done
            if not handshake_done:
                handshake_done = True
                return {"type": "websocket.connect"}
            await browser_gone.wait()
            return {"type": "websocket.disconnect", "code": 1001}

        async def send(_message):
            return None

        websocket = WebSocket(
            {"type": "websocket", "app": app, "headers": []}, receive, send
        )
        handler = asyncio.create_task(music.stream_voice_downlink(websocket, ticket.id))
        await asyncio.sleep(0.05)
        browser_gone.set()
        await asyncio.wait_for(handler, timeout=5)

        assert app.state.voice_bots.released == [(7, "guest-bot", True)]
        assert app.state.voice_bots.kept_alive == [7, 7]

    asyncio.run(scenario())


def test_guest_stream_closes_and_destroys_identity_at_session_expiry():
    app = _voice_downlink_app([b"\x01\x04\x00\x09\x03\xc0opus"])

    async def scenario():
        ticket = await app.state.voice_downlink.create(
            7,
            "guest-bot",
            ephemeral=True,
            connection_ttl_seconds=0.05,
        )
        sent: list[dict] = []
        handshake_done = False

        async def receive():
            nonlocal handshake_done
            if not handshake_done:
                handshake_done = True
                return {"type": "websocket.connect"}
            await asyncio.Event().wait()

        async def send(message):
            sent.append(message)

        websocket = WebSocket(
            {"type": "websocket", "app": app, "headers": []}, receive, send
        )
        await asyncio.wait_for(
            music.stream_voice_downlink(websocket, ticket.id), timeout=5
        )

        close_messages = [message for message in sent if message["type"] == "websocket.close"]
        assert close_messages[-1]["code"] == music.VOICE_CLOSE_GUEST_EXPIRED
        assert app.state.voice_bots.released == [(7, "guest-bot", True)]

    asyncio.run(scenario())


def test_spent_ticket_is_refused_with_a_reason_the_browser_can_show():
    app = _voice_downlink_app([b"\x01\x04\x00\x09\x03\xc0opus"])

    async def spend() -> str:
        ticket = await app.state.voice_downlink.create(7, "bot-a")
        await app.state.voice_downlink.claim(ticket.id)  # as a first listener would
        return ticket.id

    ticket_id = asyncio.run(spend())

    with TestClient(app) as client:
        try:
            with client.websocket_connect(f"/api/music/voice/{ticket_id}/stream"):
                raise AssertionError("a spent ticket must not open a stream")
        except WebSocketDisconnect as exc:
            assert exc.code == 4404


def test_tsmusic_voice_packets_uses_session_cookie_and_binary_messages_only():
    class FakeSocket:
        def __init__(self):
            self._messages = iter([b"packet-a", "ignored-text", b"packet-b"])

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._messages)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    async def scenario():
        client = TSMusicClient("https://music.example/base", "user", "password")
        await client._http.aclose()
        client._http = httpx.AsyncClient(base_url="https://music.example/base")
        client._http.cookies.set("session", "secret")
        client._logged_in = True
        calls = []

        def fake_connect(url, **kwargs):
            calls.append((url, kwargs))
            return FakeSocket()

        try:
            with patch("app.services.tsmusic_client.websocket_connect", fake_connect):
                packets = [
                    packet
                    async for packet in client.voice_packets(
                        "12345678-1234-1234-1234-123456789abc"
                    )
                ]
        finally:
            await client.close()

        assert packets == [b"packet-a", b"packet-b"]
        assert calls[0][0] == (
            "wss://music.example/base/api/voice/downlink/"
            "12345678-1234-1234-1234-123456789abc"
        )
        assert calls[0][1]["additional_headers"] == {"Cookie": "session=secret"}
        assert calls[0][1]["max_size"] == 64 * 1024

    asyncio.run(scenario())
