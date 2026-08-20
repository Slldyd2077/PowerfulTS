"""Per-account channel-entry sound upload and playback behavior."""

from __future__ import annotations

import asyncio
import io
import json
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.deps import get_authenticated_account
from app.models import Account, EntrySound
from app.routers import music
from app.services.entry_sound import (
    MAX_ENTRY_SOUND_BYTES,
    EntrySoundCapabilities,
    EntrySoundStorage,
    EntrySoundValidationError,
    inspect_audio,
    read_limited_upload,
)
from app.services.guest_access import GuestSessionRateLimiter
from app.services.tsmusic_client import TSMusicClient


def _wav_bytes(seconds: float, *, rate: int = 8_000) -> bytes:
    frames = round(seconds * rate)
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * frames)
    return output.getvalue()


def test_actual_audio_parser_accepts_wav_at_the_seven_second_boundary() -> None:
    metadata = inspect_audio(_wav_bytes(7.0), "boundary.wav")

    assert metadata.extension == "wav"
    assert metadata.mime_type == "audio/wav"
    assert metadata.duration_ms == 7_000


def test_actual_audio_parser_rejects_over_duration_and_fake_audio() -> None:
    with pytest.raises(EntrySoundValidationError, match="7 秒"):
        inspect_audio(_wav_bytes(7.001, rate=48_000), "too-long.wav")

    with pytest.raises(EntrySoundValidationError, match="音频格式"):
        inspect_audio(b"not actually an mp3", "spoofed.mp3")


def test_actual_audio_parser_rejects_extension_that_disagrees_with_content() -> None:
    with pytest.raises(EntrySoundValidationError, match="扩展名"):
        inspect_audio(_wav_bytes(1), "spoofed.mp3")


@pytest.mark.parametrize(
    ("module", "filename", "extension", "mime_type"),
    [
        ("mutagen.mp3", "tone.mp3", "mp3", "audio/mpeg"),
        ("mutagen.flac", "tone.flac", "flac", "audio/flac"),
        ("mutagen.oggvorbis", "tone.ogg", "ogg", "audio/ogg"),
        ("mutagen.mp4", "tone.m4a", "m4a", "audio/mp4"),
        ("mutagen.aac", "tone.aac", "aac", "audio/aac"),
    ],
)
def test_known_mutagen_audio_types_are_mapped_to_safe_formats(
    module: str, filename: str, extension: str, mime_type: str
) -> None:
    parsed_type = type("ParsedAudio", (), {"__module__": module})
    parsed = parsed_type()
    parsed.info = SimpleNamespace(length=1.25)
    with patch("app.services.entry_sound.MutagenFile", return_value=parsed):
        metadata = inspect_audio(b"parser-owned-bytes", filename)

    assert metadata.extension == extension
    assert metadata.mime_type == mime_type
    assert metadata.duration_ms == 1_250


def test_upload_size_guard_allows_exact_limit_and_rejects_one_byte_over() -> None:
    class FakeRequest:
        def __init__(self, chunks: list[bytes]) -> None:
            self._chunks = chunks
            self.headers: dict[str, str] = {}

        async def stream(self):
            for chunk in self._chunks:
                yield chunk

    exact = asyncio.run(
        read_limited_upload(
            FakeRequest([b"a" * (MAX_ENTRY_SOUND_BYTES - 1), b"b"]),  # type: ignore[arg-type]
        )
    )
    assert len(exact) == MAX_ENTRY_SOUND_BYTES

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            read_limited_upload(
                FakeRequest([b"a" * MAX_ENTRY_SOUND_BYTES, b"b"]),  # type: ignore[arg-type]
            )
        )
    assert exc_info.value.status_code == 413


async def _entry_sound_app(tmp_path: Path, *, role: str = "member", upload_limit: int = 10):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        account = Account(
            ts_nickname="Alice" if role != "guest" else "游客-ABC234",
            unique_identifier="uid-alice" if role != "guest" else "guest:test",
            role=role,
            status="active",
        )
        session.add(account)
        await session.commit()
        account_id = account.id

    app = FastAPI()
    app.include_router(music.router, prefix="/api")
    app.state.entry_sound_storage = EntrySoundStorage(tmp_path)
    app.state.entry_sound_capabilities = EntrySoundCapabilities(ttl_seconds=30)
    app.state.entry_sound_upload_limiter = GuestSessionRateLimiter(
        max_requests=upload_limit, window_seconds=3600
    )

    async def override_get_db():
        async with factory() as session:
            yield session

    async def override_account():
        async with factory() as session:
            return await session.get(Account, account_id)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_authenticated_account] = override_account
    return app, engine, factory, account_id


