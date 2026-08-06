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

// 刚切过去的频道。后端会催一轮 TS 轮询，但万一它超时（TS 慢 / 监控断线），
// 这一拍的快照还是旧的，直接采信就会把你「弹回」原频道。所以在服务端认同之前
// 先信任本地这次切换，最多信任 PENDING_TTL_MS —— 超时就说明真没切成功，该纠正。
const PENDING_TTL_MS = 8000
let pendingCid: number | null = null
let pendingUntil = 0

function adoptBotCid(serverCid: number | null, botIsOnline: boolean): void {
  // 通话身份已经不在服务器上（掉线 / 宽限期到点被收回）时，本地那个「刚切到哪」
  // 就没有意义了，别再拿它挡着服务端的判断。
  const expired = pendingCid !== null
    && (serverCid === pendingCid || Date.now() > pendingUntil)
  if (!botIsOnline || expired) {
    pendingCid = null
  }
  botCid.value = pendingCid ?? serverCid
}

/** 切频道成功后调用：立刻显示新频道，并保护它不被旧快照覆盖。 */
function markPendingChannel(cid: number): void {
  pendingCid = cid
  pendingUntil = Date.now() + PENDING_TTL_MS
  botCid.value = cid
}

/** 挂断/加入通话时清掉，避免拿上一次通话的频道去挡新数据。 */
function clearPendingChannel(): void {
  pendingCid = null
  pendingUntil = 0
}

function errorText(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: string } | undefined)?.detail
    if (detail) return detail
    if (!error.response) return '连不上 PowerfulTS 后端'
  }
  return error instanceof Error ? error.message : '无法获取频道列表'
}

async function refresh(fresh = false): Promise<void> {
  // 多个组件同时触发刷新（比如加入通话）时合并成一次请求。
  if (inFlight) return inFlight
  inFlight = (async () => {
    try {
      const data = await getVoiceChannels(fresh)
      channels.value = data.channels
      adoptBotCid(data.botCid, data.botOnline)
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
    markPendingChannel,
    clearPendingChannel,
  }
}
