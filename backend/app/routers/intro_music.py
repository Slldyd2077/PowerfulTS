"""开屏背景音乐路由。

/api/intro-music            扫描 data/intro-music/ 返回曲目列表（前端随机选曲）
/api/intro-music/{f}/stream 流式播放单个曲目（FileResponse 自带 Range/seek 支持）

把音频文件（mp3/wav/ogg/m4a/flac/aac）放入 backend/data/intro-music/ 即可，
登录页开屏随机播放。无需维护清单。

安全：stream 端点的 filename 必须不含路径分隔符、resolve 后仍落在 MUSIC_DIR 内、
扩展名命中白名单且真实存在 —— 杜绝路径遍历（../、符号链接）与非音频文件下载。
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

# 音乐目录：backend/data/intro-music/（相对本文件定位，不依赖 CWD）
MUSIC_DIR: Path = Path(__file__).resolve().parents[2] / "data" / "intro-music"

# 白名单扩展名（小写）—— 扫描与流式均以此为唯一准入
_ALLOWED_EXT: frozenset[str] = frozenset({".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"})

# mimetypes 兜底：精简环境（最小化容器）可能缺 m4a/aac/flac 注册，
# 避免退化为 application/octet-stream 导致浏览器拒绝内联播放。
_FALLBACK_TYPES: dict[str, str] = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
}


def _scan_tracks() -> list[dict[str, str]]:
    """扫描音乐目录，返回 [{name, filename}]，按文件名排序；目录不存在或不可读则返回空列表。"""
    if not MUSIC_DIR.is_dir():
        return []
    tracks: list[dict[str, str]] = []
    try:
        entries = sorted(MUSIC_DIR.iterdir(), key=lambda x: x.name.lower())
    except (PermissionError, OSError):
        return []
    for p in entries:
        try:
            if p.is_file() and p.suffix.lower() in _ALLOWED_EXT:
                tracks.append({"name": p.stem, "filename": p.name})
        except OSError:
            continue
    return tracks


def _resolve_track(filename: str) -> Path | None:
    """安全定位曲目（O(1)，不扫描目录）：拒绝路径分隔符；resolve 后必须落在 MUSIC_DIR 内；
    扩展名命中白名单；文件真实存在。任一不满足返回 None。"""
    if not filename or "/" in filename or "\\" in filename:
        return None
    path = MUSIC_DIR / filename
    try:
        # resolve 解析符号链接/..，relative_to 保证结果仍在 MUSIC_DIR 之下
        path.resolve().relative_to(MUSIC_DIR)
    except (ValueError, OSError):
        return None
    if path.suffix.lower() not in _ALLOWED_EXT or not path.is_file():
        return None
    return path


@router.get("/intro-music")
async def list_intro_tracks() -> dict[str, list[dict[str, str]]]:
    """开屏背景音乐曲目列表（前端随机选曲）。目录为空时返回空列表，前端据此降级。"""
    return {"tracks": _scan_tracks()}


@router.get("/intro-music/{filename}/stream")
async def stream_intro_track(filename: str) -> FileResponse:
    """流式播放单个曲目（FileResponse 自带 Range 支持，可拖动进度）。非法/不存在 → 404。"""
    path = _resolve_track(filename)
    if path is None:
        raise HTTPException(status_code=404, detail="track not found")
    media_type = (
        mimetypes.guess_type(filename)[0]
        or _FALLBACK_TYPES.get(Path(filename).suffix.lower(), "application/octet-stream")
    )
    return FileResponse(path, media_type=media_type, filename=filename)
