interface PollingOptions {
  run: () => Promise<void>
  intervalMs: number
  immediate?: boolean
  available?: boolean
  onRunning?: (running: boolean) => void
  onError?: () => void
  setTimer?: (callback: () => void, delay: number) => () => void
}

/** Schedules the next poll after completion; pausing cannot cancel an active request. */
export function createPollingScheduler(options: PollingOptions) {
  if (!Number.isFinite(options.intervalMs) || options.intervalMs <= 0) {
    throw new RangeError('Polling interval must be finite and greater than zero')
  }

  const setTimer = options.setTimer ?? ((callback, delay) => {
    const timer = setTimeout(callback, delay)
    return () => clearTimeout(timer)
  })
  let cancelTimer: (() => void) | undefined
  let enabled = false
  let disposed = false
  let available = options.available ?? true
  let running = false
  let refreshPending = false

  function clearTimer() {
    cancelTimer?.()
    cancelTimer = undefined
  }

  function schedule() {
    cancelTimer = setTimer(() => {
      cancelTimer = undefined
      void poll()
    }, options.intervalMs)
  }

  async function poll() {
    if (!enabled || disposed || !available || running) return
    clearTimer()
    refreshPending = false
    running = true
    options.onRunning?.(true)
    try {
      await options.run()
    } catch {
      options.onError?.()
    } finally {
      running = false
      options.onRunning?.(false)
      if (enabled && !disposed && available) {
        if (refreshPending) void poll()
        else schedule()
      }
    }
  }

  function refresh() {
    if (running) refreshPending = true
    else void poll()
  }

  function start() {
    if (disposed) return
    enabled = true
    clearTimer()
    refreshPending = false
    if (!available) return
    if (options.immediate ?? true) refresh()
    else if (!running) schedule()
  }

  function stop() {
    enabled = false
    refreshPending = false
    clearTimer()
  }

  function setAvailable(value: boolean) {
    if (disposed || available === value) return
    available = value
    clearTimer()
    refreshPending = false
    if (enabled && available) refresh()
  }

  function dispose() {
    disposed = true
    stop()
  }

  return { start, stop, setAvailable, dispose }
}
