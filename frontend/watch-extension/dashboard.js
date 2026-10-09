(() => {
  if (!document.querySelector('.watch-panel')) throw new Error('请先打开 PowerfulTS 网页通话页')
  if (globalThis.powerfulTSWatchDashboard) {
    globalThis.powerfulTSWatchDashboard()
  }
  const port = chrome.runtime.connect({ name: 'watch-dashboard' })
  let closed = false
  const sendToPage = message => window.postMessage({ ...message, channel: 'powerfults-watch', direction: 'from-extension' }, window.location.origin)
  const listener = event => {
    if (event.source !== window || event.origin !== window.location.origin) return
    const message = event.data
    if (message?.channel === 'powerfults-watch' && message.direction === 'to-extension' && message.type === 'state') {
      port.postMessage(message)
    }
  }
  function cleanup() {
    if (closed) return
    closed = true
    window.removeEventListener('message', listener)
    port.disconnect()
    globalThis.powerfulTSWatchDashboard = null
  }
  globalThis.powerfulTSWatchDashboard = cleanup
  window.addEventListener('message', listener)
  port.onMessage.addListener(message => {
    if (message.type === 'detached') cleanup()
    else sendToPage(message)
  })
  port.onDisconnect.addListener(cleanup)
  sendToPage({ type: 'status', message: '通话页已连接，请连接视频页。' })
})()
