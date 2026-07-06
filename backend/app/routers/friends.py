"""原生好友路由。

用 X-Session-Token 鉴权（get_current_account），
好友关系存 friends 表，在线状态从 ts3_monitor 内存查询。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from ..core.database import get_db
from ..deps import get_current_account
from ..models import Account, Friend
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
    # 我加的好友（id + 昵称）
    my_rows = (
        await db.execute(
            select(Account.id, Account.ts_nickname)
            .join(Friend, Friend.friend_account_id == Account.id)
            .where(Friend.account_id == account.id)
        )
    ).all()
    # 反向：把我加为好友的 account_id 集合（mutual 判断）
    reverse_ids = set(
        (await db.execute(
            select(Friend.account_id).where(Friend.friend_account_id == account.id)
        )).scalars().all()
    )
    friends = []
    for fid, nick in my_rows:
        status, game = monitor.get_status(nick)
        friends.append({
            "ts_nickname": nick,
            "online_status": status,
            "game": game,
            "mutual": fid in reverse_ids,
        })
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


class FriendSettingsUpdate(BaseModel):
    qq_number: str | None = Field(default=None, max_length=16)
    notify_friends_online: bool | None = None


@router.get("/friends/settings")
async def get_friend_settings(
    account: Account = Depends(get_current_account),
):
    """当前用户的好友上线提醒设置（QQ 绑定 + 开关）。"""
    return {
        "qq_number": account.qq_number or "",
        "notify_friends_online": bool(account.notify_friends_online),
    }


@router.post("/friends/settings")
async def update_friend_settings(
    body: FriendSettingsUpdate,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    """更新好友上线提醒设置。QQ 号非空须为纯数字；空串→解绑(None)。"""
    if body.qq_number is not None:
        qq = body.qq_number.strip()
        if qq == "":
            account.qq_number = None
        elif qq.isdigit():
            account.qq_number = qq
        else:
            return {"success": False, "error": "QQ 号必须为纯数字"}
        await db.commit()
    if body.notify_friends_online is not None:
        account.notify_friends_online = bool(body.notify_friends_online)
        await db.commit()
    return {"success": True}
