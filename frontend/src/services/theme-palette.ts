/**
 * 主题调色板推导：由一个主色（通常从背景图提取）生成整套 CSS 变量。
 * 纯函数、无 DOM 依赖，便于单测。
 */

export const DEFAULT_PRIMARY = '#5293e2'

export interface Hsl {
  h: number // 0-360
  s: number // 0-1
  l: number // 0-1
}

const HEX_RE = /^#?([0-9a-f]{6})$/i

export function parseHex(hex: string): [number, number, number] | null {
  const m = HEX_RE.exec(hex.trim())
  if (!m) return null
  const n = parseInt(m[1], 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

export function rgbToHsl(r: number, g: number, b: number): Hsl {
  const rn = r / 255
  const gn = g / 255
  const bn = b / 255
  const max = Math.max(rn, gn, bn)
  const min = Math.min(rn, gn, bn)
  const l = (max + min) / 2
  const d = max - min
  if (d === 0) return { h: 0, s: 0, l }
  const s = d / (1 - Math.abs(2 * l - 1))
  let h: number
  if (max === rn) h = ((gn - bn) / d) % 6
  else if (max === gn) h = (bn - rn) / d + 2
  else h = (rn - gn) / d + 4
  return { h: (h * 60 + 360) % 360, s, l }
}

export function hslToRgb({ h, s, l }: Hsl): [number, number, number] {
  const c = (1 - Math.abs(2 * l - 1)) * s
  const hp = (((h % 360) + 360) % 360) / 60
  const x = c * (1 - Math.abs((hp % 2) - 1))
  const [r1, g1, b1] =
    hp < 1 ? [c, x, 0] : hp < 2 ? [x, c, 0] : hp < 3 ? [0, c, x] : hp < 4 ? [0, x, c] : hp < 5 ? [x, 0, c] : [c, 0, x]
  const m = l - c / 2
  return [Math.round((r1 + m) * 255), Math.round((g1 + m) * 255), Math.round((b1 + m) * 255)]
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))
const toHex = ([r, g, b]: [number, number, number]) =>
  `#${[r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('')}`
const rgbStr = ([r, g, b]: [number, number, number]) => `${r}, ${g}, ${b}`
const hsl = (h: number, s: number, l: number) => hslToRgb({ h, s, l })

/** WCAG 相对亮度 */
export function relativeLuminance([r, g, b]: [number, number, number]): number {
  const lin = (v: number) => {
    const c = v / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}

/**
 * 由任意主色推导整套主题变量。
 * - 主色明度/饱和度被约束到「深色界面上可读」的区间，避免提取到过暗/过灰的颜色。
 * - 表面、边框、文字沿用主色色相的低饱和版本，保持整体色调统一。
 */
export function buildPalette(inputHex: string): Record<string, string> {
  const rgb = parseHex(inputHex) ?? parseHex(DEFAULT_PRIMARY)!
  const base = rgbToHsl(...rgb)
  const h = base.h
  // 近灰色图片：保留低饱和，不强行染色
  const sat = base.s < 0.12 ? base.s : clamp(base.s, 0.5, 0.88)

  const primary = hsl(h, sat, clamp(base.l, 0.58, 0.68))
  const primaryDim = hsl(h, clamp(sat + 0.05, 0, 0.92), 0.46)
  const secondary = hsl(h - 28, clamp(sat + 0.08, 0, 0.92), 0.62)
  const secondaryDim = hsl(h - 28, clamp(sat + 0.08, 0, 0.92), 0.42)

  // 纯黑极简底：表面只带极淡的主题色相，边框/文字接近中性白
  const surfaceSat = Math.min(base.s, 0.3)
  const surface0 = hsl(h, surfaceSat, 0.0)
  const surface1 = hsl(h, surfaceSat, 0.022)
  const surface2 = hsl(h, surfaceSat, 0.042)
  const borderTint = hsl(h, Math.min(base.s, 0.25), 0.96)
  const textSat = Math.min(base.s, 0.1)

  // 主色渐变上的文字：亮色主色（黄/青绿）用深色字，保证按钮可读
  const onPrimary = relativeLuminance(primary) > 0.45 ? '#0a0f1a' : '#ffffff'

  const p = rgbStr(primary)
  return {
    '--color-primary': toHex(primary),
    '--color-primary-dim': toHex(primaryDim),
    '--color-primary-rgb': p,
    '--color-secondary': toHex(secondary),
    '--color-secondary-dim': toHex(secondaryDim),
    '--color-secondary-rgb': rgbStr(secondary),
    '--surface-0': toHex(surface0),
    '--surface-1': toHex(surface1),
    '--surface-2': toHex(surface2),
    '--surface-0-rgb': rgbStr(surface0),
    '--surface-1-rgb': rgbStr(surface1),
    '--surface-2-rgb': rgbStr(surface2),
    '--tint-rgb': rgbStr(borderTint),
    '--text-primary': toHex(hsl(h, textSat, 0.93)),
    '--text-secondary': toHex(hsl(h, Math.min(base.s, 0.08), 0.65)),
    '--text-muted': toHex(hsl(h, Math.min(base.s, 0.06), 0.5)),
    '--text-inverse': onPrimary,
    '--gradient-brand': `linear-gradient(135deg, ${toHex(primaryDim)} 0%, ${toHex(primary)} 100%)`,
    '--meta-theme-color': toHex(surface1),
  }
}
