from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import asyncio

import httpx

from app.services.tsmusic_client import TSMusicClient


class TSMusicStatusDiagnosticsTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.upstream_status: dict = {
            "id": "abc-123",
            "playing": True,
            "audioPipeline": {
                "mode": "realtime",
                "bufferedMs": 120,
                "maxBufferedMs": 240,
                "droppedMs": 1000,
                "decoderPaused": False,
                "decodedSpeechStarts": 3,
                "lastDecodedPcmAt": 1080,
                "lastDecodedSpeechStartedAt": 1100,
                "ignored": "not-public",
            },
            "liveVoice": {
                "speechActive": True,
                "consecutiveSilentFrames": 0,
                "speechStarts": 3,
                "lastFrameSentAt": 1200,
                "lastVoicedFrameSentAt": 1190,
                "lastSpeechStartedAt": 1100,
                "lastStartBufferedMs": 80,
                "ignored": "not-public",
            },
        }

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=self.upstream_status)

        self.client = TSMusicClient(
            "http://tsmusic.test", "user", "password", bot_id="abc-123"
        )
        await self.client._http.aclose()
        self.client._http = httpx.AsyncClient(
            base_url="http://tsmusic.test",
            transport=httpx.MockTransport(handler),
        )
        self.client._logged_in = True

    async def asyncTearDown(self) -> None:
        await self.client.close()

    async def test_passes_validated_realtime_latency_metrics_to_powerfults(self) -> None:
        result = await self.client.get_bot_status()

        self.assertEqual(
            result["audioPipeline"],
            {
                "mode": "realtime",
                "bufferedMs": 120,
                "maxBufferedMs": 240,
                "droppedMs": 1000,
                "decoderPaused": False,
                "decodedSpeechStarts": 3,
                "lastDecodedPcmAt": 1080,
                "lastDecodedSpeechStartedAt": 1100,
            },
        )
        self.assertEqual(
            result["liveVoice"],
            {
                "speechActive": True,
                "consecutiveSilentFrames": 0,
                "speechStarts": 3,
                "lastFrameSentAt": 1200,
                "lastVoicedFrameSentAt": 1190,
                "lastSpeechStartedAt": 1100,
                "lastStartBufferedMs": 80,
            },
        )

    async def test_marks_metrics_unavailable_for_an_old_tsmusicbot(self) -> None:
        self.upstream_status = {"id": "abc-123", "playing": True}

        result = await self.client.get_bot_status()

        self.assertIsNone(result["audioPipeline"])
        self.assertIsNone(result["liveVoice"])

    async def test_voice_diagnostics_is_scoped_to_the_accounts_voice_bot(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from app.routers import music

        relay_status = {"active": True, "queuedChunks": 0, "lastQueueDwellMs": 7}
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    voice_bots=SimpleNamespace(
                        current_bot_id=AsyncMock(return_value="voice-bot-for-account")
                    ),
                    live_audio=SimpleNamespace(
                        status_for_bot=AsyncMock(return_value=relay_status)
                    ),
                )
            )
        )
        account = SimpleNamespace(id=42)
        tsmusic = SimpleNamespace(get_bot_status=AsyncMock(return_value={
            "playing": True,
            "title": "must-not-leak",
            "audioPipeline": self.upstream_status["audioPipeline"],
            "liveVoice": self.upstream_status["liveVoice"],
        }))

        result = await music.voice_diagnostics(request, tsmusic, account, None)

        request.app.state.voice_bots.current_bot_id.assert_awaited_once_with(None, 42)
        tsmusic.get_bot_status.assert_awaited_once_with(
            bot_id="voice-bot-for-account"
        )
        self.assertEqual(result["relay"], relay_status)
        self.assertEqual(result["audioPipeline"], self.upstream_status["audioPipeline"])
        self.assertEqual(result["liveVoice"], self.upstream_status["liveVoice"])
        self.assertNotIn("title", result)
        self.assertNotIn("botId", result)
        self.assertNotIn("sessionId", result)

    async def test_rejects_malformed_or_out_of_contract_diagnostics(self) -> None:
        self.upstream_status["audioPipeline"] = {
            "mode": "unexpected",
            "bufferedMs": "a lot",
        }
        self.upstream_status["liveVoice"] = ["not", "an", "object"]

        result = await self.client.get_bot_status()

        self.assertIsNone(result["audioPipeline"])
        self.assertIsNone(result["liveVoice"])

    async def test_voice_diagnostics_keeps_relay_data_when_upstream_times_out(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from app.routers import music

        async def slow_status(*, bot_id: str) -> dict:
            self.assertEqual(bot_id, "voice-bot-for-account")
            await asyncio.sleep(10)
            return {}

        relay_status = {"active": True, "queuedChunks": 1, "lastQueueDwellMs": 9}
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    voice_bots=SimpleNamespace(
                        current_bot_id=AsyncMock(return_value="voice-bot-for-account")
                    ),
                    live_audio=SimpleNamespace(
                        status_for_bot=AsyncMock(return_value=relay_status)
                    ),
                )
            )
        )
        tsmusic = SimpleNamespace(get_bot_status=slow_status)

        with patch.object(music, "VOICE_DIAGNOSTICS_UPSTREAM_TIMEOUT_SECONDS", 0.001):
            result = await music.voice_diagnostics(
                request,
                tsmusic,
                SimpleNamespace(id=42),
                None,
            )

        self.assertEqual(result["relay"], relay_status)
        self.assertIsNone(result["audioPipeline"])
        self.assertIsNone(result["liveVoice"])
