<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import { useTheme } from '@/composables/useTheme'
import SideNav from './SideNav.vue'
import UserAvatar from './UserAvatar.vue'

useTheme()
const auth = useAuthStore()
</script>

<template>
  <div class="app-layout" v-if="auth.isLoggedIn">
    <SideNav class="layout-sidebar" />
    <div class="layout-main">
      <header class="layout-header">
        <div class="header-left">
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
</style>
