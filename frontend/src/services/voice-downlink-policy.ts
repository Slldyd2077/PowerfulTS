export const VOICE_CLOSE_NATIVE_TS_PREEMPTED = 4412
const PERMANENT_CLOSE_CODES = new Set([4502])

export type VoiceDownlinkCloseAction = 'native-preempted' | 'stop' | 'reconnect'

export function isNativeTsPreemption(code: number): boolean {
  return code === VOICE_CLOSE_NATIVE_TS_PREEMPTED
}

export function resolveVoiceDownlinkCloseAction(
  code: number,
  reconnectAttempt: number,
  maxReconnectAttempts: number,
): VoiceDownlinkCloseAction {
  if (isNativeTsPreemption(code)) return 'native-preempted'
  if (PERMANENT_CLOSE_CODES.has(code) || reconnectAttempt >= maxReconnectAttempts) {
    return 'stop'
  }
  return 'reconnect'
}

/** WebCodecs AudioDecoder 队列超过该深度说明解码已经跟不上实时。 */
export const VOICE_DECODER_BACKLOG_DEPTH = 24
/** 连续多少个包仍然积压才切换解码后端，避免瞬时抖动触发误判。 */
export const VOICE_DECODER_BACKLOG_STRIKES = 8

export type VoiceDecoderBacklogDecision = {
  /** 需要写回解码器条目的连续积压计数。 */
  strikes: number
  /** 解码器已连续积压到该切换后端了。 */
  fallback: boolean
}

/**
 * 跟踪单个说话人的 WebCodecs 解码积压。
 *
 * 解码器卡住时不会触发 error 事件，只会让 decodeQueueSize 一直高于阈值；
 * 旧实现此时只丢包、不重置，于是整场通话永久静音。连续积压达到阈值后
 * 返回 fallback，让调用方切到 WASM 解码（与解码器报错时走同一条恢复路径）。
 */
export function trackDecoderBacklog(
  queueSize: number,
  strikes: number,
): VoiceDecoderBacklogDecision {
  if (queueSize <= VOICE_DECODER_BACKLOG_DEPTH) return { strikes: 0, fallback: false }
  const next = strikes + 1
  if (next >= VOICE_DECODER_BACKLOG_STRIKES) return { strikes: 0, fallback: true }
  return { strikes: next, fallback: false }
}
