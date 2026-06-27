import { ref, readonly, onScopeDispose } from 'vue'

/**
 * 响应式断点约定（与 CSS @media 数值保持一致，作为 JS 侧单一数据源）
 *   tablet 1100px — 平板：多栏 → 单栏
 *   mobile  768px — 移动端主断点：侧栏抽屉化、布局转纵向、触摸目标 ≥44px
 *   small   480px — 小屏精简：字号缩小、隐藏次要元素
 */
export const BREAKPOINTS = {
  tablet: 1100,
  mobile: 768,
  small: 480,
} as const

/**
 * 监听一条 media query，返回响应式 matches。
 * 必须在 setup / effect scope 内调用；scope 销毁时自动 removeEventListener。
 */
function useMediaQuery(query: string) {
  const matches = ref(false)

  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    const mql = window.matchMedia(query)
    matches.value = mql.matches
    const handler = (e: MediaQueryListEvent) => {
      matches.value = e.matches
    }
    mql.addEventListener('change', handler)
    onScopeDispose(() => mql.removeEventListener('change', handler))
  }

  return matches
}

/**
 * 暴露三级断点的响应式布尔值（max-width 语义，含端点值）。
 *   isTablet ≤1100 / isMobile ≤768 / isSmall ≤480
 * 返回值为只读 ref（readonly），调用方不应直接赋值。
 */
export function useBreakpoint() {
  const isTablet = useMediaQuery(`(max-width: ${BREAKPOINTS.tablet}px)`)
  const isMobile = useMediaQuery(`(max-width: ${BREAKPOINTS.mobile}px)`)
  const isSmall = useMediaQuery(`(max-width: ${BREAKPOINTS.small}px)`)

  return {
    isTablet: readonly(isTablet),
    isMobile: readonly(isMobile),
    isSmall: readonly(isSmall),
  }
}
