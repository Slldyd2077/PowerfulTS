"""Administrator-only TS channel management and music bot channel overrides."""
import asyncio
import httpx
import socket
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import AdminDep, TsmusicDep
from ..core.database import get_db
from ..models import BotOwnership, Account
from ..services.ts3_query import TS3QueryClient, TS3QueryError

router = APIRouter(prefix='/admin/channels', tags=['admin'])
_lock = asyncio.Lock()


async def query(request: Request, operation):
    settings = request.app.state.ts3_monitor.settings
    def run():
        client = TS3QueryClient(settings.ts3_host, settings.ts3_query_port,
            transport=settings.ts3_query_transport, username=settings.ts3_query_user,
            password=settings.ts3_query_password,
            ssh_known_hosts=settings.ts3_query_ssh_known_hosts or None)
        try:
            client.connect()
            client.authenticate(settings.ts3_query_user, settings.ts3_query_password)
            client.send('use', sid=settings.ts3_sid)
            return operation(client)
        finally:
            client.close()
    async with _lock:
        try:
            return await asyncio.to_thread(run)
        except TS3QueryError as error:
            raise HTTPException(400, f'TS 拒绝操作（{error.error_id}）：{error.msg}') from None
        except (OSError, ConnectionError, ValueError):
            raise HTTPException(503, '无法连接 TS ServerQuery，请检查服务器管理配置') from None


@router.get('')
async def overview(request: Request, account: AdminDep):
    def read(client):
        channels = client.send('channellist', flags=True)
        members = client.send('clientlist')
        return {'channels': [{'cid': int(c['cid']), 'pid': int(c.get('pid', 0)),
            'name': c['channel_name'], 'hasPassword': c.get('channel_flag_password') == '1',
            'isDefault': c.get('channel_flag_default') == '1'} for c in channels],
            'members': [{'clid': int(c['clid']), 'cid': int(c['cid']),
                'nickname': c['client_nickname']} for c in members if c.get('client_type') == '0']}
    return await query(request, read)


class ChannelEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=40)
    password: str | None = Field(default=None, max_length=128)


class ChannelCreate(ChannelEdit):
    parentId: int = Field(default=0, ge=0)


@router.post('')
async def create_channel(body: ChannelCreate, request: Request, account: AdminDep):
    if not body.name.strip():
        raise HTTPException(400, '频道名称不能为空')
    result = await query(request, lambda c: c.send('channelcreate', channel_name=body.name.strip(),
        cpid=body.parentId, channel_flag_permanent=1, channel_password=body.password or ''))
    request.app.state.ts3_monitor.request_refresh()
    return {'ok': True, 'cid': int(result[0]['cid'])}


@router.put('/{cid:int}')
async def edit_channel(cid: int, body: ChannelEdit, request: Request, account: AdminDep):
    if cid <= 0 or not body.name.strip():
        raise HTTPException(400, '频道或名称无效')
    params = {'cid': cid, 'channel_name': body.name.strip()}
    if body.password is not None:
        params['channel_password'] = body.password
    await query(request, lambda c: c.send('channeledit', **params))
    request.app.state.ts3_monitor.request_refresh()
    return {'ok': True}


@router.delete('/{cid:int}')
async def delete_channel(cid: int, request: Request, account: AdminDep):
    def remove(client):
        channels = client.send('channellist', flags=True)
        target = next((c for c in channels if int(c['cid']) == cid), None)
        if target is None:
            raise HTTPException(404, '频道已不存在')
        if target.get('channel_flag_default') == '1':
            raise HTTPException(400, '不能删除默认频道')
        if any(int(c.get('pid', 0)) == cid for c in channels):
            raise HTTPException(400, '请先处理子频道')
        if any(int(c.get('cid', 0)) == cid and c.get('client_type') == '0'
               for c in client.send('clientlist')):
            raise HTTPException(400, '请先移走频道中的成员')
        client.send('channeldelete', cid=cid, force=0)
    await query(request, remove)
    request.app.state.ts3_monitor.request_refresh()
    return {'ok': True}


class MoveMember(BaseModel):
    cid: int = Field(gt=0)


