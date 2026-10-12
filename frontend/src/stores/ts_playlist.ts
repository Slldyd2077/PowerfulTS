import { computed, ref } from 'vue'
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
  addSongsToTsPlaylist,
  removeSongFromTsPlaylist,
  updateTsPlaylistSong,
} from '@/api/ts_playlist'
import type { TsFavoriteMembership, TsPlaylist, TsPlaylistSong } from '@/api/ts_playlist'
import { useMusicStore } from './music'
import type { Song } from '@/api/music'

/**
 * TS 专属歌单 store（独立于 music store——后者是 TSMusicBot 代理状态，本 store 是本地持久化收藏）。
 * 播放时调 useMusicStore().play(...) 复用现有跨平台播放链。
 */
export const useTsPlaylistStore = defineStore('ts-playlist', () => {
  const playlists = ref<TsPlaylist[]>([])
  const favoriteMemberships = ref<TsFavoriteMembership[]>([])
  const favoriteKeys = computed(() => new Set(
    favoriteMemberships.value.map((s) => JSON.stringify([s.platform, s.songId])),
  ))
  function isFavorite(song: Song): boolean {
    return favoriteKeys.value.has(JSON.stringify([song.platform, String(song.id)]))
  }
  /** playlistId -> 歌曲列表（展开时按需加载） */
  const currentSongs = ref<Record<number, TsPlaylistSong[]>>({})
  const expandedId = ref<number | null>(null)
  const loadingSongs = ref<Record<number, boolean>>({})
  let playlistRequest = 0

  async function fetchPlaylists() {
    const request = ++playlistRequest
    try {
      const res = await getTsPlaylists()
      if (request !== playlistRequest) return
      playlists.value = res.playlists || []
      favoriteMemberships.value = res.favorites || []
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
    playlistRequest++ // 使删除前发出的列表请求失效，避免旧响应恢复收藏标记
    playlists.value = playlists.value.filter((x) => x.id !== id)
    favoriteMemberships.value = favoriteMemberships.value.filter((s) => s.playlistId !== id)
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
    if (song.platform) {
      favoriteMemberships.value.push({ playlistId, platform: song.platform, songId: String(song.id) })
    }
    await fetchPlaylists() // 刷新歌单 count
    if (expandedId.value === playlistId) await fetchSongs(playlistId)
    return res
  }

  const importProgress = ref({ running: false, processed: 0, total: 0, added: 0, skipped: 0, failed: 0 })
  async function addSongs(playlistId: number, songs: Song[]) {
    if (importProgress.value.running) throw new Error('正在收藏歌单，请等待完成')
    const target = [...songs]
    importProgress.value = { running: true, processed: 0, total: target.length, added: 0, skipped: 0, failed: 0 }
    try {
      for (let offset = 0; offset < target.length; offset += 50) {
        const batch = target.slice(offset, offset + 50)
        const result = await addSongsToTsPlaylist(playlistId, batch)
        importProgress.value.added += result.added
        importProgress.value.skipped += result.skipped
        importProgress.value.failed += result.failed
        importProgress.value.processed += batch.length
        await fetchPlaylists()
        if (expandedId.value === playlistId) await fetchSongs(playlistId)
      }
      return { ...importProgress.value }
    } finally {
      importProgress.value.running = false
    }
  }

  async function removeSong(playlistId: number, platform: string, songId: string) {
    await removeSongFromTsPlaylist(playlistId, platform, songId)
    favoriteMemberships.value = favoriteMemberships.value.filter(
      (s) => !(s.playlistId === playlistId && s.platform === platform && s.songId === songId),
    )
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

  /** 整单播放：首曲开始播放，其余分批入队并显示进度。 */
  async function playAll(id: number): Promise<{ enqueued: number; total: number }> {
    const music = useMusicStore()
    if (!music.activeBotId) {
      ElMessage.warning('请先在「TS Bot」面板创建一个 Bot')
      return { enqueued: 0, total: 0 }
    }
    const { songs } = await getTsPlaylistSongs(id)
    const res = await music.enqueueAll(songs, undefined, true)
    return { ...res, total: songs.length }
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
  const favoriteSongs = ref<Song[]>([])
  const favoriteTitle = ref('')
  function openFavorite(song: Song) {
    if (importProgress.value.running) return
    favoriteSong.value = song
    favoriteSongs.value = []
    favoriteTitle.value = ''
    favoriteVisible.value = true
  }
  function openPlaylistFavorite(songs: Song[], title: string) {
    if (importProgress.value.running) return
    importProgress.value = { running: false, processed: 0, total: songs.length, added: 0, skipped: 0, failed: 0 }
    favoriteSong.value = null
    favoriteSongs.value = [...songs]
    favoriteTitle.value = title
    favoriteVisible.value = true
  }
  function closeFavorite() {
    favoriteVisible.value = false
  }

  return {
    playlists,
    isFavorite,
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
    addSongs,
    importProgress,
    removeSong,
    updateSongNote,
    playAll,
    playSong,
    favoriteVisible,
    favoriteSong,
    favoriteSongs,
    favoriteTitle,
    openPlaylistFavorite,
    openFavorite,
    closeFavorite,
  }
})
