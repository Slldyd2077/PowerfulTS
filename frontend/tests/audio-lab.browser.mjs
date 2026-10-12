import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { fileURLToPath } from 'node:url'

const browser = await chromium.launch({ headless: true,
  executablePath: process.env.VOICE_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' })
try {
  const page = await browser.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('http://127.0.0.1:18186')
  await page.getByRole('heading', { name: '人声提取 · 本机试听', exact: true }).waitFor()
  for (const player of await page.locator('audio[src]').all()) {
    await player.evaluate(audio => new Promise((resolve, reject) => {
      if (audio.readyState >= 1) return resolve()
      audio.addEventListener('loadedmetadata', resolve, { once: true })
      audio.addEventListener('error', () => reject(Error('WAV playback failed')), { once: true })
      audio.load()
    }))
  }
  const samples = fileURLToPath(new URL('../../../data/audio-lab/samples/', import.meta.url))
  for (const [mode, input] of [['deepfilter', 'noise-input.wav'], ['spex', 'two-speakers-input.wav']]) {
    await page.locator('#mode').selectOption(mode)
    await page.locator('#input').setInputFiles(samples + input)
    if (mode === 'spex') await page.locator('#reference').setInputFiles(samples + 'spk1_snt2.wav')
    await page.getByRole('button', { name: '处理录音', exact: true }).click()
    await page.locator('#status').filter({ hasText: '完成：' }).waitFor({ timeout: 120000 })
    assert.equal(await page.locator('#result').isVisible(), true)
    console.log('PASS local upload, browser WAV conversion, model processing and result UI:', mode)
  }
  await page.setViewportSize({ width: 390, height: 844 })
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
  assert.deepEqual(errors, [])
  console.log('PASS sample audio loads, mobile layout and no page errors')
} finally { await browser.close() }
