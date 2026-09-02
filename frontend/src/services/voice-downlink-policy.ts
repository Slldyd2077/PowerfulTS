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
