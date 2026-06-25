import { defineStore } from 'pinia'
import { ref, type Ref } from 'vue'
import { getStats, type StatsData, type OnlineUser } from '@/api/monitor'

/** 采样历史长度（最近 N 次轮询的真实样本） */
const HISTORY_LEN = 32

export const useMonitorStore = defineStore('monitor', () => {
  const stats = ref<StatsData | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const lastUpdate = ref<string>('--')

  /** 在线用户列表（按在线时长降序） */
  const onlineUsers = ref<OnlineUser[]>([])

  /** 游戏统计（按人数降序） */
  const gameStats = ref<{ name: string; count: number }[]>([])

  /** 真实采样历史：在线人数（最近 HISTORY_LEN 次轮询），供 sparkline 使用 */
  const onlineHistory = ref<number[]>([])

  /** 拉取最新数据 */
  async function fetchStats() {
    loading.value = true
    error.value = null

    try {
      const data = await getStats()
      stats.value = data
      lastUpdate.value = new Date().toLocaleTimeString('zh-CN')

      // 派生：在线用户
      onlineUsers.value = (data.online_list || []).sort(
        (a, b) => b.online_time - a.online_time,
      )

      // 派生：游戏统计
      gameStats.value = Object.entries(data.games || {})
        .map(([name, count]) => ({ name, count: Number(count) }))
        .sort((a, b) => b.count - a.count)

      // 真实采样：累积最近 HISTORY_LEN 个样本
      pushSample(onlineHistory, data.online_users ?? 0)
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : '获取数据失败'
    } finally {
      loading.value = false
    }
  }

  function pushSample(buf: Ref<number[]>, v: number) {
    buf.value.push(v)
    if (buf.value.length > HISTORY_LEN) buf.value.shift()
  }

  return {
    stats,
    loading,
    error,
    lastUpdate,
    onlineUsers,
    gameStats,
    onlineHistory,
    fetchStats,
  }
})
