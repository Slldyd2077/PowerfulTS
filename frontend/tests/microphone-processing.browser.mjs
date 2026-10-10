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
      const output = await processor.prepare(input.stream, { ...DEFAULT_MICROPHONE_PROCESSING, keyboardSuppression: false }, 100)
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

  const context = await browser.newContext({ viewport: { width: 1360, height: 1000 } })
  let microphoneStarts = 0
  let uploadedChunks = 0
  await context.addInitScript(() => { localStorage.setItem('session_token', 'audio-test-only') })
  await context.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    let body = {}
    if (path === '/api/auth/get_session') body = { success: true, session_data: { ts_nickname: '音频测试', role: 'member', is_admin: false } }
    if (path === '/api/theme') body = { desktop: null, mobile: null, dim: 45, blur: 0 }
    if (path === '/api/music/voice/channels') body = { channels: [], botCid: null, botOnline: false, monitorRunning: true }
    if (path === '/api/music/voice/entry-sound') body = { configured: false }
    if (path === '/api/music/voice/session') body = { ok: true, botId: 'test-bot', nickname: '音频测试' }
    if (path === '/api/music/voice/start') body = { ok: true, sessionId: 'down', streamPath: '/test-downlink', expiresIn: 30 }
    if (path === '/api/music/voice/mic/start') {
      microphoneStarts++
      body = { ok: true, sessionId: `mic-${microphoneStarts}`, uploadPath: `/test-uplink/${microphoneStarts}` }
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
  })
  await context.routeWebSocket('**/test-downlink', () => {})
  await context.routeWebSocket('**/test-uplink/*', (socket) => {
    socket.onMessage(() => { uploadedChunks++ })
  })
  const ui = await context.newPage()
  const uiErrors = []
  ui.on('pageerror', (error) => uiErrors.push(error.message))
  await ui.goto(`${appOrigin}/voice`)
  const fieldset = ui.locator('.processing-settings')
  await fieldset.waitFor()
  await ui.getByRole('checkbox', { name: '自动麦克风增益' }).uncheck()
  await ui.reload()
  await fieldset.waitFor()
  assert.equal(await ui.getByRole('checkbox', { name: '自动麦克风增益' }).isChecked(), false)
  assert.equal(await ui.getByRole('checkbox', { name: '回声消除' }).isChecked(), true)
  await ui.getByRole('button', { name: '加入通话', exact: false }).click()
  await ui.getByText('RNNoise 智能降噪 · 键盘抑制运行中', { exact: true }).waitFor()
  await ui.getByRole('button', { name: '麦克风发送中 · 点击静音', exact: false }).waitFor()
  assert.ok(uploadedChunks > 0)
  await ui.getByRole('checkbox', { name: '键盘与停顿噪声抑制' }).uncheck()
  await ui.getByText('RNNoise 智能降噪运行中', { exact: true }).waitFor()
  assert.equal(microphoneStarts, 1, 'gate changes do not reconnect the microphone')
  await ui.getByRole('combobox', { name: '背景降噪', exact: true }).press('ArrowDown')
  await ui.getByRole('option', { name: '浏览器基础降噪（省电）', exact: true }).click()
  await ui.getByRole('button', { name: '麦克风发送中 · 点击静音', exact: false }).waitFor()
  assert.equal(microphoneStarts, 2, 'mode switch rebuilds capture')
  assert.equal(await ui.getByRole('checkbox', { name: '键盘与停顿噪声抑制' }).isDisabled(), true)
  await ui.getByRole('button', { name: '挂断', exact: false }).click()
  await ui.getByRole('button', { name: '加入通话', exact: false }).waitFor()
  await ui.setViewportSize({ width: 390, height: 844 })
  await fieldset.scrollIntoViewIfNeeded()
  const bounds = await fieldset.boundingBox()
  assert.ok(bounds && bounds.x >= 0 && bounds.x + bounds.width <= 390, 'mobile controls fit the screen')
  if (process.env.VOICE_TEST_SCREENSHOT) await ui.screenshot({ path: process.env.VOICE_TEST_SCREENSHOT })
  assert.deepEqual(uiErrors, [])
  console.log('PASS production call UI: persisted settings, neural microphone upload, live gate update, mode switch, hangup and mobile layout')
  await context.close()
} finally {
  await browser.close()
}
