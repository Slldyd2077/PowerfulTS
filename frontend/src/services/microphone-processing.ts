import type { MicrophoneProcessingSettings, NoiseSuppressionMode } from './microphone-processing-settings'

export interface MicrophoneProcessingStatus {
  mode: NoiseSuppressionMode | 'idle' | 'loading'
  message: string
}

interface AudioGraph {
  context: AudioContext
  source: MediaStreamAudioSourceNode
  gain: GainNode
  output: MediaStreamAudioDestinationNode
  denoiser?: AudioWorkletNode
  cancelInitialization?: () => void
}

async function setBrowserSuppression(stream: MediaStream, enabled: boolean) {
  const track = stream.getAudioTracks()[0]
  if (track) await track.applyConstraints({ ...track.getConstraints(), noiseSuppression: enabled })
}

function waitForGraph(graph: AudioGraph, operation: Promise<void>, message: string, timeoutMs = 8000): Promise<void> {
  return new Promise((resolve, reject) => {
    let settled = false
    const timer = setTimeout(() => finish(new Error(message)), timeoutMs)
    function finish(error?: unknown) {
      if (settled) return
      settled = true
      clearTimeout(timer)
      graph.cancelInitialization = undefined
      if (error) reject(error)
      else resolve()
    }
    graph.cancelInitialization = () => finish(new Error('麦克风处理已取消'))
    operation.then(() => finish(), finish)
  })
}

/** Owns only the processed stream; the uplink controller owns the capture tracks. */
export class MicrophoneProcessing {
  private graph: AudioGraph | null = null
  private generation = 0
  private readonly workletUrl: string
  private readonly onStatus: (status: MicrophoneProcessingStatus) => void

  constructor(workletUrl: string, onStatus: (status: MicrophoneProcessingStatus) => void) {
    this.workletUrl = workletUrl
    this.onStatus = onStatus
  }

  setVolume(percent: number): boolean {
    if (!this.graph) return false
    this.graph.gain.gain.setTargetAtTime(percent / 100, this.graph.context.currentTime, 0.015)
    return true
  }

  configure(settings: MicrophoneProcessingSettings) {
    this.graph?.denoiser?.port.postMessage({ type: 'configure', ...settings })
  }

  resume() {
    return this.graph?.context.resume()
  }

  async prepare(stream: MediaStream, settings: MicrophoneProcessingSettings, volume: number): Promise<MediaStream> {
    const releasing = this.release()
    const generation = this.generation
    await releasing
    if (generation !== this.generation) throw new Error('麦克风处理已取消')
    const needsDenoiser = settings.mode === 'rnnoise'
    if (!needsDenoiser && volume === 100) {
      this.onStatus({ mode: settings.mode, message: '' })
      return stream
    }
    let context: AudioContext | null = null
    try {
      context = new AudioContext({ latencyHint: 'interactive', ...(needsDenoiser ? { sampleRate: 48000 } : {}) })
      const graph: AudioGraph = {
        context,
        source: context.createMediaStreamSource(stream),
        gain: context.createGain(),
        output: context.createMediaStreamDestination(),
      }
      this.graph = graph
      graph.gain.gain.value = volume / 100
      graph.gain.connect(graph.output)
      await waitForGraph(graph, context.resume(), '音频处理线程启动超时', 5000)
      if (generation !== this.generation) throw new Error('麦克风处理已取消')
      if (context.state !== 'running') throw new Error('音频处理线程未运行')
      if (needsDenoiser) {
        this.onStatus({ mode: 'loading', message: '' })
        await waitForGraph(graph, context.audioWorklet.addModule(this.workletUrl), '降噪模块加载超时')
        if (generation !== this.generation) throw new Error('麦克风处理已取消')
        graph.denoiser = new AudioWorkletNode(context, 'microphone-denoise', {
          numberOfInputs: 1, numberOfOutputs: 1,
          outputChannelCount: [1], channelCount: 1, channelCountMode: 'explicit',
          processorOptions: settings,
        })
        await waitForGraph(graph, new Promise<void>((resolve, reject) => {
          graph.denoiser!.port.onmessage = ({ data }) => {
            if (data?.type === 'ready') resolve()
            if (data?.type === 'error') reject(new Error(data.message))
          }
          graph.denoiser!.onprocessorerror = () => reject(new Error('降噪线程启动失败'))
        }), '降噪模型初始化超时')
        if (generation !== this.generation) throw new Error('麦克风处理已取消')
        // AEC and AGC remain at capture; avoid cascading two noise suppressors.
        let constraintNote = ''
        await setBrowserSuppression(stream, false).catch(() => {
          constraintNote = '浏览器未允许关闭基础降噪，智能降噪仍在运行'
        })
        if (generation !== this.generation) throw new Error('麦克风处理已取消')
        graph.source.connect(graph.denoiser).connect(graph.gain)
        const fallback = () => {
          if (this.graph !== graph || !graph.denoiser) return
          graph.source.disconnect()
          graph.denoiser.port.postMessage({ type: 'destroy' })
          graph.denoiser.disconnect()
          graph.denoiser = undefined
          graph.source.connect(graph.gain)
          this.onStatus({ mode: 'browser', message: '智能降噪线程中断，已回退到浏览器基础降噪' })
          void setBrowserSuppression(stream, true).then(() => {
            if (this.graph === graph) this.onStatus({ mode: 'browser', message: '智能降噪线程中断，已回退到浏览器基础降噪' })
          }).catch(() => {
            if (this.graph === graph) this.onStatus({ mode: 'browser', message: '智能降噪线程中断，浏览器基础降噪恢复失败；请重新开启麦克风' })
          })
        }
        graph.denoiser.port.onmessage = ({ data }) => { if (data?.type === 'error') fallback() }
        graph.denoiser.onprocessorerror = fallback
        this.onStatus({ mode: 'rnnoise', message: constraintNote })
      } else {
        graph.source.connect(graph.gain)
        this.onStatus({ mode: settings.mode, message: '' })
      }
      if (generation !== this.generation) throw new Error('麦克风处理已取消')
      return graph.output.stream
    } catch (error) {
      if (generation !== this.generation) throw error
      console.warn('Microphone audio processing unavailable', error)
      const releasing = this.release()
      const fallbackGeneration = this.generation
      await releasing
      if (fallbackGeneration !== this.generation) throw new Error('麦克风处理已取消')
      if (needsDenoiser) await setBrowserSuppression(stream, true).catch(() => {})
      if (context && context.state !== 'closed') await context.close().catch(() => {})
      if (fallbackGeneration !== this.generation) throw new Error('麦克风处理已取消')
      this.onStatus({
        mode: needsDenoiser ? 'browser' : settings.mode,
        message: needsDenoiser
          ? '智能降噪不可用，已回退到浏览器基础降噪；网页麦克风增益暂不可用'
          : '网页麦克风增益不可用，已使用系统麦克风音量',
      })
      return stream
    }
  }

  async release() {
    const generation = ++this.generation
    const graph = this.graph
    this.graph = null
    if (graph) {
      graph.cancelInitialization?.()
      graph.denoiser?.port.postMessage({ type: 'destroy' })
      graph.denoiser?.disconnect()
      graph.source.disconnect()
      graph.gain.disconnect()
      graph.output.disconnect()
      graph.output.stream.getTracks().forEach((track) => track.stop())
      await graph.context.close().catch(() => {})
    }
    if (generation === this.generation) this.onStatus({ mode: 'idle', message: '' })
  }
}
