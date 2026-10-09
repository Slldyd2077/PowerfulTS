<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useThemeStore } from '@/stores/theme'

const theme = useThemeStore()
const url = computed(() => theme.activeBackground?.url ?? '')
// 图片解码完成后再淡入，避免出现半截加载的闪烁
const loadedUrl = ref('')
watch(url, () => {
  if (!url.value) loadedUrl.value = ''
})

const dim = computed(() => theme.config.dim / 100)
const blur = computed(() => theme.config.blur)
</script>

<template>
  <div class="backdrop" aria-hidden="true">
    <!-- 氛围光：始终存在，随主题色缓慢流动；有背景图时变得更淡 -->
    <div class="aurora" :class="{ 'aurora--faint': url }">
      <span class="blob blob-a"></span>
      <span class="blob blob-b"></span>
      <span class="blob blob-c"></span>
    </div>

    <div v-if="url" class="photo" :class="{ 'photo--ready': loadedUrl === url }">
      <img
        :key="url"
        :src="url"
        class="photo-img"
        :style="{ filter: blur ? `blur(${blur}px)` : undefined }"
        decoding="async"
        alt=""
        @load="loadedUrl = url"
      />
    </div>

    <div class="grid"></div>
    <div v-if="url" class="shade" :style="{ opacity: dim }"></div>
    <div class="vignette"></div>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  z-index: 0;
  overflow: hidden;
  pointer-events: none;
  background: var(--surface-1);
}

/* ── 氛围光 ── */
.aurora {
  position: absolute;
  inset: -20%;
  opacity: 0.55;
  transition: opacity 1.2s var(--ease-soft);
}
.aurora--faint {
  opacity: 0.2;
}

.blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(90px);
  will-change: transform;
}
.blob-a {
  width: 46vmax;
  height: 46vmax;
  top: -8%;
  left: -6%;
  background: rgba(var(--color-primary-rgb), 0.22);
  animation: blob-drift-a 26s ease-in-out infinite alternate;
}
.blob-b {
  width: 38vmax;
  height: 38vmax;
  right: -10%;
  top: 30%;
  background: rgba(var(--color-secondary-rgb), 0.16);
  animation: blob-drift-b 32s ease-in-out infinite alternate;
}
.blob-c {
  width: 30vmax;
  height: 30vmax;
  left: 28%;
  bottom: -14%;
  background: rgba(var(--color-primary-rgb), 0.14);
  animation: blob-drift-c 38s ease-in-out infinite alternate;
}

@keyframes blob-drift-a {
  to { transform: translate3d(14vw, 10vh, 0) scale(1.15); }
}
@keyframes blob-drift-b {
  to { transform: translate3d(-12vw, -8vh, 0) scale(0.9); }
}
@keyframes blob-drift-c {
  to { transform: translate3d(-10vw, -12vh, 0) scale(1.2); }
}

/* ── 背景图：淡入 + 缓慢呼吸（仅 transform，GPU 合成） ── */
.photo {
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 0.9s var(--ease-soft);
  animation: photo-breathe 48s ease-in-out infinite alternate;
  will-change: transform;
}
.photo--ready {
  opacity: 1;
}
.photo-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center;
  display: block;
  /* 模糊会让边缘透明，放大一点遮住 */
  transform: scale(1.04);
}
@keyframes photo-breathe {
  from { transform: scale(1) translate3d(0, 0, 0); }
  to { transform: scale(1.06) translate3d(-1%, -1%, 0); }
}

/* ── 遮罩：保证文字可读，色调取自主题表面色 ── */
.shade {
  position: absolute;
  inset: 0;
  background: rgb(var(--surface-0-rgb));
  transition: opacity 0.4s var(--ease-soft);
}
/* 点阵网格：极淡的「方格纸」质感，向下渐隐 */
.grid {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(rgba(var(--tint-rgb), 0.11) 1px, transparent 1px);
  background-size: 22px 22px;
  -webkit-mask-image: radial-gradient(ellipse 80% 60% at 50% 0%, #000 0%, transparent 75%);
  mask-image: radial-gradient(ellipse 80% 60% at 50% 0%, #000 0%, transparent 75%);
}
.vignette {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse at 50% 38%, transparent 38%, rgba(var(--surface-0-rgb), 0.55) 100%);
}

@media (max-width: 768px) {
  .blob { filter: blur(60px); }
  /* 手机端省电：背景图静止 */
  .photo { animation: none; }
}
</style>
