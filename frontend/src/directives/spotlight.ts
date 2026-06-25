import type { Directive } from 'vue'

/**
 * v-spotlight —— 光标跟随聚光
 * 极轻量：仅在 mousemove 时写两个 CSS 变量（--mx / --my），不做任何逐帧计算。
 * 元素需 position:relative + overflow:hidden；CSS 侧用变量画 radial-gradient。
 */
function onMove(e: MouseEvent) {
  const el = e.currentTarget as HTMLElement
  const r = el.getBoundingClientRect()
  el.style.setProperty('--mx', `${e.clientX - r.left}px`)
  el.style.setProperty('--my', `${e.clientY - r.top}px`)
}

export const vSpotlight: Directive<HTMLElement> = {
  mounted(el: HTMLElement) {
    el.addEventListener('mousemove', onMove, { passive: true })
  },
  unmounted(el: HTMLElement) {
    el.removeEventListener('mousemove', onMove)
  },
}
