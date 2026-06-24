"""原生好友路由。

替换透传 S-QC-Bot 的 /api/friends。用 X-Session-Token 鉴权（get_current_account），
好友关系存 friends 表，在线状态从 ts3_monitor 内存查询。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..deps import get_current_account
from ..models import Account
from ..services.friend_service import FriendService

router = APIRouter(tags=["friends"])


class FriendRequest(BaseModel):
    friend_ts_nickname: str = Field(min_length=1, max_length=64)


@router.get("/friends")
async def list_friends(
    request: Request,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    """好友列表（含在线状态，从 TS3 监控内存查询）。"""
    monitor = request.app.state.ts3_monitor
    nicks = await FriendService(db).list_friend_nicknames(account)
    friends = []
    for nick in nicks:
        status, game = monitor.get_status(nick)
        friends.append({"ts_nickname": nick, "online_status": status, "game": game})
    return {"logged_in": True, "friends": friends}


@router.post("/friends/add")
async def add_friend(
    body: FriendRequest,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    """添加好友（按 TS 昵称）。"""
    if body.friend_ts_nickname == account.ts_nickname:
        return {"success": False, "error": "不能添加自己为好友"}
    svc = FriendService(db)
    friend = await svc.get_by_nickname(body.friend_ts_nickname)
    if friend is None:
        return {"success": False, "error": "该用户不存在"}
    try:
        await svc.add_relation(account.id, friend.id)
    except IntegrityError:
        await db.rollback()
        return {"success": False, "error": "已经是好友了"}
    return {"success": True}


@router.post("/friends/delete")
async def delete_friend(
    body: FriendRequest,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    """删除好友（按 TS 昵称）。"""
    svc = FriendService(db)
    friend = await svc.get_by_nickname(body.friend_ts_nickname)
    if friend is None:
        return {"success": False, "error": "该用户不存在"}
    await svc.remove_relation(account.id, friend.id)
    return {"success": True}
