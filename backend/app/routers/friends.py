"""原生好友路由。

用 X-Session-Token 鉴权（get_current_account），
好友关系存 friends 表，在线状态从 ts3_monitor 内存查询。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from ..core.config import get_settings
from ..core.database import get_db
from ..deps import get_current_account
from ..models import Account, Friend, FriendRequest
from ..services import app_setting, ts3_auth
from ..services.friend_service import FriendService

settings = get_settings()

# 默认消息模板
DEFAULT_TS_MESSAGE = "【PowerfulTS】用户「{nickname}」添加你为好友，你们现在是好友关系了！"
DEFAULT_QQ_MESSAGE = "【PowerfulTS】用户「{nickname}」添加你为好友，你们现在是好友关系了！"
DEFAULT_ONLINE_NOTICE = "✅ 你添加的好友「{nickname}」当前在线{game}"


async def get_friend_add_messages(db: AsyncSession) -> tuple[str, str, str]:
    """获取好友添加消息模板，返回 (ts_message, qq_message, online_notice)。"""
    ts_msg = await app_setting.get_setting(db, "sys.friend_add_ts_message", DEFAULT_TS_MESSAGE)
    qq_msg = await app_setting.get_setting(db, "sys.friend_add_qq_message", DEFAULT_QQ_MESSAGE)
    online_notice = await app_setting.get_setting(db, "sys.friend_online_notice_message", DEFAULT_ONLINE_NOTICE)
    return ts_msg, qq_msg, online_notice

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
    request: Request,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    """添加好友（按 TS 昵称）。
    - 如果对方已经是好友：返回错误
    - 如果对方已经发送了好友申请：自动接受并建立双向好友关系
    - 如果是单向好友（你加了他，他没加你）：自动建立双向好友关系
    - 如果没有任何关系：创建好友申请，对方收到后需要接受
    """
    if body.friend_ts_nickname == account.ts_nickname:
        return {"success": False, "error": "不能添加自己为好友"}
    svc = FriendService(db)
    friend = await svc.get_by_nickname(body.friend_ts_nickname)
    if friend is None:
        return {"success": False, "error": "该用户不存在"}

    # 检查是否已经是好友
    if await svc.check_is_friend(account.id, friend.id):
        return {"success": False, "error": "已经是好友了"}

    # 检查是否是单向好友（对方已经添加了我）
    reverse_friend = await svc.check_is_friend(friend.id, account.id)

    # 检查是否有待处理的好友申请
    from sqlalchemy import select
    existing_request = await db.execute(
        select(FriendRequest).where(
            FriendRequest.requester_id == account.id,
            FriendRequest.recipient_id == friend.id,
            FriendRequest.status == "pending"
        )
    )
    if existing_request.scalar_one_or_none():
        return {"success": False, "error": "已经发送过好友申请，请等待对方接受"}

    # 检查对方是否已经发送了好友申请
    reverse_request = await db.execute(
        select(FriendRequest).where(
            FriendRequest.requester_id == friend.id,
            FriendRequest.recipient_id == account.id,
            FriendRequest.status == "pending"
        )
    )
    reverse_req = reverse_request.scalar_one_or_none()

    monitor = request.app.state.ts3_monitor
    online_status, game = monitor.get_status(body.friend_ts_nickname)
    is_online = online_status != "离线"

    # 获取消息模板
    ts_template, qq_template, online_template = await get_friend_add_messages(db)

    # 如果对方已经添加了我，直接建立双向好友关系
    if reverse_friend:
        await svc.add_relation(account.id, friend.id)
        # 发送双向好友建立通知
        if is_online:
            ts_message = f"【PowerfulTS】用户「{account.ts_nickname}」接受了你的好友请求，你们现在是好友了！"
            await asyncio.to_thread(ts3_auth.send_private_message, settings, body.friend_ts_nickname, ts_message)

            if friend.qq_number:
                napcat = request.app.state.napcat
                qq_message = f"【PowerfulTS】用户「{account.ts_nickname}」接受了你的好友请求，你们现在是好友了！"
                await napcat.send_private_msg(friend.qq_number, qq_message)

        # 发送在线提醒给当前用户
        if is_online and account.qq_number:
            napcat = request.app.state.napcat
            game_text = f"（{game}）" if game else ""
            message = online_template.format(nickname=body.friend_ts_nickname, game=game_text)
            await napcat.send_private_msg(account.qq_number, message)

        return {"success": True, "friend_online": is_online, "online_status": online_status, "game": game, "message": "已自动建立双向好友关系"}

    # 如果对方发送了好友申请，自动接受
    if reverse_req:
        await svc.accept_friend_request(reverse_req.id)
        # 发送接受通知
        if is_online:
            ts_message = f"【PowerfulTS】用户「{account.ts_nickname}」接受了你的好友申请，你们现在是好友了！"
            await asyncio.to_thread(ts3_auth.send_private_message, settings, body.friend_ts_nickname, ts_message)

            if friend.qq_number:
                napcat = request.app.state.napcat
                qq_message = f"【PowerfulTS】用户「{account.ts_nickname}」接受了你的好友申请，你们现在是好友了！"
                await napcat.send_private_msg(friend.qq_number, qq_message)

        # 发送在线提醒给当前用户
        if is_online and account.qq_number:
            napcat = request.app.state.napcat
            game_text = f"（{game}）" if game else ""
            message = online_template.format(nickname=body.friend_ts_nickname, game=game_text)
            await napcat.send_private_msg(account.qq_number, message)

        return {"success": True, "friend_online": is_online, "online_status": online_status, "game": game, "message": "已自动接受对方的好友申请"}

    # 创建好友申请
    friend_request = await svc.create_friend_request(account.id, friend.id)
    if not friend_request:
        return {"success": False, "error": "已经发送过好友申请，请等待对方接受"}

    # 向对方发送好友申请通知
    if is_online:
        # 发送 TS 私聊消息给对方
        ts_message = f"【PowerfulTS】用户「{account.ts_nickname}」请求添加你为好友"
        await asyncio.to_thread(ts3_auth.send_private_message, settings, body.friend_ts_nickname, ts_message)

        # 如果对方绑定了 QQ，也发送 QQ 通知
        if friend.qq_number:
            napcat = request.app.state.napcat
            qq_message = f"【PowerfulTS】用户「{account.ts_nickname}」请求添加你为好友，请在管理后台接受或拒绝。"
            await napcat.send_private_msg(friend.qq_number, qq_message)

    return {"success": True, "is_request": True, "message": "好友申请已发送"}


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


@router.get("/friends/requests")
async def list_friend_requests(
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    """获取待处理的好友申请列表。"""
    svc = FriendService(db)
    requests = await svc.get_pending_requests(account.id)

    result = []
    for req in requests:
        # 获取申请人的信息
        requester = await db.get(Account, req.requester_id)
        if requester:
            result.append({
                "id": req.id,
                "requester_id": req.requester_id,
                "requester_nickname": requester.ts_nickname,
                "created_at": req.created_at.isoformat(),
            })

    return {"requests": result}


class FriendRequestAction(BaseModel):
    request_id: int = Field(..., description="好友申请ID")
    action: str = Field(..., description="操作类型：accept 或 reject")


@router.post("/friends/requests/action")
async def handle_friend_request(
    body: FriendRequestAction,
    request: Request,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    """接受或拒绝好友申请。"""
    if body.action not in ["accept", "reject"]:
        return {"success": False, "error": "无效的操作类型"}

    svc = FriendService(db)

    # 验证申请是属于当前用户的
    friend_request = await db.get(FriendRequest, body.request_id)
    if not friend_request or friend_request.recipient_id != account.id:
        return {"success": False, "error": "好友申请不存在"}

    if body.action == "accept":
        success = await svc.accept_friend_request(body.request_id)
        if not success:
            return {"success": False, "error": "接受失败"}

        # 获取申请人信息
        requester = await db.get(Account, friend_request.requester_id)
        if requester:
            # 检查申请人是否在线
            monitor = request.app.state.ts3_monitor
            online_status, game = monitor.get_status(requester.ts_nickname)
            is_online = online_status != "离线"

            # 发送接受通知给申请人
            if is_online:
                ts_message = f"【PowerfulTS】用户「{account.ts_nickname}」接受了你的好友申请，你们现在是好友了！"
                await asyncio.to_thread(ts3_auth.send_private_message, settings, requester.ts_nickname, ts_message)

                if requester.qq_number:
                    napcat = request.app.state.napcat
                    qq_message = f"【PowerfulTS】用户「{account.ts_nickname}」接受了你的好友申请，你们现在是好友了！"
                    await napcat.send_private_msg(requester.qq_number, qq_message)

            # 发送在线提醒给当前用户
            if is_online and account.qq_number:
                napcat = request.app.state.napcat
                game_text = f"（{game}）" if game else ""
                online_template = (await get_friend_add_messages(db))[2]
                message = online_template.format(nickname=requester.ts_nickname, game=game_text)
                await napcat.send_private_msg(account.qq_number, message)

        return {"success": True, "message": "已接受好友申请"}

    else:  # reject
        success = await svc.reject_friend_request(body.request_id)
        if not success:
            return {"success": False, "error": "拒绝失败"}

        return {"success": True, "message": "已拒绝好友申请"}


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
