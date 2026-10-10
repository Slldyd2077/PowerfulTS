export type NoiseSuppressionMode = 'off' | 'browser' | 'rnnoise'

export interface MicrophoneProcessingSettings {
  mode: NoiseSuppressionMode
  echoCancellation: boolean
  autoGainControl: boolean
  keyboardSuppression: boolean
  voiceThreshold: number
}

export const MICROPHONE_PROCESSING_KEY = 'voice_microphone_processing_v1'
export const DEFAULT_MICROPHONE_PROCESSING: Readonly<MicrophoneProcessingSettings> = {
  mode: 'rnnoise',
  echoCancellation: true,
  autoGainControl: true,
  keyboardSuppression: true,
  voiceThreshold: 0.6,
}

export function normalizeMicrophoneProcessing(value: unknown): MicrophoneProcessingSettings {
  const saved = value && typeof value === 'object'
    ? value as Partial<MicrophoneProcessingSettings> : {}
  const defaults = DEFAULT_MICROPHONE_PROCESSING
  return {
    mode: saved.mode === 'off' || saved.mode === 'browser' || saved.mode === 'rnnoise'
      ? saved.mode : defaults.mode,
    echoCancellation: typeof saved.echoCancellation === 'boolean' ? saved.echoCancellation : defaults.echoCancellation,
    autoGainControl: typeof saved.autoGainControl === 'boolean' ? saved.autoGainControl : defaults.autoGainControl,
    keyboardSuppression: typeof saved.keyboardSuppression === 'boolean' ? saved.keyboardSuppression : defaults.keyboardSuppression,
    voiceThreshold: typeof saved.voiceThreshold === 'number' && Number.isFinite(saved.voiceThreshold)
      ? Math.min(0.9, Math.max(0.1, saved.voiceThreshold)) : defaults.voiceThreshold,
  }
}

export function microphoneConstraints(
  settings: MicrophoneProcessingSettings,
  deviceId = '',
): MediaTrackConstraints {
  return {
    echoCancellation: settings.echoCancellation,
    autoGainControl: settings.autoGainControl,
    // Keep a usable baseline until RNNoise initialization has succeeded.
    noiseSuppression: settings.mode !== 'off',
    channelCount: 1,
    ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
  }
}
