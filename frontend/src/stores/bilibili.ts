import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  searchBili,
  playBili,
  cleanTitle,
  type BiliVideo,
} from '@/api/bilibili'

export const useBiliStore = defineStore('bilibili', () => {
  const results = ref<BiliVideo[]>([])
  const searching = ref(false)
  const keyword = ref('')
  /** 当前正在播放的 BV 号（用于 UI 高亮） */
  const playingBvid = ref<string | null>(null)
  const playingTitle = ref('')

  async function search(kw: string) {
    if (!kw.trim()) return
    searching.value = true
    keyword.value = kw
    try {
      const res = await searchBili(kw)
      results.value = res.results
    } catch {
      results.value = []
    } finally {
      searching.value = false
    }
  }

  async function play(video: BiliVideo) {
    await playBili(video.bvid)
    playingBvid.value = video.bvid
    playingTitle.value = cleanTitle(video.title)
  }

  return {
    results,
    searching,
    keyword,
    playingBvid,
    playingTitle,
    search,
    play,
  }
})
