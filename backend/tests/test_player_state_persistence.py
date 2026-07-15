import json
from unittest import IsolatedAsyncioTestCase

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.services.bot_player_state import BotPlayerStateStore
from app.services.tsmusic_client import TSMusicClient


class FakeStateStore:
    def __init__(self, state: dict | None = None) -> None:
        self.state = state
        self.saved: list[tuple[str, int, list[dict]]] = []
        self.deleted: list[str] = []

    async def save(self, bot_id: str, volume: int, queue: list[dict]) -> None:
        self.saved.append((bot_id, volume, queue))
        self.state = {"volume": volume, "queue": queue}

    async def load(self, _bot_id: str) -> dict | None:
        return self.state

    async def delete(self, bot_id: str) -> None:
        self.deleted.append(bot_id)


class PlayerStatePersistenceTests(IsolatedAsyncioTestCase):
    async def test_sqlite_store_round_trip_and_delete(self) -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        store = BotPlayerStateStore(async_sessionmaker(engine, expire_on_commit=False))
        try:
            await store.save("abc-123", 88, [{"id": "song", "name": "测试"}])
            self.assertEqual(
                await store.load("abc-123"),
                {"volume": 88, "queue": [{"id": "song", "name": "测试"}]},
            )
            await store.delete("abc-123")
            self.assertIsNone(await store.load("abc-123"))
        finally:
            await engine.dispose()

    async def test_volume_change_snapshots_volume_and_queue(self) -> None:
        store = FakeStateStore()
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.method == "POST" and request.url.path.endswith("/volume"):
                return httpx.Response(200, json={"success": True})
            if request.method == "GET" and request.url.path == "/api/bot/abc-123":
                return httpx.Response(200, json={"id": "abc-123", "volume": 73})
            if request.method == "GET" and request.url.path.endswith("/queue"):
                return httpx.Response(
                    200,
                    json={"queue": [{"id": "song-1", "platform": "qq", "name": "Song"}]},
                )
            return httpx.Response(404)

        client = TSMusicClient("http://tsmusic.test", "user", "pass", state_store=store)
        await client._http.aclose()
        client._http = httpx.AsyncClient(
            base_url="http://tsmusic.test", transport=httpx.MockTransport(handler)
        )
        client._logged_in = True
        try:
            await client.set_volume(73, bot_id="abc-123")
        finally:
            await client.close()

        self.assertEqual(
            store.saved,
            [("abc-123", 73, [{"id": "song-1", "platform": "qq", "name": "Song"}])],
        )
        self.assertEqual([request.method for request in requests], ["POST", "GET", "GET"])

    async def test_start_restores_saved_volume_and_empty_runtime_queue(self) -> None:
        store = FakeStateStore(
            {
                "volume": 37,
                "queue": [
                    {"id": "100", "platform": "netease", "name": "First"},
                    {"id": "200", "platform": "qq", "name": "Second"},
                ],
            }
        )
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.method == "POST" and request.url.path == "/api/bot/abc-123/start":
                return httpx.Response(200, json={"success": True})
            if request.method == "GET" and request.url.path == "/api/bot/abc-123":
                return httpx.Response(
                    200, json={"id": "abc-123", "connected": True, "volume": 50}
                )
            if request.method == "GET" and request.url.path.endswith("/queue"):
                return httpx.Response(200, json={"queue": []})
            if request.method == "POST" and request.url.path.endswith("/volume"):
                return httpx.Response(200, json={"success": True})
            if request.method == "POST" and request.url.path.endswith("/add"):
                return httpx.Response(200, json={"success": True})
            return httpx.Response(404)

        client = TSMusicClient("http://tsmusic.test", "user", "pass", state_store=store)
        await client._http.aclose()
        client._http = httpx.AsyncClient(
            base_url="http://tsmusic.test", transport=httpx.MockTransport(handler)
        )
        client._logged_in = True
        try:
            result = await client.start_bot("abc-123")
        finally:
            await client.close()

        self.assertEqual(
            result["playerState"],
            {"restored": True, "volume": 37, "queue": 2, "keptExistingQueue": False},
        )
        posts = [request for request in requests if request.method == "POST"]
        self.assertEqual(json.loads(posts[1].content), {"volume": 37})
        self.assertEqual(
            [json.loads(request.content) for request in posts[2:]],
            [
                {"query": "id:100", "platform": "netease"},
                {"query": "id:200", "platform": "qq"},
            ],
        )

    async def test_restore_keeps_existing_runtime_queue_without_duplicates(self) -> None:
        store = FakeStateStore({"volume": 60, "queue": [{"id": "saved"}]})
        add_calls = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal add_calls
            if request.method == "GET" and request.url.path == "/api/bot/abc-123":
                return httpx.Response(200, json={"id": "abc-123", "connected": True})
            if request.method == "GET" and request.url.path.endswith("/queue"):
                return httpx.Response(200, json={"queue": [{"id": "runtime"}]})
            if request.method == "POST" and request.url.path.endswith("/volume"):
                return httpx.Response(200, json={"success": True})
            if request.method == "POST" and request.url.path.endswith("/add"):
                add_calls += 1
                return httpx.Response(200, json={"success": True})
            return httpx.Response(404)

        client = TSMusicClient("http://tsmusic.test", "user", "pass", state_store=store)
        await client._http.aclose()
        client._http = httpx.AsyncClient(
            base_url="http://tsmusic.test", transport=httpx.MockTransport(handler)
        )
        client._logged_in = True
        try:
            result = await client.restore_player_state("abc-123")
        finally:
            await client.close()

        self.assertTrue(result["keptExistingQueue"])
        self.assertEqual(add_calls, 0)

    async def test_playback_ready_restores_before_implicit_reconnect(self) -> None:
        store = FakeStateStore({"volume": 42, "queue": [{"id": "saved", "platform": "qq"}]})
        paths: list[tuple[str, str]] = []
        status_reads = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal status_reads
            paths.append((request.method, request.url.path))
            if request.method == "GET" and request.url.path == "/api/bot/abc-123":
                status_reads += 1
                return httpx.Response(
                    200,
                    json={"id": "abc-123", "connected": status_reads > 1, "volume": 50},
                )
            if request.method == "POST" and request.url.path == "/api/bot/abc-123/start":
                return httpx.Response(200, json={"success": True})
            if request.method == "GET" and request.url.path.endswith("/queue"):
                return httpx.Response(200, json={"queue": []})
            if request.method == "POST" and (
                request.url.path.endswith("/volume") or request.url.path.endswith("/add")
            ):
                return httpx.Response(200, json={"success": True})
            return httpx.Response(404)

        client = TSMusicClient("http://tsmusic.test", "user", "pass", state_store=store)
        await client._http.aclose()
        client._http = httpx.AsyncClient(
            base_url="http://tsmusic.test", transport=httpx.MockTransport(handler)
        )
        client._logged_in = True
        try:
            await client.ensure_player_ready("abc-123")
        finally:
            await client.close()

        self.assertEqual(
            paths,
            [
                ("GET", "/api/bot/abc-123"),
                ("POST", "/api/bot/abc-123/start"),
                ("GET", "/api/bot/abc-123"),
                ("GET", "/api/player/abc-123/queue"),
                ("POST", "/api/player/abc-123/volume"),
                ("POST", "/api/player/abc-123/add"),
            ],
        )
