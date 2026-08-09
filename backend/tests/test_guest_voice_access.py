"""Temporary guest sessions are scoped to browser TeamSpeak voice only."""

from __future__ import annotations

import asyncio
import re
import secrets
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.deps import AccountDep, VoiceAccountDep
from app.models import Account, Session, VoiceBot
from app.routers import auth
from app.routers import music
from app.services.auth_service import GUEST_SESSION_TTL
from app.services.guest_access import GuestSessionRateLimiter
from app.services.voice_bot import VoiceBotManager
from app.services.voice_downlink import VoiceDownlinkTickets


async def _exercise_guest_access(*, request_limit: int = 5) -> dict:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    app = FastAPI()
    app.include_router(auth.router, prefix="/api")
    app.include_router(music.router, prefix="/api")
    app.state.guest_session_limiter = GuestSessionRateLimiter(
        max_requests=request_limit,
        window_seconds=3600,
    )
    app.state.guest_voice_limiter = GuestSessionRateLimiter(
        max_requests=20,
        window_seconds=60,
    )
    app.state.voice_downlink = VoiceDownlinkTickets()

    class FakeVoiceBots:
        async def acquire(self, _db, account) -> dict:
            return {"botId": "guest-bot", "nickname": account.ts_nickname}

        def schedule_release(self, *_args, **_kwargs) -> None:
            return None

        async def current_bot_id(self, _db, _account_id) -> str | None:
            return "guest-bot"

    app.state.voice_bots = FakeVoiceBots()
    app.state.ts3_monitor = SimpleNamespace(running=False)
    app.state.tsmusic = SimpleNamespace()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    @app.get("/member-only")
    async def member_only(account: AccountDep):
        return {"role": account.role}

    @app.get("/voice-allowed")
    async def voice_allowed(account: VoiceAccountDep):
        return {"role": account.role, "nickname": account.ts_nickname}

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            issued = await client.post("/api/auth/guest")
            body = issued.json()
            token = body.get("token", "")
            headers = {"X-Session-Token": token}
            session_response = await client.post(
                "/api/auth/get_session", json={"token": token}
            )
            member_response = await client.get("/member-only", headers=headers)
            voice_response = await client.get("/voice-allowed", headers=headers)
            real_voice_response = await client.post(
                "/api/music/voice/session", headers=headers
            )
            real_downlink_response = await client.post(
                "/api/music/voice/start", headers=headers
            )
            real_music_response = await client.get("/api/music/bots", headers=headers)

        async with session_factory() as session:
            stored_session = await session.scalar(
                select(Session).where(Session.token == token)
            )
    finally:
        await engine.dispose()

    return {
        "issued_status": issued.status_code,
        "issued": body,
        "session": session_response.json(),
        "member_status": member_response.status_code,
        "voice_status": voice_response.status_code,
        "voice": voice_response.json(),
        "real_voice_status": real_voice_response.status_code,
        "real_downlink_status": real_downlink_response.status_code,
        "real_music_status": real_music_response.status_code,
        "stored_session": stored_session,
    }


def test_guest_session_gets_a_generated_short_lived_identity() -> None:
    result = asyncio.run(_exercise_guest_access())

    assert result["issued_status"] == 200
    assert result["issued"]["success"] is True
    assert result["issued"]["role"] == "guest"
    assert result["issued"]["expires_in"] == int(GUEST_SESSION_TTL.total_seconds())
    assert re.fullmatch(r"游客-[A-Z2-9]{6}", result["issued"]["ts_nickname"])
    assert result["issued"]["token"]

    session_data = result["session"]["session_data"]
    assert session_data["role"] == "guest"
    assert session_data["ts_nickname"] == result["issued"]["ts_nickname"]

    stored_session = result["stored_session"]
    assert stored_session is not None
    remaining = stored_session.expires_at - datetime.now()
    assert GUEST_SESSION_TTL.total_seconds() - 10 <= remaining.total_seconds()
    assert remaining <= GUEST_SESSION_TTL


def test_guest_token_is_rejected_by_member_endpoints_but_allowed_for_voice() -> None:
    result = asyncio.run(_exercise_guest_access())

    assert result["member_status"] == 403
    assert result["voice_status"] == 200
    assert result["voice"]["role"] == "guest"
    assert result["voice"]["nickname"] == result["issued"]["ts_nickname"]
    assert result["real_voice_status"] == 200
    assert result["real_downlink_status"] == 200
    assert result["real_music_status"] == 403


