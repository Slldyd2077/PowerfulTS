import type { MicrophoneProcessingSettings, NoiseSuppressionMode } from './microphone-processing-settings'
import { resumeVoiceAudio } from './audio-context-state.js'
import { MicrophoneModel } from './microphone-model.js'

export interface MicrophoneProcessingStatus {
  mode: NoiseSuppressionMode | 'idle' | 'loading'
  message: string
}

interface AudioGraph {
  context: AudioContext
  source: MediaStreamAudioSourceNode
  compressor: DynamicsCompressorNode | null
  gain: GainNode
  output: MediaStreamAudioDestinationNode
  denoiser?: AudioWorkletNode
  cancelInitialization?: () => void
}

interface ModelBypass {
  context: AudioContext
  local: MicrophoneProcessing
  localSource: MediaStreamAudioSourceNode
  modelSource?: MediaStreamAudioSourceNode
  localGain: GainNode
  modelGain: GainNode
  gain: GainNode
  output: MediaStreamAudioDestinationNode
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
  private unlockedContext: AudioContext | null = null
  private model: MicrophoneModel | null = null
  private bypass: ModelBypass | null = null
  private readonly workletUrl: string
  private readonly onStatus: (status: MicrophoneProcessingStatus) => void
  private readonly onActivity: (speaking: boolean) => void

  constructor(workletUrl: string, onStatus: (status: MicrophoneProcessingStatus) => void, onActivity: (speaking: boolean) => void = () => {}) {
    this.workletUrl = workletUrl
    this.onStatus = onStatus
    this.onActivity = onActivity
  }

  /** Call directly from the tap, before permission/network awaits consume activation. */
  unlock(fresh = false) {
    try {
      const context = (!fresh && this.graph?.context) || (this.unlockedContext ??= new AudioContext({ latencyHint: 'interactive', sampleRate: 48000 }))
      void context.resume().catch(() => {})
    } catch { /* prepare reports failure and falls back to capture. */ }
  }

  get running(): boolean { return this.graph?.context.state === 'running' || !this.graph }

  setVolume(percent: number): boolean {
    if (this.bypass) {
      this.bypass.gain.gain.setTargetAtTime(percent / 100, this.bypass.context.currentTime, .015)
      return true
    }
    if (this.model) return this.model.setVolume(percent)
    if (!this.graph) return false
    this.graph.gain.gain.setTargetAtTime(percent / 100, this.graph.context.currentTime, 0.015)
    return true
  }

  configure(settings: MicrophoneProcessingSettings) {
    this.graph?.denoiser?.port.postMessage({ type: 'configure', ...settings })
  }

  resume(): Promise<void> | undefined {
    if (this.bypass) return Promise.all([
      resumeVoiceAudio(this.bypass.context), this.bypass.local.resume(), this.model?.resume(),
    ]).then(() => {})
    return this.model ? this.model.resume() : this.graph ? resumeVoiceAudio(this.graph.context) : undefined
  }