def test_member_can_upload_get_replace_and_delete_entry_sound(tmp_path: Path) -> None:
    async def scenario() -> tuple[list[int], list[dict], int, list[str], int]:
        app, engine, factory, account_id = await _entry_sound_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                first = await client.put(
                    "/api/music/voice/entry-sound",
                    params={"filename": "first.wav"},
                    content=_wav_bytes(1),
                    headers={"Content-Type": "audio/wav"},
                )
                status = await client.get("/api/music/voice/entry-sound")
                old_files = sorted(path.name for path in tmp_path.iterdir())
                second = await client.put(
                    "/api/music/voice/entry-sound",
                    params={"filename": "../../replacement.wav"},
                    content=_wav_bytes(2),
                    headers={"Content-Type": "application/octet-stream"},
                )
                new_files = sorted(path.name for path in tmp_path.iterdir())
                deleted = await client.delete("/api/music/voice/entry-sound")
                missing = await client.get("/api/music/voice/entry-sound")
            async with factory() as session:
                row = await session.scalar(
                    select(EntrySound).where(EntrySound.account_id == account_id)
                )
            return (
                [first.status_code, status.status_code, second.status_code, deleted.status_code],
                [first.json(), status.json(), second.json(), missing.json()],
                len(old_files),
                new_files,
                0 if row is None else 1,
            )
        finally:
            await engine.dispose()

    statuses, bodies, old_count, new_files, db_count = asyncio.run(scenario())
    assert statuses == [200, 200, 200, 200]
    assert bodies[0]["enabled"] is True
    assert bodies[1]["filename"] == "first.wav"
    assert bodies[2]["filename"] == "replacement.wav"
    assert bodies[2]["durationMs"] == 2_000
    assert bodies[3] == {"enabled": False}
    assert old_count == 1
    assert len(new_files) == 1
    assert "replacement" not in new_files[0]
    assert db_count == 0
    assert list(tmp_path.iterdir()) == []


def test_invalid_replacement_keeps_existing_sound(tmp_path: Path) -> None:
    async def scenario() -> tuple[int, dict, list[str]]:
        app, engine, _factory, _account_id = await _entry_sound_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                await client.put(
                    "/api/music/voice/entry-sound",
                    params={"filename": "keep.wav"},
                    content=_wav_bytes(1),
                )
                invalid = await client.put(
                    "/api/music/voice/entry-sound",
                    params={"filename": "bad.mp3"},
                    content=b"not audio",
                )
                current = await client.get("/api/music/voice/entry-sound")
            return invalid.status_code, current.json(), [p.name for p in tmp_path.iterdir()]
        finally:
            await engine.dispose()

    invalid_status, current, files = asyncio.run(scenario())
    assert invalid_status == 400
    assert current["filename"] == "keep.wav"
    assert len(files) == 1


def test_entry_sound_api_rejects_guests_and_rate_limits_members(tmp_path: Path) -> None:
    async def scenario() -> tuple[int, list[int]]:
        guest_app, guest_engine, _guest_factory, _ = await _entry_sound_app(
            tmp_path / "guest", role="guest"
        )
        member_app, member_engine, _member_factory, _ = await _entry_sound_app(
            tmp_path / "member", upload_limit=1
        )
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=guest_app), base_url="http://test"
            ) as client:
                guest = await client.get("/api/music/voice/entry-sound")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=member_app), base_url="http://test"
            ) as client:
                uploads = [
                    await client.put(
                        "/api/music/voice/entry-sound",
                        params={"filename": "tone.wav"},
                        content=_wav_bytes(0.1),
                    )
                    for _ in range(2)
                ]
            return guest.status_code, [response.status_code for response in uploads]
        finally:
            await guest_engine.dispose()
            await member_engine.dispose()

    guest_status, upload_statuses = asyncio.run(scenario())
    assert guest_status == 403
    assert upload_statuses == [200, 429]


def test_entry_sound_api_requires_authentication(tmp_path: Path) -> None:
    async def scenario() -> int:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        app = FastAPI()
        app.include_router(music.router, prefix="/api")

        async def override_get_db():
            async with factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/music/voice/entry-sound")
            return response.status_code
        finally:
            await engine.dispose()

    assert asyncio.run(scenario()) == 401


def test_capability_is_unguessable_short_lived_and_streams_only_while_valid(tmp_path: Path) -> None:
    clock = [100.0]
    capabilities = EntrySoundCapabilities(ttl_seconds=30, clock=lambda: clock[0])
    token = capabilities.create("server-file.wav", "audio/wav")

    assert len(token) >= 40
    assert capabilities.resolve("wrong-token") is None
    assert capabilities.resolve(token) is not None
    clock[0] = 131.0
    assert capabilities.resolve(token) is None


