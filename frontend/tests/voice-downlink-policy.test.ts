import assert from 'node:assert/strict'
import test from 'node:test'

import {
  isNativeTsPreemption,
  resolveVoiceDownlinkCloseAction,
  VOICE_CLOSE_NATIVE_TS_PREEMPTED,
} from '../src/services/voice-downlink-policy.js'

test('native TS preemption is permanent and distinct from network failures', () => {
  assert.equal(isNativeTsPreemption(VOICE_CLOSE_NATIVE_TS_PREEMPTED), true)
  assert.equal(isNativeTsPreemption(1006), false)
  assert.equal(isNativeTsPreemption(1011), false)
  assert.equal(isNativeTsPreemption(4503), false)
  assert.equal(resolveVoiceDownlinkCloseAction(4412, 0, 5), 'native-preempted')
  assert.equal(resolveVoiceDownlinkCloseAction(4502, 0, 5), 'stop')
  assert.equal(resolveVoiceDownlinkCloseAction(1011, 5, 5), 'stop')
  assert.equal(resolveVoiceDownlinkCloseAction(1011, 1, 5), 'reconnect')
})
