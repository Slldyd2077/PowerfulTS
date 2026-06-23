import { ref, onMounted, onUnmounted } from 'vue'

/**
 * 轮询 hook：定期执行异步函数
 * @param fn 要执行的异步函数
 * @param intervalMs 间隔毫秒（默认 5000）
 * @param immediate 是否立即执行一次（默认 true）
 */
export function usePolling(fn: () => Promise<void>, intervalMs: number = 5000, immediate = true) {
  const timer = ref<ReturnType<typeof setInterval> | null>(null)
  const running = ref(false)

  function start() {
    stop()
    if (immediate) {
      running.value = true
      fn().finally(() => { running.value = false })
    }
    timer.value = setInterval(() => {
      running.value = true
      fn().finally(() => { running.value = false })
    }, intervalMs)
  }

  function stop() {
    if (timer.value) {
      clearInterval(timer.value)
      timer.value = null
    }
  }

  onMounted(start)
  onUnmounted(stop)

  return { running, start, stop }
}
