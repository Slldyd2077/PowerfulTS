import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getStats, type StatsData, type OnlineUser } from '@/api/monitor'

export const useMonitorStore = defineStore('monitor', () => {
  const stats = ref<StatsData | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const lastUpdate = ref<string>('--')

  /** 在线用户列表（按在线时长降序） */
  const onlineUsers = ref<OnlineUser[]>([])

  /** 游戏统计（按人数降序） */
  const gameStats = ref<{ name: string; count: number }[]>([])

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
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : '获取数据失败'
    } finally {
      loading.value = false
    }
  }

  return {
    stats,
    loading,
    error,
    lastUpdate,
    onlineUsers,
    gameStats,
    fetchStats,
  }
})