def test_capability_stream_serves_only_a_valid_server_generated_file(tmp_path: Path) -> None:
    async def scenario() -> tuple[int, bytes, int, str]:
        storage = EntrySoundStorage(tmp_path)
        filename = storage.write_atomic(_wav_bytes(0.1), "wav")
        capabilities = EntrySoundCapabilities(ttl_seconds=30)
        token = capabilities.create(filename, "audio/wav")
        app = FastAPI()
        app.include_router(music.router, prefix="/api")
        app.state.entry_sound_storage = storage
        app.state.entry_sound_capabilities = capabilities
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            valid = await client.get(
                f"/api/music/voice/entry-sound/stream/{token}"
            )
            invalid = await client.get(
                "/api/music/voice/entry-sound/stream/not-a-ticket"
            )
        return (
            valid.status_code,
            valid.content,
            invalid.status_code,
            valid.headers.get("cache-control", ""),
        )

    valid_status, content, invalid_status, cache_control = asyncio.run(scenario())
    assert valid_status == 200
    assert content == _wav_bytes(0.1)
    assert invalid_status == 404
    assert cache_control == "private, no-store"


class _FakeVoiceBots:
    async def current_bot_id(self, _db, _account_id: int) -> str:
        return "voice-bot"

    async def ensure_existing_connected(self, _db, _account_id: int) -> str:
        return "voice-bot"


class _FakeTsmusic:
    def __init__(
        self, *, effect_error: Exception | None = None, effect_delay: float = 0
    ) -> None:
        self.effect_error = effect_error
        self.effect_delay = effect_delay
        self.effect_urls: list[tuple[str, str]] = []

    async def get_bot_client_id(self, _bid: str) -> int:
        return 77

    async def join_channel(self, _cid: int, _password: str, *, bot_id: str) -> dict:
        return {"ok": True, "detail": ""}

    async def play_sound_effect(self, url: str, *, bot_id: str) -> dict:
        self.effect_urls.append((url, bot_id))
        if self.effect_delay:
            await asyncio.sleep(self.effect_delay)
        if self.effect_error:
            raise self.effect_error
        return {"ok": True}


def test_successful_member_channel_move_triggers_sound_and_effect_failure_is_nonfatal(
    tmp_path: Path,
) -> None:
    async def run_once(
        effect_error: Exception | None,
        *,
        effect_delay: float = 0,
        public_url: str = "https://voice.example",
    ) -> tuple[dict, _FakeTsmusic]:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            account = Account(
                ts_nickname="Alice", unique_identifier="uid", role="member", status="active"
            )
            session.add(account)
            await session.flush()
            session.add(
                EntrySound(
                    account_id=account.id,
                    storage_filename="server.wav",
                    original_filename="tone.wav",
                    mime_type="audio/wav",
                    size_bytes=100,
                    duration_ms=500,
                )
            )
            await session.commit()

        fake = _FakeTsmusic(effect_error=effect_error, effect_delay=effect_delay)
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    voice_bots=_FakeVoiceBots(),
                    ts3_monitor=SimpleNamespace(running=False),
                    entry_sound_capabilities=EntrySoundCapabilities(),
                )
            ),
            url=httpx.URL("https://attacker.invalid/api/music/voice/channel"),
            headers={"host": "attacker.invalid"},
        )
        async with factory() as session:
            account = await session.scalar(select(Account))
            with patch.object(
                music,
                "settings",
                SimpleNamespace(live_audio_public_url=public_url),
            ), patch.object(music, "ENTRY_SOUND_EFFECT_TIMEOUT_SECONDS", 0.02):
                result = await music.move_voice_channel(
                    music.VoiceChannelRequest(cid=9), request, fake, account, session
                )
                await asyncio.sleep(0.03)
        await engine.dispose()
        return result, fake

    success, success_fake = asyncio.run(run_once(None))
    failed_effect, failed_fake = asyncio.run(run_once(RuntimeError("upstream failed")))
    hostile, hostile_fake = asyncio.run(run_once(None, public_url=""))
    assert success == {"ok": True, "cid": 9}
    assert failed_effect == {"ok": True, "cid": 9}
    assert hostile == {"ok": True, "cid": 9}
    assert hostile_fake.effect_urls == []
    for fake in (success_fake, failed_fake):
        assert len(fake.effect_urls) == 1
        url, bot_id = fake.effect_urls[0]
        assert bot_id == "voice-bot"
        assert url.startswith(
            "https://voice.example/api/music/voice/entry-sound/stream/"
        )


def test_effect_delivery_has_a_deadline_without_blocking_the_move() -> None:
    async def scenario() -> _FakeTsmusic:
        fake = _FakeTsmusic(effect_delay=1)
        with patch.object(music, "ENTRY_SOUND_EFFECT_TIMEOUT_SECONDS", 0.01):
            await music._deliver_entry_sound(
                fake,
                "https://voice.example/capability",
                account_id=1,
                bot_id="voice-bot",
            )
        return fake

    fake = asyncio.run(asyncio.wait_for(scenario(), timeout=0.2))
    assert fake.effect_urls == [
        ("https://voice.example/capability", "voice-bot")
    ]


