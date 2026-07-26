"""TS 专属歌单服务（SQLite 持久化 + 跨平台整单播放）。

歌单/歌曲 CRUD 按 account_id 做 owner 隔离；整单播放走 TSMusicBot，
因 song_id 仅平台内唯一、跨平台混合，需逐首 add（每首自带 platform）——
对照 bot_player_state 的 restore_player_state 范式。
"""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import TsPlaylist, TsPlaylistSong

if TYPE_CHECKING:
    from .tsmusic_client import TSMusicClient

logger = logging.getLogger(__name__)

# 来源平台白名单（出处 + 播放路由）
_PLATFORMS = {"netease", "qq", "bilibili", "kugou"}
# song_id 格式校验（防 TSMusicBot 侧解析异常；router 复用同一常量，避免定义漂移）
_SONG_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class TsPlaylistService:
    """TS 歌单的数据库操作 + 整单播放（所有写操作先校验 owner）。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ───────────────────────── 歌单 CRUD ─────────────────────────

    async def _get_owned(self, account_id: int, playlist_id: int) -> TsPlaylist | None:
        p = await self.db.get(TsPlaylist, playlist_id)
        if p is None or p.account_id != account_id:
            return None
        return p

    async def list_playlists(self, account_id: int) -> list[dict]:
        rows = (
            await self.db.execute(
                select(TsPlaylist)
                .where(TsPlaylist.account_id == account_id)
                .order_by(TsPlaylist.sort_order, TsPlaylist.created_at)
            )
        ).scalars().all()
        out: list[dict] = []
        for p in rows:
            cnt = (
                await self.db.execute(
                    select(func.count(TsPlaylistSong.id)).where(
                        TsPlaylistSong.playlist_id == p.id
                    )
                )
            ).scalar() or 0
            out.append(self._serialize_playlist(p, cnt))
        return out

    async def create_playlist(self, account_id: int, name: str, description: str | None) -> dict:
        p = TsPlaylist(account_id=account_id, name=name, description=description)
        self.db.add(p)
        await self.db.commit()
        await self.db.refresh(p)
        return self._serialize_playlist(p, 0)

    async def update_playlist(
        self, account_id: int, playlist_id: int, name: str | None, description: str | None
    ) -> dict | None:
        p = await self._get_owned(account_id, playlist_id)
        if p is None:
            return None
        if name is not None:
            p.name = name
        if description is not None:
            p.description = description
        await self.db.commit()
        await self.db.refresh(p)
        cnt = (
            await self.db.execute(
                select(func.count(TsPlaylistSong.id)).where(TsPlaylistSong.playlist_id == p.id)
            )
        ).scalar() or 0
        return self._serialize_playlist(p, cnt)

    async def delete_playlist(self, account_id: int, playlist_id: int) -> bool:
        p = await self._get_owned(account_id, playlist_id)
        if p is None:
            return False
        await self.db.delete(p)  # 外键 ondelete CASCADE 级联删歌曲
        await self.db.commit()
        return True

    async def set_cover(self, account_id: int, playlist_id: int, data_url: str) -> dict | None:
        p = await self._get_owned(account_id, playlist_id)
        if p is None:
            return None
        p.cover_data_url = data_url
        await self.db.commit()
        return {"coverDataUrl": data_url}

    # ───────────────────────── 歌曲 CRUD ─────────────────────────

    async def list_songs(self, account_id: int, playlist_id: int) -> list[dict] | None:
        if await self._get_owned(account_id, playlist_id) is None:
            return None
        rows = (
            await self.db.execute(
                select(TsPlaylistSong)
                .where(TsPlaylistSong.playlist_id == playlist_id)
                .order_by(TsPlaylistSong.sort_order, TsPlaylistSong.added_at)
            )
        ).scalars().all()
        return [self._serialize_song(s) for s in rows]

    async def add_song(self, account_id: int, playlist_id: int, song: dict) -> tuple[bool, str, int]:
        """收藏歌曲。返回 (success, message, http_status)。"""
        p = await self._get_owned(account_id, playlist_id)
        if p is None:
            return False, "歌单不存在", 404
        platform = str(song.get("platform") or "").strip()
        song_id = str(song.get("songId") or song.get("id") or "").strip()
        if platform not in _PLATFORMS or not _SONG_ID_RE.match(song_id):
            return False, "platform/songId 不合法", 400
        item = TsPlaylistSong(
            playlist_id=playlist_id,
            platform=platform,
            song_id=song_id,
            name=str(song.get("name") or "")[:255] or f"App {song_id}",
            artist=str(song.get("artist") or "")[:255],
            album=song.get("album"),
            duration=song.get("duration"),
            cover_url=song.get("coverUrl"),
            vip=song.get("vip"),
        )
        self.db.add(item)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            return False, "该歌曲已在歌单中", 409
        return True, "已收藏", 201

    async def remove_song(
        self, account_id: int, playlist_id: int, platform: str, song_id: str
    ) -> bool:
        if await self._get_owned(account_id, playlist_id) is None:
            return False
        await self.db.execute(
            delete(TsPlaylistSong).where(
                TsPlaylistSong.playlist_id == playlist_id,
                TsPlaylistSong.platform == platform,
                TsPlaylistSong.song_id == song_id,
            )
        )
        await self.db.commit()
        return True

    async def update_song(
        self,
        account_id: int,
        playlist_id: int,
        platform: str,
        song_id: str,
        note: str | None = None,
        sort_order: int | None = None,
    ) -> dict | None:
        if await self._get_owned(account_id, playlist_id) is None:
            return None
        item = (
            await self.db.execute(
                select(TsPlaylistSong).where(
                    TsPlaylistSong.playlist_id == playlist_id,
                    TsPlaylistSong.platform == platform,
                    TsPlaylistSong.song_id == song_id,
                )
            )
        ).scalar_one_or_none()
        if item is None:
            return None
        if note is not None:
            stripped = note.strip()
            item.note = stripped[:255] if stripped else None
        if sort_order is not None:
            item.sort_order = sort_order
        await self.db.commit()
        await self.db.refresh(item)
        return self._serialize_song(item)

    # ───────────────────────── 整单播放（跨平台逐首）─────────────────────────

    async def play_playlist(
        self, account_id: int, playlist_id: int, bot_id: str | None, tsmusic: "TSMusicClient"
    ) -> dict | None:
        """第一首 play（开始播放）+ 其余逐首 add，每首自带 platform（跨平台混合）。
        单首失败（如某平台未登录）不阻断，记 warning。"""
        if await self._get_owned(account_id, playlist_id) is None:
            return None
        songs = (
            await self.db.execute(
                select(TsPlaylistSong)
                .where(TsPlaylistSong.playlist_id == playlist_id)
                .order_by(TsPlaylistSong.sort_order, TsPlaylistSong.added_at)
            )
        ).scalars().all()
        if not songs:
            return {"enqueued": 0, "total": 0}
        first = songs[0]
        added = 0
        try:
            await tsmusic.play(
                query=f"id:{first.song_id}",
                platform=first.platform,
                meta=self._meta(first),
                bot_id=bot_id,
            )
            added = 1
        except Exception as exc:  # 首曲失败（TSMusicBot 不可达等）不阻断后续入队
            logger.warning("TS 歌单首曲播放失败 %s:%s: %s", first.platform, first.song_id, exc)
        for s in songs[1:]:
            try:
                await tsmusic.add(
                    query=f"id:{s.song_id}",
                    platform=s.platform,
                    meta=self._meta(s),
                    bot_id=bot_id,
                )
                added += 1
            except Exception as exc:  # 单首失败不阻断整单
                logger.warning("TS 歌单入队失败 %s:%s: %s", s.platform, s.song_id, exc)
        return {"enqueued": added, "total": len(songs)}

    # ───────────────────────── 序列化 ─────────────────────────

    @staticmethod
    def _meta(s: TsPlaylistSong) -> dict:
        """供 TSMusicBot 队列回填的 song meta（与 Song 字段对齐）。"""
        return {
            "id": s.song_id,
            "platform": s.platform,
            "name": s.name,
            "artist": s.artist,
            "album": s.album,
            "duration": s.duration,
            "coverUrl": s.cover_url,
            "vip": s.vip,
        }

    @staticmethod
    def _serialize_playlist(p: TsPlaylist, song_count: int) -> dict:
        return {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "coverDataUrl": p.cover_data_url,
            "songCount": song_count,
            "createdAt": p.created_at.isoformat() if p.created_at else None,
        }

    @staticmethod
    def _serialize_song(s: TsPlaylistSong) -> dict:
        return {
            "id": s.song_id,  # Song.id（前端播放 'id:${id}'）
            "songId": s.song_id,
            "platform": s.platform,
            "name": s.note or s.name,  # 备注名覆盖显示
            "originalName": s.name,
            "artist": s.artist,
            "album": s.album,
            "duration": s.duration,
            "coverUrl": s.cover_url,
            "vip": s.vip,
            "note": s.note,
            "sort": s.sort_order,
            "addedAt": s.added_at.isoformat() if s.added_at else None,
        }
