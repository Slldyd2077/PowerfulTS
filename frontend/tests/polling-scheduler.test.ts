import assert from 'node:assert/strict'
import test from 'node:test'
import { createPollingScheduler } from '../src/services/polling-scheduler.js'

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((done) => { resolve = done })
  return { promise, resolve }
}

async function settle() {
  for (let index = 0; index < 5; index++) await Promise.resolve()
}

function setup(run: () => Promise<void>, immediate = true, available = true) {
  let nextId = 0
  const timers = new Map<number, { callback: () => void; delay: number }>()
  const running: boolean[] = []
  let errors = 0
  const scheduler = createPollingScheduler({
    run, intervalMs: 100, immediate, available,
    onRunning: (value) => running.push(value),
    onError: () => { errors++ },
    setTimer: (callback, delay) => {
      const id = ++nextId
      timers.set(id, { callback, delay })
      return () => { timers.delete(id) }
    },
  })
  function tick() {
    const entry = [...timers.entries()][0]
    assert.ok(entry, 'a future poll should be scheduled')
    timers.delete(entry[0])
    entry[1].callback()
  }
  return { scheduler, timers, running, tick, errors: () => errors }
}

test('awaits each request before scheduling the next interval', async () => {
  const request = deferred()
  let calls = 0
  const state = setup(() => { calls++; return request.promise })
  state.scheduler.start()
  assert.equal(calls, 1)
  assert.deepEqual(state.running, [true])
  assert.equal(state.timers.size, 0)
  request.resolve()
  await settle()
  assert.deepEqual(state.running, [true, false])
  assert.equal([...state.timers.values()][0]?.delay, 100)
  state.tick()
  await settle()
  assert.equal(calls, 2)
  state.scheduler.dispose()
})

test('immediate false delays the initial request and start replaces the timer', async () => {
  let calls = 0
  const state = setup(async () => { calls++ }, false)
  state.scheduler.start()
  state.scheduler.start()
  assert.equal(calls, 0)
  assert.equal(state.timers.size, 1)
  state.tick()
  await settle()
  assert.equal(calls, 1)
  state.scheduler.stop()
  assert.equal(state.timers.size, 0)
})

test('hidden or offline state pauses timers and restoration refreshes immediately', async () => {
  let calls = 0
  const state = setup(async () => { calls++ }, false, false)
  state.scheduler.start()
  assert.equal(state.timers.size, 0)
  state.scheduler.setAvailable(true)
  await settle()
  assert.equal(calls, 1)
  state.scheduler.setAvailable(false)
  assert.equal(state.timers.size, 0)
  state.scheduler.setAvailable(false)
  state.scheduler.setAvailable(true)
  await settle()
  assert.equal(calls, 2)
  state.scheduler.setAvailable(true)
  assert.equal(calls, 2)
  state.scheduler.dispose()
})

test('restoration and repeated start wait for an in-flight request', async () => {
  const first = deferred()
  let calls = 0
  const state = setup(() => ++calls === 1 ? first.promise : Promise.resolve())
  state.scheduler.start()
  state.scheduler.setAvailable(false)
  state.scheduler.setAvailable(true)
  state.scheduler.start()
  assert.equal(calls, 1)
  first.resolve()
  await settle()
  assert.equal(calls, 2)
  assert.equal(state.timers.size, 1)
  state.scheduler.dispose()
})

test('stop prevents a settling request or restored availability from restarting', async () => {
  const request = deferred()
  let calls = 0
  const state = setup(() => { calls++; return request.promise })
  state.scheduler.start()
  state.scheduler.setAvailable(false)
  state.scheduler.setAvailable(true)
  state.scheduler.stop()
  request.resolve()
  await settle()
  state.scheduler.setAvailable(false)
  state.scheduler.setAvailable(true)
  assert.equal(calls, 1)
  assert.equal(state.timers.size, 0)
  assert.deepEqual(state.running, [true, false])
})

test('dispose is permanent, including when a request is pending', async () => {
  const request = deferred()
  let calls = 0
  const state = setup(() => { calls++; return request.promise })
  state.scheduler.start()
  state.scheduler.dispose()
  state.scheduler.start()
  state.scheduler.setAvailable(false)
  state.scheduler.setAvailable(true)
  request.resolve()
  await settle()
  assert.equal(calls, 1)
  assert.equal(state.timers.size, 0)
})

test('stop then restart also preserves serial execution', async () => {
  const first = deferred()
  let calls = 0
  const state = setup(() => ++calls === 1 ? first.promise : Promise.resolve())
  state.scheduler.start()
  state.scheduler.stop()
  state.scheduler.start()
  assert.equal(calls, 1)
  first.resolve()
  await settle()
  assert.equal(calls, 2)
  state.scheduler.dispose()
})

test('async rejection and synchronous errors are handled and polling continues', async () => {
  let calls = 0
  const state = setup(() => {
    if (++calls === 1) return Promise.reject(new Error('private request details'))
    throw new Error('private request details')
  })
  state.scheduler.start()
  await settle()
  assert.equal(state.errors(), 1)
  state.tick()
  await settle()
  assert.equal(state.errors(), 2)
  assert.deepEqual(state.running, [true, false, true, false])
  assert.equal(state.timers.size, 1)
  state.scheduler.dispose()
})

test('default timers work and invalid intervals are rejected', async () => {
  const scheduler = createPollingScheduler({ run: async () => {}, intervalMs: 100 })
  scheduler.start()
  await settle()
  scheduler.stop()
  for (const intervalMs of [0, -1, NaN, Infinity]) {
    assert.throws(() => createPollingScheduler({ run: async () => {}, intervalMs }), RangeError)
  }
})
