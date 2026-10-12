import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { readdir } from 'node:fs/promises'

// Run against Vite dev for service imports and the production worklet from dist.
const origin = process.env.VOICE_TEST_ORIGIN || 'http://127.0.0.1:18184'
const appOrigin = process.env.VOICE_TEST_APP_ORIGIN || 'http://127.0.0.1:18185'
const browser = await chromium.launch({
  headless: true,
  ...(process.env.VOICE_TEST_BROWSER ? { executablePath: process.env.VOICE_TEST_BROWSER } : {}),
  args: ['--autoplay-policy=no-user-gesture-required', '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'],
})
const assets = await readdir(new URL('../dist/assets/', import.meta.url))
const worklet = assets.find((name) => /^microphone-denoise-worklet-.*\.js$/.test(name))
assert.ok(worklet, 'build the production worklet before testing')
try {
  const page = await browser.newPage()
  const errors = []
  page.on('console', (message) => { if (message.type() === 'warning' || message.type() === 'error') console.log(message.text()) })
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto(origin)
  const results = await page.evaluate(async (worklet) => {
    const { MicrophoneProcessing } = await import('/src/services/microphone-processing.ts')
    const { DEFAULT_MICROPHONE_PROCESSING } = await import('/src/services/microphone-processing-settings.ts')
    const statuses = []
    const processor = new MicrophoneProcessing(`/dist/assets/${worklet}`, (status) => statuses.push(status))
    const ctx = new AudioContext({ sampleRate: 48000 })
    await ctx.resume()
    const noise = ctx.createBuffer(1, 48000, 48000)
    let seed = 42
    const data = noise.getChannelData(0)
    for (let i = 0; i < data.length; i++) {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0
      data[i] = ((seed / 4294967296) * 2 - 1) * 0.1
    }
    const source = ctx.createBufferSource()
    source.buffer = noise
    source.loop = true
    const input = ctx.createMediaStreamDestination()
    source.connect(input)
    source.start()
    try {
      const output = await processor.prepare(input.stream, { ...DEFAULT_MICROPHONE_PROCESSING, mode: 'rnnoise', keyboardSuppression: false }, 100)
      const neuralStatus = statuses.at(-1)
      const analyzer = ctx.createAnalyser()
      analyzer.fftSize = 2048
      ctx.createMediaStreamSource(output).connect(analyzer)
      const samples = new Float32Array(analyzer.fftSize)
      await new Promise((resolve) => setTimeout(resolve, 1800))
      let power = 0
      for (let i = 0; i < 10; i++) {
        analyzer.getFloatTimeDomainData(samples)
        power += samples.reduce((sum, sample) => sum + sample * sample, 0) / samples.length
        await new Promise((resolve) => setTimeout(resolve, 30))
      }
      const noiseRms = Math.sqrt(power / 10)
      const chunks = []
      const recorder = new MediaRecorder(output, { mimeType: 'audio/webm;codecs=opus' })
      recorder.ondataavailable = ({ data }) => { if (data.size) chunks.push(data.size) }
      recorder.start(100)
      await new Promise((resolve) => setTimeout(resolve, 400))
      await new Promise((resolve) => { recorder.onstop = resolve; recorder.stop() })
      processor.configure({ ...DEFAULT_MICROPHONE_PROCESSING, keyboardSuppression: true, voiceThreshold: 0.9 })
      await new Promise((resolve) => setTimeout(resolve, 1000))
      analyzer.getFloatTimeDomainData(samples)
      const gatedRms = Math.sqrt(samples.reduce((sum, sample) => sum + sample * sample, 0) / samples.length)
      await processor.release()
      const outputStopped = output.getTracks().every((track) => track.readyState === 'ended')
      const captureAlive = input.stream.getTracks().every((track) => track.readyState === 'live')
      const fallback = new MicrophoneProcessing('/missing-noise-worklet.js', (status) => statuses.push(status))
      const fallbackStream = await fallback.prepare(input.stream, { ...DEFAULT_MICROPHONE_PROCESSING }, 100)
      const fallbackStatus = statuses.at(-1)
      await fallback.release()
      return { neuralStatus, noiseRms, gatedRms, chunks, outputStopped, captureAlive,
        fallbackRaw: fallbackStream === input.stream, fallbackStatus }
    } finally {
      await processor.release()
      source.stop()
      input.stream.getTracks().forEach((track) => track.stop())
      await ctx.close()
    }
  }, worklet)
  assert.equal(results.neuralStatus.mode, 'rnnoise', JSON.stringify(results))
  assert.ok(results.noiseRms > 0, 'neural output is live, not a dead silent graph')
  assert.ok(results.noiseRms < 0.02, `white noise RMS reduced from ~0.058 to ${results.noiseRms}`)
  assert.ok(results.gatedRms < results.noiseRms * 0.1, 'keyboard gate suppresses non-speech')
  assert.ok(results.chunks.length > 0, 'MediaRecorder receives processed audio')
  assert.equal(results.outputStopped, true)
  assert.equal(results.captureAlive, true)
  assert.equal(results.fallbackRaw, true)
  assert.equal(results.fallbackStatus.mode, 'browser')
  assert.ok(results.fallbackStatus.message.includes('回退'))
  assert.deepEqual(errors, [])
  console.log('PASS production RNNoise worklet, live PCM, noise suppression, speech gate, recorder, cleanup and fallback', results)
  await page.close()

  const context = await browser.newContext({ viewport: { width: 1360, height: 1000 },
    ...(process.env.VOICE_TEST_MOBILE ? { userAgent: 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130.0.0.0 Mobile Safari/537.36' } : {}) })
  let microphoneStarts = 0
  let downlinkStarts = 0
  const downlinkSockets = []
  let uploadedChunks = 0
  let musicNickname = 'MusicBot'
  let musicClid = 12
  await context.addInitScript(() => { localStorage.setItem('session_token', 'audio-test-only') })
  await context.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    let body = {}
    if (path === '/api/auth/get_session') body = { success: true, session_data: { ts_nickname: '音频测试', role: 'member', is_admin: false } }
    if (path === '/api/theme') body = { desktop: null, mobile: null, dim: 45, blur: 0 }
    if (path === '/api/music/voice/channels') body = {
      channels: [{ cid: 1, pid: 0, depth: 0, name: '测试频道', hasPassword: false,
        clients: [
          { clid: 11, nickname: '音频测试', isBot: false, isSelf: true },
          { clid: musicClid, nickname: musicNickname, volumeKey: 'ts:test-music-identity', isBot: true, isSelf: false },
        ] }], botCid: 1, botOnline: true, monitorRunning: true,
    }
    if (path === '/api/music/voice/entry-sound') body = { configured: false }
    if (path === '/api/music/voice/session') body = { ok: true, botId: 'test-bot', nickname: '音频测试' }
    if (path === '/api/music/voice/start') {
      downlinkStarts++
      if (downlinkStarts > 1) await new Promise((resolve) => setTimeout(resolve, 800))
      body = { ok: true, sessionId: 'down', streamPath: '/test-downlink', expiresIn: 30 }
    }
    if (path === '/api/music/voice/mic/start') {
      microphoneStarts++
      body = { ok: true, sessionId: `mic-${microphoneStarts}`, uploadPath: `/test-uplink/${microphoneStarts}` }
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
  })
  await context.routeWebSocket('**/test-downlink', (socket) => { downlinkSockets.push(socket) })
  await context.routeWebSocket('**/test-uplink/*', (socket) => {
    socket.onMessage(() => { uploadedChunks++ })
  })
  const ui = await context.newPage()
  const uiErrors = []
  ui.on('pageerror', (error) => uiErrors.push(error.message))
  await ui.goto(`${appOrigin}/voice`)
  const fieldset = ui.locator('.processing-settings')
  await fieldset.waitFor()
  await ui.getByText('音频设置', { exact: false }).click()
  await ui.getByRole('checkbox', { name: '自动麦克风增益' }).uncheck()
  await ui.reload()
  await fieldset.waitFor()
  await ui.getByText('音频设置', { exact: false }).click()
  assert.equal(await ui.getByRole('checkbox', { name: '自动麦克风增益' }).isChecked(), false)
  assert.equal(await ui.getByRole('checkbox', { name: '回声消除' }).isChecked(), true)
  await ui.getByRole('button', { name: '加入通话', exact: false }).click()
  await ui.getByText('人声增强运行中 · RNNoise + 语音门控', { exact: true }).waitFor()
  await ui.getByRole('button', { name: '静音麦克风', exact: true }).waitFor()
  assert.ok(uploadedChunks > 0)
  await ui.locator('.member-list').getByText('你', { exact: true }).waitFor()
  assert.equal(await ui.locator('.member-list .tag').allTextContents().then((tags) => tags.sort()).then(JSON.stringify), JSON.stringify(['你', '机器人'].sort()))
  assert.ok((await ui.locator('.browser-head').innerText()).includes('1 人在场'))
  assert.equal(await ui.locator('.speaker-mixer input[type="range"]').count(), 1, 'music has an independent gain control, self is excluded')
  await ui.getByRole('slider', { name: 'MusicBot 收听音量', exact: true }).fill('50')
  assert.equal(await ui.locator('.mixer-list b').innerText(), '50%')
  assert.equal(await ui.evaluate(() => JSON.parse(localStorage.getItem('voice_speaker_volumes'))['ts:test-music-identity']), 50)
  await ui.getByRole('slider', { name: 'MusicBot 收听音量', exact: true }).fill('35')
  musicNickname = '正在播放另一首歌'
  musicClid = 99
  await ui.locator('.channel-browser .refresh').click()
  const renamedVolume = ui.getByRole('slider', { name: '正在播放另一首歌 收听音量', exact: true })
  await renamedVolume.waitFor()
  assert.equal(await renamedVolume.inputValue(), '35', 'nickname and connection changes preserve personal volume')
  assert.equal(await ui.locator('.mixer-list b').innerText(), '35%')
  downlinkSockets[0].close({ code: 1011, reason: 'simulated upstream interruption' })
  await ui.waitForTimeout(1150)
  await ui.evaluate(() => {
    window.dispatchEvent(new Event('focus'))
    window.dispatchEvent(new Event('pageshow'))
    window.dispatchEvent(new Event('online'))
  })
  await ui.waitForTimeout(1100)
  assert.equal(downlinkStarts, 2, 'foreground events share one in-flight reconnect request')
  assert.equal(downlinkSockets.length, 2, 'only one replacement downlink is opened')
  assert.ok(uploadedChunks > 0)
  await ui.locator('summary').filter({ hasText: '音频设置' }).click()
  await ui.screenshot({ path: '../../data/audio-lab/voice-desktop-stream.png' })
  await ui.locator('summary').filter({ hasText: '音频设置' }).click()
  await ui.getByRole('button', { name: '恢复声音', exact: true }).click()
  await ui.getByRole('slider', { name: '人声门限' }).fill('0.5')
  await ui.getByText('人声增强运行中 · RNNoise + 语音门控', { exact: true }).waitFor()
  assert.equal(microphoneStarts, 1, 'gate changes do not reconnect the microphone')
  await ui.getByRole('combobox', { name: '背景降噪', exact: true }).press('ArrowDown')
  await ui.getByRole('option', { name: '浏览器基础降噪 · 省电', exact: true }).click()
  await ui.getByRole('button', { name: '静音麦克风', exact: true }).waitFor()
  assert.equal(microphoneStarts, 2, 'mode switch rebuilds capture')
  assert.equal(await ui.getByRole('checkbox', { name: '键盘与停顿噪声抑制' }).isDisabled(), true)
  await ui.getByRole('button', { name: '挂断', exact: false }).click()
  await ui.getByRole('button', { name: '加入通话', exact: false }).waitFor()
  await ui.getByRole('combobox', { name: '背景降噪', exact: true }).press('ArrowDown')
  assert.equal(await ui.getByRole('option', { name: 'SpEx+ · 目标说话人', exact: true }).getAttribute('aria-disabled'), 'true')
  await ui.keyboard.press('Escape')
  await ui.locator('summary').filter({ hasText: '目标说话人' }).click()
  await ui.getByLabel('目标参考录音', { exact: true }).setInputFiles(new URL('../../../data/audio-lab/samples/spk1_snt2.wav', import.meta.url).pathname.replace(/^\/(?:([A-Za-z]:))/, '$1'))
  await ui.getByText('目标参考录音 · 已保存', { exact: true }).waitFor()
  await ui.getByRole('combobox', { name: '背景降噪', exact: true }).press('ArrowDown')
  assert.notEqual(await ui.getByRole('option', { name: 'SpEx+ · 目标说话人', exact: true }).getAttribute('aria-disabled'), 'true')
  await ui.keyboard.press('Escape')
  await ui.getByRole('button', { name: '删除参考', exact: true }).click()
  assert.equal(await ui.evaluate(() => localStorage.getItem('voice_model_reference_v1')), null)
  await ui.locator('summary').filter({ hasText: '音频设置' }).click()
  await ui.locator('summary').filter({ hasText: '目标说话人' }).click()
  await ui.setViewportSize({ width: 390, height: 844 })
  await ui.locator('summary').filter({ hasText: '音频设置' }).click()
  assert.equal(await ui.getByRole('combobox', { name: '播放设备', exact: true }).count(), 1, 'mobile retains the output selector')
  assert.equal(await ui.getByRole('combobox', { name: '麦克风设备', exact: true }).count(), 1)
  await fieldset.scrollIntoViewIfNeeded()
  const bounds = await fieldset.boundingBox()
  assert.ok(bounds && bounds.x >= 0 && bounds.x + bounds.width <= 390, 'mobile controls fit the screen')
  assert.ok(await ui.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'page has no horizontal overflow')
  await ui.waitForTimeout(3200)
  if (process.env.VOICE_TEST_SCREENSHOT) await ui.screenshot({ path: process.env.VOICE_TEST_SCREENSHOT })
  assert.deepEqual(uiErrors, [])
  console.log('PASS production call UI: persisted settings, neural microphone upload, live gate update, mode switch, hangup and mobile layout')
  await context.close()
} finally {
  await browser.close()
}
