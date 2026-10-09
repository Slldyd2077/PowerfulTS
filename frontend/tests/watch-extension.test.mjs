import assert from 'node:assert/strict'
import { test } from 'node:test'
import vm from 'node:vm'
import { readFileSync } from 'node:fs'

const script = name => readFileSync(new URL(`../watch-extension/${name}`, import.meta.url), 'utf8')
function harness() {
  const context = vm.createContext({ URL })
  let connect
  context.chrome = { runtime: { onConnect: { addListener(fn) { connect = fn } }, onMessage: { addListener() {} } } }
  context.importScripts = name => vm.runInContext(script(name), context)
  vm.runInContext(script('background.js'), context)
  function port(name, id) {
    const messages = []
    let receive, closed
    const instance = { name, sender: { tab: { id } },
      postMessage(message) { messages.push(message) }, disconnect() { closed?.() },
      onMessage: { addListener(fn) { receive = fn } }, onDisconnect: { addListener(fn) { closed = fn } } }
    connect(instance)
    return { messages, send(message) { receive?.(message) }, close() { closed?.() } }
  }
  return { port, context }
}
test('identity preserves episode IDs, arbitrary video query IDs and hash routes', () => {
  const { context } = harness()
  const key = context.powerfulTSMediaKey
  assert.equal(key('https://www.bilibili.com/video/BV1?p=1&vd_source=abc'), key('https://www.bilibili.com/video/BV1/'))
  assert.notEqual(key('https://www.bilibili.com/video/BV1?p=2'), key('https://www.bilibili.com/video/BV1'))
  assert.notEqual(key('https://example.com/watch?v=a'), key('https://example.com/watch?v=b'))
  assert.notEqual(key('https://example.com/#/video/a'), key('https://example.com/#/video/b'))
})
test('ready and pause reports reach viewer dashboard; different video cannot report ready', () => {
  const { port } = harness()
  const dashboard = port('watch-dashboard', 1), video = port('watch-video', 2)
  dashboard.send({ type: 'state', mode: 'viewer', url: 'https://v.qq.com/x/cover/show/episode.html' })
  video.send({ type: 'video', url: 'https://v.qq.com/x/cover/show/episode.html', ready: true, userPaused: true })
  assert.ok(dashboard.messages.some(message => message.type === 'video' && message.userPaused))
  const before = dashboard.messages.filter(message => message.type === 'video').length
  video.send({ type: 'video', url: 'https://v.qq.com/x/cover/show/other.html', ready: true })
  assert.equal(dashboard.messages.filter(message => message.type === 'video').length, before)
})
test('rebinding replaces previous tab and closing dashboard leaves video idle', () => {
  const { port } = harness()
  const dashboard = port('watch-dashboard', 1), oldVideo = port('watch-video', 2), video = port('watch-video', 3)
  assert.equal(oldVideo.messages.at(-1).type, 'detached')
  const before = dashboard.messages.length
  oldVideo.send({ type: 'video', url: 'https://example.com' })
  assert.equal(dashboard.messages.length, before)
  dashboard.close()
  assert.equal(video.messages.at(-1).mode, 'idle')
})
