import assert from 'node:assert/strict'
import test from 'node:test'
import { tsNicknameError } from '../src/services/ts-nickname.js'

test('nickname limits reject short and long ASCII and Chinese names', () => {
  for (const name of ['1', '雪凌', 'a'.repeat(31), '中'.repeat(31), '😀😀']) {
    assert.equal(tsNicknameError(name), 'TS 昵称需为 3–30 个字符')
  }
  assert.equal(tsNicknameError('   '), 'TS 昵称不能为空')
})

test('nickname limits count Unicode characters instead of bytes or UTF-16 units', () => {
  for (const name of ['abc', 'a'.repeat(30), '中文名', '中'.repeat(30), '😀😀😀', '😀'.repeat(30)]) {
    assert.equal(tsNicknameError(name), null)
  }
  assert.equal(tsNicknameError('  ab  '), 'TS 昵称需为 3–30 个字符')
  assert.equal(tsNicknameError('  abc  '), null)
})
