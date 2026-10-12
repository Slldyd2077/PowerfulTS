"""Run in backend image; temporary ASGI app with fake auth, real streaming worker."""
import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app.routers.voice_processing import router

app = FastAPI()
app.include_router(router)


with TestClient(app) as client:
    with client.websocket_connect('/voice-processing/stream') as socket:
        socket.send_json({'token': ''})
        try:
            socket.receive_json()
            raise AssertionError('Accepted unauthorized session')
        except WebSocketDisconnect as error:
            assert error.code == 4401
    with patch('app.routers.voice_processing.AuthService.get_session_account',
               AsyncMock(return_value=SimpleNamespace(id=987654))):
        with client.websocket_connect('/voice-processing/stream') as socket:
            socket.send_json({'token': 'test-only-never-a-live-account'})
            assert socket.receive_json()['ready']
            for _ in range(10):
                socket.send_bytes(bytes(1920))
                assert socket.receive_bytes() == bytes(1920)
            with client.websocket_connect('/voice-processing/stream') as duplicate:
                duplicate.send_json({'token': 'test-only-never-a-live-account'})
                try:
                    duplicate.receive_json()
                    raise AssertionError('Duplicate account accepted')
                except WebSocketDisconnect as error:
                    assert error.code == 4429
        # ASGI disconnect cleanup runs asynchronously after the client closes.
        time.sleep(.2)
        with client.websocket_connect('/voice-processing/stream') as socket:
            socket.send_json({'token': 'test-only-never-a-live-account'})
            assert socket.receive_json()['ready']
            socket.send_bytes(b'bad')
            try:
                socket.receive_bytes()
                raise AssertionError('Malformed frame accepted')
            except WebSocketDisconnect:
                pass
print('PASS authenticated Docker-to-host binary bridge, unauthorized rejection, duplicate limit, cleanup and reconnect')
