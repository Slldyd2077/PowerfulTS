"""FastAPI 共享依赖。

get_current_account：基于 X-Session-Token 校验登录态，返回当前 Account（无效则 401）。
供好友、频道租赁等原生路由复用，统一鉴权入口。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from .core.database import get_db
from .models import Account
from .services.auth_service import AuthService
from .services.tsmusic_client import TSMusicClient


async def get_authenticated_account(
    x_session_token: Annotated[str | None, Header(alias="X-Session-Token")] = None,
    db: AsyncSession = Depends(get_db),
) -> Account:
    """Resolve any valid session, including a voice-scoped guest session."""
    if not x_session_token:
        raise HTTPException(status_code=401, detail="未登录")
    account = await AuthService(db).get_session_account(x_session_token)
    if account is None:
        raise HTTPException(status_code=401, detail="会话无效或已过期")
    return account


AuthenticatedAccountDep = Annotated[Account, Depends(get_authenticated_account)]


async def get_current_account(account: AuthenticatedAccountDep) -> Account:
    """Require a registered member/admin session for ordinary application APIs."""
    if account.role == "guest":
        raise HTTPException(status_code=403, detail="游客仅可使用服务器监控和网页通话")
    return account


AccountDep = Annotated[Account, Depends(get_current_account)]


async def get_voice_account(account: AuthenticatedAccountDep) -> Account:
    """Allow registered accounts and temporary guests to use browser voice."""
    return account


VoiceAccountDep = Annotated[Account, Depends(get_voice_account)]


async def require_admin(account: AccountDep) -> Account:
    """要求当前账号是 admin，否则 403。供管理类端点（系统设置等）用。"""
    if account.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return account


AdminDep = Annotated[Account, Depends(require_admin)]


def get_tsmusic(request: Request) -> TSMusicClient:
    """单例 TSMusicClient（连接单一共享 TSMusicBot 容器）。"""
    return request.app.state.tsmusic


TsmusicDep = Annotated[TSMusicClient, Depends(get_tsmusic)]

