import asyncio
import json
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import httpx
from websockets.exceptions import InvalidStatus
from websockets.http11 import Response
from websockets.datastructures import Headers

from app.services.tsmusic_client import TSMusicClient


class TSMusicUpstreamCompatibilityTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.requests: list[httpx.Request] = []
        self.responses: list[httpx.Response] = []
        self.login_count = 0
        self.login_status = 200

        async def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            if request.url.path == "/api/session/login":
                self.login_count += 1
                await asyncio.sleep(0)
                return httpx.Response(
                    self.login_status,
                    json={"id": "upstream-user"},
                    headers={"Set-Cookie": "tsmb_session=renewed; Path=/"},
                )
            if self.responses:
                return self.responses.pop(0)
            return httpx.Response(200, json={"message": "ok"})

        self.client = TSMusicClient(
            "http://per-user-tsmusic:3000", "user", "password", bot_id="abc-123"
        )
        headers = self.client._http.headers
        await self.client._http.aclose()
        self.client._http = httpx.AsyncClient(
            base_url="http://per-user-tsmusic:3000",
            headers=headers,
            transport=httpx.MockTransport(handler),
        )
        self.client._logged_in = True

    async def asyncTearDown(self) -> None:
        await self.client.close()

    async def test_mutating_requests_use_the_client_origin_for_upstream_csrf(self) -> None:
        await self.client.pause()

        self.assertEqual(
            self.requests[0].headers["Origin"], "http://per-user-tsmusic:3000"
        )

    async def test_origin_excludes_proxy_base_path_and_url_credentials(self) -> None:
        client = TSMusicClient("https://user:secret@[::1]:3443/music/", "u", "p")
        try:
            self.assertEqual(client._http.headers["Origin"], "https://[::1]:3443")
        finally:
            await client.close()

    async def test_expired_session_is_renewed_and_post_retried_once(self) -> None:
        self.responses = [httpx.Response(401, json={"error": "unauthenticated"})]

        result = await self.client.pause()

        self.assertEqual(result, {"message": "ok"})
        self.assertEqual(self.login_count, 1)
        self.assertEqual(
            [request.url.path for request in self.requests],
            ["/api/player/abc-123/pause", "/api/session/login", "/api/player/abc-123/pause"],
        )
        self.assertIn("tsmb_session=renewed", self.requests[-1].headers["Cookie"])

    async def test_permission_denial_does_not_trigger_reauthentication(self) -> None:
        self.responses = [httpx.Response(403, json={"error": "forbidden"})]

        self.assertEqual(await self.client.pause(), {"error": "forbidden"})
        self.assertEqual(self.login_count, 0)

    async def test_failed_login_does_not_retry_a_mutation(self) -> None:
        self.login_status = 401
        self.responses = [httpx.Response(401, json={"error": "unauthenticated"})]

        self.assertEqual(await self.client.pause(), {"error": "unauthenticated"})
        self.assertEqual(self.login_count, 1)
        self.assertEqual(len(self.requests), 2)

    async def test_second_unauthorized_response_is_not_retried(self) -> None:
        self.responses = [
            httpx.Response(401, json={"error": "unauthenticated"}),
            httpx.Response(401, json={"error": "unauthenticated"}),
        ]

        self.assertEqual(await self.client.pause(), {"error": "unauthenticated"})
        self.assertEqual(self.login_count, 1)
        self.assertEqual(len(self.requests), 3)

    async def test_parallel_initial_requests_share_one_login(self) -> None:
        self.client._logged_in = False

        await asyncio.gather(*(self.client.pause() for _ in range(5)))

        self.assertEqual(self.login_count, 1)

    async def test_parallel_expired_sessions_share_one_renewal(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            if request.url.path == "/api/session/login":
                self.login_count += 1
                await asyncio.sleep(0.01)
                return httpx.Response(200, headers={"Set-Cookie": "tsmb_session=renewed; Path=/"})
            if "tsmb_session=renewed" in request.headers.get("Cookie", ""):
                return httpx.Response(200, json={"message": "ok"})
            await asyncio.sleep(0)
            return httpx.Response(401, json={"error": "unauthenticated"})

        await self.client._http.aclose()
        self.client._http = httpx.AsyncClient(
            base_url="http://per-user-tsmusic:3000", transport=httpx.MockTransport(handler)
        )

        results = await asyncio.gather(*(self.client.pause() for _ in range(5)))

        self.assertEqual(results, [{"message": "ok"}] * 5)
        self.assertEqual(self.login_count, 1)

    async def test_network_failure_does_not_replay_a_mutation(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            raise httpx.ReadTimeout("timed out", request=request)

        await self.client._http.aclose()
        self.client._http = httpx.AsyncClient(
            base_url="http://per-user-tsmusic:3000", transport=httpx.MockTransport(handler)
        )

        with self.assertRaises(httpx.ReadTimeout):
            await self.client.pause()
        self.assertEqual(len(self.requests), 1)

    async def test_late_expired_response_cannot_clear_a_renewed_session_cookie(self) -> None:
        login_finished = asyncio.Event()
        expired_requests = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal expired_requests
            if request.url.path == "/api/session/login":
                self.login_count += 1
                await asyncio.sleep(0)
                login_finished.set()
                return httpx.Response(200, headers={"Set-Cookie": "tsmb_session=renewed; Path=/"})
            if "tsmb_session=renewed" in request.headers.get("Cookie", ""):
                return httpx.Response(200, json={"message": "ok"})
            expired_requests += 1
            if expired_requests == 2:
                await login_finished.wait()
            else:
                await asyncio.sleep(0)
            return httpx.Response(
                401,
                json={"error": "unauthenticated"},
                headers={"Set-Cookie": "tsmb_session=; Path=/; Max-Age=0"},
            )

        await self.client._http.aclose()
        self.client._http = httpx.AsyncClient(
            base_url="http://per-user-tsmusic:3000", transport=httpx.MockTransport(handler)
        )

        results = await asyncio.gather(self.client.pause(), self.client.pause())

        self.assertEqual(results, [{"message": "ok"}] * 2)
        self.assertEqual(self.login_count, 1)

    async def test_read_apis_send_default_bot_scope_required_by_the_fork(self) -> None:
        await self.client.search("song", platform="qq")
        await self.client.user_playlists("qq")
        await self.client.get_auth_status("qq")
        await self.client.get_qrcode_status("qr-key", "qq")
        await self.client.delete_cookie("qq")

        self.assertEqual(
            [request.url.params.get("botId") for request in self.requests],
            ["abc-123"] * 5,
        )

    async def test_auth_write_apis_send_default_bot_scope_required_by_the_fork(self) -> None:
        await self.client.get_qrcode("qq")
        await self.client.set_cookie("qq", "test-cookie")
        await self.client.jellyfin_test({"serverUrl": "http://jellyfin:8096"})
        await self.client.jellyfin_login({"serverUrl": "http://jellyfin:8096"})

        self.assertEqual(
            [json.loads(request.content).get("botId") for request in self.requests],
            ["abc-123"] * 4,
        )

    async def test_expired_voice_websocket_session_is_renewed_before_reconnecting(self) -> None:
        self.client._http.cookies.set("tsmb_session", "expired")
        connections = []

        class Socket:
            async def __aenter__(socket):
                if len(connections) == 1:
                    raise InvalidStatus(Response(401, "Unauthorized", Headers()))
                return socket

            async def __aexit__(socket, *_args):
                return False

            def __aiter__(socket):
                async def packets():
                    yield b"opus-frame"
                return packets()

        def connect(url, **kwargs):
            connections.append((url, kwargs))
            return Socket()

        with patch("app.services.tsmusic_client.websocket_connect", connect):
            packets = [packet async for packet in self.client.voice_packets()]

        self.assertEqual(packets, [b"opus-frame"])
        self.assertEqual(self.login_count, 1)
        self.assertEqual(len(connections), 2)
        self.assertIn("tsmb_session=renewed", connections[-1][1]["additional_headers"]["Cookie"])

    async def test_mixed_playlist_preserves_each_song_platform(self) -> None:
        result = await self.client.enqueue_songs(
            [
                {"id": "163-song", "platform": "netease"},
                {"id": "qq-song", "platform": "qq"},
                {"id": "BVvideo", "platform": "bilibili"},
            ],
            platform="netease",
        )

        self.assertEqual(result, {"ok": True, "enqueued": 3, "failed": 0})
        self.assertEqual(
            [json.loads(request.content)["platform"] for request in self.requests],
            ["netease", "qq", "bilibili"],
        )

    async def test_batch_enqueue_counts_upstream_business_errors_as_failures(self) -> None:
        self.responses = [httpx.Response(200, json={"error": "provider disabled"})]

        result = await self.client.enqueue_songs([{"id": "song"}], platform="qq")

        self.assertEqual(result, {"ok": True, "enqueued": 0, "failed": 1})

    async def test_fork_spotify_and_jellyfin_quality_values_are_forwarded(self) -> None:
        for platform, quality in [("spotify", "320"), ("jellyfin", "direct"), ("jellyfin", "192")]:
            with self.subTest(platform=platform, quality=quality):
                result = await self.client.set_quality(quality, platform)
                self.assertNotIn("error", result)
                self.assertEqual(
                    json.loads(self.requests[-1].content),
                    {"platform": platform, "quality": quality, "botId": "abc-123"},
                )

    async def test_invalid_quality_payload_types_are_rejected(self) -> None:
        for platform, quality in [("qq", []), ({}, "320"), ("spotify", True)]:
            with self.subTest(platform=platform, quality=quality):
                result = await self.client.set_quality(quality, platform)
                self.assertEqual(result["_status"], 400)
        self.assertEqual(self.requests, [])
