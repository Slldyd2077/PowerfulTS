import assert from 'node:assert/strict'
import test from 'node:test'
import {
  DEFAULT_MICROPHONE_PROCESSING,
  normalizeMicrophoneProcessing,
  microphoneConstraints,
} from '../src/services/microphone-processing-settings.js'
import { DenoiseFrames } from '../src/services/denoise-frames.js'
import { MicrophoneProcessing, type MicrophoneProcessingStatus } from '../src/services/microphone-processing.js'

test('invalid saved preferences restore safe defaults and clamp the voice threshold', () => {
  assert.deepEqual(normalizeMicrophoneProcessing(null), DEFAULT_MICROPHONE_PROCESSING)
  assert.deepEqual(normalizeMicrophoneProcessing({ mode: 'bad', echoCancellation: 'false' }), DEFAULT_MICROPHONE_PROCESSING)
  assert.equal(normalizeMicrophoneProcessing({ voiceThreshold: 2 }).voiceThreshold, 0.9)
  assert.equal(normalizeMicrophoneProcessing({ voiceThreshold: -1 }).voiceThreshold, 0.1)
  assert.equal(normalizeMicrophoneProcessing({ voiceThreshold: NaN }).voiceThreshold, 0.6)
  assert.equal(normalizeMicrophoneProcessing({ mode: 'off', keyboardSuppression: false }).mode, 'off')
})

test('capture retains browser noise suppression until the neural processor is ready', () => {
  const preferences = { ...DEFAULT_MICROPHONE_PROCESSING, echoCancellation: false, autoGainControl: false }
  assert.deepEqual(microphoneConstraints(preferences, 'mic-1'), {
    echoCancellation: false, autoGainControl: false, noiseSuppression: true,
    channelCount: 1, deviceId: { exact: 'mic-1' },
  })
  assert.equal(microphoneConstraints({ ...preferences, mode: 'off' }).noiseSuppression, false)
  assert.equal(microphoneConstraints({ ...preferences, mode: 'browser' }).noiseSuppression, true)
})

test('480-sample neural frames preserve continuous PCM across 128-sample render blocks', () => {
  const frames: Float32Array[] = []
  const dsp = new DenoiseFrames((frame) => { frames.push(frame.slice()); return 1 }, false, 0.6)
  const input = Float32Array.from({ length: 3840 }, (_, i) => (i % 100) / 200)
  const output = new Float32Array(input.length)
  for (let i = 0; i < input.length; i += 128) {
    dsp.process(input.subarray(i, i + 128), output.subarray(i, i + 128))
  }
  assert.equal(frames.length, 8)
  assert.equal(frames[0]![99], input[99]! * 32768)
  assert.deepEqual(output.slice(0, 480), new Float32Array(480))
  assert.deepEqual(output.slice(480), input.slice(0, -480))
})

test('neural output, rather than raw microphone samples, reaches the output', () => {
  const dsp = new DenoiseFrames((frame) => { frame.fill(8192); return 1 }, false, 0.6)
  const output = new Float32Array(960)
  dsp.process(new Float32Array(960).fill(1), output)
  assert.deepEqual(output.slice(480), new Float32Array(480).fill(0.25))
})

test('keyboard suppression closes for noise, retains speech tails and opens smoothly', () => {
  let probability = 0
  const dsp = new DenoiseFrames(() => probability, true, 0.6)
  const input = new Float32Array(480).fill(0.5)
  const output = new Float32Array(480)
  dsp.process(input, output)
  dsp.process(input, output)
  assert.ok(output.every((value) => value === 0))
  probability = 1
  dsp.process(input, output)
  dsp.process(input, output)
  assert.ok(output[479]! > 0.4)
  probability = 0
  for (let i = 0; i < 15; i++) dsp.process(input, output)
  assert.ok(output[479]! > 0.49, 'quiet syllables survive the hold period')
  for (let i = 0; i < 100; i++) dsp.process(input, output)
  assert.ok(output[479]! < 0.001)
  dsp.configure(false, 0.6)
  for (let i = 0; i < 5; i++) dsp.process(input, output)
  assert.ok(output[479]! > 0.49)
})

test('output clips oversized samples and treats absent input as silence', () => {
  const dsp = new DenoiseFrames((frame) => { frame.fill(65536); return 1 }, false, 0.6)
  dsp.process(undefined, new Float32Array(480))
  const output = new Float32Array(480)
  dsp.process(undefined, output)
  assert.ok(output.every((value) => value === 1))
})

