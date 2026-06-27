<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Menu } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useTheme } from '@/composables/useTheme'
import { useBreakpoint } from '@/composables/useBreakpoint'
import SideNav from './SideNav.vue'
import UserAvatar from './UserAvatar.vue'

useTheme()
const auth = useAuthStore()
const route = useRoute()
const { isMobile } = useBreakpoint()

// 移动端抽屉开关
const drawerOpen = ref(false)
// 路由变化后自动收起抽屉（用 fullPath 兼容同 path 不同 query 的跳转）
watch(
  () => route.fullPath,
  () => {
    drawerOpen.value = false
  },
)
// 切回桌面端时复位抽屉状态，避免再次进入移动端时残留为打开态
watch(
  () => isMobile.value,
  (mobile) => {
    if (!mobile) drawerOpen.value = false
  },
)
</script>

<template>
  <div class="app-layout" v-if="auth.isLoggedIn">
    <!-- 移动端遮罩：点击关闭抽屉 -->
    <transition name="nav-fade">
      <div
        v-if="isMobile && drawerOpen"
        class="nav-backdrop"
        @click="drawerOpen = false"
      ></div>
    </transition>

    <!-- 侧栏：桌面端常驻 230px；移动端为左侧 fixed 抽屉 -->
    <SideNav
      class="layout-sidebar"
      :class="{ 'is-drawer-open': isMobile && drawerOpen }"
    />

    <div class="layout-main">
      <header class="layout-header">
        <div class="header-left">
          <button
            v-if="isMobile"
            class="menu-toggle"
            :aria-expanded="drawerOpen"
            aria-label="切换导航菜单"
            @click="drawerOpen = !drawerOpen"
          >
            <el-icon :size="20"><Menu /></el-icon>
          </button>
          <div class="status-dot"></div>
          <span class="status-label label-mono">UPLINK · 在线</span>
        </div>
        <UserAvatar />
      </header>
      <main class="layout-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  height: 100%;
  width: 100%;
  background: var(--surface-0);
}

.layout-sidebar {
  width: 230px;
  flex-shrink: 0;
  background: rgba(13, 16, 20, 0.85);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-right: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
}

.layout-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--surface-1);
}

.layout-header {
  height: 50px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  border-bottom: 1px solid var(--border-subtle);
  background: rgba(13, 16, 20, 0.7);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 9px;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-success);
  animation: pulse-glow 2.4s ease-in-out infinite;
}

.status-label {
  font-size: 0.64em;
  color: var(--text-muted);
  letter-spacing: 0.14em;
}

.layout-content {
  flex: 1;
  overflow-y: auto;
  padding: 26px;
}

/* ── 移动端抽屉导航（≤768px；桌面端完全不受影响）── */

/* 遮罩（仅在移动端抽屉打开时由 v-if 渲染） */
.nav-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
  z-index: 55;
}

.nav-fade-enter-active,
.nav-fade-leave-active {
  transition: opacity 0.28s var(--ease-out-expo);
}
.nav-fade-enter-from,
.nav-fade-leave-to {
  opacity: 0;
}

/* 汉堡按钮默认隐藏，移动端媒体查询中显示 */
.menu-toggle {
  display: none;
}

@media (max-width: 768px) {
  /* 侧栏：脱离 flex 流，转为左侧抽屉，默认滑出视口外 */
  .layout-sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    width: 230px;
    max-width: 80vw;
    z-index: 60;
    transform: translateX(-100%);
    transition: transform 0.28s var(--ease-out-expo);
    box-shadow: var(--shadow-lg);
  }
  .layout-sidebar.is-drawer-open {
    transform: translateX(0);
  }

  /* 汉堡按钮：触摸目标 ≥44px */
  .menu-toggle {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    margin-right: 6px;
    margin-left: -8px;
    background: transparent;
    border: none;
    color: var(--text-secondary);
    border-radius: var(--radius-sm);
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
    transition: background 0.2s, color 0.2s;
  }
  .menu-toggle:hover,
  .menu-toggle:active {
    background: var(--surface-3-hover);
    color: var(--text-primary);
  }

  .layout-header {
    padding: 0 12px;
  }

  .layout-content {
    padding: 14px;
  }
}
</style>
