import json
from unittest import IsolatedAsyncioTestCase

import httpx

from app.services.tsmusic_client import TSMusicClient


class MusicQualityClientTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.requests: list[httpx.Request] = []
        self.auth_status = {"loggedIn": False, "vip": False}

        async def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            if request.url.path == "/api/auth/status":
                return httpx.Response(200, json=self.auth_status)
            if request.method == "GET":
                return httpx.Response(200, json={"qq": "320"})
            return httpx.Response(200, json={"success": True})

        self.client = TSMusicClient("http://tsmusic.test", "user", "password")
        await self.client._http.aclose()
        self.client._http = httpx.AsyncClient(
            base_url="http://tsmusic.test",
            transport=httpx.MockTransport(handler),
        )
        self.client._logged_in = True

    async def asyncTearDown(self) -> None:
        await self.client.close()

    async def test_get_quality_sends_bot_id(self) -> None:
        result = await self.client.get_quality(bot_id="abc-123")

        self.assertEqual(result, {"qq": "320"})
        self.assertEqual(self.requests[0].url.params["botId"], "abc-123")

    async def test_set_quality_sends_bot_id_and_platform_native_value(self) -> None:
        result = await self.client.set_quality("exhigh", "qq", bot_id="abc-123")

        payload = json.loads(self.requests[0].content)
        self.assertEqual(result, {"success": True})
        self.assertEqual(
            payload,
            {"quality": "320", "platform": "qq", "botId": "abc-123"},
        )

    async def test_kugou_uses_its_own_hires_value_for_verified_vip(self) -> None:
        self.auth_status = {"loggedIn": True, "vip": True}
        await self.client.set_quality("hires", "kugou", bot_id="abc-123")

        payload = json.loads(self.requests[1].content)
        self.assertEqual(payload["quality"], "high")

    async def test_vip_quality_is_rejected_when_membership_is_not_verified(self) -> None:
        result = await self.client.set_quality("lossless", "netease", bot_id="abc-123")

        self.assertEqual(result["_status"], 403)
        self.assertIn("VIP", result["error"])
        self.assertEqual([request.url.path for request in self.requests], ["/api/auth/status"])

    async def test_unknown_quality_is_rejected_before_upstream_request(self) -> None:
        result = await self.client.set_quality("made-up", "qq", bot_id="abc-123")

        self.assertEqual(result["_status"], 400)
        self.assertEqual(self.requests, [])

