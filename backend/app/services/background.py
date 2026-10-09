"""自定义背景图：校验、缩放、WebP 重编码与主题色提取。

存储路径只由固定的 kind 枚举推导（desktop.webp / mobile.webp），从不使用用户提供的文件名。
"""
from __future__ import annotations

import colorsys
import os
import secrets
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, Request
from PIL import Image, ImageOps, UnidentifiedImageError

BackgroundKind = Literal["desktop", "mobile"]
BACKGROUND_KINDS: tuple[BackgroundKind, ...] = ("desktop", "mobile")

MAX_BACKGROUND_BYTES = 10 * 1024 * 1024
MAX_SOURCE_PIXELS = 48_000_000  # 解码前拒绝超大图，防解压炸弹
# 输出上限（按比例缩放，不裁剪；前端用 object-fit: cover 铺满）
_OUTPUT_LIMITS: dict[str, tuple[int, int]] = {"desktop": (2560, 1440), "mobile": (1170, 2532)}
_ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "GIF", "BMP"})
_WEBP_QUALITY = 82
_MIN_SIDE = 320


class BackgroundValidationError(ValueError):
    """上传内容不是可接受的图片。"""


@dataclass(frozen=True)
class ProcessedBackground:
    data: bytes
    width: int
    height: int
    color: str  # 主题色 #rrggbb


async def read_limited_image_upload(request: Request) -> bytes:
    """流式读取请求体并强制上限。"""
    limit_text = f"图片不能超过 {MAX_BACKGROUND_BYTES // (1024 * 1024)} MiB"
    declared = request.headers.get("content-length")
    if declared:
        try:
            if int(declared) > MAX_BACKGROUND_BYTES:
                raise HTTPException(status_code=413, detail=limit_text)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Content-Length 无效") from exc
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BACKGROUND_BYTES:
            raise HTTPException(status_code=413, detail=limit_text)
        chunks.append(chunk)
    if size == 0:
        raise HTTPException(status_code=400, detail="图片不能为空")
    return b"".join(chunks)


def extract_theme_color(image: Image.Image) -> str:
    """从图片中提取最具代表性的「鲜明色」，返回 #rrggbb。

    缩小后做中位切分量化，按「占比 × 饱和度权重」打分，并排除近黑/近白，
    这样主题色取自画面中显眼的色块，而不是大面积的暗背景或高光。
    """
    small = image.convert("RGB").resize((96, 96), Image.Resampling.BILINEAR)
    quant = small.quantize(colors=10, method=Image.Quantize.MEDIANCUT)
    palette = quant.getpalette() or []
    counts = sorted(quant.getcolors() or [], reverse=True)
    total = float(sum(c for c, _ in counts)) or 1.0

    best_score = -1.0
    best_rgb = (82, 147, 226)
    for count, idx in counts:
        r, g, b = palette[idx * 3: idx * 3 + 3]
        _, light, sat = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        if light < 0.12 or light > 0.92:
            continue
        # 偏好中等明度，避免选到灰蒙蒙的色块
        light_weight = 1.0 - abs(light - 0.55)
        score = (count / total) ** 0.6 * (0.15 + sat) * light_weight
        if score > best_score:
            best_score, best_rgb = score, (r, g, b)
    return "#{:02x}{:02x}{:02x}".format(*best_rgb)


def process_background(content: bytes, kind: BackgroundKind) -> ProcessedBackground:
    """校验真实字节 → 方向矫正 → 缩放 → WebP 重编码 → 提取主题色。"""
    try:
        image = Image.open(BytesIO(content))
        if image.format not in _ALLOWED_FORMATS:
            raise BackgroundValidationError("仅支持 JPG / PNG / WebP / GIF / BMP 图片")
        width, height = image.size
        if width < _MIN_SIDE or height < _MIN_SIDE:
            raise BackgroundValidationError(f"图片尺寸过小（至少 {_MIN_SIDE}×{_MIN_SIDE}）")
        if width * height > MAX_SOURCE_PIXELS:
            raise BackgroundValidationError("图片像素过大")
        image.load()
    except BackgroundValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise BackgroundValidationError("无法解析图片文件") from exc

    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail(_OUTPUT_LIMITS[kind], Image.Resampling.LANCZOS)
    color = extract_theme_color(image)
    buf = BytesIO()
    image.save(buf, format="WEBP", quality=_WEBP_QUALITY, method=4)
    return ProcessedBackground(buf.getvalue(), image.width, image.height, color)


class BackgroundStorage:
    """固定文件名的背景图存储。"""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, kind: BackgroundKind) -> Path:
        if kind not in BACKGROUND_KINDS:
            raise ValueError("invalid background kind")
        return self.root / f"{kind}.webp"

    def write_atomic(self, kind: BackgroundKind, content: bytes) -> None:
        final_path = self.path_for(kind)
        temp_path = self.root / f".{secrets.token_hex(8)}.tmp"
        try:
            with temp_path.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, final_path)
        finally:
            temp_path.unlink(missing_ok=True)

    def delete(self, kind: BackgroundKind) -> None:
        self.path_for(kind).unlink(missing_ok=True)
