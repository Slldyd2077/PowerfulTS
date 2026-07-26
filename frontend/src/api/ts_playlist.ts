import apiClient from './client'
import type { Song } from './music'

/** TS 专属歌单（用户自有，可创建多个） */
export interface TsPlaylist {
  id: number
  name: string
  description?: string | null
  coverDataUrl?: string | null
  songCount?: number
  createdAt?: string
}

/** TS 歌单内的收藏曲目（跨平台混合）。platform 即来源平台（出处）。 */
export interface TsPlaylistSong extends Song {
  songId: string
  originalName: string
  note?: string | null
  sort: number
  addedAt?: string
  platform: string // 覆盖 Song.platform?（后端保证非空，用作出处标签与重放路由）
}

// ── 歌单 CRUD ──

export async function getTsPlaylists(): Promise<{ playlists: TsPlaylist[] }> {
  const { data } = await apiClient.get('/ts-playlists')
  return data
}

export async function createTsPlaylist(name: string, description?: string): Promise<TsPlaylist> {
  const { data } = await apiClient.post('/ts-playlists', { name, description })
  return data
}

export async function updateTsPlaylist(
  id: number,
  body: { name?: string; description?: string },
): Promise<TsPlaylist> {
  const { data } = await apiClient.put(`/ts-playlists/${id}`, body)
  return data
}

export async function uploadTsPlaylistCover(
  id: number,
  dataUrl: string,
): Promise<{ coverDataUrl: string }> {
  const { data } = await apiClient.put(`/ts-playlists/${id}/cover`, { dataUrl })
  return data
}

export async function deleteTsPlaylist(id: number): Promise<void> {
  await apiClient.delete(`/ts-playlists/${id}`)
}

// ── 歌曲 CRUD ──

export async function getTsPlaylistSongs(id: number): Promise<{ songs: TsPlaylistSong[] }> {
  const { data } = await apiClient.get(`/ts-playlists/${id}/songs`)
  return data
}

/** 收藏一首歌到指定 TS 歌单。重复收藏后端返回 409（前端 catch 提示）。 */
export async function addSongToTsPlaylist(
  playlistId: number,
  song: Song,
): Promise<{ success: boolean; message: string }> {
  const { data } = await apiClient.post(`/ts-playlists/${playlistId}/songs`, {
    platform: song.platform,
    songId: song.id,
    name: song.name,
    artist: song.artist,
    album: song.album,
    duration: song.duration,
    coverUrl: song.coverUrl,
    vip: song.vip,
  })
  return data
}

export async function removeSongFromTsPlaylist(
  playlistId: number,
  platform: string,
  songId: string,
): Promise<void> {
  await apiClient.delete(`/ts-playlists/${playlistId}/songs`, { params: { platform, songId } })
}

export async function updateTsPlaylistSong(
  playlistId: number,
  platform: string,
  songId: string,
  body: { note?: string; sortOrder?: number },
): Promise<TsPlaylistSong> {
  const { data } = await apiClient.put(`/ts-playlists/${playlistId}/songs`, body, {
    params: { platform, songId },
  })
  return data
}

// ── 整单播放（跨平台逐首 add）──

export async function playTsPlaylist(
  playlistId: number,
  botId: string,
): Promise<{ enqueued: number; total: number }> {
  const { data } = await apiClient.post(`/ts-playlists/${playlistId}/play`, null, {
    params: { botId },
  })
  return data
}
