import { watch } from 'vue'
import { useThemeStore } from '@/stores/theme'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { buildPalette, DEFAULT_PRIMARY } from '@/services/theme-palette'

const APPLIED_KEYS = new Set<string>()

/**
 * 把站点主题应用到 :root：按当前视口选择背景图，用其提取色推导整套 CSS 变量。
 * 只需在根组件调用一次。
 */
export function useSiteTheme() {
  const theme = useThemeStore()
  const { isMobile } = useBreakpoint()

  watch(
    isMobile,
    (value) => {
      theme.isMobileViewport = value
    },
    { immediate: true },
  )

  watch(
    () => theme.activeBackground,
    (bg) => {
      const root = document.documentElement
      const palette = buildPalette(bg?.color || DEFAULT_PRIMARY)
      // 默认蓝调色板与 variables.css 一致；有自定义图时才覆盖，移除时清理
      const { '--meta-theme-color': metaColor, ...vars } = palette
      if (bg?.color) {
        for (const [key, value] of Object.entries(vars)) {
          root.style.setProperty(key, value)
          APPLIED_KEYS.add(key)
        }
      } else {
        APPLIED_KEYS.forEach((key) => root.style.removeProperty(key))
        APPLIED_KEYS.clear()
      }
      root.classList.toggle('has-bg', Boolean(bg))
      document
        .querySelector('meta[name="theme-color"]')
        ?.setAttribute('content', bg?.color ? metaColor : '#000000')
    },
    { immediate: true },
  )

  theme.load()
}
