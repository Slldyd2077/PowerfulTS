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


async def get_current_account(
    x_session_token: Annotated[str | None, Header(alias="X-Session-Token")] = None,
    db: AsyncSession = Depends(get_db),
) -> Account:
    """校验登录态并返回当前账号；未登录/会话无效则 401。"""
    if not x_session_token:
        raise HTTPException(status_code=401, detail="未登录")
    account = await AuthService(db).get_session_account(x_session_token)
    if account is None:
        raise HTTPException(status_code=401, detail="会话无效或已过期")
    return account


AccountDep = Annotated[Account, Depends(get_current_account)]


def get_tsmusic(request: Request) -> TSMusicClient:
    """单例 TSMusicClient（连接单一共享 TSMusicBot 容器）。"""
    return request.app.state.tsmusic


TsmusicDep = Annotated[TSMusicClient, Depends(get_tsmusic)]

