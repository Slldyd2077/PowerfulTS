from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock

import httpx

from app.services.playlist_cover import latest_song_cover
from app.services.tsmusic_client import TSMusicClient


class LatestSongCoverTests(TestCase):
    def test_latest_collection_time_wins_over_order_or_song_release_date(self):
        self.assertEqual(latest_song_cover([
            {"coverUrl": "old", "fav_time": 1_700_000_000, "publishTime": 1_900_000_000},
            {"coverUrl": "new", "addedAt": "2026-10-11T12:00:00+08:00"},
            {"coverUrl": "millisecond", "addedTime": 1_700_000_000_000},
        ]), "new")

    def test_missing_cover_is_skipped_and_unknown_times_preserve_provider_order(self):
        self.assertEqual(latest_song_cover([
            {"coverUrl": "", "addedAt": "2026-10-11"},
            {"coverUrl": " //covers.example/latest.png "},
            {"coverUrl": "old"},
        ]), "https://covers.example/latest.png")
        self.assertEqual(latest_song_cover([]), "")
        self.assertEqual(latest_song_cover([None, {"coverUrl": None}]), "")


class PlatformPlaylistCoverTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = TSMusicClient('http://music.test', 'u', 'p', bot_id='abc-123')
        self.client._logged_in = True
        self.client.playlist_songs = AsyncMock(return_value={"ok": True, "data": [
            {"coverUrl": "latest-song", "fav_time": 10}, {"coverUrl": "old-song", "fav_time": 1},
        ]})

    async def asyncTearDown(self):
        await self.client.close()

    async def test_configured_cover_takes_priority_for_each_music_platform(self):
        for platform in ('netease', 'qq', 'kugou'):
            self.client._request = AsyncMock(return_value=httpx.Response(200, json={
                "playlist": {"coverUrl": "custom-cover"},
            }))
            result = await self.client.playlist_cover('playlist-1', platform, 'abc-456')
            self.assertEqual(result, {"coverUrl": "custom-cover", "fallbackCoverUrl": ""})
            self.assertEqual(self.client._request.call_args.kwargs['params']['botId'], 'abc-456')
        self.client.playlist_songs.assert_not_awaited()

    async def test_missing_or_unsupported_detail_falls_back_to_newest_song(self):
        for response in [httpx.Response(501), httpx.Response(200, json={"playlist": {"coverUrl": ""}}),
                         httpx.Response(200, json={"playlist": []})]:
            self.client._request = AsyncMock(return_value=response)
            result = await self.client.playlist_cover('playlist-1', 'kugou')
            self.assertEqual(result['fallbackCoverUrl'], 'latest-song')

    async def test_bilibili_and_broken_images_skip_playlist_detail(self):
        self.client._request = AsyncMock()
        for platform, songs_only in [('bilibili', False), ('qq', True)]:
            result = await self.client.playlist_cover('playlist-1', platform, songs_only=songs_only)
            self.assertEqual(result['fallbackCoverUrl'], 'latest-song')
        self.client._request.assert_not_awaited()
