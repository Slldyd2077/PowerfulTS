import assert from 'node:assert/strict'
import test from 'node:test'
import { AxiosError } from 'axios'
import apiClient from '../src/api/client.js'
import { openVoiceSession } from '../src/api/voice.js'

Object.defineProperty(globalThis, 'localStorage', {
  value: { getItem: () => null },
  configurable: true,
})

test('joining voice has enough time for the backend connection deadline', async () => {
  apiClient.defaults.adapter = async (config) => {
    assert.equal(config.url, '/music/voice/session')
    assert.equal(config.timeout, 40_000)
    return { data: { ok: true, botId: 'voice-bot', nickname: 'user' }, status: 200, statusText: 'OK', headers: {}, config }
  }
  assert.equal((await openVoiceSession()).botId, 'voice-bot')
  assert.equal(apiClient.defaults.timeout, 15_000)
})

for (const code of ['ECONNABORTED', 'ETIMEDOUT']) {
  test(`voice timeout ${code} is distinct from an unreachable backend`, async () => {
    apiClient.defaults.adapter = async (config) => {
      throw new AxiosError('timeout', code, config)
    }
    await assert.rejects(openVoiceSession, /请求超时/)
    await assert.rejects(openVoiceSession, (error: Error) => !error.message.includes('后端已启动'))
  })
}

test('voice network failure still describes backend reachability', async () => {
  apiClient.defaults.adapter = async (config) => {
    throw new AxiosError('Network Error', 'ERR_NETWORK', config)
  }
  await assert.rejects(openVoiceSession, /连不上 PowerfulTS 后端/)
})

test('voice connection failure preserves the backend explanation', async () => {
  apiClient.defaults.adapter = async (config) => {
    throw new AxiosError('failed', 'ERR_BAD_RESPONSE', config, undefined, {
      status: 409, statusText: 'Conflict', headers: {}, config,
      data: { detail: '通话机器人连接 TS 超时，请稍后重试' },
    })
  }
  await assert.rejects(openVoiceSession, { message: '通话机器人连接 TS 超时，请稍后重试' })
})
