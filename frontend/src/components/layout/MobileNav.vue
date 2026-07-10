<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Monitor, Headset, User, Setting } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const items = computed(() => [
  { path: '/', label: '监控', icon: Monitor, restricted: false },
  { path: '/music', label: '音乐', icon: Headset, restricted: auth.isGuest },
  { path: '/friends', label: '好友', icon: User, restricted: auth.isGuest },
  ...(auth.isAdmin ? [{ path: '/admin', label: '设置', icon: Setting, restricted: false }] : []),
])

function navigate(path: string, restricted: boolean) {
  router.push(restricted ? '/login' : path)
}
</script>

<template>
  <nav class="mobile-nav" aria-label="主要导航">
    <button
      v-for="item in items"
      :key="item.path"
      class="mobile-nav-item"
      :class="{ active: route.path === item.path, restricted: item.restricted }"
      :aria-current="route.path === item.path ? 'page' : undefined"
      @click="navigate(item.path, item.restricted)"
    >
      <el-icon :size="20"><component :is="item.icon" /></el-icon>
      <span>{{ item.label }}</span>
      <i v-if="item.restricted" class="lock-dot" aria-hidden="true"></i>
    </button>
  </nav>
</template>

<style scoped>
.mobile-nav {
  position: fixed;
  z-index: 45;
  left: max(10px, env(safe-area-inset-left));
  right: max(10px, env(safe-area-inset-right));
  bottom: max(8px, env(safe-area-inset-bottom));
  height: 64px;
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: 1fr;
  padding: 5px;
  border: 1px solid var(--border-default);
  border-radius: 14px;
  background: rgba(17, 20, 24, 0.94);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
}

.mobile-nav-item {
  position: relative;
  min-width: 0;
  min-height: 52px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: var(--text-muted);
  font-family: inherit;
  font-size: 0.66rem;
  font-weight: 600;
  -webkit-tap-highlight-color: transparent;
  transition: color 0.18s, background 0.18s, transform 0.12s;
}

.mobile-nav-item:active { transform: scale(0.96); }
.mobile-nav-item.active {
  color: var(--color-primary);
  background: var(--gradient-brand-subtle);
  box-shadow: inset 0 0 0 1px rgba(var(--color-primary-rgb), 0.12);
}
.mobile-nav-item.restricted { opacity: 0.5; }
.lock-dot {
  position: absolute;
  top: 8px;
  right: calc(50% - 16px);
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--color-danger);
}
</style>
