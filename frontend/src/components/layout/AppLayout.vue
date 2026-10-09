<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useTheme } from '@/composables/useTheme'
import { useBreakpoint } from '@/composables/useBreakpoint'
import SideNav from './SideNav.vue'
import UserAvatar from './UserAvatar.vue'
import MobileNav from './MobileNav.vue'
import AppBackdrop from './AppBackdrop.vue'

useTheme()
const auth = useAuthStore()
const { isMobile } = useBreakpoint()
const route = useRoute()

const PAGE_TITLES: Record<string, string> = {
  Dashboard: '服务器监控',
  Music: '音乐控制',
  Voice: '网页通话',
  Friends: '好友列表',
  Steam: 'Steam',
  Admin: '系统设置',
}
const pageTitle = computed(() => PAGE_TITLES[String(route.name)] ?? 'PowerfulTS')
</script>

<template>
  <div class="app-layout" v-if="auth.isLoggedIn">
    <AppBackdrop />
    <SideNav class="layout-sidebar" />

    <div class="layout-main">
      <header class="layout-header">
        <div class="header-left">
          <img class="crumb-logo" src="/logo-mark.png" alt="" />
          <span class="crumb-sep">/</span>
          <Transition name="crumb" mode="out-in">
            <span :key="pageTitle" class="crumb-page">{{ pageTitle }}</span>
          </Transition>
        </div>
        <UserAvatar />
      </header>
      <main class="layout-content">
        <router-view v-slot="{ Component, route }">
          <transition name="page" mode="out-in">
            <component :is="Component" :key="route.path" />
          </transition>
        </router-view>
      </main>
      <MobileNav v-if="isMobile" />
    </div>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  height: 100%;
  min-height: 100dvh;
  width: 100%;
  position: relative;
  background: var(--surface-0);
}

.layout-sidebar {
  position: relative;
  z-index: 1;
  width: 230px;
  flex-shrink: 0;
  background: var(--glass-bg);
  backdrop-filter: blur(20px) saturate(1.2);
  -webkit-backdrop-filter: blur(20px) saturate(1.2);
  border-right: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
}

.layout-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  position: relative;
  z-index: 1;
  /* 透明：让 AppBackdrop（氛围光 / 自定义背景图）透出来 */
  background: transparent;
}

.layout-header {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--glass-bg-soft);
  backdrop-filter: blur(14px) saturate(1.2);
  -webkit-backdrop-filter: blur(14px) saturate(1.2);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.crumb-logo {
  width: 20px;
  height: 20px;
  object-fit: contain;
  opacity: 0.95;
}

.crumb-sep {
  color: var(--text-muted);
  font-weight: 300;
  font-size: 1.15em;
  opacity: 0.7;
}

.crumb-page {
  font-size: 0.95em;
  font-weight: 500;
  letter-spacing: -0.01em;
  color: var(--text-primary);
  white-space: nowrap;
}

.crumb-enter-active,
.crumb-leave-active {
  transition: opacity 0.18s ease, transform 0.28s var(--ease-out-expo);
}
.crumb-enter-from { opacity: 0; transform: translateY(5px); }
.crumb-leave-to { opacity: 0; transform: translateY(-5px); }




.layout-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior-y: contain;
  padding: 26px;
}

/* 页面切换：轻微上浮 + 淡入淡出 */
.page-enter-active {
  transition: opacity 0.36s var(--ease-out-expo), transform 0.36s var(--ease-out-expo);
}
.page-leave-active {
  transition: opacity 0.14s ease-in;
}
.page-enter-from {
  opacity: 0;
  transform: translateY(12px);
}
.page-leave-to {
  opacity: 0;
}

@media (max-width: 768px) {
  .layout-sidebar {
    display: none;
  }

  .layout-header {
    height: calc(52px + env(safe-area-inset-top));
    padding: env(safe-area-inset-top) max(14px, env(safe-area-inset-right)) 0 max(14px, env(safe-area-inset-left));
  }

  .layout-content {
    padding: 14px max(14px, env(safe-area-inset-right)) calc(82px + env(safe-area-inset-bottom)) max(14px, env(safe-area-inset-left));
    scroll-padding-bottom: calc(82px + env(safe-area-inset-bottom));
  }
}
</style>
