<script setup lang="ts">
/**
 * 轻量频谱条（纯 CSS scaleY 动画，无 Canvas/无 JS 逐帧）。
 * - active = 正在播放时跳动；非 active 静止半透（静止的「暂停」态）。
 * - 颜色继承 currentColor，调用处着色（封面用 teal，队列用 muted）。
 * - prefers-reduced-motion 下全局兜底会把动画时长压到 ~0，自动降级为静态。
 */
withDefaults(defineProps<{ active?: boolean; bars?: number }>(), {
  active: false,
  bars: 4,
})
</script>

<template>
  <span class="eq" :class="{ paused: !active }" aria-hidden="true">
    <span
      v-for="i in bars"
      :key="i"
      class="eq-bar"
      :style="{ animationDelay: (i - 1) * 0.16 + 's', animationDuration: 0.7 + (i % 2) * 0.35 + 's' }"
    />
  </span>
</template>

<style scoped>
.eq {
  display: inline-flex;
  align-items: flex-end;
  gap: 2px;
  height: 14px;
}
.eq-bar {
  width: 3px;
  height: 100%;
  background: currentColor;
  border-radius: 2px;
  transform: scaleY(0.3);
  transform-origin: bottom;
  animation: eq-bounce 0.9s ease-in-out infinite;
}
.eq.paused .eq-bar {
  animation-play-state: paused;
  transform: scaleY(0.3);
  opacity: 0.35;
}

@keyframes eq-bounce {
  0%,
  100% {
    transform: scaleY(0.28);
  }
  50% {
    transform: scaleY(1);
  }
}
</style>
