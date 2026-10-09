"""Admin-uploaded site background: validation, colour extraction and API access control."""

from __future__ import annotations

import asyncio
import io
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image, ImageDraw
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.deps import get_authenticated_account
from app.routers import theme
from app.services.background import (
    BackgroundStorage,
    BackgroundValidationError,
    extract_theme_color,
    process_background,
)


def _png(size=(1600, 900), bg=(18, 18, 26), blob=(220, 60, 120), mode="PNG") -> bytes:
    image = Image.new("RGB", size, bg)
    ImageDraw.Draw(image).ellipse(
        (size[0] // 5, size[1] // 5, size[0] // 2, size[1] * 4 // 5), fill=blob
    )
    buf = io.BytesIO()
    image.save(buf, mode)
    return buf.getvalue()


def _hue(hex_color: str) -> float:
    import colorsys

    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360


def test_color_is_taken_from_the_vivid_blob_not_the_dark_backdrop():
    color = extract_theme_color(Image.open(io.BytesIO(_png())))
    # 品红 ≈ 335°，远离深色底的蓝灰
    assert abs(_hue(color) - 335) < 20


def test_process_resizes_and_reencodes_to_webp():
    out = process_background(_png(size=(4000, 2250)), "desktop")
    assert (out.width, out.height) == (2560, 1440)
    assert out.data[:4] == b"RIFF" and out.data[8:12] == b"WEBP"


def test_mobile_limit_is_portrait():
    out = process_background(_png(size=(2400, 5200)), "mobile")
    assert out.height == 2532 and out.width < out.height


@pytest.mark.parametrize(
    "payload",
    [b"definitely not an image", b"", b"GIF89a" + b"\x00" * 10, _png(size=(100, 100))],
)
def test_rejects_non_images_and_tiny_images(payload):
    with pytest.raises(BackgroundValidationError):
        process_background(payload, "desktop")


def test_storage_only_serves_fixed_names(tmp_path):
    storage = BackgroundStorage(tmp_path)
    storage.write_atomic("desktop", b"x")
    assert storage.path_for("desktop").read_bytes() == b"x"
    with pytest.raises(ValueError):
        storage.path_for("../evil")  # type: ignore[arg-type]
    storage.delete("desktop")
    assert not storage.path_for("desktop").exists()


@asynccontextmanager
async def _client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    app = FastAPI()
    app.include_router(theme.router, prefix="/api")
    app.state.background_storage = BackgroundStorage(tmp_path / "bg")
    role = {"value": "admin"}

    async def _db():
        async with sessions() as session:
            yield session

    async def _account():
        return SimpleNamespace(id=1, role=role["value"])

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_authenticated_account] = _account
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as http:
            yield http, role
    finally:
        await engine.dispose()


def test_admin_upload_then_public_read_and_delete(tmp_path):
    async def scenario():
        async with _client(tmp_path) as (client, _role):
            empty = (await client.get("/api/theme")).json()
            assert empty["desktop"] is None and empty["mobile"] is None

            res = await client.put("/api/theme/background/desktop", content=_png())
            assert res.status_code == 200
            payload = res.json()
            assert payload["desktop"]["color"].startswith("#")
            assert payload["desktop"]["url"].startswith("/api/theme/background/desktop?v=")

            image = await client.get("/api/theme/background/desktop")
            assert image.status_code == 200
            assert image.headers["content-type"] == "image/webp"
            assert "immutable" in image.headers["cache-control"]

            gone = await client.delete("/api/theme/background/desktop")
            assert gone.json()["desktop"] is None
            assert (await client.get("/api/theme/background/desktop")).status_code == 404

    asyncio.run(scenario())


def test_non_admin_cannot_modify(tmp_path):
    async def scenario():
        async with _client(tmp_path) as (client, role):
            role["value"] = "member"
            assert (await client.put("/api/theme/background/desktop", content=_png())).status_code == 403
            assert (await client.delete("/api/theme/background/mobile")).status_code == 403
            assert (await client.put("/api/theme/appearance", json={"dim": 10, "blur": 2})).status_code == 403

    asyncio.run(scenario())


def test_invalid_upload_and_kind_are_rejected(tmp_path):
    async def scenario():
        async with _client(tmp_path) as (client, _role):
            assert (await client.put("/api/theme/background/desktop", content=b"nope")).status_code == 400
            assert (await client.put("/api/theme/background/tablet", content=_png())).status_code == 422

    asyncio.run(scenario())


def test_appearance_bounds(tmp_path):
    async def scenario():
        async with _client(tmp_path) as (client, _role):
            ok = await client.put("/api/theme/appearance", json={"dim": 60, "blur": 8})
            assert ok.json()["dim"] == 60 and ok.json()["blur"] == 8
            assert (await client.put("/api/theme/appearance", json={"dim": 99, "blur": 0})).status_code == 422

    asyncio.run(scenario())
