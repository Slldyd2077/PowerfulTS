import type { MicrophoneProcessingStatus } from './microphone-processing'

export type ModelMode = 'deepfilter' | 'spex' | 'combined'
export const VOICE_REFERENCE_KEY = 'voice_model_reference_v1'

function base64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192))
  return btoa(binary)
}

export async function prepareVoiceReference(file: File): Promise<string> {
  if (file.size > 20 * 1024 * 1024) throw new Error('参考录音文件最大 20 MB')
  const context = new AudioContext()
  try {
    const buffer = await context.decodeAudioData(await file.arrayBuffer())
    if (buffer.duration < 2 || buffer.duration > 15) throw new Error('参考录音需要 2–15 秒独立、清晰的本人讲话')
    const offline = new OfflineAudioContext(1, Math.round(buffer.duration * 48000), 48000)
    const source = offline.createBufferSource()
    source.buffer = buffer
    source.connect(offline.destination)
    source.start()
    const samples = (await offline.startRendering()).getChannelData(0)
    let energy = 0
    for (const value of samples) energy += value * value
    if (Math.sqrt(energy / samples.length) < 0.002) throw new Error('参考录音过小或无声，请重新录制')
    return base64(samples.slice().buffer)
  } finally { await context.close() }
}

/** Stateful DeepFilter stream; segmented target extraction. Fail closed. */
export class MicrophoneModel {
  private context: AudioContext | null = null
  private source: MediaStreamAudioSourceNode | null = null
  private node: AudioWorkletNode | null = null
  private gain: GainNode | null = null
  private output: MediaStreamAudioDestinationNode | null = null
  private controller: AbortController | null = null
  private generation = 0
  private socket: WebSocket | null = null
  private reconnectTimer: number | null = null
  private watchdog: number | null = null
  private handshakeTimer: number | null = null
  private cancelHandshake: (() => void) | null = null
  private readonly status: (status: MicrophoneProcessingStatus) => void
  private readonly availability: (available: boolean) => void
  constructor(status: (status: MicrophoneProcessingStatus) => void, availability = (_available: boolean) => {}) {
    this.status = status
    this.availability = availability
  }

  async prepare(stream: MediaStream, mode: ModelMode, volume: number): Promise<MediaStream> {
    await this.release()
    const generation = this.generation
    const reference = localStorage.getItem(VOICE_REFERENCE_KEY) || ''
    if (mode !== 'deepfilter' && !reference) throw new Error('请先上传目标人的参考录音，再启用目标提取')
    this.status({ mode: 'loading', message: '正在启动人声处理' })
    const context = this.context = new AudioContext({ sampleRate: 48000, latencyHint: 'interactive' })
    await context.resume()
    await context.audioWorklet.addModule(new URL('../workers/microphone-model-worklet.js', import.meta.url))
    if (generation !== this.generation) throw new Error('麦克风处理已取消')
    const node = this.node = new AudioWorkletNode(context, 'microphone-model', {
      outputChannelCount: [1], channelCount: 1, channelCountMode: 'explicit',
      processorOptions: { blockSize: mode === 'deepfilter' ? 960 : 96000, streaming: mode === 'deepfilter' },
    })
    this.source = context.createMediaStreamSource(stream)
    this.gain = context.createGain()
    this.gain.gain.value = volume / 100
    this.output = context.createMediaStreamDestination()
    this.source.connect(node).connect(this.gain).connect(this.output)
    if (mode === 'deepfilter') {
      // Keep the output track alive while the model starts/reconnects. The
      // parent graph supplies local processing until actual PCM is available.
      void this.startStream(node, generation).catch(() => {})
      return this.output!.stream
    }
    let busy = false
    const referenceId = crypto.randomUUID()
    let enrolled = false
    node.port.onmessage = async ({ data }) => {
      if (data.type !== 'capture' || generation !== this.generation) return
      if (busy) {
        this.status({ mode, message: '模型处理跟不上，已丢弃积压音频；可切回本地人声增强' })
        return
      }
      busy = true
      const controller = this.controller = new AbortController()
      const timeout = window.setTimeout(() => controller.abort(), 12000)
      try {
        const response = await fetch('/api/voice-processing/pcm', {
          method: 'POST', signal: controller.signal,
          headers: { 'Content-Type': 'application/json', 'X-Session-Token': localStorage.getItem('session_token') || '' },
          body: JSON.stringify({ mode, pcm: base64(data.buffer), referenceId, ...(!enrolled ? { reference } : {}) }),
        })
        if (!response.ok) {
          const error = await response.json().catch(() => ({}))
          throw new Error(error.detail || '模型处理失败')
        }
        const buffer = await response.arrayBuffer()
        if (buffer.byteLength !== data.buffer.byteLength) throw new Error('模型输出无效')
        if (generation !== this.generation) return
        enrolled = true
        node.port.postMessage({ type: 'pcm', buffer }, [buffer])
        this.status({ mode, message: '' })
      } catch (error) {
        enrolled = false
        if (generation === this.generation) this.status({ mode, message: `${error instanceof Error ? error.message : '模型不可用'}；暂停发送声音，请切回本地人声增强或恢复模型服务` })
      } finally {
        clearTimeout(timeout)
        if (this.controller === controller) this.controller = null
        busy = false
      }
    }
    this.status({ mode, message: '等待第一段音频；处理失败时不会发送未经处理的麦克风声音' })
    return this.output.stream
  }

