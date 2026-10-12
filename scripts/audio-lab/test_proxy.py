"""Run in the backend image against the local model worker, without live accounts."""
import asyncio
import base64
import json
import struct
import wave
from types import SimpleNamespace

import httpx
from fastapi import FastAPI
from app.deps import get_voice_account
from app.routers.voice_processing import router


def pcm(path, seconds=None):
    # Fixtures are 48 kHz mono PCM16; no ML dependencies in backend image.
    with wave.open(path) as file:
        assert file.getframerate() == 48000 and file.getnchannels() == 1
        count = file.getnframes() if seconds is None else min(file.getnframes(), int(seconds * 48000))
        samples = struct.unpack('<' + 'h' * count, file.readframes(count))
    return base64.b64encode(struct.pack('<' + 'f' * count, *[x / 32768 for x in samples])).decode(), count


async def main():
    app = FastAPI()
    app.include_router(router)
    body, count = pcm('/samples/two-speakers-input.wav', 2)
    reference, _ = pcm('/samples/custom-reference.wav')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        rejected = await client.post('/voice-processing/pcm', json={'mode': 'deepfilter', 'pcm': body})
        assert rejected.status_code == 401, rejected.text
        app.dependency_overrides[get_voice_account] = lambda: SimpleNamespace(id=1)
        invalid = await client.post('/voice-processing/pcm', json={'mode': 'spex', 'pcm': body})
        assert invalid.status_code == 400, invalid.text
        for mode in ('deepfilter', 'spex', 'combined'):
            response = await client.post('/voice-processing/pcm', json={'mode': mode, 'pcm': body, 'reference': reference})
            assert response.status_code == 200, response.text
            assert len(response.content) == count * 4
            output = struct.unpack('<' + 'f' * count, response.content)
            assert max(abs(x) for x in output) <= 0.951
            assert sum(x*x for x in output) > 0
            print('PASS authenticated proxy + real model:', mode, flush=True)
        print('PASS unauthenticated/missing reference rejection', flush=True)


asyncio.run(main())
