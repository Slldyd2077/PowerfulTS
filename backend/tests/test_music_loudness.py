import json
from unittest import IsolatedAsyncioTestCase

import httpx

from app.services.tsmusic_client import TSMusicClient, LoudnessNormalizationUnsupported
from app.routers.music import BotSettingsRequest, put_bot_settings
from fastapi import HTTPException
from pydantic import ValidationError


class MusicLoudnessTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.settings = {"loudnessNormalization": {"enabled": False, "targetLufs": -18}}

        async def handler(request):
            self.requests.append(request)
            if request.method == "POST":
                self.settings.update(json.loads(request.content))
            return httpx.Response(200, json=self.settings)

        self.client = TSMusicClient("http://music.test", "user", "password")
        await self.client._http.aclose()
        self.client._http = httpx.AsyncClient(base_url="http://music.test", transport=httpx.MockTransport(handler))
        self.client._logged_in = True

    async def asyncTearDown(self):
        await self.client.close()

    async def test_supported_setting_is_read_and_saved_at_engine(self):
        settings = await self.client.get_bot_settings()
        self.assertEqual(settings["loudnessNormalization"], {"supported": True, "enabled": False, "targetLufs": -18})
        result = await self.client.set_bot_settings(loudness_normalization={"enabled": True})
        self.assertTrue(result["loudnessNormalization"]["enabled"])
        self.assertEqual(json.loads(self.requests[-1].content), {"loudnessNormalization": {"enabled": True}})

    async def test_old_engine_cannot_fake_a_successful_enable(self):
        self.settings = {}
        self.assertFalse((await self.client.get_bot_settings())["loudnessNormalization"]["supported"])
        with self.assertRaises(LoudnessNormalizationUnsupported):
            await self.client.set_bot_settings(loudness_normalization={"enabled": True})
        self.assertTrue(all(request.method == "GET" for request in self.requests))

    async def test_unsupported_engine_returns_an_actionable_conflict(self):
        self.settings = {}
        with self.assertRaises(HTTPException) as error:
            await put_bot_settings(BotSettingsRequest(loudnessNormalization={"enabled": True}), self.client, object())
        self.assertEqual(error.exception.status_code, 409)
        self.assertIn("升级", error.exception.detail)

    async def test_invalid_target_is_rejected_and_unrelated_updates_stay_partial(self):
        with self.assertRaises(ValidationError):
            BotSettingsRequest(loudnessNormalization={"targetLufs": -60})
        await self.client.set_bot_settings(auto_pause_on_empty=True)
        self.assertEqual(json.loads(self.requests[-1].content), {"autoPauseOnEmpty": True})
