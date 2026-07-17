"""管理后台路由（RBAC：仅 admin）。

系统设置（NapCat / TSMusicBot / TS3 / CORS / Netease）存 app_setting（DB，sys.* key），
.env 作启动默认；admin 在网页改 → 写 DB → 热重载 client（重建 app.state 单例）。
TS3 / CORS 改需重启 backend（标记 need_restart）。
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.database import get_db
from ..deps import AdminDep
from ..services import app_setting
from ..models import Account

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

SYS_PREFIX = "sys."
MASK = "****"


@router.get("/member-notifications")
async def list_member_notifications(
    request: Request, account: AdminDep, db: AsyncSession = Depends(get_db)
):
    """列出成员的服务器动态通知订阅；QQ 仅返回是否已绑定。"""
    rows = (await db.execute(select(Account).order_by(Account.ts_nickname))).scalars().all()
    napcat_enabled = bool((await request.app.state.napcat.check_status()).get("connected"))
    return {"napcat_enabled": napcat_enabled, "members": [{
        "id": row.id,
        "ts_nickname": row.ts_nickname,
        "qq_bound": bool(row.qq_number),
        "notify_server_online": bool(row.notify_server_online),
        "notify_server_first_join": bool(row.notify_server_first_join),
        "notification_channel": row.notification_channel if row.notification_channel in {"ts", "qq"} else "ts",
    } for row in rows]}


class MemberNotificationUpdate(BaseModel):
    notify_server_online: bool
    notify_server_first_join: bool
    notification_channel: Literal["ts", "qq"] = "ts"


@router.put("/member-notifications/{account_id}")
async def update_member_notifications(
    account_id: int, body: MemberNotificationUpdate, request: Request, account: AdminDep,
    db: AsyncSession = Depends(get_db),
):
    """管理员更新一位成员的服务器动态 QQ 通知开关。"""
    member = await db.get(Account, account_id)
    if member is None:
        raise HTTPException(status_code=404, detail="成员不存在")
    if body.notification_channel == "qq":
        napcat_status = await request.app.state.napcat.check_status()
        if not napcat_status.get("connected"):
            raise HTTPException(status_code=400, detail="NapCat 未启用，无法选择 QQ 通知")
        if not member.qq_number:
            raise HTTPException(status_code=400, detail="该成员尚未绑定 QQ")
    member.notify_server_online = body.notify_server_online
    member.notify_server_first_join = body.notify_server_first_join
    member.notification_channel = body.notification_channel
    await db.commit()
    return {"success": True}

# 可配置项：env 字段名 / label / 是否敏感（GET 脱敏）/ reload=重建哪类 client / restart=需重启 backend
SPEC: list[dict] = [
    {"key": "napcat_url", "label": "NapCat HTTP 地址", "sensitive": False, "reload": "napcat"},
    {"key": "napcat_token", "label": "NapCat Token", "sensitive": True, "reload": "napcat"},
    {"key": "tsmusic_url", "label": "TSMusicBot 地址", "sensitive": False, "reload": "tsmusic"},
    {"key": "tsmusic_user", "label": "TSMusicBot 用户名", "sensitive": False, "reload": "tsmusic"},
    {"key": "tsmusic_password", "label": "TSMusicBot 密码", "sensitive": True, "reload": "tsmusic"},
    {"key": "tsmusic_bot_id", "label": "TSMusicBot 默认 bot id", "sensitive": False, "reload": "tsmusic"},
    {"key": "netease_api_url", "label": "网易云 API 地址", "sensitive": False, "reload": "netease"},
    {"key": "ts3_host", "label": "TS3 ServerQuery 主机", "sensitive": False, "restart": True},
    {"key": "ts3_query_port", "label": "TS3 ServerQuery 端口", "sensitive": False, "restart": True},
    {"key": "ts3_query_user", "label": "TS3 ServerQuery 用户", "sensitive": False, "restart": True},
    {"key": "ts3_query_password", "label": "TS3 ServerQuery 密码", "sensitive": True, "restart": True},
    {"key": "ts3_sid", "label": "TS3 虚拟服务器 ID", "sensitive": False, "restart": True},
    {"key": "cors_origins", "label": "CORS 允许来源（逗号分隔）", "sensitive": False, "restart": True},
    # 好友添加通知消息模板
    {"key": "friend_add_ts_message", "label": "好友添加 TS 通知消息", "sensitive": False},
    {"key": "friend_add_qq_message", "label": "好友添加 QQ 通知消息", "sensitive": False},
    {"key": "friend_online_notice_message", "label": "好友在线提醒消息", "sensitive": False},
    # 好友上线通知消息模板
    {"key": "friend_online_notice", "label": "好友上线通知消息", "sensitive": False},
    {"key": "server_online_notice", "label": "成员上线通知消息", "sensitive": False},
    {"key": "server_first_join_notice", "label": "新成员首次加入通知消息", "sensitive": False},
]

SPEC_BY_KEY = {s["key"]: s for s in SPEC}


def _env_default(key: str) -> str:
    """从 .env settings 取默认值（启动时读的）。"""
    s = get_settings()
    val = getattr(s, key, "")
    if isinstance(val, list):  # cors_origins 是 list
        return ",".join(val)
    return str(val) if val is not None else ""


async def _read_all(db: AsyncSession) -> dict:
    """读全部设置：env 默认 + DB sys.* 覆盖；敏感项脱敏。"""
    out = {}
    for spec in SPEC:
        key = spec["key"]
        env_val = _env_default(key)
        db_val = await app_setting.get_setting(db, SYS_PREFIX + key, "")
        has_db = db_val != ""
        final = db_val if has_db else env_val
        is_set = has_db or env_val != ""
        out[key] = {
            "label": spec["label"],
            "sensitive": spec["sensitive"],
            "restart": spec.get("restart", False),
            "reload": spec.get("reload"),
            "value": MASK if (spec["sensitive"] and final) else final,
            "is_set": is_set,
        }
    return out


@router.get("/settings")
async def get_admin_settings(account: AdminDep, db: AsyncSession = Depends(get_db)):
    """读取所有系统设置（admin；敏感项脱敏）。"""
    return {"settings": await _read_all(db)}


class SettingsUpdate(BaseModel):
    items: dict[str, str] = Field(default_factory=dict, description="要更新的 key→value")


@router.put("/settings")
async def update_admin_settings(
    body: SettingsUpdate, request: Request, account: AdminDep, db: AsyncSession = Depends(get_db)
):
    """批量更新设置（admin）：写 DB sys.*；敏感项值为 **** 时跳过（不改）；
    触发热重载（napcat/tsmusic/netease 重建 app.state 单例）；TS3/CORS 标记 need_restart。"""
    changed_reload: set[str] = set()
    need_restart = False
    for key, val in body.items.items():
        spec = SPEC_BY_KEY.get(key)
        if spec is None:
            continue  # 非法 key 跳过
        if spec["sensitive"] and val == MASK:
            continue  # 脱敏回传，不更新
        await app_setting.set_setting(db, SYS_PREFIX + key, val)
        if spec.get("restart"):
            need_restart = True
        elif spec.get("reload"):
            changed_reload.add(spec["reload"])
    reloaded = list(changed_reload)
    if reloaded:
        await _reload_clients(request, db, reloaded)
    return {"success": True, "need_restart": need_restart, "reloaded": reloaded}


async def _resolve(db: AsyncSession, key: str) -> str:
    """取某 key 的最终值（DB 覆盖 env）。"""
    spec = SPEC_BY_KEY[key]
    db_val = await app_setting.get_setting(db, SYS_PREFIX + key, "")
    return db_val if db_val != "" else _env_default(key)


async def _reload_clients(request: Request, db: AsyncSession, kinds: list[str]) -> None:
    """重建 app.state 单例（close 旧 + new 新）。"""
    st = request.app.state
    if "napcat" in kinds:
        url = await _resolve(db, "napcat_url")
        token = await _resolve(db, "napcat_token")
        from ..services.napcat_client import NapCatClient
        await st.napcat.close()
        st.napcat = NapCatClient(url, token)
        # online_notifier 持有旧 napcat 引用，同步更新
        st.online_notifier._napcat = st.napcat
        logger.info("热重载 NapCatClient: %s", url)
    if "tsmusic" in kinds:
        from ..services.tsmusic_client import TSMusicClient
        await st.tsmusic.close()
        st.tsmusic = TSMusicClient(
            await _resolve(db, "tsmusic_url"),
            await _resolve(db, "tsmusic_user"),
            await _resolve(db, "tsmusic_password"),
            bot_id=await _resolve(db, "tsmusic_bot_id"),
            state_store=st.tsmusic.state_store,
        )
        logger.info("热重载 TSMusicClient")
    if "netease" in kinds:
        from ..services.netease import NeteaseClient
        await st.netease.close()
        st.netease = NeteaseClient(await _resolve(db, "netease_api_url"))
        logger.info("热重载 NeteaseClient")


@router.get("/napcat/status")
async def napcat_status(request: Request, account: AdminDep):
    """探测 NapCat 连接 + 登录态（管理后台状态检测用）。"""
    return await request.app.state.napcat.check_status()


@router.get("/friend-message-templates")
async def get_friend_message_templates(account: AdminDep, db: AsyncSession = Depends(get_db)):
    """获取好友添加通知消息模板（admin）。"""
    from ..routers.friends import DEFAULT_ONLINE_NOTICE, DEFAULT_QQ_MESSAGE, DEFAULT_TS_MESSAGE

    ts_msg = await app_setting.get_setting(db, "sys.friend_add_ts_message", DEFAULT_TS_MESSAGE)
    qq_msg = await app_setting.get_setting(db, "sys.friend_add_qq_message", DEFAULT_QQ_MESSAGE)
    online_notice = await app_setting.get_setting(db, "sys.friend_online_notice_message", DEFAULT_ONLINE_NOTICE)

    return {
        "friend_add_ts_message": ts_msg,
        "friend_add_qq_message": qq_msg,
        "friend_online_notice_message": online_notice,
        "variables": ["{nickname}", "{game}"],  # 可用的模板变量
    }


@router.get("/notification-message-templates")
async def get_notification_message_templates(account: AdminDep, db: AsyncSession = Depends(get_db)):
    """获取所有通知消息模板（admin）。"""
    from ..services.online_notifier import (
        DEFAULT_FRIEND_ONLINE_NOTICE,
        DEFAULT_SERVER_FIRST_JOIN_NOTICE,
        DEFAULT_SERVER_ONLINE_NOTICE,
    )

    friend_online = await app_setting.get_setting(
        db, "sys.friend_online_notice", DEFAULT_FRIEND_ONLINE_NOTICE
    )
    server_online = await app_setting.get_setting(
        db, "sys.server_online_notice", DEFAULT_SERVER_ONLINE_NOTICE
    )
    server_first_join = await app_setting.get_setting(
        db, "sys.server_first_join_notice", DEFAULT_SERVER_FIRST_JOIN_NOTICE
    )

    return {
        "friend_online_notice": friend_online,
        "server_online_notice": server_online,
        "server_first_join_notice": server_first_join,
        "variables": ["{nick}"],  # 可用的模板变量
    }
