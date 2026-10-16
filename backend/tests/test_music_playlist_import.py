import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import Account, TsPlaylistSong
from app.routers.music import BotCreate, BotUpdateRequest, create_bot, update_bot
from app.routers.ts_playlist import SongAdd, SongsAdd, _check_song_key, add_songs, add_song, list_playlists
from app.services.ts_playlist_service import TsPlaylistService
from app.services.tsmusic_client import TSMusicClient


KUGOU_ID = 'b3a52a7a958bf0aed0ebfba2e9a818b7|32100648|966846'


class SongValidationTests(TestCase):
    def test_kugou_composite_id_round_trips(self):
        self.assertEqual(_check_song_key('kugou', KUGOU_ID), ('kugou', KUGOU_ID))

    def test_metadata_is_bounded_without_rejecting_long_titles_or_cover_urls(self):
        song = SongAdd(platform='kugou', songId=KUGOU_ID, name='歌🎵' * 200,
                       artist='歌手' * 200, coverUrl='https://cover.example/' + 'x' * 800)
        self.assertEqual(len(song.name), 255)
        self.assertEqual(len(song.artist), 255)
        self.assertIsNone(song.coverUrl)

    def test_other_platforms_still_reject_pipe_and_all_reject_paths(self):
        from fastapi import HTTPException
        for platform, key in [('netease', KUGOU_ID), ('kugou', '../bad'), ('kugou', 'hash|1|2\n')]:
            with self.assertRaises(HTTPException):
                _check_song_key(platform, key)


class PlaylistImportTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        self.db.add(Account(id=1, ts_nickname='测试账号', unique_identifier='test'))
        await self.db.commit()
        self.service = TsPlaylistService(self.db)
        self.playlist = await self.service.create_playlist(1, '混合歌单', None)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_import_all_123_songs_with_duplicates_and_invalid_ids(self):
        songs = [dict(platform='netease', songId=str(i), name=f'歌曲 {i}') for i in range(122)]
        songs.append(dict(platform='kugou', songId=KUGOU_ID, name='酷狗歌曲'))
        result = await self.service.add_songs(1, self.playlist['id'], songs + songs[:2] + [
            dict(platform='kugou', songId='../bad'),
        ])
        self.assertEqual(result, dict(added=123, skipped=2, failed=1))
        saved = await self.service.list_songs(1, self.playlist['id'])
        self.assertEqual([s['songId'] for s in saved], [s['songId'] for s in songs])
        result = await self.service.add_songs(1, self.playlist['id'], songs)
        self.assertEqual(result, dict(added=0, skipped=123, failed=0))

    async def test_import_cannot_write_another_accounts_playlist(self):
        self.assertIsNone(await self.service.add_songs(2, self.playlist['id'], [
            dict(platform='kugou', songId=KUGOU_ID),
        ]))
        self.assertEqual((await self.db.execute(select(TsPlaylistSong))).scalars().all(), [])

    async def test_favorites_include_all_owned_playlists_and_keep_platform_identity(self):
        pid = self.playlist['id']
        second = await self.service.create_playlist(1, '另一个歌单', None)
        await self.service.add_song(1, pid, dict(platform='qq', songId='same'))
        await self.service.add_song(1, second['id'], dict(platform='qq', songId='same'))
        await self.service.add_song(1, second['id'], dict(platform='netease', songId='same'))
        result = await list_playlists(SimpleNamespace(id=1), self.db)
        expected = {
            (pid, 'qq', 'same'), (second['id'], 'qq', 'same'),
            (second['id'], 'netease', 'same'),
        }
        self.assertEqual({(s['playlistId'], s['platform'], s['songId']) for s in result['favorites']}, expected)
        # Another account cannot read these memberships, even with matching song IDs.
        other = await list_playlists(SimpleNamespace(id=2), self.db)
        self.assertEqual(other, dict(playlists=[], favorites=[]))
        await self.service.remove_song(1, pid, 'qq', 'same')
        remaining = await self.service.list_favorites(1)
        self.assertEqual(len(remaining), 2)
        self.assertTrue(any(s['platform'] == 'qq' and s['songId'] == 'same' for s in remaining))

    async def test_batch_route_skips_invalid_metadata_and_does_not_resolve_music(self):
        body = SongsAdd(songs=[
            dict(platform='kugou', songId=KUGOU_ID, name='歌🎵' * 200, coverUrl='x' * 900),
            dict(platform='qq', songId='valid', duration='bad duration'),
            dict(platform='qq', songId='../bad'),
        ])
        result = await add_songs(self.playlist['id'], body, SimpleNamespace(id=1), self.db)
        self.assertEqual(result, dict(added=1, skipped=0, failed=2))
        saved = await self.service.list_songs(1, self.playlist['id'])
        self.assertEqual(saved[0]['songId'], KUGOU_ID)
        self.assertEqual(len(saved[0]['name']), 255)

    async def test_single_kugou_favorite_and_duplicate_response(self):
        from fastapi import HTTPException
        song = SongAdd(platform='kugou', songId=KUGOU_ID, name='酷狗歌曲')
        result = await add_song(self.playlist['id'], song, SimpleNamespace(id=1), self.db)
        self.assertTrue(result['success'])
        with self.assertRaises(HTTPException) as raised:
            await add_song(self.playlist['id'], song, SimpleNamespace(id=1), self.db)
        self.assertEqual(raised.exception.status_code, 409)

    async def test_ts_playlist_cover_uses_latest_favorite_without_overriding_custom_cover(self):
        pid = self.playlist['id']
        for sid, cover in [('old', 'old-cover'), ('new', 'new-cover'), ('no-cover', '')]:
            await self.service.add_song(1, pid, dict(platform='qq', songId=sid, coverUrl=cover))
        await self.service.update_song(1, pid, 'qq', 'old', note=None, sort_order=999)
        self.assertEqual((await self.service.list_playlists(1))[0]['coverUrl'], 'new-cover')
        await self.service.set_cover(1, pid, 'data:image/png;base64,custom')
        playlist = (await self.service.list_playlists(1))[0]
        self.assertEqual(playlist['coverDataUrl'], 'data:image/png;base64,custom')
        self.assertEqual(playlist['coverUrl'], 'new-cover')
        await self.service.remove_song(1, pid, 'qq', 'new')
        playlist = await self.service.update_playlist(1, pid, '改名', None)
        self.assertEqual(playlist['coverUrl'], 'old-cover')


