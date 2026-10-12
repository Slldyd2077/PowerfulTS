import assert from 'node:assert/strict'
import { readdir } from 'node:fs/promises'
import { chromium } from 'playwright'

// Run against Vite after pnpm build; the built RNNoise worklet is used below.
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.VOICE_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  args: ['--autoplay-policy=no-user-gesture-required'],
})
try {
  const page = await browser.newPage()
  await page.routeWebSocket('**/api/voice-processing/stream', socket => {
    socket.onMessage(() => socket.close({ code: 4401 }))
  })
  await page.goto(process.env.VOICE_TEST_BASE_URL || 'http://127.0.0.1:18184')
  const worklet = (await readdir(new URL('../dist/assets/', import.meta.url)))
    .find(name => /^microphone-denoise-worklet-.*\.js$/.test(name))
  assert.ok(worklet, 'run pnpm build to create the RNNoise worklet')
  const result = await page.evaluate(async worklet => {
    const { MicrophoneProcessing } = await import('/src/services/microphone-processing.ts')
    const { MicrophoneUplink } = await import('/src/services/microphone-uplink.ts')
    const { DEFAULT_MICROPHONE_PROCESSING } = await import('/src/services/microphone-processing-settings.ts')
    const context = new AudioContext({ sampleRate: 48000 })
    await context.resume()
    const oscillator = context.createOscillator()
    const amplitude = context.createGain()
    amplitude.gain.value = 0.1
    oscillator.connect(amplitude)
    // Keep the synthetic source rendering even before a recorder consumes it.
    const silentOutput = context.createGain()
    silentOutput.gain.value = 0
    amplitude.connect(silentOutput).connect(context.destination)
    oscillator.start()
    const rms = async stream => {
      const source = context.createMediaStreamSource(stream)
      const analyzer = context.createAnalyser()
      source.connect(analyzer)
      try {
        await new Promise(resolve => setTimeout(resolve, 600))
        const samples = new Float32Array(analyzer.fftSize)
        analyzer.getFloatTimeDomainData(samples)
        return Math.sqrt(samples.reduce((total, value) => total + value * value, 0) / samples.length)
      } finally { source.disconnect(); analyzer.disconnect() }
    }
    const modes = []
    try {
      for (const mode of ['off', 'browser']) {
        const input = context.createMediaStreamDestination()
        amplitude.connect(input)
        const processor = new MicrophoneProcessing(`/dist/assets/${worklet}`, () => {})
        let volume = 100
        let captureRequests = 0
        let uploadedBytes = 0
        let state = 'idle'
        let recordingStream = null
        const uplink = new MicrophoneUplink({
          acquireStream: async () => { captureRequests++; return input.stream },
          prepareStream: stream => processor.prepare(stream, { ...DEFAULT_MICROPHONE_PROCESSING, mode }, volume),
          releasePreparedStream: () => processor.release(),
          chooseMimeType: () => 'audio/webm;codecs=opus',
          startSession: async () => ({ sessionId: 'test', uploadPath: '/test' }),
          stopSession: async () => {},
          createSocket: () => {
            const socket = { readyState: 0, onopen: null, onclose: null, onerror: null,
              send(chunk) { uploadedBytes += chunk.size }, close() { socket.readyState = 3 } }
            queueMicrotask(() => { socket.readyState = 1; socket.onopen?.() })
            return socket
          },
          createRecorder: stream => { recordingStream = stream; return new MediaRecorder(stream) },
          isRecoveryAllowed: () => true,
          setTimer: (callback, delay) => setTimeout(callback, delay), clearTimer: timer => clearTimeout(timer),
          onStateChange: next => { state = next }, onWarning: () => {}, onError: () => {},
        })
        try {
          await uplink.start()
          const initial = await rms(recordingStream)
          volume = 0
          if (!processor.setVolume(volume)) await uplink.restartTransport()
          const muted = await rms(recordingStream)
          processor.setVolume(50)
          const restored = await rms(recordingStream)
          modes.push({ mode, initial, muted, restored, captureRequests, uploadedBytes, state })
        } finally {
          await uplink.stop(); await processor.release()
          amplitude.disconnect(input)
          input.stream.getTracks().forEach(track => track.stop())
        }
      }
      // Uplink stop owns capture; use a fresh synthetic track for the bypass.
      const bypassInput = context.createMediaStreamDestination()
      amplitude.connect(bypassInput)
      const processor = new MicrophoneProcessing(`/dist/assets/${worklet}`, () => {})
      const configurations = []
      const originalPost = MessagePort.prototype.postMessage
      MessagePort.prototype.postMessage = function (...args) {
        if (args[0]?.type === 'configure') configurations.push(args[0])
        return originalPost.apply(this, args)
      }
      try {
        const output = await processor.prepare(bypassInput.stream, { ...DEFAULT_MICROPHONE_PROCESSING, mode: 'deepfilter' }, 100)
        const track = output.getAudioTracks()[0]
        for (const voiceThreshold of [0.1, 0.9]) {
          processor.configure({ ...DEFAULT_MICROPHONE_PROCESSING, mode: 'deepfilter', voiceThreshold })
        }
        return { modes, configurations, trackAlive: track.readyState === 'live' && output.getAudioTracks()[0] === track }
      } finally {
        MessagePort.prototype.postMessage = originalPost
        await processor.release()
        bypassInput.stream.getTracks().forEach(track => track.stop())
      }
    } finally {
      oscillator.stop()
      await context.close()
    }
  }, worklet)
  for (const mode of result.modes) {
    assert.ok(mode.initial > 0.01, JSON.stringify(mode))
    assert.ok(mode.muted < 0.00001, JSON.stringify(mode))
    assert.ok(mode.restored > 0.001, JSON.stringify(mode))
    assert.equal(mode.captureRequests, 1)
    assert.ok(mode.uploadedBytes > 0, 'the real recorder uploaded encoded audio')
    assert.equal(mode.state, 'live')
  }
  assert.deepEqual(result.configurations.map(({ mode, voiceThreshold }) => ({ mode, voiceThreshold })), [
    { mode: 'voice', voiceThreshold: 0.1 }, { mode: 'voice', voiceThreshold: 0.9 },
  ])
  assert.equal(result.trackAlive, true)
  console.log('PASS real recorder mute/unmute in off/browser modes and live DeepFilter bypass thresholds', result)
} finally { await browser.close() }
