// Measure decoded PCM before volume compensation: background noise must not
// become "speech" simply because playback gain was increased.
const SPEAKING_START_RMS = 0.0032 // approximately -50 dBFS
const SPEAKING_KEEP_RMS = 0.002 // approximately -54 dBFS
const SPEAKING_HOLD_SECONDS = 0.18

class VoicePlayerProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this.speakers = new Map()
    // clientId -> 增益（1 = 原音量）。独立于 speakers：某人的音量要在他开口之前
    // 就能设好，而 speakers 里的条目是收到语音包才建的。
    this.gains = new Map()
    this.framesSinceReport = 0
    this.port.onmessage = (event) => {
      const message = event.data
      if (message?.type === 'reset') {
        this.speakers.clear()
        return
      }
      if (message?.type === 'gain') {
        if (message.value === 1) this.gains.delete(message.clientId)
        else this.gains.set(message.clientId, message.value)
        return
      }
      if (message?.type !== 'pcm') return
      let speaker = this.speakers.get(message.clientId)
      if (!speaker) {
        speaker = {
          chunks: [], offset: 0, buffered: 0, started: false, lastSeen: currentTime,
          levelGain: 1, speakingUntil: -Infinity,
        }
        this.speakers.set(message.clientId, speaker)
      }
      const left = new Float32Array(message.left)
      const right = new Float32Array(message.right)
      speaker.chunks.push({ left, right })
      speaker.buffered += left.length
      speaker.lastSeen = currentTime

      // Bound latency if the tab was suspended or decoding outran playback.
      while (speaker.buffered > sampleRate * 0.25 && speaker.chunks.length > 1) {
        const dropped = speaker.chunks.shift()
        // The first queued chunk may already be partially consumed. Only its
        // unread tail is included in `buffered`.
        speaker.buffered -= dropped.left.length - speaker.offset
        speaker.offset = 0
      }
    }
  }

  process(_inputs, outputs) {
    const output = outputs[0]
    if (!output?.length) return true
    const leftOut = output[0]
    const rightOut = output[1] || output[0]
    leftOut.fill(0)
    if (rightOut !== leftOut) rightOut.fill(0)

    let active = 0
    const speaking = []
    for (const [clientId, speaker] of this.speakers) {
      if (currentTime - speaker.lastSeen > 5) {
        this.speakers.delete(clientId)
        continue
      }
      // A small jitter buffer prevents packet-arrival variance from chattering.
      if (!speaker.started) {
        if (speaker.buffered < sampleRate * 0.04) continue
        speaker.started = true
      }
      if (speaker.buffered === 0) {
        speaker.started = false
        continue
      }
      const userGain = this.gains.get(clientId) ?? 1
      const gain = userGain * speaker.levelGain
      let energy = 0
      let measured = 0
      for (let i = 0; i < leftOut.length; i++) {
        const chunk = speaker.chunks[0]
        if (!chunk) {
          speaker.started = false
          break
        }
        const left = chunk.left[speaker.offset] || 0
        const right = chunk.right[speaker.offset] || 0
        leftOut[i] += left * gain
        rightOut[i] += right * gain
        energy += left * left + right * right
        measured += 2
        speaker.offset++
        speaker.buffered--
        if (speaker.offset >= chunk.left.length) {
          speaker.chunks.shift()
          speaker.offset = 0
        }
      }
      // Web Opus decoders can produce valid speech with a much lower PCM
      // level than a native TS client. Compensate per speaker gradually so a
      // quiet browser listener is not forced to max the master volume. The
      // cap avoids turning silence/noise into an aggressive signal.
      if (measured > 0) {
        const rms = Math.sqrt(energy / measured)
        const threshold = currentTime < speaker.speakingUntil ? SPEAKING_KEEP_RMS : SPEAKING_START_RMS
        if (rms >= threshold) speaker.speakingUntil = currentTime + SPEAKING_HOLD_SECONDS
        if (rms >= SPEAKING_KEEP_RMS) {
          const desired = Math.max(0.75, Math.min(3, 0.08 / rms))
          speaker.levelGain += (desired - speaker.levelGain) * 0.08
        }
      }
    }
    for (const [clientId, speaker] of this.speakers) {
      if (currentTime < speaker.speakingUntil) speaking.push(clientId)
    }
    active = speaking.length

    // Saturating mix avoids hard wraparound when several users talk at once.
    for (let i = 0; i < leftOut.length; i++) {
      leftOut[i] = Math.tanh(leftOut[i])
      rightOut[i] = Math.tanh(rightOut[i])
    }
    if (++this.framesSinceReport >= 12) {
      this.framesSinceReport = 0
      this.port.postMessage({ type: 'activity', active, speaking })
    }
    return true
  }
}

registerProcessor('voice-player', VoicePlayerProcessor)
