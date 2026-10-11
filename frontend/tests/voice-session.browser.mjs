import assert from 'node:assert/strict'
import { chromium } from 'playwright'

// Production UI with real browser audio capture and mocked backend transports.
const origin = process.env.VOICE_TEST_APP_ORIGIN || 'http://127.0.0.1:18185'
// Generated 20 ms, 48 kHz stereo 440 Hz tone encoded with libopus; no external media.
const tone = Buffer.from('/LSZP2G+qRqin9MSWFJ30paN0OaiFvkxRJtDINcT6XJmAnB357AQ80JKYTWEFGCbadT8yPscrpq0VCE2RQ8xd4qew7mUIXO1ajpBr0JkIRVDXFUX+kPWjnFMOhG0e0fjZcGyrpFWfY6pWrf+LIPJ8n/7Jb4zMZFL/GI8n0zvXEEw8Lr+yKfFGOPgjBDcgx+RV8BBE3LlEtufsmeQMbJcLyd2GwQqSjHqaOEIOUXw3a4X98Q6L2NOHZnMslWjVNkpW8FCaqe7O7NqLtnuVSu4qE7Gudh9ZCoBzB0ky3jmZ6aTwZxckv68Rv3nygq8RvzJ2ZL5j1xidK1EWwZmduOlOIh4IxsBOiHPo+qqXRDn0FyJoM9Rn0BkXqkSng3mZuviv9OSQNkdSoY3kQYj0SONiCeH6Fo0UDhOpKN8/DRCnKRjrc76+Ft/Ly+XE+0H1Qn2b8MblKxYlXXI6uVeIXQuO+qgbZX1+qnEpdJallj/Ua2oKBmYBsA2Ts3//+BttJJ/I2BbbQ==', 'base64')
const voicePacket = Buffer.concat([Buffer.from([1, 5, 0, 12, 3, 192]), tone])
const browser = await chromium.launch({
  headless: true,
  ...(process.env.VOICE_TEST_BROWSER ? { executablePath: process.env.VOICE_TEST_BROWSER } : {}),
  args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'],
})
try {
  const context = await browser.newContext({ permissions: ['microphone'], viewport: { width: 1360, height: 1000 } })
  const counts = { joins: 0, stops: 0, downlinks: 0, microphones: 0, chunks: 0, downlinkCloses: 0 }
  let online = false
  await context.addInitScript(() => {
    const NativeDecoder = window.AudioDecoder
    if (NativeDecoder) window.AudioDecoder = class extends NativeDecoder {
      static isConfigSupported(config) { return NativeDecoder.isConfigSupported(config) }
      constructor(options) { super(options); this.voiceTestError = options.error }
      decode(chunk) {
        if (window.voiceTestFailDecoder) {
          window.voiceTestFailDecoder = false
          this.close()
          this.voiceTestError(new Error('forced runtime decoder failure'))
          return
        }
        super.decode(chunk)
      }
    }
    window.voiceTestContexts = []
    window.voiceTestAnalysers = []
    const OriginalContext = window.AudioContext
    window.AudioContext = class extends OriginalContext {
      constructor(options) { super(options); window.voiceTestContexts.push(this) }
      createGain() {
        const gain = super.createGain()
        const analyser = this.createAnalyser()
        gain.connect(analyser)
        window.voiceTestAnalysers.push(analyser)
        return gain
      }
    }
    if (!sessionStorage.getItem('voice-test-initialized')) {
      localStorage.setItem('session_token', 'voice-test-only')
      localStorage.setItem('voice_audio_preferences_v1', JSON.stringify({ outputVolume: 0, microphoneVolume: 150,
        selectedInput: 'saved-mic', selectedOutput: 'saved-speaker', microphoneEnabled: true }))
      localStorage.setItem('voice_microphone_processing_v1', JSON.stringify({ mode: 'browser' }))
      sessionStorage.setItem('voice-test-initialized', 'yes')
    }
    const enumerate = navigator.mediaDevices.enumerateDevices.bind(navigator.mediaDevices)
    window.voiceTestDevicesVisible = false
    navigator.mediaDevices.enumerateDevices = () => window.voiceTestDevicesVisible ? enumerate()
      : Promise.resolve([{ kind: 'audioinput', deviceId: '', label: '' }, { kind: 'audiooutput', deviceId: '', label: '' }])
    const getUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices)
    window.voiceTestTracks = []
    navigator.mediaDevices.getUserMedia = async (constraints) => {
      const stream = await getUserMedia(constraints)
      window.voiceTestTracks.push(...stream.getTracks())
      return stream
    }
  })
  await context.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    let body = {}
    if (path === '/api/auth/get_session') body = { success: true, session_data: { ts_nickname: '通话测试', role: 'member', is_admin: false } }
    if (path === '/api/theme') body = { desktop: null, mobile: null, dim: 45, blur: 0 }
    if (path === '/api/music/voice/channels') body = { channels: [{ cid: 1, pid: 0, depth: 0, name: '测试频道', hasPassword: false, clients: [] }], botCid: online ? 1 : null, botOnline: online, monitorRunning: true }
    if (path === '/api/music/voice/entry-sound') body = { configured: false }
    if (path === '/api/music/voice/session') {
      counts.joins++; online = true
      body = { ok: true, botId: 'test-bot', nickname: '通话测试' }
    }
    if (path === '/api/music/voice/session/stop') { counts.stops++; online = false }
    if (path === '/api/music/voice/start') {
      counts.downlinks++
      body = { ok: true, sessionId: 'down', streamPath: '/test-downlink', expiresIn: 30 }
    }
    if (path === '/api/music/voice/mic/start') {
      counts.microphones++
      body = { ok: true, sessionId: `mic-${counts.microphones}`, uploadPath: `/test-uplink/${counts.microphones}` }
    }
    if (path === '/api/music/voice/watch/ticket') body = { path: '/test-watch', iceServers: [] }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
  })
  await context.routeWebSocket('**/test-downlink', socket => {
    const timer = setInterval(() => socket.send(voicePacket), 20)
    socket.onClose(() => { clearInterval(timer); counts.downlinkCloses++ })
  })
  await context.routeWebSocket('**/test-uplink/*', socket => { socket.onMessage(() => { counts.chunks++ }) })
  await context.routeWebSocket('**/test-watch', socket => {
    socket.send(JSON.stringify({ type: 'welcome', peerId: 'test-peer' }))
    socket.send(JSON.stringify({ type: 'room', peers: [{ id: 'test-peer', nickname: '通话测试' }], share: null, host: 'test-peer' }))
  })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  const saved = () => page.evaluate(() => JSON.parse(localStorage.getItem('voice_audio_preferences_v1')))
  const receivesTone = () => page.waitForFunction(() => window.voiceTestAnalysers.some(analyser => {
    if (analyser.context.state !== 'running') return false
    const samples = new Float32Array(analyser.fftSize)
    analyser.getFloatTimeDomainData(samples)
    return samples.some(sample => Math.abs(sample) > 0.01)
  }))
  const navigateToMonitor = () => page.locator('.side-nav').getByRole('menuitem', { name: '服务器监控' }).click()
  const setRange = async (locator, value) => {
    await locator.evaluate((input, value) => {
      input.value = String(value)
      input.dispatchEvent(new Event('input', { bubbles: true }))
      input.dispatchEvent(new Event('change', { bubbles: true }))
    }, value)
  }
  await page.goto(`${origin}/voice`)
  await page.locator('.voice-settings').waitFor()
  assert.equal((await saved()).selectedInput, 'saved-mic', 'hidden device IDs must not erase saved choices')
  await page.evaluate(() => {
    window.voiceTestDevicesVisible = true
    navigator.mediaDevices.dispatchEvent(new Event('devicechange'))
  })
  await page.waitForFunction(() => JSON.parse(localStorage.getItem('voice_audio_preferences_v1')).selectedInput === '')
  assert.equal((await saved()).selectedOutput, '', 'missing labelled devices fall back to system default')
  await setRange(page.locator('.voice-settings input[type=range]').nth(0), 37)
  await setRange(page.locator('.voice-settings input[type=range]').nth(1), 145)
  // Choose a real enumerated fake device so exact capture constraints are exercised.
  await page.getByRole('combobox', { name: '麦克风设备', exact: true }).press('ArrowDown')
  await page.getByRole('option', { name: /Fake/ }).first().click()
  const device = (await saved()).selectedInput
  assert.ok(device)
  const outputPicker = page.getByRole('combobox', { name: '播放设备', exact: true })
  if (await outputPicker.count()) {
    await outputPicker.press('ArrowDown')
    const listId = await outputPicker.getAttribute('aria-controls')
    await page.locator(`[id="${listId}"]`).getByRole('option', { name: /Fake/ }).first().click()
  }
  const outputDevice = (await saved()).selectedOutput
  await page.reload()
  await page.locator('.voice-settings').waitFor()
  assert.equal(await page.locator('.voice-settings input[type=range]').nth(0).inputValue(), '37')
  assert.equal(await page.locator('.voice-settings input[type=range]').nth(1).inputValue(), '145')
  assert.equal((await saved()).selectedInput, device)
  assert.equal((await saved()).selectedOutput, outputDevice)
  // Listen-only never opens a capture track, avoiding Android communication routing.
  await page.getByRole('button', { name: '只收听（不开麦克风）', exact: true }).click()
  await page.getByRole('button', { name: '已静音 · 点击说话', exact: false }).waitFor()
  assert.equal(counts.microphones, 0)
  assert.equal(await page.evaluate(() => window.voiceTestTracks.length), 0)
  await receivesTone()
  await page.evaluate(() => { window.voiceTestFailDecoder = true })
  await page.getByText('兼容模式已启用：当前设备使用 WASM 解码频道语音。', { exact: true }).waitFor()
  await receivesTone()
  console.log('PASS runtime WebCodecs failure falls back to WASM and audible decoded PCM continues')
  await page.locator('.leave-button').click()
  await page.getByRole('button', { name: '加入通话', exact: false }).waitFor()
  // Re-enable the mic explicitly; listen-only intentionally saves the mute preference.
  await page.evaluate(() => { window.voiceTestDevicesVisible = true })
  await page.getByRole('button', { name: '加入通话', exact: false }).click()
  await page.getByRole('button', { name: '已静音 · 点击说话', exact: false }).click()
  await page.getByRole('button', { name: '麦克风发送中 · 点击静音', exact: false }).waitFor()
  await page.waitForFunction(() => window.voiceTestTracks.some(track => track.readyState === 'live'))
  // OS interruption must have a real user-gesture recovery path, with a fresh recorder.
  const beforeRecovery = counts.microphones
  await page.evaluate(async () => {
    await Promise.all(window.voiceTestContexts.filter(c => c.state === 'running').map(c => c.suspend()))
  })
  await page.getByText('音频被手机系统暂停，请点击“恢复声音与麦克风”。', { exact: true }).waitFor()
  await page.getByRole('button', { name: '恢复声音与麦克风', exact: true }).click()
  await page.getByRole('button', { name: '恢复声音与麦克风', exact: true }).waitFor()
  await page.getByRole('button', { name: '麦克风发送中 · 点击静音', exact: false }).waitFor()
  assert.equal(counts.microphones, beforeRecovery + 1)
  assert.ok(await page.evaluate(() => window.voiceTestContexts.filter(c => c.state !== 'closed').every(c => c.state === 'running')))
  await receivesTone()
  await page.getByRole('button', { name: '加入共享房间', exact: true }).click()
  await page.getByRole('checkbox', { name: '允许成员暂停' }).uncheck()
  await page.getByRole('checkbox', { name: '等待成员加载完成' }).uncheck()
  await page.getByRole('checkbox', { name: '这是直播' }).check()
  await page.getByRole('combobox', { name: '观看方式', exact: true }).press('ArrowDown')
  await page.getByRole('option', { name: '视频直链（MP4 / WebM 等）', exact: true }).click()
  const beforeNavigation = { ...counts }
  await navigateToMonitor()
  await page.locator('.dashboard').waitFor()
  const bar = page.getByRole('complementary', { name: '当前网页通话', exact: true })
  await bar.waitFor()
  // Wait for a fresh upload, rather than asserting just a retained UI label.
  const chunkTarget = counts.chunks
  await new Promise((resolve, reject) => {
    const deadline = Date.now() + 5000
    const check = () => counts.chunks > chunkTarget ? resolve()
      : Date.now() > deadline ? reject(new Error('audio upload stopped after navigation')) : setTimeout(check, 50)
    check()
  })
  assert.equal(counts.stops, beforeNavigation.stops)
  assert.equal(counts.downlinkCloses, beforeNavigation.downlinkCloses)
  assert.equal(counts.microphones, beforeNavigation.microphones)
  await page.setViewportSize({ width: 390, height: 844 })
  const bounds = await bar.boundingBox()
  assert.ok(bounds && bounds.x >= 0 && bounds.x + bounds.width <= 390 && bounds.y + bounds.height < 844 - 60)
  await bar.getByRole('button', { name: '静音', exact: true }).click()
  await bar.getByRole('button', { name: '开启麦克风', exact: true }).waitFor()
  assert.equal(await page.evaluate(() => window.voiceTestTracks.every(track => track.readyState === 'ended')), true)
  await bar.getByRole('link').click()
  await page.locator('.voice-settings').waitFor()
  await page.getByRole('button', { name: '已静音 · 点击说话', exact: false }).waitFor()
  assert.equal(counts.joins, beforeNavigation.joins)
  assert.equal(counts.downlinks, beforeNavigation.downlinks)
  await page.getByRole('button', { name: '加入共享房间', exact: true }).click()
  assert.equal(await page.getByRole('checkbox', { name: '允许成员暂停' }).isChecked(), false)
  assert.equal(await page.getByRole('checkbox', { name: '这是直播' }).isChecked(), true)
  assert.equal(await page.getByRole('checkbox', { name: '等待成员加载完成' }).isChecked(), false)
  await page.setViewportSize({ width: 1360, height: 1000 })
  await navigateToMonitor()
  await bar.getByRole('button', { name: '挂断', exact: true }).click()
  await page.waitForFunction(() => window.voiceTestTracks.every(track => track.readyState === 'ended'))
  await page.locator('.side-nav').getByRole('menuitem', { name: '网页通话' }).click()
  await page.getByRole('button', { name: '加入通话', exact: false }).waitFor()
  await page.evaluate(() => {
    const saved = JSON.parse(localStorage.getItem('voice_audio_preferences_v1'))
    localStorage.setItem('voice_audio_preferences_v1', JSON.stringify({ ...saved, selectedInput: 'removed-mic' }))
  })
  await page.reload()
  await page.locator('.voice-settings').waitFor()
  assert.equal((await saved()).microphoneEnabled, false)
  await page.getByRole('button', { name: '加入通话', exact: false }).click()
  await page.getByRole('button', { name: '已静音 · 点击说话', exact: false }).waitFor()
  assert.equal(counts.microphones, beforeNavigation.microphones, 'joining again must respect saved mute preference')
  await page.getByRole('button', { name: '已静音 · 点击说话', exact: false }).click()
  await page.getByRole('button', { name: '麦克风发送中 · 点击静音', exact: false }).waitFor()
  assert.equal((await saved()).selectedInput, '', 'a missing saved microphone falls back even before device permission reveals IDs')
  await page.setViewportSize({ width: 1360, height: 1000 })
  await navigateToMonitor()
  await bar.waitFor()
  await page.getByTitle('登出', { exact: true }).click()
  await page.waitForURL('**/login')
  assert.equal(await page.evaluate(() => window.voiceTestTracks.every(track => track.readyState === 'ended')), true)
  assert.equal(await bar.count(), 0)
  assert.deepEqual(errors, [])
  console.log('PASS navigation keeps real microphone upload and downlink alive; floating controls, mobile layout, saved preferences, device fallback, muted rejoin and logout cleanup')
  await context.close()
} finally {
  await browser.close()
}
