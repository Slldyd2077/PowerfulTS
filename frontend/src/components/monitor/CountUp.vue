<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'

/**
 * CountUp —— 数字平滑补间
 * value 变化时用 rAF + easeOutCubic 滚动到新值；reduced-motion 下直接跳变。
 */
const props = withDefaults(defineProps<{ value: number; duration?: number }>(), {
  duration: 650,
})

const display = ref(0)
let raf = 0

const reduceMotion =
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

function tween(from: number, to: number) {
  if (!Number.isFinite(to)) {
    display.value = 0
    return
  }
  if (reduceMotion || from === to) {
    display.value = to
    return
  }
  cancelAnimationFrame(raf)
  const start = performance.now()
  const dur = props.duration
  const ease = (t: number) => 1 - Math.pow(1 - t, 3) // easeOutCubic
  const step = (now: number) => {
    const t = Math.min(1, (now - start) / dur)
    display.value = Math.round(from + (to - from) * ease(t))
    if (t < 1) raf = requestAnimationFrame(step)
  }
  raf = requestAnimationFrame(step)
}

onMounted(() => tween(0, props.value))
watch(() => props.value, (n, o) => tween(o ?? 0, n ?? 0))
onBeforeUnmount(() => cancelAnimationFrame(raf))
</script>

<template>
  <span>{{ display }}</span>
</template>
