"""账号 / 会话 / 验证码 服务 (SQLite + SQLAlchemy async)。

安全设计：
  - 验证码 attempts 上限（防暴力枚举）+ 发码节流（防轰炸）
  - 验证码绑定 expected_uid（注册时校验，防昵称换人冒名）
  - 登录失败计数 + 锁定（防密码爆破）+ 统一错误消息 + dummy 哈希恒定时间（防账号枚举/时序）
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import generate_token, hash_password, verify_password
from ..models import Account, Session, VerifyCode

logger = logging.getLogger(__name__)

SESSION_TTL = timedelta(days=15)
CODE_TTL = timedelta(minutes=5)
CODE_DIGITS = 6
CODE_MAX_ATTEMPTS = 5  # 验证码最大尝试次数，超过即失效
SEND_CODE_INTERVAL = 60  # 同一昵称发码节流（秒）
LOGIN_MAX_FAILS = 5  # 登录连续失败上限
LOGIN_LOCK = timedelta(minutes=15)  # 触发上限后的锁定时长

# 占位哈希：账号不存在时也执行一次校验，恒定化响应时间（防时序枚举）
_DUMMY_HASH = hash_password("__powerfults_dummy__")


def _now() -> datetime:
    return datetime.now()


class AuthService:
    """账号 / 会话 / 验证码 的数据库操作封装。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ───────────────────── 账号 ─────────────────────

    async def get_by_nickname(self, ts_nickname: str) -> Account | None:
        result = await self.db.execute(
            select(Account).where(Account.ts_nickname == ts_nickname)
        )
        return result.scalar_one_or_none()

    async def get_by_uid(self, unique_identifier: str) -> Account | None:
        result = await self.db.execute(
            select(Account).where(Account.unique_identifier == unique_identifier)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, account_id: int) -> Account | None:
        return await self.db.get(Account, account_id)

    async def create_account(
        self, ts_nickname: str, unique_identifier: str, password: str
    ) -> Account:
        # 首个注册者自动 admin（系统初始化）；后续都是 member
        is_first = (await self.db.execute(select(func.count(Account.id)))).scalar_one() == 0
        account = Account(
            ts_nickname=ts_nickname,
            unique_identifier=unique_identifier,
            password_hash=hash_password(password),
            role="admin" if is_first else "member",
            status="active",
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        logger.info("创建账号: %s", ts_nickname)
        return account

    # ───────────────────── 会话 ─────────────────────

    async def create_session(self, account: Account) -> str:
        token = generate_token()
        self.db.add(Session(
            token=token,
            account_id=account.id,
            expires_at=_now() + SESSION_TTL,
        ))
        await self.db.commit()
        return token

    async def get_session_account(self, token: str) -> Account | None:
        """返回 token 对应的有效账号；过期/不存在返回 None。"""
        result = await self.db.execute(select(Session).where(Session.token == token))
        session = result.scalar_one_or_none()
        if session is None or session.expires_at < _now():
            return None
        return await self.get_by_id(session.account_id)

    async def delete_session(self, token: str) -> None:
        await self.db.execute(delete(Session).where(Session.token == token))
        await self.db.commit()

    # ───────────────────── 验证码（TS 身份认证）─────────────────────

    async def _latest_code(self, key: str) -> VerifyCode | None:
        result = await self.db.execute(
            select(VerifyCode)
            .where(VerifyCode.key == key)
            .order_by(VerifyCode.created_at.desc())
        )
        return result.scalars().first()

    async def issue_code(self, key: str) -> str | None:
        """生成验证码；节流期内返回 None。expected_uid 留待发码后绑定。"""
        now = _now()
        existing = await self._latest_code(key)
        if existing is not None and (now - existing.created_at).total_seconds() < SEND_CODE_INTERVAL:
            return None  # 节流
        code = "".join(secrets.choice("0123456789") for _ in range(CODE_DIGITS))
        await self.db.execute(delete(VerifyCode).where(VerifyCode.key == key))
        self.db.add(VerifyCode(
            key=key, code=code, expected_uid="", attempts=0, expires_at=now + CODE_TTL,
        ))
        await self.db.commit()
        return code

    async def bind_code_uid(self, key: str, expected_uid: str) -> None:
        """发码成功后，把目标 uid 绑定到验证码（注册时校验）。"""
        latest = await self._latest_code(key)
        if latest is not None:
            latest.expected_uid = expected_uid
            await self.db.commit()

    async def get_expected_uid(self, key: str) -> str | None:
        latest = await self._latest_code(key)
        if latest is not None and latest.expires_at > _now():
            return latest.expected_uid or None
        return None

    async def consume_code(self, key: str, code: str) -> bool:
        """校验并消费：匹配则删除该 key 全部码；失败累计 attempts，达上限也删除。"""
        latest = await self._latest_code(key)
        if latest is None or latest.expires_at <= _now():
            return False
        latest.attempts = (latest.attempts or 0) + 1
        matched = latest.code == code
        expired_by_attempts = latest.attempts >= CODE_MAX_ATTEMPTS
        await self.db.commit()
        if matched or expired_by_attempts:
            await self.db.execute(delete(VerifyCode).where(VerifyCode.key == key))
            await self.db.commit()
        return matched

    async def verify_only(self, key: str, code: str) -> bool:
        """只读校验（不消费、不计 attempts），供 /verify_code 端点预检。"""
        latest = await self._latest_code(key)
        return latest is not None and latest.expires_at > _now() and latest.code == code

    async def delete_code(self, key: str) -> None:
        await self.db.execute(delete(VerifyCode).where(VerifyCode.key == key))
        await self.db.commit()

    # ───────────────────── 登录（含锁定 / 恒定时间）─────────────────────

    async def verify_login(
        self, ts_nickname: str, password: str
    ) -> tuple[Account | None, str | None, str | None]:
        """返回 (account, token, error)。错误统一为“昵称或密码错误”以防枚举。"""
        account = await self.get_by_nickname(ts_nickname)
        now = _now()
        if account is not None and account.locked_until is not None and account.locked_until > now:
            return None, None, "账号已锁定，请稍后再试"

        # 恒定时间：账号不存在时也对 dummy 哈希做一次完整校验
        stored = account.password_hash if (account and account.password_hash) else _DUMMY_HASH
        ok = verify_password(password, stored)

        if account is None or not account.password_hash or not ok:
            # 仅对真实账号累计失败（dummy 账号不持久化）
            if account is not None and account.password_hash:
                account.failed_login_count = (account.failed_login_count or 0) + 1
                if account.failed_login_count >= LOGIN_MAX_FAILS:
                    account.locked_until = now + LOGIN_LOCK
                    account.failed_login_count = 0
                await self.db.commit()
            return None, None, "昵称或密码错误"

        # 成功：清零失败计数 + 建会话
        account.failed_login_count = 0
        account.locked_until = None
        account.last_login_at = now
        token = generate_token()
        self.db.add(Session(token=token, account_id=account.id, expires_at=now + SESSION_TTL))
        await self.db.commit()
        return account, token, None