function audioHarness() {
  class Track {
    stopped = false
    constraints: MediaTrackConstraints = { echoCancellation: true, autoGainControl: true }
    getConstraints() { return this.constraints }
    async applyConstraints(value: MediaTrackConstraints) { this.constraints = value }
    stop() { this.stopped = true }
  }
  class Stream {
    track = new Track()
    getAudioTracks() { return [this.track] }
    getTracks() { return [this.track] }
  }
  class Node {
    connections: Node[] = []
    connect(target: Node) { this.connections.push(target); return target }
    disconnect() { this.connections = [] }
  }
  class Gain extends Node {
    gain = { value: 1, setTargetAtTime: (value: number) => { this.gain.value = value } }
  }
  class Destination extends Node { stream = new Stream() }
  let failModule = false
  let failResume = false
  let nodeMessage = 'ready'
  let rejectConstraints = false
  let rejectConstruction = false
  let waitModule: Promise<void> | null = null
  class Context {
    static instances: Context[] = []
    state: AudioContextState = 'suspended'
    currentTime = 0
    source = new Node()
    gain = new Gain()
    output = new Destination()
    audioWorklet = { addModule: async () => {
      if (failModule) throw new Error('blocked by CSP')
      if (waitModule) await waitModule
    } }
    constructor() { if (rejectConstruction) throw new Error('AudioContext unavailable'); Context.instances.push(this) }
    createMediaStreamSource() { return this.source }
    createGain() { return this.gain }
    createMediaStreamDestination() { return this.output }
    async resume() { if (!failResume) this.state = 'running' }
    async close() { this.state = 'closed' }
  }
  class Worklet extends Node {
    static instances: Worklet[] = []
    port = {
      onmessage: null as ((event: { data: { type: string; message?: string } }) => void) | null,
      messages: [] as unknown[],
      postMessage: (value: unknown) => { this.port.messages.push(value) },
    }
    onprocessorerror: (() => void) | null = null
    constructor() {
      super()
      Worklet.instances.push(this)
      if (nodeMessage !== 'pending') queueMicrotask(() => this.port.onmessage?.({ data: { type: nodeMessage, message: 'model failed' } }))
    }
  }
  const originalContext = globalThis.AudioContext
  const originalWorklet = globalThis.AudioWorkletNode
  globalThis.AudioContext = Context as unknown as typeof AudioContext
  globalThis.AudioWorkletNode = Worklet as unknown as typeof AudioWorkletNode
  const stream = new Stream()
  const applyConstraints = stream.track.applyConstraints.bind(stream.track)
  stream.track.applyConstraints = async (value) => {
    if (rejectConstraints) throw new Error('constraint unsupported')
    await applyConstraints(value)
  }
  const statuses: MicrophoneProcessingStatus[] = []
  const processor = new MicrophoneProcessing('/model.js', (status) => statuses.push(status))
  return {
    processor, stream: stream as unknown as MediaStream, track: stream.track, statuses,
    contexts: Context.instances, nodes: Worklet.instances,
    failModule: () => { failModule = true },
    failResume: () => { failResume = true },
    failModel: () => { nodeMessage = 'error' },
    holdModel: () => { nodeMessage = 'pending' },
    failConstraints: () => { rejectConstraints = true },
    failConstruction: () => { rejectConstruction = true },
    delayModule: (promise: Promise<void>) => { waitModule = promise },
    restore: async () => {
      await processor.release()
      globalThis.AudioContext = originalContext
      globalThis.AudioWorkletNode = originalWorklet
    },
  }
}

test('off and browser mode at unity gain use the original capture stream', async () => {
  const h = audioHarness()
  try {
    for (const mode of ['off', 'browser'] as const) {
      assert.equal(await h.processor.prepare(h.stream, { ...DEFAULT_MICROPHONE_PROCESSING, mode }, 100), h.stream)
      assert.equal(h.statuses.at(-1)?.mode, mode)
    }
    assert.equal(h.contexts.length, 0)
    assert.equal(h.processor.setVolume(20), false)
  } finally { await h.restore() }
})

test('neural stream is wired to the recorder after initialization and preserves AEC/AGC constraints', async () => {
  const h = audioHarness()
  try {
    const output = await h.processor.prepare(h.stream, { ...DEFAULT_MICROPHONE_PROCESSING }, 80)
    const graph = h.contexts[0]!
    assert.equal(output, graph.output.stream)
    assert.equal(h.statuses.at(-1)?.mode, 'rnnoise')
    assert.deepEqual(h.track.constraints, { echoCancellation: true, autoGainControl: true, noiseSuppression: false })
    assert.equal(graph.source.connections[0], h.nodes[0])
    assert.equal(h.nodes[0]!.connections[0], graph.gain)
    assert.equal(graph.gain.connections[0], graph.output)
    assert.equal(h.processor.setVolume(120), true)
    assert.equal(graph.gain.gain.value, 1.2)
    h.processor.configure({ ...DEFAULT_MICROPHONE_PROCESSING, keyboardSuppression: false })
    assert.equal((h.nodes[0]!.port.messages[0] as { type: string }).type, 'configure')
    await h.processor.resume()
    await h.processor.release()
    assert.equal(graph.state, 'closed')
    assert.equal(graph.output.stream.track.stopped, true)
    assert.equal(h.track.stopped, false)
    assert.deepEqual(h.nodes[0]!.port.messages.at(-1), { type: 'destroy' })
  } finally { await h.restore() }
})

