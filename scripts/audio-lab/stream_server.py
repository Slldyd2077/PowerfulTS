"""Loopback binary streaming gateway; only the authenticated backend exposes it."""
import asyncio
import sys
from pathlib import Path

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

active = 0


async def stream(socket):
    global active
    if active >= 4:
        await socket.close(1013, 'Model capacity reached')
        return
    active += 1
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(Path(__file__).with_name('stream_runtime.py')),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL)
        if await asyncio.wait_for(process.stdout.readline(), 20) != b'READY\n':
            raise RuntimeError('Runtime initialization failed')
        await socket.send('{"ready":true}')
        while True:
            raw = await asyncio.wait_for(socket.recv(), 15)
            if not isinstance(raw, bytes) or len(raw) != 1920:
                await socket.close(1008, 'Expected 20 ms PCM16LE')
                break
            process.stdin.write(raw)
            await process.stdin.drain()
            result = await asyncio.wait_for(process.stdout.readexactly(1920), 2)
            await socket.send(result)
    except ConnectionClosed:
        pass
    except (TimeoutError, RuntimeError, asyncio.IncompleteReadError, BrokenPipeError):
        await socket.close(1011, 'Speech processing unavailable')
    finally:
        active -= 1
        if process is not None:
            if process.returncode is None:
                process.kill()
            await process.wait()


async def main():
    async with serve(stream, '127.0.0.1', 18187, max_size=1920, max_queue=4,
                     compression=None, ping_interval=10, ping_timeout=10):
        await asyncio.Future()


if __name__ == '__main__':
    asyncio.run(main())
