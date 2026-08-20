"""Single-use friend invitation issuance, inspection, and redemption."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import hash_password
from ..models import Account, Friend, FriendInvitation

INVITATION_TTL = timedelta(days=7)


def _now() -> datetime:
    return datetime.now()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class InvitationDetails:
    inviter_nickname: str
    expires_at: datetime


class InvitationService:
    """Database operations for invitation links.

    Raw bearer tokens are returned only at issuance and are never persisted.
    Redemption uses a conditional UPDATE as the single-use compare-and-swap.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def issue(self, inviter: Account) -> tuple[str, datetime]:
        if inviter.role == "guest" or inviter.status != "active":
            raise ValueError("only active registered accounts may issue invitations")

        now = _now()
        expires_at = now + INVITATION_TTL
        for _attempt in range(3):
            token = secrets.token_urlsafe(32)
            await self.db.execute(
                select(Account.id)
                .where(Account.id == inviter.id)
                .with_for_update()
            )
            await self.db.execute(
                update(FriendInvitation)
                .where(
                    FriendInvitation.inviter_account_id == inviter.id,
                    FriendInvitation.used_at.is_(None),
                    FriendInvitation.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            self.db.add(
                FriendInvitation(
                    inviter_account_id=inviter.id,
                    token_hash=_token_hash(token),
                    expires_at=expires_at,
                )
            )
            try:
                await self.db.commit()
                return token, expires_at
            except IntegrityError:
                await self.db.rollback()
        raise RuntimeError("unable to allocate a unique invitation token")

    async def inspect(self, token: str) -> InvitationDetails | None:
        row = (
            await self.db.execute(
                select(FriendInvitation.expires_at, Account.ts_nickname)
                .join(Account, Account.id == FriendInvitation.inviter_account_id)
                .where(
                    FriendInvitation.token_hash == _token_hash(token),
                    FriendInvitation.expires_at > _now(),
                    FriendInvitation.used_at.is_(None),
                    FriendInvitation.revoked_at.is_(None),
                    Account.status == "active",
                    Account.role != "guest",
                )
            )
        ).one_or_none()
        if row is None:
            return None
        return InvitationDetails(
            inviter_nickname=row.ts_nickname,
            expires_at=row.expires_at,
        )

    async def redeem(
        self,
        *,
        token: str,
        ts_nickname: str,
        qq_number: str,
        password: str,
    ) -> Account | None:
        """Atomically claim an invitation, create an account, and add friendships."""
        now = _now()
        invitation = await self.db.scalar(
            select(FriendInvitation)
            .join(Account, Account.id == FriendInvitation.inviter_account_id)
            .where(
                FriendInvitation.token_hash == _token_hash(token),
                FriendInvitation.expires_at > now,
                FriendInvitation.used_at.is_(None),
                FriendInvitation.revoked_at.is_(None),
                Account.status == "active",
                Account.role != "guest",
            )
            .with_for_update(of=Account)
        )
        if invitation is None:
            await self.db.rollback()
            return None

        account = Account(
            ts_nickname=ts_nickname,
            unique_identifier=f"invite:{secrets.token_urlsafe(32)}",
            password_hash=hash_password(password),
            qq_number=qq_number,
            notification_channel="qq",
            role="member",
            status="active",
        )
        self.db.add(account)
        await self.db.flush()

        claim = await self.db.execute(
            update(FriendInvitation)
            .where(
                FriendInvitation.id == invitation.id,
                FriendInvitation.expires_at > now,
                FriendInvitation.used_at.is_(None),
                FriendInvitation.revoked_at.is_(None),
            )
            .values(used_at=now, used_by_account_id=account.id)
            .execution_options(synchronize_session=False)
        )
        if claim.rowcount != 1:
            await self.db.rollback()
            return None

        self.db.add_all(
            [
                Friend(
                    account_id=invitation.inviter_account_id,
                    friend_account_id=account.id,
                ),
                Friend(
                    account_id=account.id,
                    friend_account_id=invitation.inviter_account_id,
                ),
            ]
        )
        await self.db.commit()
        return account
