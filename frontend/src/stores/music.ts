import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  searchMusic as apiSearch,
  playMusic as apiPlay,
  pauseMusic as apiPause,
  resumeMusic as apiResume,
  nextMusic as apiNext,
  stopMusic as apiStop,
  seekMusic as apiSeek,
  setVolume as apiSetVolume,
  setMode as apiSetMode,
  clearQueue as apiClear,
  getNowplaying as apiGetNowplaying,
  getQueue as apiGetQueue,
  type Song,
  type NowPlaying,
} from '@/api/music'

export const useMusicStore = defineStore('music', () => {
  const searchResults = ref<Song[]>([])
  const searching = ref(false)
  const searchKeyword = ref('')
  const nowplaying = ref<NowPlaying | null>(null)
  const queue = ref<Song[]>([])
  const volume = ref(50)
  const playMode = ref('seq')
  // 本地进度（每秒递增，轮询校正）
  const localPosition = ref(0)

  const searchPlatform = ref<'all' | 'netease' | 'qq' | 'bilibili'>('all')

  /** 搜索（按当前平台；all=三平台并行） */
  async function search(q: string) {
    if (!q.trim()) return
    searching.value = true
    searchKeyword.value = q
    try {
      if (searchPlatform.value === 'all') {
        // 三平台并行搜索，合并结果
        const [ne, qq, bili] = await Promise.allSettled([
          apiSearch(q, 'netease'),
          apiSearch(q, 'qq'),
          apiSearch(q, 'bilibili'),
        ])
        const all: Song[] = []
        for (const r of [ne, qq, bili]) {
          if (r.status === 'fulfilled') all.push(...(r.value.results || []))
        }
        searchResults.value = all
      } else {
        const res = await apiSearch(q, searchPlatform.value)
        searchResults.value = res.results || []
      }
    } catch {
      searchResults.value = []
    } finally {
      searching.value = false
    }
  }

  /** 播放（query=歌名 或 'id:xxx'，platform 指定音源） */
  async function play(query: string, queued = false, platform?: string) {
    const res = await apiPlay(query, queued, platform)
    await fetchNowplaying()
    await fetchQueue()
    return res
  }

  /** 暂停 */
  async function pause() {
    await apiPause()
    await fetchNowplaying()
  }

  /** 恢复 */
  async function resume() {
    await apiResume()
    await fetchNowplaying()
  }

  /** 下一首 */
  async function next() {
    await apiNext()
    await fetchNowplaying()
    await fetchQueue()
  }

  /** 停止 */
  async function stop() {
    await apiStop()
    await fetchNowplaying()
    await fetchQueue()
  }

  /** 跳转 */
  async function seek(position: number) {
    await apiSeek(position)
    localPosition.value = position
    await fetchNowplaying()
  }

  /** 音量（防抖发送，避免频繁请求） */
  let volTimer: ReturnType<typeof setTimeout> | null = null
  async function updateVolume(val: number) {
    volume.value = val
    // 防抖：拖动结束后 300ms 才发送
    if (volTimer) clearTimeout(volTimer)
    volTimer = setTimeout(async () => {
      try { await apiSetVolume(val) } catch { /* 静默 */ }
    }, 300)
  }

  /** 清空队列 */
  async function clear() {
    await apiClear()
    await fetchQueue()
  }

  /** 当前播放 */
  async function fetchNowplaying() {
    try {
      const np = await apiGetNowplaying()
      nowplaying.value = np
      volume.value = np.volume ?? 50
      playMode.value = np.playMode || 'seq'
      if (typeof np.position === 'number') localPosition.value = np.position
    } catch {
      // 静默
    }
  }

  /** 队列 */
  async function fetchQueue() {
    try {
      const res = await apiGetQueue()
      queue.value = (res.items || []) as Song[]
    } catch {
      queue.value = []
    }
  }

  /** 播放模式 */
  async function setMode(mode: string) {
    playMode.value = mode
    try { await apiSetMode(mode) } catch { /* 静默 */ }
    await fetchNowplaying()
  }

  return {
    searchResults,
    searching,
    searchKeyword,
    searchPlatform,
    nowplaying,
    queue,
    volume,
    playMode,
    localPosition,
    search,
    play,
    pause,
    resume,
    next,
    stop,
    seek,
    updateVolume,
    clear,
    setMode,
    fetchNowplaying,
    fetchQueue,
  }
})
