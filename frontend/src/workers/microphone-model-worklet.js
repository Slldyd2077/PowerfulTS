class ModelMicrophone extends AudioWorkletProcessor {
  constructor(options) {
    super()
    this.blockSize = options.processorOptions.blockSize
    this.streaming = options.processorOptions.streaming === true
    this.started = false
    this.available = false
    this.emptySamples = 0
    this.input = new Float32Array(this.blockSize)
    this.inputOffset = 0
    this.queue = []
    this.offset = 0
    this.buffered = 0
    this.port.onmessage = ({ data }) => {
      if (data.type === 'reset') {
        this.queue = []
        this.offset = this.buffered = 0
        this.started = false
        this.emptySamples = 0
        this.setAvailable(false)
        return
      }
      if (data.type !== 'pcm') return
      const chunk = new Float32Array(data.buffer)
      // Bound playback delay if network/model response was stalled.
      if (this.buffered + chunk.length > (this.streaming ? 4800 : this.blockSize * 2)) {
        this.queue = []
        this.offset = this.buffered = 0
        this.started = false
      }
      this.queue.push(chunk)
      this.buffered += chunk.length
    }
  }
  setAvailable(available) {
    if (!this.streaming || available === this.available) return
    this.available = available
    this.port.postMessage({ type: 'availability', available })
  }
  process(inputs, outputs) {
    const output = outputs[0]?.[0]
    if (!output) return true
    const input = inputs[0]?.[0]
    for (let i = 0; i < output.length; i++) {
      // Two frames absorb network jitter without a whole-second audio buffer.
      if (!this.started && this.buffered >= (this.streaming ? 1920 : this.blockSize)) {
        this.started = true
        this.setAvailable(true)
      }
      const chunk = this.started ? this.queue[0] : null
      output[i] = chunk ? chunk[this.offset++] : 0
      if (chunk) {
        this.emptySamples = 0
        this.buffered--
        if (this.offset === chunk.length) { this.queue.shift(); this.offset = 0 }
      }
      else if (++this.emptySamples >= 1920) this.setAvailable(false)
      if (!this.buffered) this.started = false
      this.input[this.inputOffset++] = input?.[i] ?? 0
      if (this.inputOffset === this.blockSize) {
        this.port.postMessage({ type: 'capture', buffer: this.input.buffer }, [this.input.buffer])
        this.input = new Float32Array(this.blockSize)
        this.inputOffset = 0
      }
    }
    return true
  }
}
registerProcessor('microphone-model', ModelMicrophone)
