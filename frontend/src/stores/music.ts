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
  type Song,
} from '@/api/music'

export const useMusicStore = defineStore('music', () => {
  const searchResults = ref<Song[]>([])
  const searching = ref(false)
  const playing = ref(false)
  const volume = ref(50)
  const searchKeyword = ref('')

  /** 搜索歌曲 */
  async function search(keyword: string) {
    if (!keyword.trim()) return
    searching.value = true
    searchKeyword.value = keyword
    try {
      const res = await apiSearch(keyword)
      searchResults.value = res.results || []
    } catch {
      searchResults.value = []
    } finally {
      searching.value = false
    }
  }

  /** 播放指定歌曲 */
  async function play(songId: string) {
    await apiPlay(songId)
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
