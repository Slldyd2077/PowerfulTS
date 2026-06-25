"""原生认证路由（TS 身份认证）。

身份以 TS unique_identifier 为锚点：
注册需 TS 在线（ServerQuery 私聊下发验证码 + 绑定 expected_uid，注册时校验一致防冒名）。
登录用 ts_nickname + 密码（失败计数锁定 + 统一错误消息防枚举）。
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.database import get_db
from ..services import ts3_auth
from ..services.auth_service import AuthService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


# ───────────────────── 请求模型 ─────────────────────

class NicknameRequest(BaseModel):
    ts_nickname: str = Field(min_length=1, max_length=64)


class VerifyCodeRequest(BaseModel):
    ts_nickname: str
    code: str


class RegisterRequest(BaseModel):
    ts_nickname: str
    password: str = Field(min_length=8, max_length=128)
    code: str
    ip: str = "unknown"


class LoginRequest(BaseModel):
    ts_nickname: str
    password: str
    ip: str = "unknown"


class TokenRequest(BaseModel):
    token: str


def _monitor(request: Request):
    return request.app.state.ts3_monitor


# ───────────────────── 端点 ─────────────────────

@router.post("/send_code")
async def send_code(body: NicknameRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """向在线 TS 客户端私聊下发验证码（含 60s 节流）。"""
    monitor = _monitor(request)
    if not ts3_auth.is_online(monitor, body.ts_nickname):
        return {"success": False, "error": "该昵称当前不在线，请先用此昵称登录 TS 服务器"}
    svc = AuthService(db)
    code = await svc.issue_code(body.ts_nickname)
    if code is None:
        return {"success": False, "error": "请求过于频繁，请稍后再试"}
    # send_verify_code 是同步 socket，放线程池避免阻塞事件循环
    try:
        uid = await asyncio.to_thread(ts3_auth.send_verify_code, settings, body.ts_nickname, code)
    except Exception:
        logger.warning("send_verify_code 异常", exc_info=True)
        uid = None
    if not uid:
        await svc.delete_code(body.ts_nickname)
        return {"success": False, "error": "验证码发送失败（客户端可能已下线）"}
    # 绑定发码目标 uid，注册时校验（防昵称换人冒名）
    await svc.bind_code_uid(body.ts_nickname, uid)
    return {"success": True, "message": "验证码已通过 TS 私聊发送"}


@router.post("/verify_code")
async def verify_code(body: VerifyCodeRequest, db: AsyncSession = Depends(get_db)):
    """只读校验验证码（不消费、不计尝试）。"""
    ok = await AuthService(db).verify_only(body.ts_nickname, body.code)
    return {"success": ok}


@router.post("/register")
async def register(body: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """注册：验证码校验 + uid 一致性校验 + 建账号。"""
    svc = AuthService(db)
    # 先取 expected_uid（码还在），再消费验证码（会删除）
    expected_uid = await svc.get_expected_uid(body.ts_nickname)
    if not expected_uid:
        return {"success": False, "error": "请先获取验证码"}
    if not await svc.consume_code(body.ts_nickname, body.code):
        return {"success": False, "error": "验证码错误、已失效或尝试次数过多"}
    current_uid = ts3_auth.get_online_uid(_monitor(request), body.ts_nickname)
    if not current_uid or current_uid != expected_uid:
        return {"success": False, "error": "身份校验失败，请用同一 TS 客户端保持在线后重试"}
    try:
        await svc.create_account(body.ts_nickname, current_uid, body.password)
    except IntegrityError:
        # 并发注册同一昵称/uid 的最后防线（DB 唯一约束）
        await db.rollback()
        return {"success": False, "error": "该昵称或 TS 客户端已被注册"}
    return {"success": True, "message": "注册成功"}


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """登录：ts_nickname + 密码（失败锁定 + 统一错误消息防枚举）。"""
    account, token, error = await AuthService(db).verify_login(body.ts_nickname, body.password)
    if error:
        return {"success": False, "error": error}
    return {
        "success": True,
        "token": token,
        "ts_nickname": account.ts_nickname,
        "is_admin": account.role == "admin",
    }


@router.post("/get_session")
async def get_session(body: TokenRequest, db: AsyncSession = Depends(get_db)):
    """查询当前会话。"""
    account = await AuthService(db).get_session_account(body.token)
    if account is None:
        return {"success": False, "error": "会话无效或已过期"}
    return {
        "success": True,
        "is_admin": account.role == "admin",
        "session_data": {
            "ts_nickname": account.ts_nickname,
            "is_admin": account.role == "admin",
            "role": account.role,
        },
    }


@router.post("/logout")
async def logout(body: TokenRequest, db: AsyncSession = Depends(get_db)):
    await AuthService(db).delete_session(body.token)
    return {"success": True}


@router.get("/get_ip")
async def get_ip(request: Request):
    return {"ip": request.client.host if request.client else "unknown"}


@router.get("/check_binding")
async def check_binding(ts_nickname: str, db: AsyncSession = Depends(get_db)):
    account = await AuthService(db).get_by_nickname(ts_nickname)
    return {"bound": account is not None}


@router.post("/check_online")
async def check_online(body: NicknameRequest, request: Request):
    return {"online": ts3_auth.is_online(_monitor(request), body.ts_nickname)}
