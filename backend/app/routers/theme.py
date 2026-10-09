"""站点外观：管理员自定义背景图（PC / 手机分别设置）+ 自动提取的主题色。

GET    /api/theme                      公开：背景地址、主题色、遮罩参数（登录前也要用）
GET    /api/theme/background/{kind}    公开：背景图文件（URL 带 ?v= 版本号，可长缓存）
PUT    /api/theme/background/{kind}    管理员：原始请求体上传图片
DELETE /api/theme/background/{kind}    管理员：移除背景
PUT    /api/theme/appearance           管理员：遮罩暗度 / 模糊度
"""
from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..deps import AdminDep
from ..services import app_setting
from ..services.background import (
    BackgroundKind,
    BackgroundValidationError,
    process_background,
    read_limited_image_upload,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/theme", tags=["theme"])

DEFAULT_DIM = 45
DEFAULT_BLUR = 0


def _key(kind: str, field: str) -> str:
    return f"ui.bg.{kind}.{field}"


async def _kind_payload(db: AsyncSession, kind: str) -> dict | None:
    version = await app_setting.get_setting(db, _key(kind, "v"))
    if not version:
        return None
    return {
        "url": f"/api/theme/background/{kind}?v={version}",
        "color": await app_setting.get_setting(db, _key(kind, "color")),
    }


async def _int_setting(db: AsyncSession, key: str, default: int) -> int:
    raw = await app_setting.get_setting(db, key, str(default))
    return int(raw) if raw.isdigit() else default


async def _theme_payload(db: AsyncSession) -> dict:
    return {
        "desktop": await _kind_payload(db, "desktop"),
        "mobile": await _kind_payload(db, "mobile"),
        "dim": await _int_setting(db, "ui.bg.dim", DEFAULT_DIM),
        "blur": await _int_setting(db, "ui.bg.blur", DEFAULT_BLUR),
    }


@router.get("")
async def get_theme(db: AsyncSession = Depends(get_db)):
    return await _theme_payload(db)


@router.get("/background/{kind}")
async def get_background(kind: BackgroundKind, request: Request):
    path = request.app.state.background_storage.path_for(kind)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="未设置背景图")
    return FileResponse(
        path,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.put("/background/{kind}")
async def put_background(
    kind: BackgroundKind,
    request: Request,
    _admin: AdminDep,
    db: AsyncSession = Depends(get_db),
):
    content = await read_limited_image_upload(request)
    try:
        processed = await asyncio.to_thread(process_background, content, kind)
    except BackgroundValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await asyncio.to_thread(
        request.app.state.background_storage.write_atomic, kind, processed.data
    )
    await app_setting.set_setting(db, _key(kind, "color"), processed.color)
    await app_setting.set_setting(db, _key(kind, "v"), str(int(time.time() * 1000)))
    return await _theme_payload(db)


@router.delete("/background/{kind}")
async def delete_background(
    kind: BackgroundKind,
    request: Request,
    _admin: AdminDep,
    db: AsyncSession = Depends(get_db),
):
    await app_setting.set_setting(db, _key(kind, "v"), "")
    await app_setting.set_setting(db, _key(kind, "color"), "")
    try:
        await asyncio.to_thread(request.app.state.background_storage.delete, kind)
    except OSError:
        logger.warning("删除背景图文件失败", exc_info=True)
    return await _theme_payload(db)


class AppearanceUpdate(BaseModel):
    dim: int = Field(ge=0, le=85)
    blur: int = Field(ge=0, le=24)


@router.put("/appearance")
async def put_appearance(
    body: AppearanceUpdate, _admin: AdminDep, db: AsyncSession = Depends(get_db)
):
    await app_setting.set_setting(db, "ui.bg.dim", str(body.dim))
    await app_setting.set_setting(db, "ui.bg.blur", str(body.blur))
    return await _theme_payload(db)
