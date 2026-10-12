"""RBAC and command regressions; no live server mutations."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI
from app.deps import get_authenticated_account, get_tsmusic
from app.core.database import get_db
from app.routers import channel_admin as module


class Query:
    def __init__(self):
        self.commands = []
        self.occupied = False
    def send(self, command, **params):
        self.commands.append((command, params))
        if command == 'channellist':
            return [{'cid': '1', 'pid': '0', 'channel_name': '初始', 'channel_flag_default': '1'},
                    {'cid': '2', 'pid': '0', 'channel_name': '朋友的频道'}]
        if command == 'clientlist':
            return [{'clid': '9', 'cid': '2', 'client_type': '0', 'client_nickname': '好友'}] if self.occupied else []
        if command == 'channelcreate': return [{'cid': '3'}]
        if command == 'serverinfo': return [{'virtualserver_port': '9987'}]
        return []


async def main():
    app = FastAPI()
    app.include_router(module.router)
    app.state.ts3_monitor = SimpleNamespace(host='localhost', request_refresh=lambda: None)
    query = Query()
    async def execute(request, operation): return operation(query)
    music = SimpleNamespace(update_bot=AsyncMock(return_value={}),
        get_bot_config=AsyncMock(return_value={'serverAddress': 'localhost', 'serverPort': 9987, 'channelPassword': 'private'}),
        join_channel=AsyncMock(return_value={'ok': True}), list_bots=AsyncMock(return_value=[{'id': 'music', 'name': 'MusicBot'}, {'id': 'voice'}]))
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(first=lambda: ('music',), all=lambda: [('music', '好友')])))
    app.dependency_overrides[get_tsmusic] = lambda: music
    app.dependency_overrides[get_db] = lambda: db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
        assert (await client.get('/admin/channels')).status_code == 401
        app.dependency_overrides[get_authenticated_account] = lambda: SimpleNamespace(id=1, role='member')
        assert (await client.get('/admin/channels')).status_code == 403
        assert (await client.put('/admin/channels/bots/music', json={'cid': 2})).status_code == 403
        assert (await client.post('/admin/channels/members/9/kick', json={})).status_code == 403
        app.dependency_overrides[get_authenticated_account] = lambda: SimpleNamespace(id=1, role='admin')
        with patch.object(module, 'query', execute):
            response = await client.get('/admin/channels/bots')
            assert response.json()['bots'] == [{'id': 'music', 'name': 'MusicBot', 'ownerNickname': '好友'}]
            assert (await client.post('/admin/channels', json={'name': '测试', 'parentId': 1})).status_code == 200
            assert ('channelcreate', {'channel_name': '测试', 'cpid': 1, 'channel_flag_permanent': 1, 'channel_password': ''}) in query.commands
            await client.put('/admin/channels/2', json={'name': '改名'})
            assert query.commands[-1] == ('channeledit', {'cid': 2, 'channel_name': '改名'})
            await client.put('/admin/channels/2', json={'name': '改名', 'password': ''})
            assert query.commands[-1][1]['channel_password'] == ''
            assert (await client.delete('/admin/channels/1')).status_code == 400
            query.occupied = True
            assert (await client.post('/admin/channels/members/9/kick', json={'reason': '测试移除'})).status_code == 200
            assert ('clientkick', {'clid': 9, 'reasonid': 5, 'reason': '测试移除'}) in query.commands
            assert (await client.post('/admin/channels/members/99/kick', json={})).status_code == 404
            assert (await client.post('/admin/channels/members/0/kick', json={})).status_code == 400
            assert (await client.delete('/admin/channels/2')).status_code == 400
            query.occupied = False
            assert (await client.delete('/admin/channels/2')).status_code == 200
            assert query.commands[-1] == ('channeldelete', {'cid': 2, 'force': 0})
            assert (await client.put('/admin/channels/bots/music', json={'cid': 2, 'saveDefault': True})).status_code == 200
            music.update_bot.assert_awaited_once_with('music', {'channelId': '2', 'defaultChannel': ''})
            assert (await client.put('/admin/channels/bots/music', json={'cid': 2})).status_code == 200
            music.join_channel.assert_awaited_once_with(2, 'private', bot_id='music')
            music.get_bot_config.return_value['serverPort'] = 12345
            assert (await client.put('/admin/channels/bots/music', json={'cid': 2, 'saveDefault': True})).status_code == 400
            db.execute.return_value.first = lambda: None
            assert (await client.put('/admin/channels/bots/voice', json={'cid': 2})).status_code == 404
    print('PASS admin RBAC, music/voice isolation, channel validation, password preservation/removal, deletion guards and server mismatch')


def test_channel_admin_permissions_and_commands():
    asyncio.run(main())


if __name__ == '__main__':
    asyncio.run(main())
