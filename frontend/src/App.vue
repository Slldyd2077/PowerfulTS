<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

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
