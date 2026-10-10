import assert from 'node:assert/strict'
import { chromium } from 'playwright'

const browser = await chromium.launch({
  headless: true,
  ...(process.env.VOICE_TEST_BROWSER ? { executablePath: process.env.VOICE_TEST_BROWSER } : {}),
})
const origin = process.env.VOICE_TEST_APP_ORIGIN || 'http://127.0.0.1:18185'
try {
  const context = await browser.newContext({ viewport: { width: 1360, height: 1000 } })
  await context.addInitScript(() => { localStorage.setItem('session_token', 'music-loudness-test') })
  let supported = true
  let enabled = false
  let status = 'applied'
  const writes = []
  await context.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    let data = {}
    if (path === '/api/auth/get_session') data = { success: true, session_data: { ts_nickname: '响度测试', role: 'member', is_admin: false } }
    if (path === '/api/theme') data = { desktop: null, mobile: null, dim: 45, blur: 0 }
    if (path === '/api/music/bots') data = { bots: [{ id: 'music-test', name: '音乐机器人', nickname: '音乐机器人', status: 'running', playing: true, paused: false, connected: true, volume: 50, shared: false }] }
    if (path === '/api/music/bots/my-shares') data = { shares: [] }
    if (path === '/api/music/queue') data = { queue: [] }
    if (path === '/api/music/quality') data = { netease: 'standard' }
    if (path === '/api/music/bot-settings') {
      if (route.request().method() === 'PUT') {
        const body = route.request().postDataJSON()
        writes.push(body)
        enabled = body.loudnessNormalization.enabled
      }
      data = { idleTimeoutMinutes: 0, autoPauseOnEmpty: false, voiceDucking: { enabled: false, volumePercent: 30 }, loudnessNormalization: { supported, enabled, targetLufs: -18 } }
    }
    if (path === '/api/music/nowplaying') data = {
      playing: true, paused: false, title: '动态测试曲', artist: '测试', songId: 'track-1', platform: 'netease',
      duration: 180, position: 10, volume: 50, playMode: 'seq',
      loudnessNormalization: { state: status, gainDb: -9 },
    }
    if (path === '/api/music/follow-setting') data = { enabled: true }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) })
  })
  const page = await context.newPage()
  const errors = []
  page.on('console', (message) => { if (message.type() === 'warning' || message.type() === 'error') console.error(message.text()) })
  page.on('pageerror', (error) => { errors.push(error.message); console.error(error.message) })
  await page.goto(`${origin}/music`)
  await page.getByText('逐曲均衡已应用 · 整首固定 -9.0 dB', { exact: true }).waitFor()
  await page.getByRole('button', { name: /机器人行为/ }).click()
  const toggle = page.getByRole('switch', { name: '逐曲响度均衡', exact: true })
  await toggle.waitFor()
  assert.equal(await toggle.getAttribute('aria-checked'), 'false')
  await toggle.click()
  await page.getByText('已保存，从下一首歌起生效', { exact: true }).waitFor()
  assert.equal(await toggle.getAttribute('aria-checked'), 'true')
  assert.equal(writes.length, 1)
  assert.equal(writes[0].loudnessNormalization.enabled, true)
  await page.reload()
  await page.getByRole('button', { name: /机器人行为/ }).click()
  assert.equal(await toggle.getAttribute('aria-checked'), 'true')
  supported = false
  status = 'failed'
  await page.reload()
  await page.getByText('本首响度分析失败，按原始响度播放。', { exact: true }).waitFor()
  await page.getByRole('button', { name: /机器人行为/ }).click()
  assert.equal(await toggle.isDisabled(), true)
  await page.getByText('当前机器人引擎未确认支持，需要应用响度均衡引擎补丁并重建引擎。', { exact: true }).waitFor()
  assert.equal(writes.length, 1, 'unsupported engines cannot submit a fake enable')
  await page.setViewportSize({ width: 390, height: 844 })
  await toggle.scrollIntoViewIfNeeded()
  const bounds = await toggle.boundingBox()
  assert.ok(bounds && bounds.x >= 0 && bounds.x + bounds.width <= 390)
  assert.deepEqual(errors, [])
  console.log('PASS music UI: engine settings, next-track notice, fixed gain status, persistence, unsupported engine guard, failure status and mobile layout')
  await context.close()
} finally { await browser.close() }
