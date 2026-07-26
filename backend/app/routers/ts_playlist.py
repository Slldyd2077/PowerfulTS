"""TS 专属歌单路由（用户自有的跨平台混合收藏歌单）。

独立于 4 个音源平台：用户创建多个歌单、设封面，收藏搜索结果/平台歌单里的歌，
形成混合歌单；每首标来源平台，可改备注名；点歌单歌曲按 (platform, song_id) 重放。
权限：歌单/歌曲 CRUD 仅 owner（service 内 account_id 校验）；整单播放复用 music 的 OwnedBotId。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..deps import AccountDep, TsmusicDep
from ..routers.music import OwnedBotId
from ..services.ts_playlist_service import TsPlaylistService, _PLATFORMS, _SONG_ID_RE

router = APIRouter(prefix="/ts-playlists", tags=["ts-playlist"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


def _check_song_key(platform: str | None, song_id: str | None) -> tuple[str, str]:
    if not platform or platform not in _PLATFORMS or not song_id or not _SONG_ID_RE.match(song_id):
        raise HTTPException(status_code=400, detail="platform/songId 不合法")
    return platform, song_id


# ───────────────────────── 请求模型 ─────────────────────────


class PlaylistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)


class PlaylistUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)


class CoverUpdate(BaseModel):
    dataUrl: str = Field(max_length=300_000)


class SongAdd(BaseModel):
    platform: str = Field(min_length=1, max_length=16)
    songId: str = Field(min_length=1, max_length=64)
    name: str = Field(default="", max_length=255)
    artist: str = Field(default="", max_length=255)
    album: str | None = Field(default=None, max_length=255)
    duration: int | None = None
    coverUrl: str | None = Field(default=None, max_length=512)
    vip: bool | None = None


class SongUpdate(BaseModel):
    note: str | None = Field(default=None, max_length=255)
    sortOrder: int | None = None


# ───────────────────────── 歌单 CRUD ─────────────────────────


@router.get("")
async def list_playlists(account: AccountDep, db: DbDep):
    return {"playlists": await TsPlaylistService(db).list_playlists(account.id)}


@router.post("", status_code=201)
async def create_playlist(body: PlaylistCreate, account: AccountDep, db: DbDep):
    return await TsPlaylistService(db).create_playlist(account.id, body.name, body.description)


@router.put("/{playlist_id}")
async def update_playlist(playlist_id: int, body: PlaylistUpdate, account: AccountDep, db: DbDep):
    res = await TsPlaylistService(db).update_playlist(
        account.id, playlist_id, body.name, body.description
    )
    if res is None:
        raise HTTPException(status_code=404, detail="歌单不存在")
    return res


@router.put("/{playlist_id}/cover")
async def set_cover(playlist_id: int, body: CoverUpdate, account: AccountDep, db: DbDep):
    if not body.dataUrl.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="封面必须是 data:image/* base64")
    # 大小由 CoverUpdate.dataUrl 的 max_length=300_000 限制（与 bot avatar 对齐，≈225KB 二进制）
    res = await TsPlaylistService(db).set_cover(account.id, playlist_id, body.dataUrl)
    if res is None:
        raise HTTPException(status_code=404, detail="歌单不存在")
    return res


@router.delete("/{playlist_id}")
async def delete_playlist(playlist_id: int, account: AccountDep, db: DbDep):
    if not await TsPlaylistService(db).delete_playlist(account.id, playlist_id):
        raise HTTPException(status_code=404, detail="歌单不存在")
    return {"success": True}


# ───────────────────────── 歌曲 CRUD ─────────────────────────


@router.get("/{playlist_id}/songs")
async def list_songs(playlist_id: int, account: AccountDep, db: DbDep):
    res = await TsPlaylistService(db).list_songs(account.id, playlist_id)
    if res is None:
        raise HTTPException(status_code=404, detail="歌单不存在")
    return {"songs": res}


@router.post("/{playlist_id}/songs", status_code=201)
async def add_song(playlist_id: int, body: SongAdd, account: AccountDep, db: DbDep):
    ok, msg, status = await TsPlaylistService(db).add_song(account.id, playlist_id, body.model_dump())
    if not ok:
        raise HTTPException(status_code=status, detail=msg)
    return {"success": True, "message": msg}


@router.delete("/{playlist_id}/songs")
async def remove_song(
    playlist_id: int,
    account: AccountDep,
    db: DbDep,
    platform: str = Query(...),
    songId: str = Query(...),
):
    plat, sid = _check_song_key(platform, songId)
    await TsPlaylistService(db).remove_song(account.id, playlist_id, plat, sid)
    return {"success": True}


@router.put("/{playlist_id}/songs")
async def update_song(
    playlist_id: int,
    body: SongUpdate,
    account: AccountDep,
    db: DbDep,
    platform: str = Query(...),
    songId: str = Query(...),
):
    plat, sid = _check_song_key(platform, songId)
    res = await TsPlaylistService(db).update_song(
        account.id, playlist_id, plat, sid, note=body.note, sort_order=body.sortOrder
    )
    if res is None:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    return res


# ───────────────────────── 整单播放（跨平台逐首 add）─────────────────────────


@router.post("/{playlist_id}/play")
async def play_playlist(
    playlist_id: int,
    account: AccountDep,
    db: DbDep,
    tsmusic: TsmusicDep,
    bot_id: OwnedBotId = None,
):
    res = await TsPlaylistService(db).play_playlist(account.id, playlist_id, bot_id, tsmusic)
    if res is None:
        raise HTTPException(status_code=404, detail="歌单不存在")
    return res
