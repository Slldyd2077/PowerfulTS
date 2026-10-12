import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { readdir, readFile } from 'node:fs/promises'
const browser = await chromium.launch({ headless: true,
  executablePath: process.env.VOICE_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  args: ['--autoplay-policy=no-user-gesture-required'] })
try {
  const page = await browser.newPage()
  let connections = 0
  let frames = 0
  let drop = true
  await page.routeWebSocket('**/api/voice-processing/stream', socket => {
    connections++
    if (connections === 1) { socket.onMessage(() => socket.close({ code: 1011 })); return }
    const worker = new WebSocket('ws://127.0.0.1:18187')
    worker.binaryType = 'arraybuffer'
    worker.onmessage = ({ data }) => socket.send(typeof data === 'string' ? data : Buffer.from(data))
    worker.onclose = () => socket.close()
    socket.onMessage(data => {
      if (typeof data === 'string') return
      frames++
      if (drop && frames === 90) { drop = false; worker.close(); socket.close({ code: 1011 }); return }
      if (worker.readyState === WebSocket.OPEN) worker.send(data)
    })
    socket.onClose(() => worker.close())
  })
  const wav = await readFile(new URL('../../../data/audio-lab/samples/two-speakers-input.wav', import.meta.url))
  await page.route('**/fixture.wav', route => route.fulfill({ contentType: 'audio/wav', body: wav }))
  const worklet = (await readdir(new URL('../dist/assets/', import.meta.url))).find(n => /^microphone-denoise-worklet-.*\.js$/.test(n))
  await page.goto('http://127.0.0.1:18184')
  const result = await page.evaluate(async worklet => {
    const { MicrophoneProcessing } = await import('/src/services/microphone-processing.ts')
    const { DEFAULT_MICROPHONE_PROCESSING } = await import('/src/services/microphone-processing-settings.ts')
    const ctx = new AudioContext({ sampleRate: 48000 })
    await ctx.resume()
    const src = ctx.createBufferSource()
    src.buffer = await ctx.decodeAudioData(await (await fetch('/fixture.wav')).arrayBuffer())
    src.loop = true
    const input = ctx.createMediaStreamDestination()
    src.connect(input); src.start()
    const statuses = []
    const processing = new MicrophoneProcessing(`/dist/assets/${worklet}`, s => statuses.push(s))
    const t = performance.now()
    const stream = await processing.prepare(input.stream, { ...DEFAULT_MICROPHONE_PROCESSING, mode: 'deepfilter' }, 100)
    const prepareMs = performance.now() - t
    const track = stream.getAudioTracks()[0]
    const analyzer = ctx.createAnalyser()
    const source = ctx.createMediaStreamSource(stream)
    source.connect(analyzer)
    const samples = new Float32Array(analyzer.fftSize)
    const rms = []
    const chunks = []
    const recorder = new MediaRecorder(stream)
    recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data.size) }
    recorder.start(100)
    for (let i = 0; i < 100; i++) {
      await new Promise(r => setTimeout(r, 100))
      analyzer.getFloatTimeDomainData(samples)
      rms.push({ mode: statuses.at(-1)?.mode, value: Math.sqrt(samples.reduce((s,x) => s+x*x,0)/samples.length) })
      if (stream.getAudioTracks()[0] !== track || track.readyState !== 'live') throw Error('Output track changed during failover')
    }
    await new Promise(r => { recorder.onstop = r; recorder.stop() })
    processing.setVolume(80)
    await processing.resume()
    await processing.release()
    const stopped = track.readyState === 'ended'
    const captureAlive = input.stream.getTracks().every(t => t.readyState === 'live')
    source.disconnect(); src.stop(); input.stream.getTracks().forEach(t => t.stop()); await ctx.close()
    return { statuses, prepareMs, rms, chunks: chunks.length, stopped, captureAlive }
  }, worklet)
  assert.ok(result.prepareMs < 3000, 'local bypass does not wait for model handshake')
  assert.ok(result.statuses.some(s => s.mode === 'voice' && s.message.includes('旁路')))
  assert.ok(result.statuses.some(s => s.mode === 'deepfilter'))
  const transitions = result.statuses.map(s => s.mode).filter((s,i,a) => i === 0 || s !== a[i-1])
  assert.ok(transitions.filter(s => s === 'deepfilter').length >= 2, JSON.stringify(transitions))
  assert.ok(result.rms.some(s => s.mode === 'voice' && s.value > .001), 'fallback sends processed speech')
  assert.ok(result.rms.some(s => s.mode === 'deepfilter' && s.value > .001), 'model recovers real speech')
  assert.ok(result.chunks > 50 && result.stopped && result.captureAlive)
  const stoppedFrames = frames
  await page.waitForTimeout(2000)
  assert.equal(frames, stoppedFrames)
  console.log('PASS initial model unavailable, local bypass speech, real model recovery, forced mid-call disconnect, stable recording track and cleanup', { connections, frames, transitions, chunks: result.chunks, prepareMs: result.prepareMs })
} finally { await browser.close() }
