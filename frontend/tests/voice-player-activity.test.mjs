import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

test('activity ignores silence and quiet PCM, holds speech briefly, then clears', () => {
  let Processor
  const reports = []
  const scope = vm.createContext({
    currentTime: 0, sampleRate: 48000, Float32Array,
    AudioWorkletProcessor: class { port = { postMessage: value => reports.push(value) } },
    registerProcessor: (_name, value) => { Processor = value },
  })
  vm.runInContext(readFileSync(new URL('../src/workers/voice-player-worklet.js', import.meta.url), 'utf8'), scope)
  const player = new Processor()
  player.port.onmessage({ data: { type: 'gain', clientId: 1, value: 2 } })
  function render(level, blocks = 60) {
    const pcm = new Float32Array(blocks * 128 + 2400).fill(level)
    player.port.onmessage({ data: { type: 'pcm', clientId: 1, left: pcm.buffer, right: pcm.buffer } })
    for (let i = 0; i < blocks; i++) {
      player.process([], [[new Float32Array(128), new Float32Array(128)]])
      scope.currentTime += 128 / 48000
    }
    return reports.at(-1)
  }
  assert.equal(render(0).active, 0)
  assert.equal(render(0.001).active, 0, 'gain must not turn quiet noise into activity')
  assert.equal(render(0.02).active, 1)
  assert.equal(render(0, 12).active, 1, 'retain short speech pauses')
  assert.equal(render(0, 180).active, 0, 'silence must release activity')
  assert.equal(render(0.001, 60).active, 0)
})
