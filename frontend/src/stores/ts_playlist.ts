import { ref } from 'vue'
import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'
import {
  getTsPlaylists,
  createTsPlaylist,
  updateTsPlaylist,
  deleteTsPlaylist,
  uploadTsPlaylistCover,
  getTsPlaylistSongs,
  addSongToTsPlaylist,
  removeSongFromTsPlaylist,
  updateTsPlaylistSong,
  playTsPlaylist,
} from '@/api/ts_playlist'
import type { TsPlaylist, TsPlaylistSong } from '@/api/ts_playlist'
import { useMusicStore } from './music'
import type { Song } from '@/api/music'

/**
 * TS 专属歌单 store（独立于 music store——后者是 TSMusicBot 代理状态，本 store 是本地持久化收藏）。
 * 播放时调 useMusicStore().play(...) 复用现有跨平台播放链。
 */
export const useTsPlaylistStore = defineStore('ts-playlist', () => {
  const playlists = ref<TsPlaylist[]>([])
  /** playlistId -> 歌曲列表（展开时按需加载） */
  const currentSongs = ref<Record<number, TsPlaylistSong[]>>({})
  const expandedId = ref<number | null>(null)
  const loadingSongs = ref<Record<number, boolean>>({})

  async function fetchPlaylists() {
    try {
      const res = await getTsPlaylists()
      playlists.value = res.playlists || []
    } catch {
      /* 静默 */
    }
  }

  async function createPlaylist(name: string, description?: string) {
    const p = await createTsPlaylist(name, description)
    playlists.value.unshift(p)
    return p
  }

  async function renamePlaylist(id: number, name: string, description?: string) {
    const p = await updateTsPlaylist(id, { name, description })
    const i = playlists.value.findIndex((x) => x.id === id)
    if (i >= 0) playlists.value[i] = { ...playlists.value[i], ...p }
  }

  async function deletePlaylist(id: number) {
    await deleteTsPlaylist(id)
    playlists.value = playlists.value.filter((x) => x.id !== id)
    delete currentSongs.value[id]
    if (expandedId.value === id) expandedId.value = null
  }

  async function uploadCover(id: number, dataUrl: string) {
    await uploadTsPlaylistCover(id, dataUrl)
    const i = playlists.value.findIndex((x) => x.id === id)
    if (i >= 0) playlists.value[i] = { ...playlists.value[i], coverDataUrl: dataUrl }
  }

  async function fetchSongs(id: number) {
    loadingSongs.value[id] = true
    try {
      const res = await getTsPlaylistSongs(id)
      currentSongs.value[id] = res.songs || []
    } catch {
      currentSongs.value[id] = []
    } finally {
      loadingSongs.value[id] = false
    }
  }

  async function toggleExpand(id: number) {
    if (expandedId.value === id) {
      expandedId.value = null
      return
    }
    expandedId.value = id
    await fetchSongs(id)
  }

  /** 收藏一首歌到指定歌单。返回 {success,message}（重复收藏后端 409 → axios 抛错，调用方 catch）。 */
  async function addSong(playlistId: number, song: Song) {
    const res = await addSongToTsPlaylist(playlistId, song)
    await fetchPlaylists() // 刷新歌单 count
    if (expandedId.value === playlistId) await fetchSongs(playlistId)
    return res
  }

  async function removeSong(playlistId: number, platform: string, songId: string) {
    await removeSongFromTsPlaylist(playlistId, platform, songId)
    await fetchPlaylists()
    const arr = currentSongs.value[playlistId]
    if (arr) {
      currentSongs.value[playlistId] = arr.filter(
        (s) => !(s.platform === platform && s.songId === songId),
      )
    }
  }

  async function updateSongNote(
    playlistId: number,
    platform: string,
    songId: string,
    note: string,
  ) {
    const s = await updateTsPlaylistSong(playlistId, platform, songId, { note })
    const arr = currentSongs.value[playlistId]
    if (arr) {
      const i = arr.findIndex((x) => x.platform === platform && x.songId === songId)
      if (i >= 0) arr[i] = s
    }
  }

  /** 整单播放（后端逐首跨平台 add 到当前 active bot 队列）。返回 {enqueued,total} 供组件提示。 */
  async function playAll(id: number): Promise<{ enqueued: number; total: number }> {
    const music = useMusicStore()
    if (!music.activeBotId) {
      ElMessage.warning('请先在「TS Bot」面板创建一个 Bot')
      return { enqueued: 0, total: 0 }
    }
    const res = await playTsPlaylist(id, music.activeBotId)
    await music.fetchNowplaying()
    await music.fetchQueue()
    return res
  }

  /** 单首播放（复用 music 跨平台链）。VIP/版权/未登录等失败显式提示，不静默吞。 */
  async function playSong(song: TsPlaylistSong, queued: boolean) {
    const music = useMusicStore()
    if (!music.activeBotId) {
      ElMessage.warning('请先在「TS Bot」面板创建一个 Bot')
      return
    }
    const s: Song = {
      id: song.songId,
      name: song.name,
      artist: song.artist,
      album: song.album,
      duration: song.duration,
      coverUrl: song.coverUrl,
      platform: song.platform,
      vip: song.vip,
    }
    try {
      await music.play(`id:${song.songId}`, queued, song.platform, s)
    } catch (e) {
      ElMessage.error(e instanceof Error ? e.message : '播放失败')
    }
  }

  // ── 收藏弹窗（全局：搜索结果 / 平台歌单歌曲都调 openFavorite 打开同一个弹窗）──
  const favoriteVisible = ref(false)
  const favoriteSong = ref<Song | null>(null)
  function openFavorite(song: Song) {
    favoriteSong.value = song
    favoriteVisible.value = true
  }
  function closeFavorite() {
    favoriteVisible.value = false
  }

  return {
    playlists,
    currentSongs,
    expandedId,
    loadingSongs,
    fetchPlaylists,
    createPlaylist,
    renamePlaylist,
    deletePlaylist,
    uploadCover,
    fetchSongs,
    toggleExpand,
    addSong,
    removeSong,
    updateSongNote,
    playAll,
    playSong,
    favoriteVisible,
    favoriteSong,
    openFavorite,
    closeFavorite,
  }
})