test('browser mode with manual gain uses a graph without loading the neural model', async () => {
  const h = audioHarness()
  try {
    await h.processor.prepare(h.stream, { ...DEFAULT_MICROPHONE_PROCESSING, mode: 'browser' }, 60)
    assert.equal(h.nodes.length, 0)
    assert.equal(h.contexts[0]!.gain.gain.value, 0.6)
    assert.equal(h.contexts[0]!.source.connections[0], h.contexts[0]!.gain)
  } finally { await h.restore() }
})

for (const failure of ['failModule', 'failResume', 'failModel'] as const) {
  test(`initialization failure (${failure}) falls back and releases audio resources`, async () => {
    const h = audioHarness()
    try {
      h[failure]()
      assert.equal(await h.processor.prepare(h.stream, { ...DEFAULT_MICROPHONE_PROCESSING }, 100), h.stream)
      assert.equal(h.contexts[0]!.state, 'closed')
      assert.equal(h.contexts[0]!.output.stream.track.stopped, true)
      assert.equal(h.statuses.at(-1)?.mode, 'browser')
      assert.ok(h.statuses.at(-1)?.message.includes('回退'))
    } finally { await h.restore() }
  })
}

test('runtime processor failure reconnects raw capture and restores browser suppression', async () => {
  const h = audioHarness()
  try {
    await h.processor.prepare(h.stream, { ...DEFAULT_MICROPHONE_PROCESSING }, 100)
    h.nodes[0]!.onprocessorerror?.()
    assert.equal(h.contexts[0]!.source.connections[0], h.contexts[0]!.gain)
    assert.deepEqual(h.track.constraints, { echoCancellation: true, autoGainControl: true, noiseSuppression: true })
    assert.equal(h.statuses.at(-1)?.mode, 'browser')
    h.nodes[0]!.onprocessorerror?.()
    assert.equal(h.contexts[0]!.source.connections.length, 1)
  } finally { await h.restore() }
})

test('stopping while the module loads cannot reconnect or publish a stale stream', async () => {
  const h = audioHarness()
  try {
    let finish!: () => void
    h.delayModule(new Promise<void>((resolve) => { finish = resolve }))
    const preparation = h.processor.prepare(h.stream, { ...DEFAULT_MICROPHONE_PROCESSING }, 100)
    await new Promise<void>((resolve) => setImmediate(resolve))
    await h.processor.release()
    finish()
    await assert.rejects(preparation, /取消/)
    assert.equal(h.statuses.at(-1)?.mode, 'idle')
    assert.equal(h.nodes.length, 0)
  } finally { await h.restore() }
})

test('unsupported constraints are visible and do not interrupt neural audio', async () => {
  const h = audioHarness()
  try {
    h.failConstraints()
    assert.notEqual(await h.processor.prepare(h.stream, { ...DEFAULT_MICROPHONE_PROCESSING }, 100), h.stream)
    assert.equal(h.statuses.at(-1)?.mode, 'rnnoise')
    assert.ok(h.statuses.at(-1)?.message.includes('未允许'))
    h.nodes[0]!.port.onmessage?.({ data: { type: 'error' } })
    await new Promise<void>((resolve) => setImmediate(resolve))
    assert.ok(h.statuses.at(-1)?.message.includes('恢复失败'))
  } finally { await h.restore() }
})

test('unavailable AudioContext and manual-gain failure keep capture usable', async () => {
  const h = audioHarness()
  try {
    h.failConstruction()
    assert.equal(await h.processor.prepare(h.stream, { ...DEFAULT_MICROPHONE_PROCESSING, mode: 'off' }, 80), h.stream)
    assert.equal(h.statuses.at(-1)?.mode, 'off')
    assert.ok(h.statuses.at(-1)?.message.includes('系统麦克风音量'))
  } finally { await h.restore() }
})

test('stopping during neural initialization rejects promptly and closes the graph', async () => {
  const h = audioHarness()
  try {
    h.holdModel()
    const preparation = h.processor.prepare(h.stream, { ...DEFAULT_MICROPHONE_PROCESSING }, 100)
    await new Promise<void>((resolve) => setImmediate(resolve))
    const rejected = assert.rejects(preparation, /取消/)
    await h.processor.release()
    await rejected
    assert.equal(h.contexts[0]!.state, 'closed')
    assert.equal(h.statuses.at(-1)?.mode, 'idle')
  } finally { await h.restore() }
})

test('an older asynchronous release cannot overwrite the status of a new preparation', async () => {
  const h = audioHarness()
  try {
    await h.processor.prepare(h.stream, { ...DEFAULT_MICROPHONE_PROCESSING }, 100)
    let finishClose!: () => void
    h.contexts[0]!.close = async () => {
      await new Promise<void>((resolve) => { finishClose = resolve })
      h.contexts[0]!.state = 'closed'
    }
    const releasing = h.processor.release()
    await h.processor.prepare(h.stream, { ...DEFAULT_MICROPHONE_PROCESSING, mode: 'off' }, 100)
    finishClose()
    await releasing
    assert.equal(h.statuses.at(-1)?.mode, 'off')
  } finally { await h.restore() }
})
