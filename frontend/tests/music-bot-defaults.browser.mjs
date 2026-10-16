import assert from 'node:assert/strict'
import { chromium } from 'playwright'

const browser = await chromium.launch({ headless: true,
  ...(process.env.VOICE_TEST_BROWSER ? { executablePath: process.env.VOICE_TEST_BROWSER } : {}),
})
try {
  const context = await browser.newContext()
  await context.addInitScript(() => localStorage.setItem('session_token', 'bot-defaults-test'))
  let host = 'saved-ts.example.com'
  let failDefaults = false
  const writes = []
  await context.route('**/api/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    let data = {}
    if (path === '/api/auth/get_session') data = { success: true, session_data: { ts_nickname: '测试账号', role: 'member', is_admin: false } }
    if (path === '/api/theme') data = { desktop: null, mobile: null, dim: 45, blur: 0 }
    if (path === '/api/music/bots') {
      data = { bots: [] }
      if (request.method() === 'POST') {
        writes.push(request.postDataJSON())
        data = { id: 'abc-123', name: '测试 Bot', status: 'disconnected' }
      }
    }
    if (path === '/api/music/bots/defaults') {
      if (failDefaults) return route.fulfill({ status: 503, body: '{}' })
      data = { serverAddress: host, serverPort: 9987 }
    }
    if (path === '/api/music/bots/my-shares') data = { shares: [] }
    if (path === '/api/music/queue') data = { queue: [] }
    if (path === '/api/music/quality') data = { netease: 'standard' }
    if (path === '/api/music/bot-settings') data = { idleTimeoutMinutes: 0 }
    if (path === '/api/music/nowplaying') data = { playing: false, volume: 50 }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) })
  })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(`${process.env.VOICE_TEST_APP_ORIGIN || 'http://127.0.0.1:18192'}/music`)
  const open = () => page.getByRole('button', { name: /新建.*Bot/ }).click()
  const address = page.locator('input[name="music-bot-host"]')
  await open()
  await address.waitFor({ state: 'attached' })
  assert.equal(await address.inputValue(), host)
  assert.equal(await page.locator('input[name="music-bot-udp"]').inputValue(), '9987')
  await page.locator('.create-form').getByRole('button', { name: '取消', exact: true }).click()
  host = 'changed-ts.example.com'
  await open()
  await address.waitFor({ state: 'attached' })
  assert.equal(await address.inputValue(), host, 'reopening reads the latest saved setting')
  await page.locator('.create-form summary').click()
  await address.fill('manual-ts.example.com')
  await page.locator('input[name="music-bot-label"]').fill('测试 Bot')
  await page.locator('.create-form').getByRole('button', { name: '创建', exact: true }).click()
  await page.locator('.create-form').waitFor({ state: 'detached' })
  assert.equal(writes.length, 1)
  assert.equal(writes[0].serverAddress, 'manual-ts.example.com')
  assert.equal(writes[0].serverPort, 9987)
  failDefaults = true
  await open()
  await page.getByText('读取 TS 服务器默认设置失败，请重试').waitFor()
  assert.equal(await page.locator('.create-form').count(), 0)
  failDefaults = false
  await open()
  await address.waitFor({ state: 'attached' })
  assert.equal(await address.inputValue(), host)
  assert.deepEqual(errors, [])
  console.log('PASS: saved TS host, fresh defaults, manual override, voice port, failure and retry')
} finally {
  await browser.close()
}
