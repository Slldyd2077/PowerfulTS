<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'
import { SwitchButton } from '@element-plus/icons-vue'

const auth = useAuthStore()
const router = useRouter()

async function handleLogout() {
  await auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="user-avatar">
    <div class="user-info" v-if="auth.isLoggedIn">
      <div class="avatar-circle" :class="{ 'avatar-circle--guest': auth.isGuest }">
        {{ auth.nickname.charAt(0) }}
      </div>
      <div class="user-meta">
        <span class="user-name">{{ auth.nickname }}</span>
        <span class="user-role label-mono" v-if="auth.isAdmin">管理员</span>
        <span class="user-role label-mono user-role--guest" v-else-if="auth.isGuest">游客</span>
      </div>
    </div>
    <button class="logout-btn" @click="handleLogout" title="登出">
      <el-icon :size="15"><SwitchButton /></el-icon>
    </button>
  </div>
</template>

<style scoped>
.user-avatar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.avatar-circle {
  width: 30px;
  height: 30px;
  border-radius: var(--radius-sm);
  background: rgba(45, 212, 191, 0.1);
  border: 1px solid rgba(45, 212, 191, 0.25);
  color: var(--color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.78em;
  font-weight: 700;
  flex-shrink: 0;
}

.user-meta {
  display: flex;
  flex-direction: column;
}

.user-name {
  color: var(--text-primary);
  font-weight: 600;
  font-size: 0.86em;
  line-height: 1.2;
}

.user-role {
  font-size: 0.58em;
  color: var(--color-accent);
  letter-spacing: 0.12em;
}

.avatar-circle--guest {
  background: rgba(255, 255, 255, 0.04);
  border-color: var(--border-default);
  color: var(--text-muted);
}

.user-role--guest {
  color: var(--text-muted);
}

.logout-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s, background 0.2s;
}

.logout-btn:hover {
  border-color: var(--color-danger);
  color: var(--color-danger);
  background: rgba(248, 113, 113, 0.06);
}
</style>
