import assert from 'node:assert/strict'
import { chromium } from 'playwright'

const browser = await chromium.launch({ headless: true,
  executablePath: process.env.VOICE_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  args: ['--autoplay-policy=no-user-gesture-required'] })
try {
  const page = await browser.newPage()
  let streamFrames = 0
  let streamConnections = 0
  await page.routeWebSocket('**/api/voice-processing/stream', socket => {
    streamConnections++
    const worker = new WebSocket('ws://127.0.0.1:18187')
    worker.binaryType = 'arraybuffer'
    worker.onmessage = ({ data }) => socket.send(typeof data === 'string' ? data : Buffer.from(data))
    worker.onclose = () => socket.close()
    socket.onMessage(data => {
      if (typeof data === 'string') return // fake browser auth; worker is loopback only
      streamFrames++
      if (streamFrames === 80) { worker.close(); socket.close({ code: 1011 }); return }
      if (worker.readyState === WebSocket.OPEN) worker.send(data)
    })
    socket.onClose(() => worker.close())
  })
  let requests = 0
  await page.route('**/api/voice-processing/pcm', async route => {
    requests++
    const body = route.request().postDataJSON()
    if (body.referenceId) body.referenceKey = `test:${body.referenceId}`
    const response = await fetch('http://127.0.0.1:18186/pcm', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    await route.fulfill({ status: response.status, contentType: response.headers.get('content-type'),
      body: Buffer.from(await response.arrayBuffer()) }).catch(() => {})
  })
  await page.route('**/fixture/*.wav', async route => {
    const name = new URL(route.request().url()).pathname.split('/').at(-1)
    const response = await fetch(`http://127.0.0.1:18186/audio/${name}`)
    await route.fulfill({ contentType: 'audio/wav', body: Buffer.from(await response.arrayBuffer()) })
  })
  await page.goto('http://127.0.0.1:18184')
  const result = await page.evaluate(async () => {
    const { MicrophoneModel, prepareVoiceReference, VOICE_REFERENCE_KEY } = await import('/src/services/microphone-model.ts')
    const ref = await (await fetch('/fixture/spk1_snt2.wav')).blob()
    localStorage.setItem(VOICE_REFERENCE_KEY, await prepareVoiceReference(new File([ref], 'reference.wav')))
    const ctx = new AudioContext({ sampleRate: 48000 })
    const source = ctx.createBufferSource()
    source.buffer = await ctx.decodeAudioData(await (await fetch('/fixture/two-speakers-input.wav')).arrayBuffer())
    source.loop = true
    const input = ctx.createMediaStreamDestination()
    source.connect(input); source.start(); await ctx.resume()
    const statuses = []
    const processor = new MicrophoneModel(status => statuses.push(status))
    const results = []
    try {
      for (const mode of ['deepfilter', 'spex', 'combined']) {
        const output = await processor.prepare(input.stream, mode, 100)
        const analyzer = ctx.createAnalyser()
        analyzer.fftSize = 2048
        const node = ctx.createMediaStreamSource(output)
        node.connect(analyzer)
        let peak = 0
        const samples = new Float32Array(2048)
        for (let i = 0; i < 90; i++) {
          await new Promise(resolve => setTimeout(resolve, 80))
          analyzer.getFloatTimeDomainData(samples)
          peak = Math.max(peak, ...samples.map(Math.abs))
        }
        results.push({ mode, peak, status: statuses.at(-1) })
        node.disconnect()
        await processor.release()
        if (!output.getTracks().every(track => track.readyState === 'ended')) throw Error('Output tracks leaked')
      }
    } finally {
      await processor.release(); source.stop(); input.stream.getTracks().forEach(track => track.stop()); await ctx.close()
    }
    return results
  })
  for (const item of result) {
    assert.equal(item.status.mode, item.mode)
    assert.ok(item.peak > 0.00001 && item.peak <= (item.mode === 'deepfilter' ? 1 : 0.951), JSON.stringify(item))
    console.log('PASS live capture, actual model, processed output and cleanup:', item)
  }
  const stopped = requests
  const stoppedFrames = streamFrames
  await page.waitForTimeout(1200)
  assert.equal(requests, stopped, 'no requests after release')
  assert.equal(streamFrames, stoppedFrames, 'no streaming frames after release')
  assert.ok(streamFrames > 150 && streamConnections >= 2, 'real streaming model recovers after disconnect')
  console.log('PASS persistent binary PCM, actual DeepFilter runtime, forced reconnect and release:', { streamFrames, streamConnections })
} finally { await browser.close() }
