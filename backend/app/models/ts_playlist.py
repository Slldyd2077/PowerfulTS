"""TS 专属歌单 —— 用户自有的跨平台混合收藏歌单。

独立于 4 个音源平台（网易云/QQ/B站/酷狗）：用户可创建多个歌单、设封面，
把搜索结果或平台歌单里的歌收藏进来混合存放；每首歌标注来源平台，可改备注名。
点歌单曲目按 (platform, song_id) 经 TSMusicBot 重新播放。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class TsPlaylist(Base):
    """TS 专属歌单（用户自有，可创建多个用于分类）。"""

    __tablename__ = "ts_playlists"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 封面以 base64 data URL 入库（复用 netease_cookie 的 Text 大字段范式；前端直接 <img :src>)
    cover_data_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class TsPlaylistSong(Base):
    """TS 歌单内的收藏曲目（跨平台混合）。

    复合唯一键 (playlist_id, platform, song_id) 防止同一歌单重复收藏同一首；
    song_id 仅平台内唯一，跨平台靠 platform 区分（B 站 song_id 即 BV 号）。
    """

    __tablename__ = "ts_playlist_songs"
    __table_args__ = (
        UniqueConstraint("playlist_id", "platform", "song_id", name="uq_ts_playlist_song"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    playlist_id: Mapped[int] = mapped_column(
        ForeignKey("ts_playlists.id", ondelete="CASCADE"), index=True
    )
    platform: Mapped[str] = mapped_column(String(16))  # netease|qq|bilibili|kugou（来源平台=出处）
    song_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))  # 原标题（用于展示与搜索回退）
    artist: Mapped[str] = mapped_column(String(255), default="", server_default="")
    album: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    vip: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 用户备注名（覆盖显示，可改）
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
