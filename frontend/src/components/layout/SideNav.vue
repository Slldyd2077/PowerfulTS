<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { computed } from 'vue'
import {
  Monitor,
  Headset,
  User,
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()

// 当前激活的菜单项（与 menu-item index 对应）
const activeIndex = computed(() => {
  if (route.path === '/') return 'dashboard'
  if (route.path === '/music') return 'music'
  if (route.path === '/friends') return 'friends'
  return ''
})

function navigate(key: string) {
  if (key === 'dashboard') router.push('/')
  else if (key === 'music') window.open('http://localhost:3000', '_blank')
  else if (key === 'friends') router.push('/friends')
}
</script>

<template>
  <nav class="side-nav">
    <!-- 品牌 -->
    <div class="nav-brand">
      <div class="brand-logo">
        <svg width="26" height="26" viewBox="0 0 26 26" fill="none">
          <!-- 信号条：单一青绿，呼应「监控」语义 -->
          <rect x="3" y="14" width="3.5" height="8" rx="0.5" fill="var(--color-primary)" opacity="0.45" />
          <rect x="8.5" y="9" width="3.5" height="13" rx="0.5" fill="var(--color-primary)" opacity="0.7" />
          <rect x="14" y="5" width="3.5" height="17" rx="0.5" fill="var(--color-primary)" />
          <rect x="19.5" y="11" width="3.5" height="11" rx="0.5" fill="var(--color-primary)" opacity="0.55" />
        </svg>
      </div>
      <div class="brand-text">
        <span class="brand-kicker label-mono">PowerfulTS</span>
        <h1 class="brand-title">监控面板</h1>
      </div>
    </div>

    <div class="divider-glow"></div>

    <!-- 导航 -->
    <el-menu :default-active="activeIndex" @select="navigate" class="nav-menu">
      <el-menu-item index="dashboard">
        <el-icon><Monitor /></el-icon>
        <span>服务器监控</span>
      </el-menu-item>

      <el-menu-item index="music">
        <el-icon><Headset /></el-icon>
        <span>音乐控制</span>
      </el-menu-item>

      <el-menu-item index="friends">
        <el-icon><User /></el-icon>
        <span>好友列表</span>
      </el-menu-item>
    </el-menu>

    <!-- 底部 -->
    <div class="nav-footer">
      <div class="footer-line"></div>
      <span class="version">v1.1.0</span>
    </div>
  </nav>
</template>

<style scoped>
.side-nav {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.nav-brand {
  padding: 22px 18px 14px;
  display: flex;
  align-items: center;
  gap: 11px;
}

.brand-logo {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.brand-kicker {
  font-size: 0.58em;
  color: var(--color-primary);
  letter-spacing: 0.16em;
}

.brand-title {
  font-size: 1em;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
  line-height: 1.2;
  letter-spacing: -0.01em;
}

.nav-menu {
  flex: 1;
  padding: 8px 10px;
}

.nav-footer {
  padding: 0 18px 16px;
}

.footer-line {
  height: 1px;
  background: var(--border-default);
  margin-bottom: 12px;
}

.version {
  display: block;
  text-align: center;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.66em;
  color: var(--text-muted);
  letter-spacing: 0.1em;
}
</style>