def test_guest_session_issuance_is_rate_limited_per_client() -> None:
    async def scenario() -> list[int]:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        app = FastAPI()
        app.include_router(auth.router, prefix="/api")
        app.state.guest_session_limiter = GuestSessionRateLimiter(
            max_requests=2,
            window_seconds=3600,
        )

        async def override_get_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        transport = httpx.ASGITransport(app=app, client=("203.0.113.7", 12345))
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                responses = [await client.post("/api/auth/guest") for _ in range(3)]
            return [response.status_code for response in responses]
        finally:
            await engine.dispose()

    assert asyncio.run(scenario()) == [200, 200, 429]


def test_guest_hangup_deletes_identity_while_member_hangup_only_stops_it() -> None:
    class FakeTsmusic:
        def __init__(self) -> None:
            self.stopped: list[str] = []
            self.deleted: list[str] = []

        async def stop_bot(self, bot_id: str) -> None:
            self.stopped.append(bot_id)

        async def delete_bot(self, bot_id: str) -> None:
            self.deleted.append(bot_id)

    async def scenario() -> tuple[FakeTsmusic, FakeTsmusic]:
        member_tsmusic = FakeTsmusic()
        member_manager = VoiceBotManager(lambda: member_tsmusic)
        await member_manager.release_now(1, "member-bot")

        guest_tsmusic = FakeTsmusic()
        guest_manager = VoiceBotManager(lambda: guest_tsmusic)
        await guest_manager.release_now(2, "guest-bot", destroy=True)
        return member_tsmusic, guest_tsmusic

    member, guest = asyncio.run(scenario())
    assert member.stopped == ["member-bot"]
    assert member.deleted == []
    assert guest.stopped == []
    assert guest.deleted == ["guest-bot"]


def test_expired_guest_cleanup_deletes_upstream_identity_before_local_records() -> None:
    class FakeTsmusic:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        async def delete_bot(self, bot_id: str) -> dict:
            self.deleted.append(bot_id)
            return {}

    async def scenario() -> tuple[int, FakeTsmusic, object, object, object]:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        fake = FakeTsmusic()
        manager = VoiceBotManager(lambda: fake, session_factory)
        async with session_factory() as session:
            account = Account(
                ts_nickname="游客-EXPIRE",
                unique_identifier="guest:expired",
                role="guest",
                status="active",
            )
            session.add(account)
            await session.flush()
            session.add_all(
                [
                    Session(
                        token=secrets.token_urlsafe(12),
                        account_id=account.id,
                        expires_at=datetime.now() - timedelta(seconds=1),
                    ),
                    VoiceBot(account_id=account.id, bot_id="expired-bot"),
                ]
            )
            await session.commit()
            account_id = account.id

        async with session_factory() as session:
            removed = await manager.cleanup_expired_guests(session)
        async with session_factory() as session:
            account_row = await session.get(Account, account_id)
            voice_row = await session.scalar(
                select(VoiceBot).where(VoiceBot.account_id == account_id)
            )
            session_row = await session.scalar(
                select(Session).where(Session.account_id == account_id)
            )
        await engine.dispose()
        return removed, fake, account_row, voice_row, session_row

    removed, fake, account, voice_bot, session = asyncio.run(scenario())
    assert removed == 1
    assert fake.deleted == ["expired-bot"]
    assert account is None
    assert voice_bot is None
    assert session is None


def test_expired_guest_cleanup_keeps_local_record_when_upstream_delete_fails() -> None:
    class FailingTsmusic:
        async def delete_bot(self, _bot_id: str) -> dict:
            raise RuntimeError("upstream unavailable")

    async def scenario() -> tuple[int, object]:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            account = Account(
                ts_nickname="游客-RETRY2",
                unique_identifier="guest:retry",
                role="guest",
                status="active",
            )
            session.add(account)
            await session.flush()
            session.add_all(
                [
                    Session(
                        token="retry-token",
                        account_id=account.id,
                        expires_at=datetime.now() - timedelta(seconds=1),
                    ),
                    VoiceBot(account_id=account.id, bot_id="retry-bot"),
                ]
            )
            await session.commit()
            account_id = account.id

        manager = VoiceBotManager(lambda: FailingTsmusic(), session_factory)
        async with session_factory() as session:
            removed = await manager.cleanup_expired_guests(session)
        async with session_factory() as session:
            retained = await session.get(Account, account_id)
        await engine.dispose()
        return removed, retained

    removed, retained = asyncio.run(scenario())
    assert removed == 0
    assert retained is not None


