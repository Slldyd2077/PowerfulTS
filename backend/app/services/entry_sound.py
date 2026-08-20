"""Validation, path-safe storage, and playback capabilities for entry sounds."""
from __future__ import annotations

import math
import os
import re
import secrets
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Callable

from fastapi import HTTPException, Request
from mutagen import File as MutagenFile

MAX_ENTRY_SOUND_BYTES = 10 * 1024 * 1024
MAX_ENTRY_SOUND_SECONDS = 7.0

_AUDIO_TYPES: dict[str, tuple[str, str, frozenset[str]]] = {
    "mp3": ("mp3", "audio/mpeg", frozenset({"mp3"})),
    "wave": ("wav", "audio/wav", frozenset({"wav", "wave"})),
    "flac": ("flac", "audio/flac", frozenset({"flac"})),
    "ogg": ("ogg", "audio/ogg", frozenset({"ogg", "oga"})),
    "mp4": ("m4a", "audio/mp4", frozenset({"m4a", "mp4"})),
    "aac": ("aac", "audio/aac", frozenset({"aac"})),
}
_STORAGE_NAME = re.compile(r"[0-9a-f]{32}\.(?:mp3|wav|flac|ogg|m4a|aac)")


class EntrySoundValidationError(ValueError):
    """The uploaded bytes are not an allowed, duration-bounded audio file."""


@dataclass(frozen=True)
class InspectedAudio:
    original_filename: str
    extension: str
    mime_type: str
    duration_ms: int


@dataclass(frozen=True)
class EntrySoundCapability:
    storage_filename: str
    mime_type: str
    expires_at: float


def _safe_display_filename(filename: str) -> str:
    basename = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    basename = "".join(ch for ch in basename if ch >= " " and ch != "\x7f")
    if not basename or len(basename) > 255:
        raise EntrySoundValidationError("文件名无效")
    return basename


def _mutagen_kind(audio: object) -> str | None:
    module = audio.__class__.__module__.rsplit(".", 1)[-1].lower()
    if module.startswith("ogg"):
        return "ogg"
    return module if module in _AUDIO_TYPES else None


def inspect_audio(content: bytes, filename: str) -> InspectedAudio:
    """Inspect the actual bytes; client MIME and extension are never trusted alone."""
    safe_name = _safe_display_filename(filename)
    suffix = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    try:
        audio = MutagenFile(BytesIO(content))
    except Exception as exc:
        raise EntrySoundValidationError("无法解析音频格式") from exc
    kind = _mutagen_kind(audio) if audio is not None else None
    if kind is None:
        raise EntrySoundValidationError("不支持或无法识别的音频格式")
    extension, mime_type, allowed_suffixes = _AUDIO_TYPES[kind]
    if suffix not in allowed_suffixes:
        raise EntrySoundValidationError("文件扩展名与实际音频格式不一致")
    try:
        duration = float(audio.info.length)
    except (AttributeError, TypeError, ValueError) as exc:
        raise EntrySoundValidationError("无法读取音频时长") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise EntrySoundValidationError("音频时长无效")
    if duration > MAX_ENTRY_SOUND_SECONDS:
        raise EntrySoundValidationError("入场音效不能超过 7 秒")
    return InspectedAudio(
        original_filename=safe_name,
        extension=extension,
        mime_type=mime_type,
        duration_ms=round(duration * 1000),
    )


async def read_limited_upload(
    request: Request, max_bytes: int = MAX_ENTRY_SOUND_BYTES
) -> bytes:
    """Stream the request body with an in-process hard limit (inclusive boundary)."""
    declared = request.headers.get("content-length")
    if declared:
        try:
            if int(declared) > max_bytes:
                raise HTTPException(status_code=413, detail="文件不能超过 10 MiB")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Content-Length 无效") from exc
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > max_bytes:
            raise HTTPException(status_code=413, detail="文件不能超过 10 MiB")
        chunks.append(chunk)
    if size == 0:
        raise HTTPException(status_code=400, detail="音频文件不能为空")
    return b"".join(chunks)


class EntrySoundStorage:
    """Filesystem storage that never derives paths from user-controlled names."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, storage_filename: str) -> Path:
        if not _STORAGE_NAME.fullmatch(storage_filename):
            raise ValueError("invalid server storage filename")
        path = (self.root / storage_filename).resolve()
        if path.parent != self.root:
            raise ValueError("entry sound path escaped storage root")
        return path

    def write_atomic(self, content: bytes, extension: str) -> str:
        filename = f"{secrets.token_hex(16)}.{extension}"
        final_path = self.path_for(filename)
        temp_path = self.root / f".{secrets.token_hex(16)}.tmp"
        try:
            with temp_path.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, final_path)
        finally:
            temp_path.unlink(missing_ok=True)
        return filename

    def delete(self, storage_filename: str) -> None:
        self.path_for(storage_filename).unlink(missing_ok=True)


class EntrySoundCapabilities:
    """Short-lived bearer capabilities for TSMusicBot to pull one stored sound."""

    def __init__(
        self,
        ttl_seconds: float = 30,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._tickets: dict[str, EntrySoundCapability] = {}

    def create(self, storage_filename: str, mime_type: str) -> str:
        now = self._clock()
        self._purge(now)
        token = secrets.token_urlsafe(32)
        self._tickets[token] = EntrySoundCapability(
            storage_filename=storage_filename,
            mime_type=mime_type,
            expires_at=now + self._ttl_seconds,
        )
        return token

    def resolve(self, token: str) -> EntrySoundCapability | None:
        now = self._clock()
        ticket = self._tickets.get(token)
        if ticket is None or ticket.expires_at <= now:
            self._tickets.pop(token, None)
            return None
        return ticket

    def _purge(self, now: float) -> None:
        self._tickets = {
            token: ticket
            for token, ticket in self._tickets.items()
            if ticket.expires_at > now
        }