def test_unconfigured_public_url_never_falls_back_to_the_request_host() -> None:
    hostile_request = SimpleNamespace(
        url=httpx.URL("https://attacker.invalid/api/music/voice/channel"),
        client=SimpleNamespace(host="203.0.113.9"),
        headers={},
    )
    with patch.object(
        music, "settings", SimpleNamespace(live_audio_public_url="")
    ), pytest.raises(RuntimeError, match="LIVE_AUDIO_PUBLIC_URL"):
        music._entry_sound_public_base(hostile_request)


def test_unconfigured_public_url_allows_only_loopback_development_hosts() -> None:
    local_request = SimpleNamespace(
        url=httpx.URL("http://127.0.0.1:8001/api/music/voice/channel"),
        client=SimpleNamespace(host="127.0.0.1"),
        headers={},
    )
    with patch.object(
        music, "settings", SimpleNamespace(live_audio_public_url="")
    ):
        assert music._entry_sound_public_base(local_request) == "http://127.0.0.1:8001"


@pytest.mark.parametrize(
    ("client_host", "headers"),
    [
        ("203.0.113.9", {}),
        ("127.0.0.1", {"x-forwarded-for": "203.0.113.9"}),
        ("127.0.0.1", {"x-forwarded-host": "public.example"}),
    ],
)
def test_client_supplied_loopback_host_cannot_enable_inferred_callback(
    client_host: str, headers: dict[str, str]
) -> None:
    request = SimpleNamespace(
        url=httpx.URL("http://127.0.0.1:9999/api/music/voice/channel"),
        client=SimpleNamespace(host=client_host),
        headers=headers,
    )
    with patch.object(
        music, "settings", SimpleNamespace(live_audio_public_url="")
    ), pytest.raises(RuntimeError, match="LIVE_AUDIO_PUBLIC_URL"):
        music._entry_sound_public_base(request)


@pytest.mark.parametrize(
    "configured",
    [
        "file:///tmp/audio",
        "https://user:password@voice.example",
        "https://voice.example?redirect=evil",
        "https://voice.example#fragment",
        "https://voice.example/base-path",
    ],
)
def test_configured_public_url_must_be_a_safe_absolute_http_url(
    configured: str,
) -> None:
    request = SimpleNamespace(
        url=httpx.URL("http://127.0.0.1:8001"),
        client=SimpleNamespace(host="127.0.0.1"),
        headers={},
    )
    with patch.object(
        music, "settings", SimpleNamespace(live_audio_public_url=configured)
    ), pytest.raises(RuntimeError, match="LIVE_AUDIO_PUBLIC_URL"):
        music._entry_sound_public_base(request)


def test_guest_or_member_without_sound_does_not_trigger_effect(tmp_path: Path) -> None:
    async def run(role: str) -> _FakeTsmusic:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            account = Account(
                ts_nickname="Guest" if role == "guest" else "Member",
                unique_identifier=f"uid-{role}",
                role=role,
                status="active",
            )
            session.add(account)
            await session.commit()
        fake = _FakeTsmusic()
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    guest_voice_limiter=SimpleNamespace(
                        allow=AsyncMock(return_value=True)
                    ),
                    voice_bots=_FakeVoiceBots(),
                    ts3_monitor=SimpleNamespace(running=False),
                    entry_sound_capabilities=EntrySoundCapabilities(),
                )
            ),
            url=SimpleNamespace(scheme="http", netloc="test"),
            headers={"host": "test"},
        )
        async with factory() as session:
            account = await session.scalar(select(Account))
            await music.move_voice_channel(
                music.VoiceChannelRequest(cid=3), request, fake, account, session
            )
        await engine.dispose()
        return fake

    assert asyncio.run(run("guest")).effect_urls == []
    assert asyncio.run(run("member")).effect_urls == []


def test_tsmusic_client_posts_capability_url_to_sound_effect_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/session/login":
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, json={"ok": True})

    async def scenario() -> dict:
        client = TSMusicClient("http://bot.example", "u", "p", bot_id="bot-a")
        await client._http.aclose()
        client._http = httpx.AsyncClient(
            base_url="http://bot.example", transport=httpx.MockTransport(handler)
        )
        try:
            return await client.play_sound_effect(
                "https://voice.example/capability", bot_id="bot-a"
            )
        finally:
            await client.close()

    assert asyncio.run(scenario()) == {"ok": True}
    effect = next(request for request in requests if request.url.path.endswith("sound-effect"))
    assert effect.url.path == "/api/player/bot-a/sound-effect"
    assert json.loads(effect.content) == {"url": "https://voice.example/capability"}
