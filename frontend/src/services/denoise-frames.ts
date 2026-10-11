const FRAME_SIZE = 480 // RNNoise: 10 ms of mono PCM at 48 kHz.
const PCM_SCALE = 32768
const HOLD_FRAMES = 25
const ATTACK = 1 - Math.exp(-1 / (48000 * 0.005))
const RELEASE = 1 - Math.exp(-1 / (48000 * 0.04))

/** Adapts arbitrary render blocks to RNNoise frames with a fixed 10 ms queue. */
export class DenoiseFrames {
  private readonly frame = new Float32Array(FRAME_SIZE)
  private readonly output = new Float32Array(FRAME_SIZE)
  private inputCount = 0
  private outputIndex = 0
  private outputCount = 0
  private hold = 0
  private gain = 0
  private keyboardSuppression: boolean
  private threshold: number
  private vad: boolean
  private readonly denoise: (frame: Float32Array) => number

  constructor(denoise: (frame: Float32Array) => number, keyboardSuppression: boolean, threshold: number, vad = false) {
    this.denoise = denoise
    this.keyboardSuppression = keyboardSuppression
    this.threshold = threshold
    this.vad = vad
  }

  get speaking() { return this.hold > 0 }

  configure(keyboardSuppression: boolean, threshold: number, vad = this.vad) {
    this.keyboardSuppression = keyboardSuppression
    this.threshold = threshold
    this.vad = vad
  }

  process(input: Float32Array | undefined, output: Float32Array) {
    for (let i = 0; i < output.length; i++) {
      output[i] = this.outputCount > 0 ? this.output[this.outputIndex++]! : 0
      if (this.outputCount > 0) this.outputCount--
      this.frame[this.inputCount++] = (input?.[i] ?? 0) * PCM_SCALE
      if (this.inputCount !== FRAME_SIZE) continue

      const probability = this.denoise(this.frame)
      if (probability >= this.threshold) this.hold = HOLD_FRAMES
      else this.hold = Math.max(0, this.hold - 1)
      const gated = this.keyboardSuppression || this.vad
      const target = !gated || this.hold > 0 ? 1 : 0
      const smoothing = target > this.gain ? ATTACK : RELEASE
      for (let j = 0; j < FRAME_SIZE; j++) {
        this.gain += (target - this.gain) * smoothing
        const sample = this.frame[j]! / PCM_SCALE
        this.output[j] = Math.max(-1, Math.min(1, sample * (gated ? this.gain : 1)))
      }
      this.inputCount = 0
      this.outputIndex = 0
      this.outputCount = FRAME_SIZE
    }
  }
}