  private async startStream(node: AudioWorkletNode, generation: number): Promise<void> {
    let ready = false
    let pending = 0
    let lastResponse = performance.now()
    let attempts = 0
    let received = 0
    const reset = () => {
      ready = false
      pending = 0
      received = 0
      this.availability(false)
      node.port.postMessage({ type: 'reset' })
    }
    const open = (): Promise<void> => new Promise((resolve, reject) => {
      if (generation !== this.generation) return reject(new Error('麦克风处理已取消'))
      reset()
      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
      const socket = this.socket = new WebSocket(`${protocol}//${location.host}/api/voice-processing/stream`)
      socket.binaryType = 'arraybuffer'
      let initialized = false
      const timeout = window.setTimeout(() => socket.close(), 30000)
      this.handshakeTimer = timeout
      this.cancelHandshake = () => reject(new Error('麦克风处理已取消'))
      socket.onopen = () => socket.send(JSON.stringify({ token: localStorage.getItem('session_token') || '' }))
      socket.onmessage = ({ data }) => {
        if (generation !== this.generation || socket !== this.socket) return
        if (typeof data === 'string') {
          try {
            if (JSON.parse(data).ready !== true) return
          } catch { socket.close(); return }
          ready = initialized = true
          lastResponse = performance.now()
          clearTimeout(timeout)
          this.handshakeTimer = null
          this.cancelHandshake = null
          this.status({ mode: 'deepfilter', message: '' })
          resolve()
          return
        }
        if (!ready || !(data instanceof ArrayBuffer) || data.byteLength !== 1920 || pending <= 0) {
          socket.close(); return
        }
        pending--
        if (++received >= 100) attempts = 0
        lastResponse = performance.now()
        const input = new Int16Array(data)
        const pcm = Float32Array.from(input, value => value / 32768)
        node.port.postMessage({ type: 'pcm', buffer: pcm.buffer }, [pcm.buffer])
      }
      socket.onclose = (event) => {
        clearTimeout(timeout)
        if (generation !== this.generation || socket !== this.socket) return
        this.handshakeTimer = null
        this.cancelHandshake = null
        reset()
        if (!initialized) reject(new Error(event.reason || '无法连接人声处理服务'))
        if (event.code !== 4401) {
          this.status({ mode: 'deepfilter', message: '人声处理重连中…' })
          this.reconnectTimer = window.setTimeout(() => {
            this.reconnectTimer = null
            void open().catch(() => { /* onclose handles bounded retries */ })
          }, event.code === 4429 ? 10000 : Math.min(30000, 500 * 2 ** Math.min(attempts++, 6)))
        } else {
          this.status({ mode: 'deepfilter', message: '人声处理已暂停，请重新开启麦克风或切换本地增强' })
        }
      }
      socket.onerror = () => socket.close()
    })
    node.port.onmessage = ({ data }) => {
      if (data.type === 'availability' && generation === this.generation) {
        this.availability(data.available === true)
        return
      }
      if (data.type !== 'capture' || generation !== this.generation || !ready) return
      // Allow a brief public-network jitter burst, but bound outstanding audio.
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return
      if (pending >= 15 || this.socket.bufferedAmount > 28800) {
        reset(); this.socket.close(); return
      }
      const pcm = Float32Array.from(new Float32Array(data.buffer), value => Math.max(-1, Math.min(1, value)))
      const binary = Int16Array.from(pcm, value => Math.round(value * 32767))
      this.socket.send(binary.buffer)
      pending++
    }
    this.watchdog = window.setInterval(() => {
      if (ready && pending > 0 && performance.now() - lastResponse > 1000) {
        reset(); this.socket?.close()
      }
    }, 250)
    await open()
  }

  setVolume(percent: number): boolean {
    if (!this.gain || !this.context) return false
    this.gain.gain.setTargetAtTime(percent / 100, this.context.currentTime, 0.015)
    return true
  }
  resume() { return this.context?.resume() }
  async release() {
    this.generation++
    this.cancelHandshake?.()
    this.cancelHandshake = null
    if (this.handshakeTimer !== null) clearTimeout(this.handshakeTimer)
    this.handshakeTimer = null
    if (this.reconnectTimer !== null) clearTimeout(this.reconnectTimer)
    if (this.watchdog !== null) clearInterval(this.watchdog)
    this.reconnectTimer = this.watchdog = null
    if (this.socket) {
      this.socket.onclose = this.socket.onmessage = this.socket.onopen = this.socket.onerror = null
      this.socket.close()
      this.socket = null
    }
    this.controller?.abort()
    this.controller = null
    this.source?.disconnect()
    if (this.node) this.node.port.onmessage = null
    this.node?.disconnect()
    this.gain?.disconnect()
    this.output?.stream.getTracks().forEach(track => track.stop())
    this.output?.disconnect()
    const context = this.context
    this.source = this.node = this.gain = this.output = this.context = null
    if (context && context.state !== 'closed') await context.close()
  }
}
