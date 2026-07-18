<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { computed } from 'vue'
import {
  Monitor,
  Headset,
  User,
  Aim,
  Setting,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

// 应用版本号：构建时由 vite define 从 package.json 注入（version.d.ts 提供类型）
const appVersion = __APP_VERSION__

// 当前激活的菜单项（与 menu-item index 对应）
const activeIndex = computed(() => {
  if (route.path === '/') return 'dashboard'
  if (route.path === '/music') return 'music'
  if (route.path === '/friends') return 'friends'
  if (route.path === '/steam') return 'steam'
  if (route.path === '/admin') return 'admin'
  return ''
})

function navigate(key: string) {
  // 游客受限功能 → 跳登录页（保留游客态；登录成功后由 setToken 升级为真实用户）
  if (auth.isGuest && (key === 'music' || key === 'friends' || key === 'steam')) {
    router.push('/login')
    return
  }
  if (key === 'dashboard') router.push('/')
  else if (key === 'music') router.push('/music')
  else if (key === 'friends') router.push('/friends')
  else if (key === 'steam') router.push('/steam')
  else if (key === 'admin') router.push('/admin')
}
</script>

<template>
  <nav class="side-nav">
    <!-- 品牌 -->
    <div class="nav-brand">
      <div class="brand-logo">
        <img src="/logo-mark.svg" alt="PowerfulTS" width="26" height="26" />
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

      <el-menu-item index="music" :class="{ 'guest-locked': auth.isGuest }">
        <el-icon><Headset /></el-icon>
        <span>音乐控制</span>
        <span v-if="auth.isGuest" class="lock-hint label-mono">登录后查看</span>
      </el-menu-item>

      <el-menu-item index="friends" :class="{ 'guest-locked': auth.isGuest }">
        <el-icon><User /></el-icon>
        <span>好友列表</span>
        <span v-if="auth.isGuest" class="lock-hint label-mono">登录后查看</span>
      </el-menu-item>

      <el-menu-item index="steam" :class="{ 'guest-locked': auth.isGuest }">
        <el-icon><Aim /></el-icon>
        <span>Steam</span>
        <span v-if="auth.isGuest" class="lock-hint label-mono">登录后查看</span>
      </el-menu-item>

      <el-menu-item v-if="auth.isAdmin" index="admin">
        <el-icon><Setting /></el-icon>
        <span>系统设置</span>
      </el-menu-item>
    </el-menu>

    <!-- 底部 -->
    <div class="nav-footer">
      <div class="footer-line"></div>
      <span class="version">v{{ appVersion }}</span>
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
  padding: 18px 14px 14px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-logo {
  width: 65px;
  height: 65px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}

.brand-logo img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: contain;
}

.brand-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.brand-kicker {
  font-size: 0.62em;
  color: var(--color-primary);
  letter-spacing: 0.16em;
}

.brand-title {
  font-size: 1.04em;
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

/* 游客受限菜单项：置灰 + 删除线 + 登录后查看 */
.guest-locked {
  opacity: 0.55;
  transition: opacity 0.2s;
}

.guest-locked :deep(span:first-of-type) {
  text-decoration: line-through;
  text-decoration-color: rgba(248, 113, 113, 0.45);
  text-decoration-thickness: 1.5px;
}

.guest-locked:hover {
  opacity: 0.8;
  background: rgba(248, 113, 113, 0.04) !important;
}

.lock-hint {
  margin-left: auto;
  padding-left: 8px;
  font-size: 0.5em;
  color: var(--color-danger);
  opacity: 0.9;
  white-space: nowrap;
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
