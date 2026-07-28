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
        speaker = { chunks: [], offset: 0, buffered: 0, started: false, lastSeen: currentTime }
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
      active++
      speaking.push(clientId)
      const gain = this.gains.get(clientId) ?? 1
      for (let i = 0; i < leftOut.length; i++) {
        const chunk = speaker.chunks[0]
        if (!chunk) {
          speaker.started = false
          break
        }
        leftOut[i] += (chunk.left[speaker.offset] || 0) * gain
        rightOut[i] += (chunk.right[speaker.offset] || 0) * gain
        speaker.offset++
        speaker.buffered--
        if (speaker.offset >= chunk.left.length) {
          speaker.chunks.shift()
          speaker.offset = 0
        }
      }
    }

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
