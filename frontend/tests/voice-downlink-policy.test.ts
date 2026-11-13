import assert from 'node:assert/strict'
import test from 'node:test'

import {
  isNativeTsPreemption,
  resolveVoiceDownlinkCloseAction,
  trackDecoderBacklog,
  VOICE_CLOSE_NATIVE_TS_PREEMPTED,
  VOICE_DECODER_BACKLOG_DEPTH,
  VOICE_DECODER_BACKLOG_STRIKES,
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

test('a drained decoder clears the backlog strikes', () => {
  assert.deepEqual(trackDecoderBacklog(VOICE_DECODER_BACKLOG_DEPTH, 3), { strikes: 0, fallback: false })
  assert.deepEqual(trackDecoderBacklog(0, 7), { strikes: 0, fallback: false })
})

test('transient backlog below the strike limit does not switch the decoder', () => {
  let strikes = 0
  for (let i = 1; i < VOICE_DECODER_BACKLOG_STRIKES; i += 1) {
    const decision = trackDecoderBacklog(VOICE_DECODER_BACKLOG_DEPTH + 1, strikes)
    strikes = decision.strikes
    assert.equal(decision.fallback, false)
    assert.equal(strikes, i)
  }
})

test('sustained backlog falls back exactly once and restarts counting', () => {
  let strikes = VOICE_DECODER_BACKLOG_STRIKES - 1
  const decision = trackDecoderBacklog(VOICE_DECODER_BACKLOG_DEPTH + 1, strikes)
  assert.deepEqual(decision, { strikes: 0, fallback: true })

  const next = trackDecoderBacklog(VOICE_DECODER_BACKLOG_DEPTH + 1, decision.strikes)
  assert.deepEqual(next, { strikes: 1, fallback: false })
})
