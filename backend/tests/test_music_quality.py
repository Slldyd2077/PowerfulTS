import json
from unittest import IsolatedAsyncioTestCase

import httpx

from app.services.tsmusic_client import TSMusicClient


class MusicQualityClientTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
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

    async def test_kugou_uses_its_own_hires_value(self) -> None:
        await self.client.set_quality("hires", "kugou", bot_id="abc-123")

        payload = json.loads(self.requests[0].content)
        self.assertEqual(payload["quality"], "high")

