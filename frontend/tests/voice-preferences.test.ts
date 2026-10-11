import assert from 'node:assert/strict'
import test from 'node:test'
import {
  VOICE_AUDIO_PREFERENCES_KEY, WATCH_PREFERENCES_KEY,
  loadVoiceAudioPreferences, saveVoiceAudioPreferences,
  loadWatchPreferences, saveWatchPreferences,
} from '../src/services/voice-preferences.js'

test('audio and watch preferences survive reload with zero volume and disabled options', () => {
  const values = new Map<string, string>()
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
  } })
  try {
    const audio = { outputVolume: 0, microphoneVolume: 150, selectedInput: 'mic-1',
      selectedOutput: 'speaker-1', microphoneEnabled: false }
    const watch = { source: 'direct' as const, waitForMembers: false, allowMemberPause: false, live: true }
    saveVoiceAudioPreferences(audio)
    saveWatchPreferences(watch)
    assert.deepEqual(loadVoiceAudioPreferences(), audio)
    assert.deepEqual(loadWatchPreferences(), watch)
    values.set(VOICE_AUDIO_PREFERENCES_KEY, JSON.stringify({ outputVolume: -20, microphoneVolume: 300,
      selectedInput: 10, selectedOutput: null, microphoneEnabled: 'false' }))
    assert.deepEqual(loadVoiceAudioPreferences(), { outputVolume: 0, microphoneVolume: 200,
      selectedInput: '', selectedOutput: '', microphoneEnabled: true })
    for (const invalid of ['{broken', 'null', '[]', '42']) {
      values.set(VOICE_AUDIO_PREFERENCES_KEY, invalid)
      assert.equal(loadVoiceAudioPreferences().outputVolume, 85)
    }
    values.set(WATCH_PREFERENCES_KEY, JSON.stringify({ source: 'invalid', live: 'true', allowMemberPause: 0 }))
    assert.deepEqual(loadWatchPreferences(), { source: 'site', waitForMembers: true, allowMemberPause: true, live: false })
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw new Error('storage blocked') } })
    assert.equal(loadVoiceAudioPreferences().microphoneVolume, 100)
    assert.equal(loadWatchPreferences().source, 'site')
    assert.doesNotThrow(() => saveVoiceAudioPreferences(audio))
    assert.doesNotThrow(() => saveWatchPreferences(watch))
  } finally {
    if (previous) Object.defineProperty(globalThis, 'localStorage', previous)
    else Reflect.deleteProperty(globalThis, 'localStorage')
  }
})
