(() => {
  if (globalThis.powerfulTSWatchVideo) globalThis.powerfulTSWatchVideo()
  const port = chrome.runtime.connect({ name: 'watch-video' })
  let closed = false
  let state = { mode: 'idle' }
  let selected = null
  let applying = false
  let buffered = false
  let timer
  let lastStateAt = 0
  let applyingUntil = 0
  let autoplayBlocked = false
  const cleanups = []
  const mediaKey = globalThis.powerfulTSMediaKey
  function videos(root = document) {
    const result = [...root.querySelectorAll('video')]
    for (const element of root.querySelectorAll('*')) if (element.shadowRoot) result.push(...videos(element.shadowRoot))
    return result
  }
  function report(event) {
    if (!selected) return
    if (!Number.isFinite(selected.currentTime)) return
    if (event?.type === 'play') autoplayBlocked = false
    const controlled = applying || Date.now() < applyingUntil
    const changedPlayback = event && ['play', 'pause', 'ended'].includes(event.type) && !controlled && !state.waiting
    port.postMessage({ type: 'video', url: location.href, position: selected.currentTime,
      ready: selected.readyState >= 3 && !buffered && !selected.seeking && !autoplayBlocked,
      paused: changedPlayback ? selected.paused || selected.ended : state.requestedPaused ?? true,
      userPaused: state.mode === 'viewer' && state.allowMemberPause && !state.paused && event?.type === 'pause',
      rate: selected.playbackRate })
  }
  function detect() {
    if (selected?.isConnected) return
    cleanups.splice(0).forEach(cleanup => cleanup())
    selected = videos().filter(item => item.getBoundingClientRect().width > 0)
      .sort((a, b) => b.clientWidth * b.clientHeight - a.clientWidth * a.clientHeight)[0] || null
    buffered = false
    if (!selected) { port.postMessage({ type: 'status', message: '未找到 HTML5 视频，请先打开并播放视频；内嵌或专用播放器可能不支持。' }); return }
    for (const event of ['play', 'pause', 'seeked', 'ratechange', 'playing', 'waiting', 'ended', 'canplay']) {
      const handler = browserEvent => {
        if (event === 'waiting') buffered = true
        if (event === 'playing' || event === 'canplay') buffered = false
        report(browserEvent)
      }
      selected.addEventListener(event, handler)
      const element = selected
      cleanups.push(() => element.removeEventListener(event, handler))
    }
    report()
  }
  async function apply() {
    detect()
    if (!selected || !['viewer', 'host'].includes(state.mode) || selected.readyState < 1 || applying) return
    if (Date.now() - lastStateAt > 5000) return
    if (mediaKey(location.href) !== mediaKey(state.url)) {
      port.postMessage({ type: 'status', message: '视频页面与房间链接不同，请打开房间链接并重新连接。' })
      return
    }
    try {
      const elapsed = state.paused ? 0 : Math.max(0, Date.now() - lastStateAt) / 1000
      let position = state.position + elapsed * state.rate
      if (Number.isFinite(selected.duration)) position = Math.min(position, selected.duration)
      const seek = state.mode === 'viewer' && Math.abs(selected.currentTime - position) > 0.8
      if (!seek && selected.playbackRate === state.rate && selected.paused === state.paused) return
      applying = true
      applyingUntil = Date.now() + 250
      if (seek) selected.currentTime = position
      if (selected.playbackRate !== state.rate) selected.playbackRate = state.rate
      if (state.paused) selected.pause()
      else if (selected.paused) await selected.play()
      port.postMessage({ type: 'status', message: '正在跟随房间播放进度。' })
    } catch {
      autoplayBlocked = true
      port.postMessage({ type: 'status', message: '请在视频页面点击播放；若正在播放广告，请等正片开始再连接。' })
    } finally { if (applying) applyingUntil = Date.now() + 250; applying = false }
  }
  function cleanup() {
    if (closed) return
    closed = true
    clearInterval(timer)
    cleanups.splice(0).forEach(fn => fn())
    port.disconnect()
    globalThis.powerfulTSWatchVideo = null
  }
  globalThis.powerfulTSWatchVideo = cleanup
  port.onMessage.addListener(message => {
    if (message.type === 'detached') return cleanup()
    if (!['idle', 'host', 'viewer'].includes(message.mode)) return
    state = message
    lastStateAt = Date.now()
    void apply()
  })
  port.onDisconnect.addListener(cleanup)
  timer = setInterval(() => { detect(); report(); void apply() }, 1000)
  detect()
})()
