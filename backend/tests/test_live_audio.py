import asyncio

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
