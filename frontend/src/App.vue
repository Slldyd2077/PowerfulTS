<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import { useSiteTheme } from '@/composables/useSiteTheme'

const auth = useAuthStore()

// 站点外观：自定义背景图 + 由图片提取的主题色
useSiteTheme()

// 应用启动时尝试恢复会话
auth.restoreSession()
</script>

<template>
  <router-view />
</template>

<style>
#app {
  height: 100%;
  width: 100%;
}
</style>