@router.post('/members/{clid:int}/move')
async def move_member(clid: int, body: MoveMember, request: Request, account: AdminDep):
    if clid <= 0:
        raise HTTPException(400, '成员无效')
    await query(request, lambda c: c.send('clientmove', clid=clid, cid=body.cid))
    request.app.state.ts3_monitor.request_refresh()
    return {'ok': True}


class KickMember(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reason: str = Field(default='由管理员移除', max_length=200)


@router.post('/members/{clid:int}/kick')
async def kick_member(clid: int, body: KickMember, request: Request, account: AdminDep):
    """Remove a voice client from the TeamSpeak server.

    The endpoint deliberately accepts only the live client id returned by the
    overview call; ServerQuery performs the final authorization check.
    """
    if clid <= 0:
        raise HTTPException(400, '成员无效')

    def kick(client):
        current = client.send('clientlist')
        target = next((item for item in current if int(item.get('clid', 0)) == clid), None)
        if target is None or str(target.get('client_type', '0')) == '1':
            raise HTTPException(404, '成员已离线')
        client.send('clientkick', clid=clid, reasonid=5,
                    reason=body.reason.strip() or '由管理员移除')

    await query(request, kick)
    request.app.state.ts3_monitor.request_refresh()
    return {'ok': True}


@router.get('/bots')
async def list_music_bots(account: AdminDep, tsmusic: TsmusicDep,
                          db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(BotOwnership.bot_id, Account.ts_nickname)
        .join(Account, Account.id == BotOwnership.account_id))).all()
    owners = dict(rows)
    return {'bots': [{**b, 'ownerNickname': owners[b['id']]} for b in await tsmusic.list_bots()
                     if b.get('id') in owners]}


class BotChannel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    cid: int = Field(gt=0)
    password: str | None = Field(default=None, max_length=128)
    saveDefault: bool = False


@router.put('/bots/{bot_id}')
async def set_bot_channel(bot_id: str, body: BotChannel, request: Request,
                          account: AdminDep, tsmusic: TsmusicDep,
                          db: AsyncSession = Depends(get_db)):
    # Only registered music bots; never modify browser voice identities.
    owned = (await db.execute(select(BotOwnership.bot_id)
                            .where(BotOwnership.bot_id == bot_id))).first()
    if not owned:
        raise HTTPException(404, '音乐机器人不存在')
    channels = await query(request, lambda c: c.send('channellist'))
    if not any(int(c['cid']) == body.cid for c in channels):
        raise HTTPException(404, '目标频道不存在')
    try:
        config = await tsmusic.get_bot_config(bot_id)
        server = await query(request, lambda c: c.send('serverinfo'))
        def same_host():
            managed = request.app.state.ts3_monitor.host
            actual = str(config.get('serverAddress', ''))
            return actual == managed or bool(
                {r[4][0] for r in socket.getaddrinfo(actual, None)} &
                {r[4][0] for r in socket.getaddrinfo(managed, None)})
        if (not await asyncio.to_thread(same_host)
            or int(config.get('serverPort', 9987)) != int(server[0]['virtualserver_port'])):
            raise HTTPException(400, '该机器人连接的服务器与当前管理的 TS 服务器不同')
        if body.saveDefault:
            payload = {'channelId': str(body.cid), 'defaultChannel': ''}
            if body.password is not None:
                payload['channelPassword'] = body.password
            result = await tsmusic.update_bot(bot_id, payload)
            if result.get('error'):
                raise HTTPException(400, str(result['error']))
            return {'ok': True, 'detail': '默认频道已保存；下次重连生效。可点击立即移动切换当前频道。'}
        result = await tsmusic.join_channel(body.cid,
            body.password if body.password is not None else config.get('channelPassword', ''), bot_id=bot_id)
        if not result.get('ok'):
            raise HTTPException(400, result.get('detail', '移动失败'))
        request.app.state.ts3_monitor.request_refresh()
        return {'ok': True, 'detail': '机器人已移动；默认频道未改变'}
    except httpx.HTTPError:
        raise HTTPException(502, '音乐机器人服务不可达') from None
    except (OSError, ValueError, KeyError):
        raise HTTPException(400, '无法确认机器人目标服务器，请检查连接配置') from None
