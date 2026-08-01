import { computed, onBeforeUnmount, ref } from 'vue'
import axios from 'axios'
import { getVoiceChannels, type VoiceChannel } from '@/api/voice'

const REFRESH_MS = 5000

// 模块级单例：频道浏览器和每人音量面板都要这份数据，各自轮询会白白翻倍请求，
// 而且两边看到的「当前频道」还可能差一拍。
const channels = ref<VoiceChannel[]>([])
const botCid = ref<number | null>(null)
const botOnline = ref(false)
const monitorRunning = ref(true)
const loading = ref(true)
const loadError = ref('')

let timer: number | null = null
let subscribers = 0
let inFlight: Promise<void> | null = null

function errorText(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: string } | undefined)?.detail
    if (detail) return detail
    if (!error.response) return '连不上 PowerfulTS 后端'
  }
  return error instanceof Error ? error.message : '无法获取频道列表'
}

async function refresh(): Promise<void> {
  // 多个组件同时触发刷新（比如加入通话）时合并成一次请求。
  if (inFlight) return inFlight
  inFlight = (async () => {
    try {
      const data = await getVoiceChannels()
      channels.value = data.channels
      botCid.value = data.botCid
      botOnline.value = data.botOnline
      monitorRunning.value = data.monitorRunning
      loadError.value = ''
    } catch (error) {
      loadError.value = errorText(error)
    } finally {
      loading.value = false
      inFlight = null
    }
  })()
  return inFlight
}

/** 当前所在频道，以及频道里的人（不含你自己的通话身份）。 */
const currentChannel = computed(
  () => channels.value.find((c) => c.cid === botCid.value) || null,
)
const roommates = computed(
  () => (currentChannel.value?.clients ?? []).filter((c) => !c.isBot),
)

export function useVoiceChannels() {
  subscribers += 1
  if (timer === null) {
    void refresh()
    timer = window.setInterval(() => void refresh(), REFRESH_MS)
  }

  onBeforeUnmount(() => {
    subscribers -= 1
    if (subscribers <= 0 && timer !== null) {
      window.clearInterval(timer)
      timer = null
      subscribers = 0
    }
  })

  return {
    channels,
    botCid,
    botOnline,
    monitorRunning,
    loading,
    loadError,
    currentChannel,
    roommates,
    refresh,
  }
}
