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

const activeIndex = computed(() => {
  if (route.path === '/') return 'dashboard'
  return route.path
})

function navigate(key: string) {
  if (key === 'dashboard') router.push('/')
}
</script>

<template>
  <nav class="side-nav">
    <!-- 品牌 -->
    <div class="nav-brand">
      <div class="brand-logo">
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
          <rect x="2" y="2" width="24" height="24" rx="6" stroke="url(#snav-grad)" stroke-width="1.5" fill="none"/>
          <rect x="7" y="10" width="4" height="8" rx="0.5" fill="url(#snav-grad)"/>
          <rect x="12.5" y="7" width="4" height="11" rx="0.5" fill="url(#snav-grad)"/>
          <rect x="18" y="12" width="4" height="6" rx="0.5" fill="url(#snav-grad)"/>
          <defs>
            <linearGradient id="snav-grad" x1="0" y1="0" x2="28" y2="28">
              <stop stop-color="#00e5ff"/>
              <stop offset="1" stop-color="#b388ff"/>
            </linearGradient>
          </defs>
        </svg>
      </div>
      <div class="brand-text">
        <h1 class="brand-title">PowerfulTS</h1>
        <span class="brand-sub">Monitoring</span>
      </div>
    </div>

    <div class="divider-glow"></div>

    <!-- 导航 -->
    <el-menu :default-active="activeIndex" @select="navigate" class="nav-menu">
      <el-menu-item index="dashboard">
        <el-icon><Monitor /></el-icon>
        <span>服务器监控</span>
      </el-menu-item>

      <el-menu-item index="music" disabled>
        <el-icon><Headset /></el-icon>
        <span>音乐控制</span>
      </el-menu-item>

      <el-menu-item index="friends" disabled>
        <el-icon><User /></el-icon>
        <span>好友列表</span>
      </el-menu-item>
    </el-menu>

    <!-- 底部 -->
    <div class="nav-footer">
      <div class="footer-line"></div>
      <span class="version">v1.0.0</span>
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
  padding: 24px 18px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
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
}

.brand-title {
  font-size: 1.2em;
  font-weight: 700;
  background: var(--gradient-brand);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  margin: 0;
  line-height: 1.2;
  letter-spacing: -0.3px;
}

.brand-sub {
  font-size: 0.7em;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 2px;
  font-weight: 500;
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
  background: linear-gradient(90deg, transparent, var(--border-default), transparent);
  margin-bottom: 12px;
}

.version {
  display: block;
  text-align: center;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7em;
  color: var(--text-muted);
  letter-spacing: 1px;
}
</style>
