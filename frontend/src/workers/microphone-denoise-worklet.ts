import createRNNWasmModuleSync from '@jitsi/rnnoise-wasm/dist/rnnoise-sync.js'
import { DenoiseFrames } from '../services/denoise-frames'

// AudioWorklet globals are separate from the DOM and WebWorker globals.
declare const sampleRate: number
declare class AudioWorkletProcessor {
  readonly port: MessagePort
}
interface DenoiseOptions {
  processorOptions: { keyboardSuppression: boolean; voiceThreshold: number }
}
declare function registerProcessor(name: string, processor: new (options: DenoiseOptions) => AudioWorkletProcessor): void

class MicrophoneDenoiseProcessor extends AudioWorkletProcessor {
  private module: ReturnType<typeof createRNNWasmModuleSync> | null = null
  private state = 0
  private framePointer = 0
  private frames: DenoiseFrames | null = null
  private destroyed = false

  constructor(options: DenoiseOptions) {
    super()
    this.port.onmessage = ({ data }) => {
      if (data?.type === 'destroy') this.destroy()
      if (data?.type === 'configure') this.frames?.configure(data.keyboardSuppression, data.voiceThreshold)
    }
    try {
      if (sampleRate !== 48000) throw new Error('RNNoise requires 48 kHz')
      this.module = createRNNWasmModuleSync()
      this.state = this.module._rnnoise_create(0)
      this.framePointer = this.module._malloc(480 * 4)
      if (!this.state || !this.framePointer) throw new Error('RNNoise allocation failed')
      this.frames = new DenoiseFrames((frame) => {
        const module = this.module!
        const offset = this.framePointer / 4
        module.HEAPF32.set(frame, offset)
        const probability = module._rnnoise_process_frame(this.state, this.framePointer, this.framePointer)
        frame.set(module.HEAPF32.subarray(offset, offset + 480))
        return probability
      }, options.processorOptions.keyboardSuppression, options.processorOptions.voiceThreshold)
      this.port.postMessage({ type: 'ready' })
    } catch (error) {
      this.port.postMessage({ type: 'error', message: String(error) })
      this.destroy()
    }
  }

  process(inputs: Float32Array[][], outputs: Float32Array[][]): boolean {
    if (this.destroyed) return false
    try {
      const output = outputs[0]?.[0]
      if (output) this.frames?.process(inputs[0]?.[0], output)
      return true
    } catch (error) {
      this.port.postMessage({ type: 'error', message: String(error) })
      this.destroy()
      return false
    }
  }

  private destroy() {
    this.destroyed = true
    if (this.state) this.module?._rnnoise_destroy(this.state)
    if (this.framePointer) this.module?._free(this.framePointer)
    this.state = this.framePointer = 0
    this.frames = null
    this.module = null
  }
}

registerProcessor('microphone-denoise', MicrophoneDenoiseProcessor)
