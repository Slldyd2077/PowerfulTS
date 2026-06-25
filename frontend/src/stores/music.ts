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
  // 默认网易云：原生接入（后端调 :3000），不依赖 S-QC-Bot 透传
  const source = ref<MusicSource>('netease')

  /** 搜索歌曲（按当前音源） */
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

  /** 播放指定歌曲（按当前音源） */
  async function play(songId: string) {
    if (source.value === 'netease') await apiPlayNetease(songId)
    else await apiPlay(songId)
    playing.value = true
  }

  /** 暂停/恢复 */
  async function pause() {
    await apiPause()
    playing.value = !playing.value
  }

  /** 跳过当前 */
  async function skip() {
    await apiSkip()
  }

  /** 停止播放 */
  async function stop() {
    await apiStop()
    playing.value = false
  }

  /** 获取音量 */
  async function fetchVolume() {
    try {
      volume.value = await apiGetVolume()
    } catch {
      // 静默
    }
  }

  /** 设置音量 */
  async function updateVolume(val: number) {
    volume.value = val
    await apiSetVolume(val)
  }

  /** 呼叫强基计划 */
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
    search,
    play,
    pause,
    skip,
    stop,
    fetchVolume,
    updateVolume,
    callRadio,
  }
})
