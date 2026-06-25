import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  searchMusic as apiSearch,
  playMusic as apiPlay,
  pauseMusic as apiPause,
  skipMusic as apiSkip,
  stopMusic as apiStop,
  getVolume as apiGetVolume,
  setVolume as apiSetVolume,
  callRadio as apiCallRadio,
  getQueue as apiGetQueue,
  clearQueue as apiClear,
  getNowplaying as apiGetNowplaying,
  seekMusic as apiSeek,
  searchNetease as apiSearchNetease,
  playNetease as apiPlayNetease,
  type Song,
} from '@/api/music'

export type MusicSource = 'netease' | 'default'

export const useMusicStore = defineStore('music', () => {
  const searchResults = ref<Song[]>([])
  const searching = ref(false)
  const playing = ref(false)
  const volume = ref(50)
  const searchKeyword = ref('')
  const source = ref<MusicSource>('netease')
  const queue = ref<Record<string, unknown>[]>([])
  const currentIndex = ref<number | null>(null)
  const nowplaying = ref<{ playing?: boolean; title?: string; position?: number; length?: number } | null>(null)
  // 当前播放的「歌名」（点歌时前端记录，比 TS3AudioBot 返回的 URL 友好）
  const currentTitle = ref('')

  async function search(keyword: string) {
    if (!keyword.trim()) return
    searching.value = true
    searchKeyword.value = keyword
    try {
      const res = source.value === 'netease'
        ? await apiSearchNetease(keyword)
        : await apiSearch(keyword)
      searchResults.value = res.results || []
    } catch {
      searchResults.value = []
    } finally {
      searching.value = false
    }
  }

  /** 播放（可传歌名，用于显示） */
  async function play(songId: string, name?: string) {
    if (name) currentTitle.value = name
    if (source.value === 'netease') await apiPlayNetease(songId)
    else await apiPlay(songId)
    playing.value = true
    await fetchQueue()
    await fetchNowplaying()
  }

  async function pause() {
    await apiPause()
    playing.value = !playing.value
    await fetchNowplaying()
  }

  async function skip() {
    await apiSkip()
    currentTitle.value = ''  // 下一首标题未知，清空由轮询填充
    await fetchQueue()
    await fetchNowplaying()
  }

  async function stop() {
    await apiStop()
    playing.value = false
    currentTitle.value = ''
    await fetchQueue()
    await fetchNowplaying()
  }

  async function fetchVolume() {
    try {
      volume.value = await apiGetVolume()
    } catch {
      // 静默
    }
  }

  async function updateVolume(val: number) {
    volume.value = val
    await apiSetVolume(val)
  }

  async function fetchQueue() {
    try {
      const res = await apiGetQueue()
      queue.value = (res.items || []) as Record<string, unknown>[]
      currentIndex.value = res.index ?? null
    } catch {
      // 静默
    }
  }

  async function clear() {
    await apiClear()
    await fetchQueue()
  }

  async function fetchNowplaying() {
    try {
      nowplaying.value = await apiGetNowplaying()
      // 若前端没记歌名，回退用 nowplaying.title（URL 截断）
    } catch {
      nowplaying.value = null
    }
  }

  /** 跳转播放进度 */
  async function seek(position: number) {
    await apiSeek(position)
    await fetchNowplaying()
  }

  async function callRadio() {
    await apiCallRadio()
  }

  return {
    searchResults,
    searching,
    playing,
    volume,
    searchKeyword,
    source,
    queue,
    currentIndex,
    nowplaying,
    currentTitle,
    search,
    play,
    pause,
    skip,
    stop,
    seek,
    fetchVolume,
    updateVolume,
    fetchQueue,
    clear,
    fetchNowplaying,
    callRadio,
  }
})
