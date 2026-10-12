"""Authenticated proxy to the local, optional speech-model worker."""
import asyncio
import base64
import binascii
import os
import re

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from ..deps import VoiceAccountDep
from ..core.database import AsyncSessionLocal
from ..services.auth_service import AuthService

router = APIRouter(prefix='/voice-processing', tags=['voice'])
_slots = asyncio.Semaphore(2)
_streams: set[str] = set()


@router.websocket('/stream')
async def stream_pcm(socket: WebSocket):
    # Authenticate in the first frame, never in a URL (access logs/history).
    await socket.accept()
    account_id = None
    acquired = False
    tasks = []
    try:
        credentials = await asyncio.wait_for(socket.receive_json(), 5)
        token = credentials.get('token') if isinstance(credentials, dict) else None
        if not isinstance(token, str) or not 1 <= len(token) <= 512:
            await socket.close(4401, '请先登录')
            return
        async with AsyncSessionLocal() as db:
            account = await AuthService(db).get_session_account(token)
            if account is None:
                await socket.close(4401, '会话已过期')
                return
            account_id = str(account.id)
        if len(_streams) >= 4 or account_id in _streams:
            await socket.close(4429, '人声模型繁忙')
            return
        _streams.add(account_id)
        acquired = True
        url = os.environ.get('VOICE_STREAM_WORKER_URL', 'ws://host.docker.internal:18187')
        async with connect(url, proxy=None, compression=None, max_size=1920,
                           max_queue=4, open_timeout=5) as worker:
            ready = await asyncio.wait_for(worker.recv(), 25)
            if ready != '{"ready":true}':
                raise ValueError('worker readiness')
            await socket.send_json({'ready': True})

            async def uplink():
                while True:
                    raw = await asyncio.wait_for(socket.receive_bytes(), 15)
                    if len(raw) != 1920:
                        raise ValueError('PCM frame length')
                    await worker.send(raw)

            async def downlink():
                async for raw in worker:
                    if not isinstance(raw, bytes) or len(raw) != 1920:
                        raise ValueError('worker output')
                    await socket.send_bytes(raw)

            tasks = [asyncio.create_task(uplink()), asyncio.create_task(downlink())]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
    except WebSocketDisconnect:
        pass
    except (TimeoutError, ConnectionClosed, OSError, ValueError, RuntimeError):
        try:
            await socket.close(1011, '人声处理已中断，请重试或切换本地增强')
        except RuntimeError:
            pass
    finally:
        # Release admission synchronously, including ASGI task cancellation.
        if acquired:
            _streams.discard(account_id)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


@router.post('/pcm')
async def process_pcm(request: Request, account: VoiceAccountDep):
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(413, '音频请求过大')
    try:
        import json
        body = json.loads(content)
        if body.get('mode') not in ('deepfilter', 'spex', 'combined'):
            raise ValueError('mode')
        pcm = base64.b64decode(body['pcm'], validate=True)
        if not 96000 <= len(pcm) <= 576000 or len(pcm) % 4:
            raise ValueError('pcm')
        if body['mode'] != 'deepfilter':
            if 'reference' in body:
                reference = base64.b64decode(body['reference'], validate=True)
                if not 384000 <= len(reference) <= 2880000 or len(reference) % 4:
                    raise ValueError('reference')
            elif not body.get('referenceId'):
                raise ValueError('reference')
            if body.get('referenceId'):
                if not re.fullmatch(r'[a-zA-Z0-9-]{16,64}', body['referenceId']):
                    raise ValueError('referenceId')
                body['referenceKey'] = f'{account.id}:{body["referenceId"]}'
            else:
                body.pop('referenceKey', None)
    except (ValueError, KeyError, TypeError, binascii.Error):
        raise HTTPException(400, '音频或参考录音格式无效') from None
    # Bound concurrency; reject rather than build an unbounded latency queue.
    if _slots.locked():
        raise HTTPException(429, '人声模型繁忙，请稍后重试')
    async with _slots:
        try:
            async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
                response = await client.post(
                    os.environ.get('VOICE_MODEL_WORKER_URL', 'http://host.docker.internal:18186') + '/pcm',
                    json=body)
        except httpx.HTTPError:
            raise HTTPException(503, '人声模型服务不可用，请启动本机模型服务或切换本地人声增强') from None
        if response.status_code != 200:
            raise HTTPException(429 if response.status_code == 429 else 502, '人声模型处理失败或繁忙')
        if len(response.content) != len(pcm):
            raise HTTPException(502, '人声模型输出长度异常')
        return Response(response.content, media_type='application/octet-stream', headers={'Cache-Control': 'no-store'})