  async prepare(stream: MediaStream, settings: MicrophoneProcessingSettings, volume: number): Promise<MediaStream> {
    const unlocked = this.unlockedContext
    this.unlockedContext = null
    const releasing = this.release()
    const generation = this.generation
    await releasing
    if (generation !== this.generation) {
      await unlocked?.close().catch(() => {})
      throw new Error('麦克风处理已取消')
    }
    if (settings.mode === 'deepfilter') return this.prepareWithBypass(stream, settings, volume, generation, unlocked)
    if (settings.mode === 'spex' || settings.mode === 'combined') {
      await unlocked?.close().catch(() => {})
      const model = this.model = new MicrophoneModel(this.onStatus)
      try {
        const output = await model.prepare(stream, settings.mode, volume)
        if (generation !== this.generation) throw new Error('麦克风处理已取消')
        await setBrowserSuppression(stream, false).catch(() => {})
        return output
      } catch (error) {
        await model.release()
        if (this.model === model) this.model = null
        throw error
      }
    }
    const needsDenoiser = settings.mode === 'rnnoise' || settings.mode === 'voice'
    if (!needsDenoiser && volume === 100) {
      await unlocked?.close().catch(() => {})
      this.onStatus({ mode: settings.mode, message: '' })
      return stream
    }
    let context: AudioContext | null = null
    try {
      context = unlocked ?? new AudioContext({ latencyHint: 'interactive', ...(needsDenoiser ? { sampleRate: 48000 } : {}) })
      const graph: AudioGraph = {
        context,
        source: context.createMediaStreamSource(stream),
        compressor: typeof context.createDynamicsCompressor === 'function'
          ? context.createDynamicsCompressor()
          : null,
        gain: context.createGain(),
        output: context.createMediaStreamDestination(),
      }
      this.graph = graph
      graph.gain.gain.value = volume / 100
      graph.gain.connect(graph.output)
      // Keep speech intelligible on variable mobile microphones without
      // aggressively changing dynamics or increasing background noise.
      if (graph.compressor) {
        graph.compressor.threshold.value = settings.mode === 'voice' ? -30 : -35
        graph.compressor.knee.value = 18
        graph.compressor.ratio.value = settings.mode === 'voice' ? 3 : 2
        graph.compressor.attack.value = 0.008
        graph.compressor.release.value = 0.12
        graph.compressor.connect(graph.gain)
      }
      const processingTarget = graph.compressor ?? graph.gain
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
        graph.source.connect(graph.denoiser).connect(processingTarget)
        const fallback = () => {
          if (this.graph !== graph || !graph.denoiser) return
          graph.source.disconnect()
          graph.denoiser.port.postMessage({ type: 'destroy' })
          graph.denoiser.disconnect()
          graph.denoiser = undefined
          graph.source.connect(processingTarget)
          this.onStatus({ mode: 'browser', message: '智能降噪线程中断，已回退到浏览器基础降噪' })
          void setBrowserSuppression(stream, true).then(() => {
            if (this.graph === graph) this.onStatus({ mode: 'browser', message: '智能降噪线程中断，已回退到浏览器基础降噪' })
          }).catch(() => {
            if (this.graph === graph) this.onStatus({ mode: 'browser', message: '智能降噪线程中断，浏览器基础降噪恢复失败；请重新开启麦克风' })
          })
        }
        graph.denoiser.port.onmessage = ({ data }) => {
          if (data?.type === 'error') fallback()
          if (data?.type === 'voice-activity' && this.graph === graph) this.onActivity(data.speaking === true)
        }
        graph.denoiser.onprocessorerror = fallback
        this.onStatus({ mode: settings.mode, message: constraintNote })
      } else {
        graph.source.connect(processingTarget)
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

  private async prepareWithBypass(stream: MediaStream, settings: MicrophoneProcessingSettings,
    volume: number, generation: number, unlocked: AudioContext | null = null): Promise<MediaStream> {
    let available = false
    let localMode: MicrophoneProcessingStatus['mode'] = 'voice'
    let modelMessage = '人声模型启动中'
    const report = () => {
      if (generation !== this.generation) return
      this.onStatus(available ? { mode: 'deepfilter', message: '' } : {
        mode: localMode,
        message: `${modelMessage || '人声模型缓冲中'}，已使用本地音频旁路，通话保持连接`,
      })
    }
    const context = unlocked ?? new AudioContext({ sampleRate: 48000, latencyHint: 'interactive' })
    const local = new MicrophoneProcessing(this.workletUrl, status => {
      if (status.mode !== 'loading' && status.mode !== 'idle') localMode = status.mode
      report()
    })
    const output = context.createMediaStreamDestination()
    const localGain = context.createGain()
    const modelGain = context.createGain()
    const gain = context.createGain()
    const bypass: ModelBypass = {
      context, local, output, localGain, modelGain, gain,
      // Assigned after local initialization; stored early for cancellation.
      localSource: context.createMediaStreamSource(stream),
    }
    this.bypass = bypass
    localGain.gain.value = 1
    modelGain.gain.value = 0
    gain.gain.value = volume / 100
    localGain.connect(gain)
    modelGain.connect(gain)
    gain.connect(output)
    try {
      await context.resume()
      const localStream = await local.prepare(stream, { ...settings, mode: 'voice' }, 100)
      if (generation !== this.generation) throw new Error('麦克风处理已取消')
      bypass.localSource.disconnect()
      bypass.localSource = context.createMediaStreamSource(localStream)
      bypass.localSource.connect(localGain)
      const model = this.model = new MicrophoneModel(status => {
        modelMessage = status.message
        report()
      }, next => {
        if (generation !== this.generation || this.bypass !== bypass || available === next) return
        available = next
        // Complementary crossfade: stable recorder track, no uplink restart.
        const now = context.currentTime
        localGain.gain.cancelScheduledValues(now)
        modelGain.gain.cancelScheduledValues(now)
        localGain.gain.setTargetAtTime(next ? 0 : 1, now, .008)
        modelGain.gain.setTargetAtTime(next ? 1 : 0, now, .008)
        report()
      })
      try {
        const modelStream = await model.prepare(stream, 'deepfilter', 100)
        if (generation !== this.generation) throw new Error('麦克风处理已取消')
        bypass.modelSource = context.createMediaStreamSource(modelStream)
        bypass.modelSource.connect(modelGain)
      } catch (error) {
        if (generation !== this.generation) throw error
        modelMessage = '人声模型暂不可用'
        await model.release()
        if (this.model === model) this.model = null
        report()
      }
      return output.stream
    } catch (error) {
      if (generation === this.generation) await this.release()
      throw error
    }
  }

  async release(keepUnlocked = false) {
    const generation = ++this.generation
    const model = this.model
    this.model = null
    const bypass = this.bypass
    this.bypass = null
    await model?.release()
    if (bypass) {
      await bypass.local.release()
      bypass.localSource.disconnect()
      bypass.modelSource?.disconnect()
      bypass.localGain.disconnect()
      bypass.modelGain.disconnect()
      bypass.gain.disconnect()
      bypass.output.stream.getTracks().forEach(track => track.stop())
      bypass.output.disconnect()
      await bypass.context.close().catch(() => {})
    }
    const graph = this.graph
    this.graph = null
    this.onActivity(false)
    const unlocked = keepUnlocked ? null : this.unlockedContext
    if (!keepUnlocked) this.unlockedContext = null
    if (unlocked) await unlocked.close().catch(() => {})
    if (graph) {
      graph.cancelInitialization?.()
      graph.denoiser?.port.postMessage({ type: 'destroy' })
      graph.denoiser?.disconnect()
      graph.source.disconnect()
      graph.compressor?.disconnect()
      graph.gain.disconnect()
      graph.output.disconnect()
      graph.output.stream.getTracks().forEach((track) => track.stop())
      await graph.context.close().catch(() => {})
    }
    if (generation === this.generation) this.onStatus({ mode: 'idle', message: '' })
  }
}
