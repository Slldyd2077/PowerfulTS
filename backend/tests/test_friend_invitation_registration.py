"""Invitation registration creates a QQ-backed account and mutual friendship."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.models import Account, Friend, FriendInvitation, Session
from app.routers import auth, friends


TEST_INVITER_SESSION = "inviter-session"


class _AllowAllLimiter:
    async def allow(self, _key: str) -> bool:
        return True


class _DenyAllLimiter:
    async def allow(self, _key: str) -> bool:
        return False


async def _new_app():
    database_dir = tempfile.TemporaryDirectory(prefix="powerfults-invitation-")
    database_path = Path(database_dir.name, "test.db").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    app = FastAPI()
    app.include_router(auth.router, prefix="/api")
    app.include_router(friends.router, prefix="/api")
    app.state.invite_registration_limiter = _AllowAllLimiter()
    app.state.ts3_monitor = SimpleNamespace()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with session_factory() as session:
        inviter = Account(
            ts_nickname="Inviter",
            unique_identifier="uid-inviter",
            password_hash=hash_password("invite-password"),
            role="member",
            status="active",
        )
        session.add(inviter)
        await session.flush()
        session.add(
            Session(
                token=TEST_INVITER_SESSION,
                account_id=inviter.id,
                expires_at=datetime.now() + timedelta(hours=1),
            )
        )
        await session.commit()
        inviter_id = inviter.id

    return app, engine, session_factory, inviter_id, database_dir


async def _dispose_test_engine(engine, database_dir) -> None:
    await engine.dispose()
    database_dir.cleanup()


def test_invitation_registration_creates_qq_account_and_mutual_friendship() -> None:
    async def scenario():
        app, engine, session_factory, inviter_id, database_dir = await _new_app()
        transport = httpx.ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                issued = await client.post(
                    "/api/friends/invitations",
                    headers={"X-Session-Token": "inviter-session"},
                )
                issued_body = issued.json()
                token = issued_body["token"]

                inspected = await client.post(
                    "/api/auth/invitations/inspect", json={"token": token}
                )
                registered = await client.post(
                    "/api/auth/register",
                    json={
                        "ts_nickname": "Invitee",
                        "password": "invitee-password",
                        "invite_token": token,
                        "qq_number": "12345678",
                    },
                )

            async with session_factory() as session:
                invitee = await session.scalar(
                    select(Account).where(Account.ts_nickname == "Invitee")
                )
                relations = (
                    await session.execute(
                        select(Friend.account_id, Friend.friend_account_id)
                    )
                ).all()
                invitation = await session.scalar(select(FriendInvitation))
        finally:
            await _dispose_test_engine(engine, database_dir)

        return (
            inviter_id,
            issued,
            issued_body,
            inspected,
            registered,
            invitee,
            set(relations),
            invitation,
        )

    (
        inviter_id,
        issued,
        issued_body,
        inspected,
        registered,
        invitee,
        relations,
        invitation,
    ) = asyncio.run(scenario())

    assert issued.status_code == 200
    assert issued_body["success"] is True
    assert issued_body["token"]
    assert issued_body["expires_at"]
    assert inspected.json() == {
        "valid": True,
        "inviter_nickname": "Inviter",
        "expires_at": issued_body["expires_at"],
    }
    assert registered.json() == {"success": True, "message": "注册成功，已与邀请者成为好友"}
    assert invitee is not None
    assert invitee.qq_number == "12345678"
    assert invitee.unique_identifier.startswith("invite:")
    assert invitee.notification_channel == "qq"
    assert relations == {(inviter_id, invitee.id), (invitee.id, inviter_id)}
    assert invitation is not None
    assert invitation.used_at is not None
    assert invitation.used_by_account_id == invitee.id
    assert invitation.token_hash != issued_body["token"]


def test_invitation_is_single_use_and_qq_is_required() -> None:
    async def scenario():
        app, engine, _session_factory, _inviter_id, database_dir = await _new_app()
        transport = httpx.ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                issued = await client.post(
                    "/api/friends/invitations",
                    headers={"X-Session-Token": "inviter-session"},
                )
                token = issued.json()["token"]
                missing_qq = await client.post(
                    "/api/auth/register",
                    json={
                        "ts_nickname": "NoQQ",
                        "password": "invitee-password",
                        "invite_token": token,
                    },
                )
                first = await client.post(
                    "/api/auth/register",
                    json={
                        "ts_nickname": "FirstInvitee",
                        "password": "invitee-password",
                        "invite_token": token,
                        "qq_number": "12345679",
                    },
                )
                second = await client.post(
                    "/api/auth/register",
                    json={
                        "ts_nickname": "SecondInvitee",
                        "password": "invitee-password",
                        "invite_token": token,
                        "qq_number": "12345680",
                    },
                )
        finally:
            await _dispose_test_engine(engine, database_dir)
        return missing_qq, first, second

    missing_qq, first, second = asyncio.run(scenario())

    assert missing_qq.json() == {"success": False, "error": "邀请注册必须填写 QQ 号"}
    assert first.json()["success"] is True
    assert second.json() == {"success": False, "error": "邀请链接无效、已过期或已被使用"}


def test_generating_a_new_invitation_revokes_the_previous_link() -> None:
    async def scenario():
        app, engine, _session_factory, _inviter_id, database_dir = await _new_app()
        transport = httpx.ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                headers = {"X-Session-Token": "inviter-session"}
                first = (await client.post("/api/friends/invitations", headers=headers)).json()
                second = (await client.post("/api/friends/invitations", headers=headers)).json()
                old_status = await client.post(
                    "/api/auth/invitations/inspect", json={"token": first["token"]}
                )
                new_status = await client.post(
                    "/api/auth/invitations/inspect", json={"token": second["token"]}
                )
        finally:
            await _dispose_test_engine(engine, database_dir)
        return first, second, old_status, new_status

    first, second, old_status, new_status = asyncio.run(scenario())

    assert first["token"] != second["token"]
    assert old_status.status_code == 404
    assert old_status.json() == {"detail": "邀请链接无效、已过期或已被使用"}
    assert new_status.json()["valid"] is True


def test_invitation_generation_requires_a_member_session() -> None:
    async def scenario():
        app, engine, _session_factory, _inviter_id, database_dir = await _new_app()
        transport = httpx.ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/api/friends/invitations")
        finally:
            await _dispose_test_engine(engine, database_dir)
        return response

    response = asyncio.run(scenario())
    assert response.status_code == 401


def test_invitation_generation_is_rate_limited_per_account() -> None:
    async def scenario():
        app, engine, _session_factory, _inviter_id, database_dir = await _new_app()
        app.state.friend_invitation_limiter = _DenyAllLimiter()
        transport = httpx.ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/friends/invitations",
                    headers={"X-Session-Token": "inviter-session"},
                )
        finally:
            await _dispose_test_engine(engine, database_dir)
        return response

    response = asyncio.run(scenario())
    assert response.status_code == 429
    assert response.json() == {"detail": "邀请链接生成过于频繁，请稍后再试"}


def test_qq_alone_does_not_bypass_the_existing_ts_registration_path() -> None:
    async def scenario():
        app, engine, _session_factory, _inviter_id, database_dir = await _new_app()
        transport = httpx.ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/auth/register",
                    json={
                        "ts_nickname": "NoInvitation",
                        "password": "invitee-password",
                        "qq_number": "12345681",
                    },
                )
        finally:
            await _dispose_test_engine(engine, database_dir)
        return response

    response = asyncio.run(scenario())
    assert response.json() == {"success": False, "error": "请先获取验证码"}


def test_concurrent_redemption_claims_the_invitation_once() -> None:
    async def scenario():
        app, engine, session_factory, inviter_id, database_dir = await _new_app()
        transport = httpx.ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                issued = await client.post(
                    "/api/friends/invitations",
                    headers={"X-Session-Token": "inviter-session"},
                )
                token = issued.json()["token"]

                async def redeem(nickname: str, qq_number: str):
                    return await client.post(
                        "/api/auth/register",
                        json={
                            "ts_nickname": nickname,
                            "password": "invitee-password",
                            "invite_token": token,
                            "qq_number": qq_number,
                        },
                    )

                responses = await asyncio.gather(
                    redeem("ConcurrentInviteeA", "12345682"),
                    redeem("ConcurrentInviteeB", "12345683"),
                )

            async with session_factory() as session:
                invitees = list(
                    (
                        await session.scalars(
                            select(Account).where(
                                Account.ts_nickname.in_(
                                    ["ConcurrentInviteeA", "ConcurrentInviteeB"]
                                )
                            )
                        )
                    ).all()
                )
                relations = (
                    await session.execute(
                        select(Friend.account_id, Friend.friend_account_id)
                    )
                ).all()
        finally:
            await _dispose_test_engine(engine, database_dir)
        return inviter_id, responses, invitees, set(relations)

    inviter_id, responses, invitees, relations = asyncio.run(scenario())

    bodies = [response.json() for response in responses]
    assert sum(body.get("success") is True for body in bodies) == 1
    assert bodies.count(
        {"success": False, "error": "邀请链接无效、已过期或已被使用"}
    ) == 1
    assert len(invitees) == 1
    invitee_id = invitees[0].id
    assert relations == {(inviter_id, invitee_id), (invitee_id, inviter_id)}


def test_invitation_registration_rejects_non_ascii_or_malformed_qq() -> None:
    async def scenario():
        app, engine, _session_factory, _inviter_id, database_dir = await _new_app()
        transport = httpx.ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                issued = await client.post(
                    "/api/friends/invitations",
                    headers={"X-Session-Token": "inviter-session"},
                )
                token = issued.json()["token"]
                responses = []
                for index, qq_number in enumerate(
                    ["01234", "1234", "12345678901234567", "１２３４５"]
                ):
                    responses.append(
                        await client.post(
                            "/api/auth/register",
                            json={
                                "ts_nickname": f"InvalidQQ{index}",
                                "password": "invitee-password",
                                "invite_token": token,
                                "qq_number": qq_number,
                            },
                        )
                    )
                valid = await client.post(
                    "/api/auth/register",
                    json={
                        "ts_nickname": "ValidAfterInvalidQQ",
                        "password": "invitee-password",
                        "invite_token": token,
                        "qq_number": "12345",
                    },
                )
        finally:
            await _dispose_test_engine(engine, database_dir)
        return responses, valid

    responses, valid = asyncio.run(scenario())

    assert all(
        response.json()
        == {
            "success": False,
            "error": "QQ 号格式错误，请填写 5-16 位且首位非 0 的数字",
        }
        for response in responses
    )
    assert valid.json()["success"] is True


def test_invitation_registration_trims_contact_fields_and_rejects_blank_nickname() -> None:
    async def scenario():
        app, engine, session_factory, _inviter_id, database_dir = await _new_app()
        transport = httpx.ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                issued = await client.post(
                    "/api/friends/invitations",
                    headers={"X-Session-Token": "inviter-session"},
                )
                token = issued.json()["token"]
                blank_nickname = await client.post(
                    "/api/auth/register",
                    json={
                        "ts_nickname": "   ",
                        "password": "invitee-password",
                        "invite_token": token,
                        "qq_number": "12345684",
                    },
                )
                registered = await client.post(
                    "/api/auth/register",
                    json={
                        "ts_nickname": "  TrimmedInvitee  ",
                        "password": "invitee-password",
                        "invite_token": f" {token} ",
                        "qq_number": " 12345684 ",
                    },
                )

            async with session_factory() as session:
                invitee = await session.scalar(
                    select(Account).where(Account.ts_nickname == "TrimmedInvitee")
                )
        finally:
            await _dispose_test_engine(engine, database_dir)
        return blank_nickname, registered, invitee

    blank_nickname, registered, invitee = asyncio.run(scenario())

    assert blank_nickname.json() == {"success": False, "error": "TS 昵称不能为空"}
    assert registered.json()["success"] is True
    assert invitee is not None
    assert invitee.qq_number == "12345684"
