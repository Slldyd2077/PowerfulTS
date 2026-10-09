import assert from 'node:assert/strict'
import { test } from 'node:test'
import { applyPlayback, playbackPosition } from '../src/services/watch-playback.js'

const state = { position: 10, paused: false, rate: 2, updatedAt: 1000 }
test('late joiner advances from server sample using playback rate; paused state stays fixed', () => {
  assert.equal(playbackPosition(state, 4000), 16)
  assert.equal(playbackPosition({ ...state, paused: true }, 4000), 10)
  assert.equal(playbackPosition(state, 500), 10)
})
test('drift correction seeks only beyond tolerance and caps at media duration', async () => {
  let seekCount = 0
  let currentTime = 10.4
  const video = {
    get currentTime() { return currentTime },
    set currentTime(value: number) { seekCount++; currentTime = value },
    playbackRate: 1, duration: 20, paused: false,
    play: async () => {}, pause() {},
  } as unknown as HTMLVideoElement
  await applyPlayback(video, { ...state, rate: 1 }, 1000)
  assert.equal(seekCount, 0)
  await applyPlayback(video, state, 20000)
  assert.equal(video.currentTime, 20)
  assert.equal(video.playbackRate, 2)
})
test('autoplay rejection is surfaced to caller so viewer can click play', async () => {
  const video = { currentTime: 10, duration: 100, playbackRate: 2, paused: true,
    play: async () => { throw new Error('autoplay blocked') }, pause() {} } as unknown as HTMLVideoElement
  await assert.rejects(applyPlayback(video, state, 1000), /autoplay blocked/)
})
