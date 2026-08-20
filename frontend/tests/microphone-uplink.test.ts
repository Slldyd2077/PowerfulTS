import assert from 'node:assert/strict'
import test from 'node:test'

import {
  chooseSupportedMicrophoneMimeType,
  MicrophoneUplink,
  type MicrophoneRecorder,
  type MicrophoneSocket,
  type MicrophoneUplinkDependencies,
  type MicrophoneUplinkState,
} from '../src/services/microphone-uplink.js'

test('falls back to the Safari audio/mp4 recorder format', () => {
  const selected = chooseSupportedMicrophoneMimeType((mimeType) => mimeType === 'audio/mp4')
  assert.equal(selected, 'audio/mp4')
})

class FakeTrack {
  readyState: MediaStreamTrackState = 'live'
  stopCalls = 0

  stop() {
    this.stopCalls++
    this.readyState = 'ended'
  }
}

class FakeStream {
  readonly track = new FakeTrack()

  getAudioTracks() {
    return [this.track as unknown as MediaStreamTrack]
  }

  getTracks() {
    return this.getAudioTracks()
  }
}

class FakeSocket implements MicrophoneSocket {
  static readonly OPEN = 1
  readyState = 0
  sent: Blob[] = []
  throwOnSend = false
  onopen: (() => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: (() => void) | null = null

  open() {
    this.readyState = FakeSocket.OPEN
    this.onopen?.()
  }

  disconnect() {
    this.readyState = 3
    this.onclose?.({ code: 1006, reason: '' } as CloseEvent)
  }

  send(data: Blob) {
    if (this.throwOnSend) throw new Error('network down')
    this.sent.push(data)
  }

  close() {
    this.readyState = 3
  }
}

class FakeRecorder implements MicrophoneRecorder {
  state: RecordingState = 'inactive'
  ondataavailable: ((event: BlobEvent) => void) | null = null
  onerror: (() => void) | null = null

  start() {
    this.state = 'recording'
  }

  stop() {
    this.state = 'inactive'
  }