def test_abandoned_guest_join_is_scheduled_for_identity_destruction() -> None:
    class FakeLimiter:
        async def allow(self, _key: str) -> bool:
            return True

    class FakeVoiceBots:
        def __init__(self) -> None:
            self.releases: list[tuple[int, str, bool]] = []

        async def acquire(self, _db, _account) -> dict:
            return {"botId": "guest-bot", "nickname": "游客-ABC234"}

        def schedule_release(self, account_id, bot_id, *, destroy=False) -> None:
            self.releases.append((account_id, bot_id, destroy))

    async def scenario() -> tuple[dict, list[tuple[int, str, bool]]]:
        voice_bots = FakeVoiceBots()
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    guest_voice_limiter=FakeLimiter(),
                    voice_bots=voice_bots,
                    ts3_monitor=SimpleNamespace(running=False),
                )
            )
        )
        account = SimpleNamespace(id=9, role="guest", ts_nickname="游客-ABC234")
        result = await music.open_voice_session(request, account, None)
        return result, voice_bots.releases

    result, releases = asyncio.run(scenario())
    assert result["botId"] == "guest-bot"
    assert releases == [(9, "guest-bot", True)]


def test_claiming_stream_during_grace_cancels_guest_destruction() -> None:
    class FakeTsmusic:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        async def delete_bot(self, bot_id: str) -> dict:
            self.deleted.append(bot_id)
            return {}

    async def scenario() -> list[str]:
        fake = FakeTsmusic()
        manager = VoiceBotManager(lambda: fake)
        with patch("app.services.voice_bot.RELEASE_GRACE_SECONDS", 0.05):
            manager.schedule_release(9, "guest-bot", destroy=True)
            await asyncio.sleep(0.01)
            await manager.keep_alive(9)
            await asyncio.sleep(0.08)
        return fake.deleted

    assert asyncio.run(scenario()) == []


def test_guest_capacity_check_and_bot_reservation_are_globally_serialized() -> None:
    class TrackingManager(VoiceBotManager):
        def __init__(self) -> None:
            super().__init__(lambda: object())
            self.in_reservation = 0
            self.max_concurrent_reservations = 0

        async def _ensure_guest_capacity(self, _db, _account) -> None:
            self.in_reservation += 1
            self.max_concurrent_reservations = max(
                self.max_concurrent_reservations, self.in_reservation
            )
            await asyncio.sleep(0.03)

        async def _ensure_bot(self, _db, _tsmusic, account) -> str:
            await asyncio.sleep(0.03)
            self.in_reservation -= 1
            return f"guest-bot-{account.id}"

        async def _ensure_connected(self, _tsmusic, _bot_id) -> None:
            return None

    async def scenario() -> int:
        manager = TrackingManager()
        accounts = [
            SimpleNamespace(id=1, role="guest", ts_nickname="游客-ONE234"),
            SimpleNamespace(id=2, role="guest", ts_nickname="游客-TWO234"),
        ]
        await asyncio.gather(*(manager.acquire(None, account) for account in accounts))
        return manager.max_concurrent_reservations

    assert asyncio.run(scenario()) == 1


def test_guest_microphone_start_has_its_own_operation_limit() -> None:
    async def scenario() -> tuple[dict, int]:
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    guest_voice_limiter=GuestSessionRateLimiter(
                        max_requests=1, window_seconds=60
                    ),
                    voice_bots=SimpleNamespace(
                        current_bot_id=AsyncMock(return_value="guest-bot")
                    ),
                )
            )
        )
        account = SimpleNamespace(id=9, role="guest", ts_nickname="游客-ABC234")
        body = music.VoiceMicRequest(mimeType="audio/webm;codecs=opus")
        with patch.object(
            music, "_open_live_relay", AsyncMock(return_value={"ok": True})
        ):
            first = await music.start_voice_microphone(
                body, request, SimpleNamespace(), account, None
            )
            try:
                await music.start_voice_microphone(
                    body, request, SimpleNamespace(), account, None
                )
            except HTTPException as exc:
                return first, exc.status_code
        raise AssertionError("second microphone start must be rate limited")

    first, second_status = asyncio.run(scenario())
    assert first == {"ok": True}
    assert second_status == 429
