from contextlib import asynccontextmanager
import asyncio
import anyio
from datetime import datetime, timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app.core.database import get_db
from app.deps import get_voice_account
from app.routers import watch
from app.services.guest_access import GuestSessionRateLimiter
from app.services.voice_downlink import VoiceDownlinkTickets
from app.services.watch_room import WatchRooms


class WatchAPITests(unittest.TestCase):
    def setUp(self):
        self.account = SimpleNamespace(id=1, ts_nickname="Alice", role="member", status="active")
        app = FastAPI()
        app.include_router(watch.router, prefix="/api")
        app.state.watch_rooms = WatchRooms()
        app.state.watch_tickets = VoiceDownlinkTickets()
        app.state.watch_limiter = GuestSessionRateLimiter(max_requests=20, window_seconds=60)
        app.state.watch_origins = ["http://localhost:5173"]
        app.state.watch_ice_servers = []
        app.state.voice_bots = SimpleNamespace(current_bot_id=AsyncMock(return_value="voice-1"))
        app.dependency_overrides[get_voice_account] = lambda: self.account

        async def db_dependency():
            yield None

        @asynccontextmanager
        async def session():
            yield None

        app.dependency_overrides[get_db] = db_dependency
        self.app = app
        self.client = TestClient(app)
        self.auth = SimpleNamespace(get_by_id=AsyncMock(side_effect=lambda account_id: self.account),
                                    get_active_session_expiry=AsyncMock(return_value=datetime.now() + timedelta(hours=1)))
        self.patches = [patch.object(watch, "AsyncSessionLocal", session),
                        patch.object(watch, "channel_for", AsyncMock(return_value=10)),
                        patch.object(watch, "AuthService", return_value=self.auth)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def ticket(self):
        response = self.client.post("/api/music/voice/watch/ticket")
        self.assertEqual(response.status_code, 200)
        return response.json()["path"]

    def test_no_voice_membership_cannot_issue_ticket(self):
        with patch.object(watch, "channel_for", AsyncMock(return_value=None)):
            self.assertEqual(self.client.post("/api/music/voice/watch/ticket").status_code, 409)

    def test_room_snapshot_and_one_use_ticket(self):
        path = self.ticket()
        with self.client.websocket_connect(path, headers={"origin": "http://testserver"}) as ws:
            self.assertEqual(ws.receive_json()["type"], "welcome")
            self.assertEqual(ws.receive_json()["cid"], 10)
            ws.send_json({"type": "start", "kind": "screen"})
            self.assertEqual(ws.receive_json()["share"]["kind"], "screen")
            ws.send_json({"type": "playback", "position": -2})
            self.assertEqual(ws.receive_json()["type"], "error")
        with self.assertRaises(WebSocketDisconnect) as caught:
            with self.client.websocket_connect(path, headers={"origin": "http://testserver"}):
                pass
        self.assertEqual(caught.exception.code, 4401)
        self.assertFalse(self.app.state.watch_rooms.rooms)

    def test_cross_origin_socket_rejected_without_consuming_ticket(self):
        path = self.ticket()
        with self.assertRaises(WebSocketDisconnect) as caught:
            with self.client.websocket_connect(path, headers={"origin": "https://evil.example"}):
                pass
        self.assertEqual(caught.exception.code, 4403)
        with self.client.websocket_connect(path, headers={"origin": "http://testserver"}) as ws:
            self.assertEqual(ws.receive_json()["type"], "welcome")
            self.assertEqual(ws.receive_json()["type"], "room")

    def test_channel_changed_before_claim_rejected(self):
        path = self.ticket()
        with patch.object(watch, "channel_for", AsyncMock(return_value=None)):
            with self.assertRaises(WebSocketDisconnect) as caught:
                with self.client.websocket_connect(path, headers={"origin": "http://testserver"}):
                    pass
            self.assertEqual(caught.exception.code, 4403)

    def test_cancelled_socket_removes_room_before_draining_and_releases_ticket(self):
        async def scenario():
            receive_started = asyncio.Event()
            drain_started = asyncio.Event()
            allow_drain = asyncio.Event()
            completed = asyncio.Event()

            class Socket:
                app = self.app
                headers = {"origin": "http://testserver", "host": "testserver"}
                url = SimpleNamespace(scheme="ws")

                async def accept(self):
                    pass

                async def receive(self):
                    receive_started.set()
                    await asyncio.Event().wait()

            async def sender(_socket, _peer):
                try:
                    await asyncio.Event().wait()
                finally:
                    drain_started.set()
                    await allow_drain.wait()

            async def run_socket(ticket_id, *, task_status):
                with anyio.CancelScope() as scope:
                    task_status.started(scope)
                    try:
                        await watch.room_socket(Socket(), ticket_id)
                    finally:
                        completed.set()

            tickets = self.app.state.watch_tickets
            ticket = await tickets.create(self.account.id, "voice-1")
            with patch.object(watch, "send_messages", sender):
                async with anyio.create_task_group() as group:
                    scope = await group.start(run_socket, ticket.id)
                    await asyncio.wait_for(receive_started.wait(), 1)
                    scope.cancel()
                    await asyncio.wait_for(drain_started.wait(), 1)
                    try:
                        self.assertFalse(self.app.state.watch_rooms.rooms)
                    finally:
                        allow_drain.set()
                    await asyncio.wait_for(completed.wait(), 1)

            next_ticket = await tickets.create(self.account.id, "voice-1")
            self.assertIsNotNone(await tickets.claim(next_ticket.id))
            await tickets.release(next_ticket)

        anyio.run(scenario)


if __name__ == "__main__":
    unittest.main()