  emitChunk(size = 8) {
    this.ondataavailable?.({ data: new Blob([new Uint8Array(size)]) } as BlobEvent)
  }
}

function createHarness() {
  const stream = new FakeStream()
  const sockets: FakeSocket[] = []
  const recorders: FakeRecorder[] = []
  const states: MicrophoneUplinkState[] = []
  const timers = new Map<number, () => void>()
  const stoppedSessions: string[] = []
  const warnings: string[] = []
  const errors: string[] = []
  let preparedReleases = 0
  let sessionStarts = 0
  let captureRequests = 0
  let recoveryAllowed = true
  let failSessionStart = false
  let failSocketCreate = false
  let pendingPrepare: ((stream: MediaStream) => void) | null = null

  const dependencies: MicrophoneUplinkDependencies = {
    acquireStream: async () => {
      captureRequests++
      return stream as unknown as MediaStream
    },
    prepareStream: async (raw) => {
      if (!pendingPrepare) return raw
      return new Promise((resolve) => { pendingPrepare = resolve })
    },
    releasePreparedStream: async () => { preparedReleases++ },
    chooseMimeType: () => 'audio/webm;codecs=opus',
    startSession: async () => {
      if (failSessionStart) throw new Error('session unavailable')
      sessionStarts++
      return { sessionId: `session-${sessionStarts}`, uploadPath: `/upload/${sessionStarts}` }
    },
    stopSession: async (sessionId) => { stoppedSessions.push(sessionId) },
    createSocket: () => {
      if (failSocketCreate) throw new Error('socket unavailable')
      const socket = new FakeSocket()
      sockets.push(socket)
      return socket
    },
    createRecorder: () => {
      const recorder = new FakeRecorder()
      recorders.push(recorder)
      return recorder
    },
    isRecoveryAllowed: () => recoveryAllowed,
    setTimer: (callback) => {
      const id = timers.size ? Math.max(...timers.keys()) + 1 : 1
      timers.set(id, callback)
      return id
    },
    clearTimer: (timer) => { timers.delete(timer) },
    onStateChange: (state) => states.push(state),
    onWarning: (message) => { warnings.push(message) },
    onError: (message) => { errors.push(message) },
  }

  return {
    stream,
    sockets,
    recorders,
    states,
    timers,
    stoppedSessions,
    warnings,
    errors,
    get preparedReleases() { return preparedReleases },
    get captureRequests() { return captureRequests },
    get sessionStarts() { return sessionStarts },
    setRecoveryAllowed(value: boolean) { recoveryAllowed = value },
    failSessionStart() { failSessionStart = true },
    failSocketCreate() { failSocketCreate = true },
    holdPrepare() { pendingPrepare = () => {} },
    releasePrepare() {
      const resolve = pendingPrepare
      pendingPrepare = null
      resolve?.(stream as unknown as MediaStream)
    },
    runNextTimer() {
      const next = timers.entries().next().value as [number, () => void] | undefined
      if (!next) return
      timers.delete(next[0])
      next[1]()
    },
    uplink: new MicrophoneUplink(dependencies),
  }
}

async function waitFor(predicate: () => boolean): Promise<void> {
  for (let attempt = 0; attempt < 20; attempt++) {
    if (predicate()) return
    await new Promise((resolve) => setImmediate(resolve))
  }
  throw new Error('condition was not reached')
}

test('does not report live before the first non-empty chunk is uploaded', async () => {
  const harness = createHarness()

  const starting = harness.uplink.start()
  await waitFor(() => harness.sockets.length === 1)
  harness.sockets[0]!.open()
  await starting

  assert.equal(harness.uplink.state, 'verifying')
  assert.equal(harness.states.includes('live'), false)

  harness.recorders[0]!.emitChunk()

  assert.equal(harness.uplink.state, 'live')
  assert.equal(harness.sockets[0]!.sent.length, 1)
})

test('recovers a transient socket close without requesting microphone permission again', async () => {
  const harness = createHarness()

  const starting = harness.uplink.start()
  await waitFor(() => harness.sockets.length === 1)
  harness.sockets[0]!.open()
  await starting
  harness.recorders[0]!.emitChunk()
  assert.equal(harness.uplink.state, 'live')

  harness.sockets[0]!.disconnect()
  await waitFor(() => harness.uplink.state === 'reconnecting')
  assert.equal(harness.uplink.state, 'reconnecting')

  harness.runNextTimer()
  await waitFor(() => harness.sockets.length === 2)
  harness.sockets[1]!.open()
  await Promise.resolve()
  harness.recorders[1]!.emitChunk()

  assert.equal(harness.uplink.state, 'live')
  assert.equal(harness.captureRequests, 1)
  assert.equal(harness.sessionStarts, 2)
})

test('defers reconnect attempts while hidden or offline and resumes on foreground', async () => {
  const harness = createHarness()
  const starting = harness.uplink.start()
  await waitFor(() => harness.sockets.length === 1)
  harness.sockets[0]!.open()
  await starting
  harness.recorders[0]!.emitChunk()

  harness.setRecoveryAllowed(false)
  harness.sockets[0]!.disconnect()
  await waitFor(() => harness.uplink.state === 'reconnecting')

  assert.equal(harness.uplink.state, 'reconnecting')
  assert.equal(harness.timers.size, 0)
  assert.equal(harness.sessionStarts, 1)

  harness.setRecoveryAllowed(true)
  const recovery = harness.uplink.recover()
  await waitFor(() => harness.sockets.length === 2)
  harness.sockets[1]!.open()
  await recovery
  harness.recorders[1]!.emitChunk()

  assert.equal(harness.uplink.state, 'live')
  assert.equal(harness.captureRequests, 1)
})

test('times out a recorder that never produces a chunk and schedules recovery', async () => {
  const harness = createHarness()
  const starting = harness.uplink.start()
  await waitFor(() => harness.sockets.length === 1)
  harness.sockets[0]!.open()
  await starting

  assert.equal(harness.uplink.state, 'verifying')
  harness.runNextTimer()
  await waitFor(() => harness.uplink.state === 'reconnecting')

  assert.equal(harness.warnings.includes('麦克风没有产生音频数据，正在重连'), true)
  assert.equal(harness.captureRequests, 1)
})

test('stops the relay, recorder, socket and capture track exactly once', async () => {
  const harness = createHarness()
  const starting = harness.uplink.start()
  await waitFor(() => harness.sockets.length === 1)
  harness.sockets[0]!.open()
  await starting
  harness.recorders[0]!.emitChunk()

  await harness.uplink.stop()
  await harness.uplink.stop()

  assert.equal(harness.uplink.state, 'idle')
  assert.equal(harness.stream.track.stopCalls, 1)
  assert.equal(harness.recorders[0]!.state, 'inactive')
  assert.deepEqual(harness.stoppedSessions, ['session-1'])
})

test('rejects an ended capture track instead of opening a false-live relay', async () => {
  const harness = createHarness()
  harness.stream.track.readyState = 'ended'

  await assert.rejects(harness.uplink.start(), /没有可用的麦克风音轨/)

  assert.equal(harness.uplink.state, 'idle')
  assert.equal(harness.sessionStarts, 0)
  assert.equal(harness.errors.some((message) => message.includes('没有可用的麦克风音轨')), true)
})

test('cleans up when the upload socket closes before it opens', async () => {
  const harness = createHarness()
  const starting = harness.uplink.start()
  await waitFor(() => harness.sockets.length === 1)
  harness.sockets[0]!.disconnect()

  await assert.rejects(starting, /建立前已关闭/)

  assert.equal(harness.uplink.state, 'idle')
  assert.equal(harness.stream.track.stopCalls, 1)
  assert.deepEqual(harness.stoppedSessions, ['session-1'])
})

test('cleans up a reconnect session whose socket closes before opening', async () => {
  const harness = createHarness()
  const starting = harness.uplink.start()
  await waitFor(() => harness.sockets.length === 1)
  harness.sockets[0]!.open()
  await starting
  harness.recorders[0]!.emitChunk()
  harness.sockets[0]!.disconnect()
  await waitFor(() => harness.uplink.state === 'reconnecting')

  harness.runNextTimer()
  await waitFor(() => harness.sockets.length === 2)
  harness.sockets[1]!.disconnect()
  await waitFor(() => harness.stoppedSessions.includes('session-2'))

  assert.equal(harness.uplink.state, 'reconnecting')
  assert.deepEqual(harness.stoppedSessions.slice(0, 2), ['session-1', 'session-2'])
  assert.equal(harness.captureRequests, 1)
})

test('waits for an in-flight connection before restarting its transport', async () => {
  const harness = createHarness()
  const starting = harness.uplink.start()
  await waitFor(() => harness.sockets.length === 1)

  const restarting = harness.uplink.restartTransport()
  harness.sockets[0]!.open()
  await starting
  await waitFor(() => harness.sockets.length === 2)
  harness.sockets[1]!.open()
  await restarting
  harness.recorders[1]!.emitChunk()

  assert.equal(harness.uplink.state, 'live')
  assert.equal(harness.captureRequests, 1)
  assert.equal(harness.sessionStarts, 2)
  assert.deepEqual(harness.stoppedSessions, ['session-1'])
})

test('recovers when a chunk cannot be sent on a stale mobile socket', async () => {
  const harness = createHarness()
  const starting = harness.uplink.start()
  await waitFor(() => harness.sockets.length === 1)
  harness.sockets[0]!.open()
  await starting

  harness.sockets[0]!.throwOnSend = true
  assert.doesNotThrow(() => harness.recorders[0]!.emitChunk())
  await waitFor(() => harness.uplink.state === 'reconnecting')

  assert.equal(harness.warnings.includes('麦克风连接已中断，正在重连'), true)
  harness.runNextTimer()
  await waitFor(() => harness.sockets.length === 2)
  harness.sockets[1]!.open()
  await Promise.resolve()
  harness.recorders[1]!.emitChunk()

  assert.equal(harness.uplink.state, 'live')
  assert.equal(harness.captureRequests, 1)
})

test('releases prepared capture when the server refuses a microphone session', async () => {
  const harness = createHarness()
  harness.failSessionStart()

  await assert.rejects(harness.uplink.start(), /session unavailable/)

  assert.equal(harness.uplink.state, 'idle')
  assert.equal(harness.stream.track.stopCalls, 1)
  assert.equal(harness.preparedReleases, 1)
  assert.deepEqual(harness.stoppedSessions, [])
})

test('releases prepared capture when stopped during async stream preparation', async () => {
  const harness = createHarness()
  harness.holdPrepare()
  const starting = harness.uplink.start()
  await waitFor(() => harness.captureRequests === 1)

  await harness.uplink.stop()
  harness.releasePrepare()
  await starting

  assert.equal(harness.uplink.state, 'idle')
  assert.equal(harness.stream.track.stopCalls, 1)
  assert.equal(harness.preparedReleases, 1)
  assert.deepEqual(harness.stoppedSessions, [])
})

test('releases prepared capture and stops the session when socket creation fails', async () => {
  const harness = createHarness()
  harness.failSocketCreate()

  await assert.rejects(harness.uplink.start(), /socket unavailable/)

  assert.equal(harness.uplink.state, 'idle')
  assert.equal(harness.stream.track.stopCalls, 1)
  assert.equal(harness.preparedReleases, 1)
  assert.deepEqual(harness.stoppedSessions, ['session-1'])
})
