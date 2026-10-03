import { ref, onMounted, onUnmounted } from 'vue'
import { createPollingScheduler } from '@/services/polling-scheduler'

/**
 * 轮询 hook：定期执行异步函数
 * @param fn 要执行的异步函数
 * @param intervalMs 间隔毫秒（默认 5000）
 * @param immediate 是否立即执行一次（默认 true）
 */
export function usePolling(fn: () => Promise<void>, intervalMs: number = 5000, immediate = true) {
  const running = ref(false)
  function isAvailable() {
    return document.visibilityState !== 'hidden' && navigator.onLine !== false
  }
  const scheduler = createPollingScheduler({
    run: fn,
    intervalMs,
    immediate,
    onRunning: (value) => { running.value = value },
    onError: () => { console.warn('轮询请求失败，将在下次轮询时重试') },
  })
  function updateAvailability() {
    scheduler.setAvailable(isAvailable())
  }
  function start() {
    updateAvailability()
    scheduler.start()
  }
  onMounted(() => {
    document.addEventListener('visibilitychange', updateAvailability)
    window.addEventListener('online', updateAvailability)
    window.addEventListener('offline', updateAvailability)
    start()
  })
  onUnmounted(() => {
    scheduler.dispose()
    document.removeEventListener('visibilitychange', updateAvailability)
    window.removeEventListener('online', updateAvailability)
    window.removeEventListener('offline', updateAvailability)
  })
  return { running, start, stop: scheduler.stop }
}
