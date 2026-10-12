export type NoiseSuppressionMode = 'off' | 'browser' | 'rnnoise' | 'voice' | 'deepfilter' | 'spex' | 'combined'

export interface MicrophoneProcessingSettings {
  mode: NoiseSuppressionMode
  echoCancellation: boolean
  autoGainControl: boolean
  keyboardSuppression: boolean
  voiceActivityDetection: boolean
  voiceThreshold: number
}

export const MICROPHONE_PROCESSING_KEY = 'voice_microphone_processing_v2'
export const DEFAULT_MICROPHONE_PROCESSING: Readonly<MicrophoneProcessingSettings> = {
  mode: 'voice',
  echoCancellation: true,
  autoGainControl: true,
  keyboardSuppression: true,
  voiceActivityDetection: true,
  voiceThreshold: 0.6,
}

export function normalizeMicrophoneProcessing(value: unknown): MicrophoneProcessingSettings {
  const saved = value && typeof value === 'object'
    ? value as Partial<MicrophoneProcessingSettings> : {}
  const defaults = DEFAULT_MICROPHONE_PROCESSING
  return {
    mode: saved.mode === 'off' || saved.mode === 'browser' || saved.mode === 'rnnoise' || saved.mode === 'voice'
      || saved.mode === 'deepfilter' || saved.mode === 'spex' || saved.mode === 'combined'
      ? saved.mode : defaults.mode,
    echoCancellation: typeof saved.echoCancellation === 'boolean' ? saved.echoCancellation : defaults.echoCancellation,
    autoGainControl: typeof saved.autoGainControl === 'boolean' ? saved.autoGainControl : defaults.autoGainControl,
    keyboardSuppression: typeof saved.keyboardSuppression === 'boolean' ? saved.keyboardSuppression : defaults.keyboardSuppression,
    voiceActivityDetection: typeof saved.voiceActivityDetection === 'boolean' ? saved.voiceActivityDetection : defaults.voiceActivityDetection,
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
