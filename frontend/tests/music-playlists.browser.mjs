import assert from 'node:assert/strict'
import { chromium } from 'playwright'

const browser = await chromium.launch({ headless: true, ...(process.env.MUSIC_TEST_BROWSER ? { executablePath: process.env.MUSIC_TEST_BROWSER } : {}) })
const origin = process.env.MUSIC_TEST_APP_ORIGIN || 'http://127.0.0.1:18186'
try {
  const context = await browser.newContext({ viewport: { width: 1360, height: 1000 } })
  await context.addInitScript(() => { localStorage.setItem('session_token', 'playlist-test') })
  const songs = Array.from({ length: 123 }, (_, i) => ({ id: String(i), name: `歌曲 ${i}`, artist: '测试歌手' }))
  songs[122].id = 'b3a52a7a958bf0aed0ebfba2e9a818b7|32100648|966846'
  const favorites = new Map()
  const queueWrites = []
  const favoriteWrites = []
  const botWrites = []
  const playWrites = []
  const coverWrites = []
  let activeCovers = 0
  let maxActiveCovers = 0
  const queue = []
  let failImportOnce = false
  let failQueueOnce = false
  let importCall = 0
  let queueCall = 0
  const bots = ['abc-123', 'abc-456'].map((id, i) => ({ id, name: `音乐机器人${i + 1}`, status: 'connected', shared: false }))
  await context.route('**/covers/**', async (route) => {
    if (route.request().url().endsWith('/broken.png')) return route.fulfill({ status: 404, body: '' })
    await route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64') })
  })
  await context.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    let data = {}
    if (path === '/api/auth/get_session') data = { success: true, session_data: { ts_nickname: '测试账号', role: 'member', is_admin: false } }
    if (path === '/api/theme') data = { desktop: null, mobile: null, dim: 45, blur: 0 }
    if (path === '/api/music/bots') {
      if (request.method() === 'POST') {
        const body = request.postDataJSON()
        botWrites.push(body)
        data = { id: 'abc-789', name: body.name, status: 'offline' }
        bots.push(data)
      } else data = { bots }
    }
    if (path === '/api/music/bots/my-shares') data = { shares: [] }
    if (path === '/api/music/auth/status') data = { loggedIn: true }
    if (path === '/api/music/my/playlists') data = { ok: true, data: [
      { id: 'playlist-1', name: '完整歌单', songCount: songs.length },
      { id: 'configured', name: '自定义封面歌单', songCount: 10, coverUrl: '/covers/custom.png' },
      { id: 'broken', name: '封面失效歌单', songCount: 10, coverUrl: '/covers/broken.png' },
      { id: 'empty', name: '空歌单', songCount: 0 },
    ] }
    if (path.endsWith('/cover')) {
      const platform = url.searchParams.get('platform')
      coverWrites.push({ path, platform, songsOnly: url.searchParams.get('songsOnly') })
      activeCovers++
      maxActiveCovers = Math.max(maxActiveCovers, activeCovers)
      await new Promise((resolve) => setTimeout(resolve, 80))
      activeCovers--
      data = { coverUrl: '', fallbackCoverUrl: `/covers/${platform}-latest.png` }
    }
    if (path === '/api/music/my/playlist/playlist-1/songs') {
      data = { ok: true, data: songs }
      await new Promise((resolve) => setTimeout(resolve, 100))
    }
    if (path === '/api/music/my/enqueue') {
      queueCall++
      const body = request.postDataJSON()
      queueWrites.push({ botId: url.searchParams.get('botId'), ...body })
      await new Promise((resolve) => setTimeout(resolve, 80))
      if (failQueueOnce && queueCall === 2) {
        failQueueOnce = false
        return route.fulfill({ status: 502, contentType: 'application/json', body: '{"detail":"test upstream unavailable"}' })
      }
      queue.push(...body.songs)
      data = { ok: true, enqueued: body.songs.length, failed: 0 }
    }
    if (path === '/api/music/queue') data = { items: queue }
    if (path === '/api/music/play') {
      playWrites.push({ ...request.postDataJSON(), botId: url.searchParams.get('botId') })
      data = { success: true }
    }
    if (path === '/api/music/nowplaying') data = { playing: false, volume: 50, position: 0, duration: 0 }
    if (path === '/api/music/quality') data = { netease: 'standard' }
    if (path === '/api/music/bot-settings') data = { idleTimeoutMinutes: 0 }
    if (path === '/api/music/follow-setting') data = { enabled: false }
    if (path === '/api/ts-playlists') data = { playlists: [{ id: 1, name: '目标歌单', songCount: favorites.size, coverUrl: '/covers/ts-latest.png' }] }
    if (path === '/api/ts-playlists/1/songs/batch') {
      importCall++
      const batch = request.postDataJSON().songs
      favoriteWrites.push(batch)
      await new Promise((resolve) => setTimeout(resolve, 120))
      if (failImportOnce && importCall === 2) {
        failImportOnce = false
        return route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"test write failure"}' })
      }
      let added = 0
      for (const song of batch) {
        const key = `${song.platform}:${song.songId}`
        if (!favorites.has(key)) { favorites.set(key, song); added++ }
      }
      data = { added, skipped: batch.length - added, failed: 0 }
    }
    if (path === '/api/ts-playlists/1/songs') data = { songs: [...favorites.values()].map((s) => ({ ...s, id: s.songId, originalName: s.name })) }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) })
  })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto(`${origin}/music`)
  const library = page.locator('.panel').filter({ has: page.getByRole('heading', { name: '我的音乐', exact: true }) })
  for (const [label, platform] of [['网易云', 'netease'], ['QQ音乐', 'qq'], ['B站', 'bilibili'], ['酷狗', 'kugou']]) {
    await library.getByRole('button', { name: label, exact: true }).click()
    await page.waitForFunction((src) => document.querySelector('img[alt="完整歌单"]')?.getAttribute('src') === src, `/covers/${platform}-latest.png`)
    assert.equal(await library.getByAltText('自定义封面歌单').getAttribute('src'), '/covers/custom.png')
    await page.waitForFunction((src) => document.querySelector('img[alt="封面失效歌单"]')?.getAttribute('src') === src, `/covers/${platform}-latest.png`)
    assert.equal(await library.locator('.playlist-item').filter({ hasText: '空歌单' }).locator('img').count(), 0)
  }
  assert.ok(maxActiveCovers <= 2)
  assert.ok(!coverWrites.some((write) => write.path.includes('/configured/') || write.path.includes('/empty/')))
  assert.ok(coverWrites.some((write) => write.path.includes('/broken/') && write.songsOnly === 'true'))
  await library.getByRole('button', { name: '酷狗', exact: true }).click()
  const playlist = library.locator('.playlist-item').filter({ hasText: '完整歌单' })
  const favorite = playlist.getByTitle('整单收藏到 TS 歌单', { exact: true })
  const enqueue = playlist.getByTitle('整单加入队列', { exact: true })
  await favorite.waitFor()

  // A failure after the first 50 saves partial work, and retry skips duplicates.
  failImportOnce = true
  await favorite.click()
  await page.locator('.dlg-btn.primary').click()
  await page.getByText(/收藏中断，已处理 50\/123 首/).waitFor()
  assert.equal(favorites.size, 50)
  await page.locator('.dlg-btn.primary').click()
  await page.getByText('已收藏 73 首，跳过 50 首重复曲目', { exact: true }).waitFor()
  assert.equal(favorites.size, 123)
  assert.ok(favoriteWrites.every((batch) => batch.length <= 50))
  assert.ok([...favorites.values()].every((song) => song.platform === 'kugou'))
  assert.ok(favorites.has(`kugou:${songs[122].id}`))

  await enqueue.click()
  await page.waitForFunction(() => Number(document.querySelector('.queue-progress progress')?.value) >= 4)
  const interim = await page.locator('.queue-progress progress').getAttribute('value')
  assert.ok(Number(interim) > 0 && Number(interim) < 123)
  assert.equal(await enqueue.isDisabled(), true)
  // Switching the visible Bot cannot redirect a running import.
  await page.locator('.bot-trigger').click()
  await page.locator('.bot-option').filter({ hasText: '音乐机器人2' }).click()
  await page.getByText('已加入 123 首到队列', { exact: true }).waitFor()
  assert.equal(queue.length, 123)
  assert.ok(queueWrites.every((write) => write.botId === 'abc-123' && write.songs.length <= 4))

  // A transport failure stops remaining requests and keeps visible progress.
  queueCall = 0
  failQueueOnce = true
  const previousWrites = queueWrites.length
  await enqueue.click()
  await page.getByText(/处理已暂停（4\/123）/).waitFor()
  assert.equal(queueWrites.length - previousWrites, 2)

  await library.getByRole('button', { name: 'TS 歌单', exact: true }).click()
  await page.getByAltText('目标歌单', { exact: true }).waitFor()
  assert.equal(await page.getByAltText('目标歌单', { exact: true }).getAttribute('src'), '/covers/ts-latest.png')
  await page.getByRole('button', { name: '▶ 播放', exact: true }).click()
  await page.getByText('已加入 123 首', { exact: true }).waitFor()
  assert.equal(playWrites.length, 1)
  assert.equal(playWrites[0].platform, 'kugou')
  assert.equal(playWrites[0].botId, 'abc-456')

  await page.getByRole('button', { name: '+ 新建 Bot', exact: true }).click()
  const form = page.locator('form.create-form').first()
  assert.equal(await form.getAttribute('autocomplete'), 'off')
  assert.equal(await form.locator('[name="music-bot-host"]').isVisible(), false)
  assert.equal(await form.locator('[name="music-bot-host"]').inputValue(), '127.0.0.1')
  assert.equal(await form.locator('[name="music-bot-channel"]').inputValue(), '')
  assert.equal(await form.locator('[name="music-bot-channel-secret"]').inputValue(), '')
  assert.equal(await form.locator('input').count(), 6)
  await form.locator('[name="music-bot-label"]').fill('新音乐机器人')
  await form.getByText('高级设置', { exact: true }).click()
  const secret = form.locator('[name="music-bot-channel-secret"]')
  assert.equal(await secret.getAttribute('autocomplete'), 'new-password')
  assert.equal(await secret.getAttribute('readonly'), '')
  await secret.click()
  await secret.fill('test-channel-secret')
  await secret.fill('')
  await form.getByText('高级设置', { exact: true }).click()
  await form.getByRole('button', { name: '创建', exact: true }).click()
  await page.getByText(/Bot「新音乐机器人」已创建/).waitFor()
  assert.equal(botWrites[0].name, botWrites[0].nickname)
  assert.equal(botWrites[0].serverAddress, '127.0.0.1')
  assert.equal(botWrites[0].serverPort, 9987)

  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: '+ 新建 Bot', exact: true }).click()
  await form.scrollIntoViewIfNeeded()
  const bounds = await form.boundingBox()
  assert.ok(bounds && bounds.x >= 0 && bounds.x + bounds.width <= 390)
  await page.screenshot({ path: 'music-playlists-mobile.png', fullPage: true })
  assert.deepEqual(errors, [])
  console.log('PASS playlists: covers on all 4 platforms, custom cover priority, missing/broken cover fallback, 2-request limit, TS cover, 123-song queue, incremental progress, pinned Bot, retry deduplication, Kugou IDs, Bot form and mobile layout')
  await context.close()
} finally {
  await browser.close()
}
