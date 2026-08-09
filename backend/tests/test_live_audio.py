import asyncio
from contextlib import suppress

from app.services.live_audio import LiveAudioRelay


def test_live_audio_upload_is_single_use_and_close_invalidates_capability():
    async def scenario():
        relay = LiveAudioRelay()
        session = await relay.create(7, "bot-a", "audio/webm;codecs=opus")
        assert await relay.attach_upload(session.id) is session
        assert await relay.attach_upload(session.id) is None

        assert await relay.push(session.id, b"header")
        assert await relay.push(session.id, b"audio")
        await relay.close(session.id)

        chunks = [chunk async for chunk in relay.stream(session.id)]
        # A closed session cannot be consumed again; closing invalidates its
        # capability URL immediately.
        assert chunks == []
        assert await relay.get(session.id) is None

    asyncio.run(scenario())


def test_new_session_for_same_bot_invalidates_previous_capability():
    async def scenario():
        relay = LiveAudioRelay()
        first = await relay.create(1, "bot-a", "audio/webm")
        second = await relay.create(2, "bot-a", "audio/webm")
        assert first.closed is True
        assert await relay.get(first.id) is None
        assert await relay.get(second.id) is second

    asyncio.run(scenario())


def test_stream_forwards_until_closed():
    async def scenario():
        relay = LiveAudioRelay()
        session = await relay.create(1, "bot-a", "audio/webm")

        async def consume():
            return [chunk async for chunk in relay.stream(session.id)]

        consumer = asyncio.create_task(consume())
        await asyncio.sleep(0)
        await relay.push(session.id, b"one")
        await relay.push(session.id, b"two")
        await relay.close(session.id)
        assert await consumer == [b"one", b"two"]

    asyncio.run(scenario())


def test_relay_diagnostics_measure_queue_dwell_without_exposing_capability():
    async def scenario():
        monotonic = 10.0
        wall_ms = 1_800_000_000_000

        def monotonic_fn():
            return monotonic

        def wall_time_fn():
            return wall_ms

        relay = LiveAudioRelay(
            monotonic_fn=monotonic_fn,
            wall_time_fn=wall_time_fn,
        )
        session = await relay.create(7, "bot-a", "audio/ogg;codecs=opus")
        await relay.push(session.id, b"speech")

        queued = await relay.status_for_bot("bot-a")
        assert queued == {
            "active": True,
            "uploadConnected": False,
            "consumerConnected": False,
            "queuedChunks": 1,
            "queuedBytes": 6,
            "peakQueuedChunks": 1,
            "peakQueuedBytes": 6,
            "chunksPushed": 1,
            "bytesPushed": 6,
            "chunksStreamed": 0,
            "bytesStreamed": 0,
            "lastEnqueueAt": wall_ms,
            "lastDequeueAt": None,
            "lastQueueDwellMs": None,
            "maxQueueDwellMs": 0,
        }
        assert "sessionId" not in queued

        monotonic += 0.035
        wall_ms += 35
        stream = relay.stream(session.id)
        assert await anext(stream) == b"speech"
        forwarded = await relay.status_for_bot("bot-a")
        assert forwarded["queuedChunks"] == 0
        assert forwarded["queuedBytes"] == 0
        assert forwarded["chunksStreamed"] == 1
        assert forwarded["bytesStreamed"] == 6
        assert forwarded["lastDequeueAt"] == wall_ms
        assert forwarded["lastQueueDwellMs"] == 35
        assert forwarded["maxQueueDwellMs"] == 35
        await stream.aclose()

    asyncio.run(scenario())


def test_relay_diagnostics_remain_consistent_when_consumer_is_already_waiting():
    async def scenario():
        relay = LiveAudioRelay()
        session = await relay.create(7, "bot-a", "audio/ogg;codecs=opus")
        stream = relay.stream(session.id)
        received = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)

        assert await relay.push(session.id, b"speech") is True
        assert await received == b"speech"

        status = await relay.status_for_bot("bot-a")
        assert status["queuedChunks"] == 0
        assert status["queuedBytes"] == 0
        assert status["chunksPushed"] == 1
        assert status["chunksStreamed"] == 1
        await stream.aclose()

    asyncio.run(scenario())


def test_relay_diagnostics_do_not_wait_for_a_full_queue_producer():
    async def scenario():
        relay = LiveAudioRelay()
        session = await relay.create(7, "bot-a", "audio/ogg;codecs=opus")
        for _ in range(session.queue.maxsize):
            assert await relay.push(session.id, b"x") is True

        blocked_push = asyncio.create_task(relay.push(session.id, b"overflow"))
        await asyncio.sleep(0)
        status = await asyncio.wait_for(relay.status_for_bot("bot-a"), timeout=0.05)

        assert status["queuedChunks"] == session.queue.maxsize
        assert status["queuedBytes"] == session.queue.maxsize
        blocked_push.cancel()
        with suppress(asyncio.CancelledError):
            await blocked_push
        await relay.close(session.id)

    asyncio.run(scenario())
