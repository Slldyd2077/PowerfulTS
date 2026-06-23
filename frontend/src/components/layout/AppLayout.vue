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
          <span class="status-label">在线</span>
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
  background: rgba(12, 12, 29, 0.6);
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
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  border-bottom: 1px solid var(--border-subtle);
  background: rgba(12, 12, 29, 0.4);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-success);
  box-shadow: 0 0 8px rgba(105, 240, 174, 0.5);
  animation: pulse-glow 2s ease-in-out infinite;
}

.status-label {
  font-size: 0.8em;
  color: var(--text-muted);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.layout-content {
  flex: 1;
  overflow-y: auto;
  padding: 28px;
}
</style>
