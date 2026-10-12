import assert from 'node:assert/strict'
import { chromium } from 'playwright'
const browser = await chromium.launch({ headless: true, executablePath: process.env.VOICE_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' })
try {
  const context = await browser.newContext()
  await context.addInitScript(() => localStorage.setItem('session_token', 'test-only'))
  let admin = true
  const writes = []
  await context.route('**/api/**', async route => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    let body = {}
    if (path === '/api/auth/get_session') body = { success: true, session_data: { ts_nickname: '管理测试', role: admin ? 'admin' : 'member', is_admin: admin } }
    if (path === '/api/theme') body = { desktop: null, mobile: null, dim: 45, blur: 0 }
    if (path === '/api/music/voice/channels') body = { channels: [], botOnline: false, monitorRunning: true }
    if (path === '/api/admin/channels' && req.method() === 'GET') body = { channels: [{ cid: 1, pid: 0, name: '初始', isDefault: true }, { cid: 2, pid: 0, name: '朋友频道' }], members: [{ clid: 9, cid: 1, nickname: '好友' }] }
    if (path === '/api/admin/channels/bots') body = { bots: [{ id: 'friends-music', name: '朋友机器人', status: 'connected', ownerNickname: '好友' }] }
    if (['POST', 'PUT', 'DELETE'].includes(req.method()) && path.startsWith('/api/admin/channels')) { writes.push({ path, body: req.postDataJSON() }); body = { ok: true, detail: '操作成功' } }
    await route.fulfill({ json: body })
  })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  await page.goto(`${process.env.VOICE_TEST_BASE_URL || 'http://127.0.0.1:18185'}/voice`)
  const panel = page.locator('.channel-admin')
  await panel.getByText('朋友机器人', { exact: false }).count()
  await panel.getByRole('combobox', { name: '管理目标频道' }).press('ArrowDown')
  await page.getByRole('option', { name: '朋友频道 · #2', exact: true }).click()
  await panel.getByRole('combobox', { name: '管理音乐机器人' }).press('ArrowDown')
  await page.getByRole('option', { name: '朋友机器人 · 好友 · 在线', exact: true }).click()
  await panel.getByRole('button', { name: '立即移动机器人', exact: true }).click()
  await panel.getByRole('button', { name: '保存默认频道', exact: true }).click()
  assert.deepEqual(writes.slice(0, 2).map(x => x.body), [{ cid: 2, saveDefault: false }, { cid: 2, saveDefault: true }])
  await panel.getByRole('combobox', { name: '管理在线成员' }).press('ArrowDown')
  await page.getByRole('option', { name: '好友 · 初始', exact: true }).click()
  await panel.getByRole('button', { name: '移动成员到目标频道', exact: true }).click()
  await panel.getByRole('button', { name: '移除成员', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: '移除', exact: true }).click()
  assert.equal(writes.some(x => x.path.endsWith('/members/9/move')), true)
  assert.equal(writes.some(x => x.path.endsWith('/members/9/kick')), true)
  await panel.getByRole('button', { name: '新建频道', exact: true }).click()
  await page.getByRole('dialog').getByLabel('频道名称', { exact: true }).fill('新频道')
  await page.getByRole('dialog').getByRole('button', { name: '保存', exact: true }).click()
  await page.getByRole('dialog').waitFor({ state: 'hidden' })
  assert.equal(writes.at(-1).body.name, '新频道')
  assert.equal(await panel.getByRole('button', { name: '删除', exact: true }).first().isDisabled(), true)
  await page.setViewportSize({ width: 390, height: 844 })
  await panel.scrollIntoViewIfNeeded()
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
  await page.waitForTimeout(3200)
  if (process.env.VOICE_TEST_SCREENSHOT) await page.screenshot({ path: process.env.VOICE_TEST_SCREENSHOT })
  admin = false
  await page.reload()
  await page.locator('.channel-browser').waitFor()
  assert.equal(await page.locator('.channel-admin').count(), 0)
  assert.deepEqual(errors, [])
  console.log('PASS admin channel UI, friend music move/default save, create, default delete guard, mobile bounds and member-hidden management')
} finally { await browser.close() }
