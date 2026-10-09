importScripts('identity.js')
const mediaKey = globalThis.powerfulTSMediaKey
let dashboard = null
let video = null
let state = { mode: 'idle' }

function post(port, message) {
  if (!port) return
  try { port.postMessage(message) } catch { /* A closed port is removed by onDisconnect. */ }
}
function status(message) { post(dashboard, { type: 'status', message }) }

chrome.runtime.onConnect.addListener(port => {
  if (!port.sender?.tab?.id) return port.disconnect()
  if (port.name === 'watch-dashboard') {
    if (dashboard && dashboard !== port) post(dashboard, { type: 'detached' })
    dashboard = port
    state = { mode: 'idle' }
    post(video, state)
    status(video ? '视频页已连接，请发起或加入同步观看。' : '请在视频标签页点击扩展的「连接视频页」。')
    port.onMessage.addListener(message => {
      if (port !== dashboard || message.type !== 'state') return
      if (!['idle', 'host', 'viewer'].includes(message.mode)) return
      state = message
      post(video, state)
      status(video ? '视频页已连接。' : '请连接视频页。')
    })
  } else if (port.name === 'watch-video') {
    if (video && video !== port) post(video, { type: 'detached' })
    video = port
    post(video, state)
    status('视频页已连接。')
    port.onMessage.addListener(message => {
      if (port !== video) return
      if (message.type === 'status') return status(message.message)
      if (message.type !== 'video') return
      if (state.mode !== 'idle' && mediaKey(message.url) !== mediaKey(state.url)) {
        status('所连接的视频页与房间视频不同，请打开房间链接并重新连接视频页。')
        return
      }
      post(dashboard, message)
    })
  } else return port.disconnect()
  port.onDisconnect.addListener(() => {
    if (dashboard === port) { dashboard = null; state = { mode: 'idle' }; post(video, state) }
    if (video === port) { video = null; status('视频页已断开，请重新连接。') }
  })
})
chrome.runtime.onMessage.addListener((message, sender) => {
  if (message.type !== 'disconnect' || sender.tab) return
  post(dashboard, { type: 'detached' })
  post(video, { type: 'detached' })
  dashboard = null
  video = null
  state = { mode: 'idle' }
})
