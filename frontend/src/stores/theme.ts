import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getTheme, type BackgroundInfo, type ThemeConfig } from '@/api/theme'

const CACHE_KEY = 'site_theme_cache'
const EMPTY: ThemeConfig = { desktop: null, mobile: null, dim: 45, blur: 0 }

function readCache(): ThemeConfig {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    return raw ? { ...EMPTY, ...JSON.parse(raw) } : EMPTY
  } catch {
    return EMPTY
  }
}

/**
 * 站点外观配置（背景图 + 主题色）。
 * 上次的配置缓存在 localStorage，首屏即可套用，避免「先蓝后变色」的闪烁。
 */
export const useThemeStore = defineStore('theme', () => {
  const config = ref<ThemeConfig>(readCache())
  const isMobileViewport = ref(false)

  /** 当前视口应展示的背景：优先匹配设备，缺失则用另一端兜底 */
  const activeBackground = computed<BackgroundInfo | null>(() => {
    const { desktop, mobile } = config.value
    return (isMobileViewport.value ? mobile ?? desktop : desktop ?? mobile) ?? null
  })

  function setConfig(next: ThemeConfig) {
    config.value = next
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify(next))
    } catch {
      /* 隐私模式下忽略 */
    }
  }

  async function load() {
    try {
      setConfig(await getTheme())
    } catch {
      /* 获取失败则沿用缓存/默认主题 */
    }
  }

  return { config, isMobileViewport, activeBackground, setConfig, load }
})
