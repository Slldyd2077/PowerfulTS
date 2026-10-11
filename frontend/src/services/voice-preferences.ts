export const VOICE_AUDIO_PREFERENCES_KEY = 'voice_audio_preferences_v1'
export const WATCH_PREFERENCES_KEY = 'voice_watch_preferences_v1'

export interface VoiceAudioPreferences {
  outputVolume: number
  microphoneVolume: number
  selectedInput: string
  selectedOutput: string
  microphoneEnabled: boolean
}

export interface WatchPreferences {
  source: 'direct' | 'site'
  waitForMembers: boolean
  allowMemberPause: boolean
  live: boolean
}

function readPreferences(key: string): Record<string, unknown> {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(key) || 'null')
    return saved && typeof saved === 'object' && !Array.isArray(saved)
      ? saved as Record<string, unknown> : {}
  } catch {
    return {}
  }
}

function volume(value: unknown, fallback: number, max: number): number {
  return typeof value === 'number' && Number.isFinite(value)
    ? Math.min(max, Math.max(0, value)) : fallback
}

export function loadVoiceAudioPreferences(): VoiceAudioPreferences {
  const saved = readPreferences(VOICE_AUDIO_PREFERENCES_KEY)
  return {
    outputVolume: volume(saved.outputVolume, 85, 100),
    microphoneVolume: volume(saved.microphoneVolume, 100, 200),
    selectedInput: typeof saved.selectedInput === 'string' ? saved.selectedInput : '',
    selectedOutput: typeof saved.selectedOutput === 'string' ? saved.selectedOutput : '',
    microphoneEnabled: typeof saved.microphoneEnabled === 'boolean' ? saved.microphoneEnabled : true,
  }
}

export function loadWatchPreferences(): WatchPreferences {
  const saved = readPreferences(WATCH_PREFERENCES_KEY)
  return {
    source: saved.source === 'direct' ? 'direct' : 'site',
    waitForMembers: typeof saved.waitForMembers === 'boolean' ? saved.waitForMembers : true,
    allowMemberPause: typeof saved.allowMemberPause === 'boolean' ? saved.allowMemberPause : true,
    live: typeof saved.live === 'boolean' ? saved.live : false,
  }
}

export function saveVoiceAudioPreferences(preferences: VoiceAudioPreferences): void {
  savePreferences(VOICE_AUDIO_PREFERENCES_KEY, preferences)
}

export function saveWatchPreferences(preferences: WatchPreferences): void {
  savePreferences(WATCH_PREFERENCES_KEY, preferences)
}

function savePreferences(key: string, preferences: VoiceAudioPreferences | WatchPreferences): void {
  try {
    localStorage.setItem(key, JSON.stringify(preferences))
  } catch { /* Preferences still apply in memory when browser storage is unavailable. */ }
}
