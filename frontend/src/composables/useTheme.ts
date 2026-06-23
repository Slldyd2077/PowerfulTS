import { ref, onMounted, onUnmounted } from 'vue'

type ThemeName = 'day' | 'sunset' | 'night' | 'late-night'

/**
 * 时间感知主题 hook
 * 根据当前小时自动切换：
 * - 6:00-17:00  → day（明亮）
 * - 17:00-19:00 → sunset（暖色）
 * - 19:00-23:00 → night（深蓝）
 * - 23:00-6:00  → late-night（极暗）
 */
export function useTheme() {
  const theme = ref<ThemeName>('night')

  function update() {
    const hour = new Date().getHours()
    if (hour >= 6 && hour < 17) theme.value = 'day'
    else if (hour >= 17 && hour < 19) theme.value = 'sunset'
    else if (hour >= 19 && hour < 23) theme.value = 'night'
    else theme.value = 'late-night'

    document.body.className = `theme-${theme.value}`
  }

  let timer: ReturnType<typeof setInterval>

  onMounted(() => {
    update()
    timer = setInterval(update, 60000)
  })

  onUnmounted(() => clearInterval(timer))

  return { theme, update }
}
