"""Exercise the real native model through four persistent WebSockets."""
import asyncio
import json
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed
from paths import ROOT


async def run(raw):
    times = []
    output = []
    async with connect('ws://127.0.0.1:18187', compression=None) as socket:
        assert json.loads(await socket.recv())['ready']
        for offset in range(0, len(raw), 1920):
            start = time.perf_counter()
            await socket.send(raw[offset:offset+1920])
            response = await socket.recv()
            assert isinstance(response, bytes) and len(response) == 1920
            output.append(response)
            times.append((time.perf_counter() - start) * 1000)
            await asyncio.sleep(max(0, .02 - (time.perf_counter() - start)))
    return np.frombuffer(b''.join(output), dtype='<i2').astype(np.float32) / 32768, times


async def main():
    async with connect('ws://127.0.0.1:8080/api/voice-processing/stream') as socket:
        await socket.send(json.dumps({'token': 'invalid-test-token'}))
        try:
            await socket.recv()
            raise AssertionError('Public proxy accepted invalid login')
        except ConnectionClosed as error:
            assert error.code == 4401
    print('PASS deployed Nginx WebSocket upgrade and authentication rejection', flush=True)
    root = ROOT
    audio, rate = sf.read(root / 'samples' / 'noise-input.wav', dtype='float32')
    assert rate == 48000 and audio.ndim == 1
    audio = np.tile(audio, 4)[:96000]
    raw = (np.clip(audio, -.95, .95) * 32767).astype('<i2').tobytes()
    baseline, _ = await run(raw)
    await asyncio.sleep(.1)
    results = await asyncio.gather(*(run(raw if i < 3 else bytes(len(raw))) for i in range(4)))
    np.savez(root / 'stream-verification.npz', baseline=baseline, **{f'out{i}': r[0] for i,r in enumerate(results)})
    for index, (output, times) in enumerate(results):
        print(f'MEASURE stream {index+1}: median={np.median(times):.1f}ms '
              f'p95={np.percentile(times,95):.1f}ms max={max(times):.1f}ms', flush=True)
        assert np.isfinite(output).all() and np.max(np.abs(output)) < 1
        if index == 3:
            assert np.max(np.abs(output)) == 0, 'Speech from another session leaked'
        else:
            assert np.max(np.abs(output)) > .001
            # The official plugin can insert a zero frame on an underrun, so
            # compare energy, not sample positions across separate native runs.
            ratio = np.mean(output**2) / np.mean(baseline**2)
            assert .95 < ratio < 1.05, f'State isolation regression: {ratio}'
            assert np.percentile(times, 95) < 20, 'Four streams cannot keep up'
        print(f'PASS stream {index+1}: frame response median={np.median(times):.1f}ms '
              f'p95={np.percentile(times,95):.1f}ms max={max(times):.1f}ms')
    await asyncio.sleep(.1)
    reset, _ = await run(raw)
    assert np.max(np.abs(reset[:480])) == 0, 'New call leaked previous DSP output'
    assert .95 < np.mean(reset**2) / np.mean(baseline**2) < 1.05
    async with connect('ws://127.0.0.1:18187') as socket:
        await socket.recv()
        await socket.send(b'bad')
        try:
            await socket.recv()
            raise AssertionError('Malformed PCM was accepted')
        except ConnectionClosed as error:
            assert error.code == 1008
    sf.write(root / 'samples' / 'deepfilter-stream-output.wav', baseline, 48000)
    print('PASS state continuity/isolation, reconnect reset, silence, bounded PCM and malformed rejection')


asyncio.run(main())