class QueueImportTests(IsolatedAsyncioTestCase):
    async def test_more_than_50_songs_are_attempted_and_failures_are_counted(self):
        client = TSMusicClient('http://music.test', 'u', 'p', bot_id='abc-123')
        requests = []

        async def handler(request):
            payload = json.loads(request.content)
            requests.append(payload)
            return httpx.Response(400 if payload['query'] == 'id:52' else 200, json={})

        await client._http.aclose()
        client._http = httpx.AsyncClient(base_url='http://music.test', transport=httpx.MockTransport(handler))
        client._logged_in = True
        client.ensure_player_ready = AsyncMock()
        client.persist_player_state = AsyncMock()
        try:
            result = await client.enqueue_songs([dict(id=str(i), platform='netease') for i in range(123)])
            self.assertEqual(len(requests), 123)
            self.assertEqual(result, dict(ok=True, enqueued=122, failed=1))
        finally:
            await client.close()

    async def test_playlist_read_allows_upstream_pagination_to_finish(self):
        client = TSMusicClient('http://music.test', 'u', 'p', bot_id='abc-123')
        client._logged_in = True
        client._request = AsyncMock(return_value=httpx.Response(200, json={'songs': [
            dict(id=KUGOU_ID, name='酷狗歌曲', platform='kugou'),
        ]}))
        try:
            result = await client.playlist_songs('playlist-1', 'kugou')
            self.assertTrue(result['ok'])
            self.assertEqual(client._request.call_args.kwargs['timeout'], 120.0)
        finally:
            await client.close()

    async def test_business_failure_with_http_200_is_not_counted_as_added(self):
        client = TSMusicClient('http://music.test', 'u', 'p', bot_id='abc-123')
        client._logged_in = True
        client._request = AsyncMock(return_value=httpx.Response(200, json={'message': 'Cannot play: VIP only'}))
        client.ensure_player_ready = AsyncMock()
        client.persist_player_state = AsyncMock()
        try:
            result = await client.enqueue_songs([dict(id=KUGOU_ID, platform='kugou')])
            self.assertEqual(result['failed'], 1)
            self.assertEqual(client._request.call_args.kwargs['json']['query'], f'id:{KUGOU_ID}')
        finally:
            await client.close()


class BotCreationTests(IsolatedAsyncioTestCase):
    async def test_name_is_the_ts_nickname_and_server_uses_saved_setting(self):
        body = BotCreate(name='音乐机器人', nickname='旧的分离昵称')
        client = SimpleNamespace(create_bot=AsyncMock(return_value={'id': 'new-bot'}))
        db = SimpleNamespace(add=lambda value: None, commit=AsyncMock())
        with patch('app.services.app_setting.get_setting', AsyncMock(return_value='ts.example.com')):
            await create_bot(body, client, SimpleNamespace(id=1), db)
        payload = client.create_bot.call_args.args[0]
        self.assertEqual(payload['name'], payload['nickname'])
        self.assertEqual(payload['serverAddress'], 'ts.example.com')

    async def test_rename_keeps_both_names_equal_including_legacy_nickname_updates(self):
        client = SimpleNamespace(update_bot=AsyncMock(return_value={}))
        for body in [BotUpdateRequest(name='新音乐机器人', nickname='旧昵称'),
                     BotUpdateRequest(nickname='新音乐机器人')]:
            with patch('app.routers.music._check_bot_owner', new=AsyncMock()):
                await update_bot('abc-123', body, client, SimpleNamespace(id=1), AsyncMock())
            payload = client.update_bot.call_args.args[1]
            self.assertEqual(payload['name'], '新音乐机器人')
            self.assertEqual(payload['name'], payload['nickname'])
