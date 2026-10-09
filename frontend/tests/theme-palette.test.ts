import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildPalette,
  DEFAULT_PRIMARY,
  hslToRgb,
  parseHex,
  relativeLuminance,
  rgbToHsl,
} from '../src/services/theme-palette.js'

const hexToHsl = (hex: string) => rgbToHsl(...parseHex(hex)!)

test('hsl and rgb conversions round-trip', () => {
  for (const rgb of [[82, 147, 226], [220, 60, 120], [10, 200, 90]] as [number, number, number][]) {
    const back = hslToRgb(rgbToHsl(...rgb))
    back.forEach((v, i) => assert.ok(Math.abs(v - rgb[i]) <= 1))
  }
})

test('palette keeps the extracted hue and clamps lightness for dark UI', () => {
  const pink = buildPalette('#dc3c78')
  const primary = hexToHsl(pink['--color-primary'])
  const source = hexToHsl('#dc3c78')
  assert.ok(Math.abs(primary.h - source.h) < 3)
  assert.ok(primary.l >= 0.57 && primary.l <= 0.69)

  const veryDark = hexToHsl(buildPalette('#101010')['--color-primary'])
  assert.ok(veryDark.l >= 0.57, 'near-black colours are lifted to a readable lightness')
})

test('surfaces are near-black with only a faint theme tint', () => {
  const palette = buildPalette('#2fb36b')
  for (const key of ['--surface-0', '--surface-1', '--surface-2']) {
    const channels = parseHex(palette[key])!
    assert.ok(hexToHsl(palette[key]).l < 0.08, `${key} must stay near-black`)
    assert.ok(Math.max(...channels) - Math.min(...channels) <= 14, `${key} stays nearly neutral`)
  }
  const [, g] = parseHex(palette['--surface-2'])!
  const [r, , b] = parseHex(palette['--surface-2'])!
  assert.ok(g >= r && g >= b, 'green theme keeps a faint green tint')
})

test('grey images do not get an invented hue', () => {
  const palette = buildPalette('#808080')
  assert.ok(hexToHsl(palette['--color-primary']).s < 0.15)
})

test('bright primaries switch the on-primary text to dark', () => {
  assert.equal(buildPalette('#f2e11a')['--text-inverse'], '#0a0f1a')
  assert.equal(buildPalette('#3a5fd0')['--text-inverse'], '#ffffff')
})

test('invalid input falls back to the default blue palette', () => {
  assert.deepEqual(buildPalette('not-a-colour'), buildPalette(DEFAULT_PRIMARY))
  assert.ok(relativeLuminance([255, 255, 255]) > relativeLuminance([0, 0, 0]))
})
