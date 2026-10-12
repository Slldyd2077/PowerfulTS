import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const origin = process.env.MUSIC_TEST_APP_ORIGIN || 'http://127.0.0.1:18186'
const browser = await chromium.launch({ headless: true, ...(process.env.MUSIC_TEST_BROWSER ? { executablePath: process.env.MUSIC_TEST_BROWSER } : {}) })
try {
  const context = await browser.newContext({ viewport: { width: 1360, height: 1000 } })
  await context.addInitScript(() => localStorage.setItem('session_token', 'favorite-test'))
  const songs = [
    { id: 'same', platform: 'bilibili', name: '已收藏歌曲', artist: '测试歌手' },
    { id: 'new', platform: 'bilibili', name: '未收藏歌曲', artist: '测试歌手' },
  ]
  const playlists = new Map([
    [1, { name: '收藏一', songs: [songs[0]] }],
    [2, { name: '收藏二', songs: [songs[0]] }],
  ])
  let failFavoriteOnce = false
  let songReads = 0
  await context.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    let data = {}
    if (path === '/api/auth/get_session') data = { success: true, session_data: { ts_nickname: '测试账号', role: 'member', is_admin: false } }
    if (path === '/api/theme') data = { desktop: null, mobile: null, dim: 45, blur: 0 }
    if (path === '/api/music/bots') data = { bots: [{ id: 'abc-123', name: '测试 Bot', status: 'connected' }] }
    if (path === '/api/music/bots/my-shares') data = { shares: [] }
    if (path === '/api/music/auth/status') data = { loggedIn: true }
    if (path === '/api/music/my/playlists') data = { ok: true, data: [] }
    if (path === '/api/music/my/bilibili-popular') data = { ok: true, data: songs }
    if (path === '/api/music/search') {
      data = { results: url.searchParams.get('platform') === 'bilibili' ? songs : [{ ...songs[0], platform: 'qq', name: '同 ID 不同平台' }] }
    }
    if (path === '/api/music/nowplaying') data = { playing: false, volume: 50, position: 0, duration: 0 }
    if (path === '/api/music/queue') data = { items: [] }
    if (path === '/api/music/quality') data = { netease: 'standard' }
    if (path === '/api/music/bot-settings') data = { idleTimeoutMinutes: 0 }
    if (path === '/api/music/follow-setting') data = { enabled: false }
    if (path === '/api/ts-playlists') data = {
      playlists: [...playlists].map(([id, pl]) => ({ id, name: pl.name, songCount: pl.songs.length })),
      favorites: [...playlists].flatMap(([playlistId, pl]) => pl.songs.map((song) => ({ playlistId, platform: song.platform, songId: song.id }))),
    }
    const match = path.match(/^\/api\/ts-playlists\/(\d+)(\/songs)?$/)
    if (match) {
      const pid = Number(match[1])
      const pl = playlists.get(pid)
      if (request.method() === 'DELETE') {
        if (match[2]) pl.songs = pl.songs.filter((s) => !(s.platform === url.searchParams.get('platform') && s.id === url.searchParams.get('songId')))
        else playlists.delete(pid)
        data = { success: true }
      } else if (request.method() === 'POST') {
        if (failFavoriteOnce) {
          failFavoriteOnce = false
          return route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"测试收藏失败"}' })
        }
        const body = request.postDataJSON()
        pl.songs.push({ ...body, id: body.songId })
        data = { success: true, message: '已收藏' }
      } else {
        songReads++
        data = { songs: pl.songs.map((s) => ({ ...s, songId: s.id, originalName: s.name })) }
      }
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) })
  })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto(`${origin}/music`)
  const library = page.locator('.panel').filter({ has: page.getByRole('heading', { name: '我的音乐', exact: true }) })
  await library.getByRole('button', { name: 'B站', exact: true }).click()
  const row = (name, scope = page) => scope.locator('.song-item').filter({ has: page.locator('.song-name').filter({ hasText: name }) })
  const favorite = (name, scope) => row(name, scope).locator('button[aria-pressed]')
  await page.waitForFunction(() => document.querySelector('.song-item button[aria-pressed="true"]'))
  assert.equal(await favorite('已收藏歌曲', library).getAttribute('aria-pressed'), 'true')
  assert.equal(await favorite('未收藏歌曲', library).getAttribute('aria-pressed'), 'false')
  assert.equal(songReads, 0, 'favorites load without opening TS playlists or fetching full songs')
  assert.equal(await row('已收藏歌曲', library).locator('.song-actions').evaluate((el) => getComputedStyle(el).opacity), '1')

  const search = page.locator('.panel').filter({ has: page.getByRole('heading', { name: '点歌', exact: true }) })
  await search.getByRole('button', { name: 'B站', exact: true }).click()
  await page.getByRole('textbox', { name: '搜索歌曲' }).fill('歌曲')
  await page.getByRole('textbox', { name: '搜索歌曲' }).press('Enter')
  await favorite('已收藏歌曲', search).waitFor()
  assert.equal(await favorite('已收藏歌曲', search).getAttribute('aria-pressed'), 'true')

  // Both the path and its SVG box must be centered within the circular button.
  async function checkCenter(button) {
    const delta = await button.evaluate((el) => {
      const svg = el.querySelector('svg')
      const box = svg.querySelector('path').getBBox()
      const view = svg.viewBox.baseVal
      const outer = el.getBoundingClientRect()
      const inner = svg.getBoundingClientRect()
      return [box.x + box.width / 2 - view.width / 2, box.y + box.height / 2 - view.height / 2,
        inner.x + inner.width / 2 - outer.x - outer.width / 2, inner.y + inner.height / 2 - outer.y - outer.height / 2]
    })
    assert.ok(delta.every((d) => Math.abs(d) < 0.1), `heart center offset: ${delta}`)
  }
  await checkCenter(favorite('已收藏歌曲', library))
  await checkCenter(favorite('未收藏歌曲', search))

  await favorite('未收藏歌曲', search).click()
  failFavoriteOnce = true
  await page.locator('.dlg-btn.primary').click()
  await page.getByText('测试收藏失败', { exact: true }).waitFor()
  assert.equal(await favorite('未收藏歌曲', search).getAttribute('aria-pressed'), 'false')
  await page.locator('.dlg-btn.primary').click()
  await page.locator('.dlg-overlay').waitFor({ state: 'hidden' })
  assert.equal(await favorite('未收藏歌曲', search).getAttribute('aria-pressed'), 'true')
  assert.equal(await favorite('未收藏歌曲', library).getAttribute('aria-pressed'), 'true')
  await page.reload()
  await library.getByRole('button', { name: 'B站', exact: true }).click()
  await page.waitForFunction(() => [...document.querySelectorAll('.song-item button[aria-pressed="true"]')].length === 2)
  assert.equal(await favorite('未收藏歌曲', library).getAttribute('aria-pressed'), 'true')
  await search.getByRole('button', { name: 'QQ音乐', exact: true }).click()
  await page.getByRole('textbox', { name: '搜索歌曲' }).fill('歌曲')
  await page.getByRole('textbox', { name: '搜索歌曲' }).press('Enter')
  await favorite('同 ID 不同平台', search).waitFor()
  assert.equal(await favorite('同 ID 不同平台', search).getAttribute('aria-pressed'), 'false')

  await library.getByRole('button', { name: 'TS 歌单', exact: true }).click()
  const first = library.locator('.pl-item').filter({ hasText: '收藏一' })
  await first.locator('.pl-row').click()
  await first.locator('.song-row').filter({ hasText: '已收藏歌曲' }).getByTitle('移除', { exact: true }).click()
  await first.locator('.song-row').filter({ hasText: '已收藏歌曲' }).waitFor({ state: 'hidden' })
  await library.getByRole('button', { name: 'B站', exact: true }).click()
  assert.equal(await favorite('已收藏歌曲', library).getAttribute('aria-pressed'), 'true', 'other TS playlist still contains song')
  await library.getByRole('button', { name: 'TS 歌单', exact: true }).click()
  await library.locator('.pl-item').filter({ hasText: '收藏二' }).getByRole('button', { name: '删除', exact: true }).click()
  await page.locator('.el-message-box__btns .el-button--primary').click()
  await page.getByText('已删除', { exact: true }).waitFor()
  await library.getByRole('button', { name: 'B站', exact: true }).click()
  assert.equal(await favorite('已收藏歌曲', library).getAttribute('aria-pressed'), 'false', 'last membership removed by playlist deletion')
  await page.setViewportSize({ width: 390, height: 844 })
  await checkCenter(favorite('未收藏歌曲', library))
  await mkdir('../.tmp_music-favorites', { recursive: true })
  await library.screenshot({ path: '../.tmp_music-favorites/mobile.png' })
  assert.deepEqual(errors, [])
  console.log('PASS favorites: initial state, search/library sync, cross-platform identity, failed writes, reload, multiple playlists, deletion and desktop/mobile icon centering')
  await context.close()
} finally {
  await browser.close()
}
