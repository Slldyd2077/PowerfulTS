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
      <div class="avatar-circle">
        {{ auth.nickname.charAt(0) }}
      </div>
      <div class="user-meta">
        <span class="user-name">{{ auth.nickname }}</span>
        <span class="user-role" v-if="auth.isAdmin">管理员</span>
      </div>
    </div>
    <button class="logout-btn" @click="handleLogout" title="登出">
      <el-icon :size="16"><SwitchButton /></el-icon>
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
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--gradient-brand);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.8em;
  font-weight: 700;
  color: var(--text-inverse);
  flex-shrink: 0;
}

.user-meta {
  display: flex;
  flex-direction: column;
}

.user-name {
  color: var(--text-primary);
  font-weight: 600;
  font-size: 0.9em;
  line-height: 1.2;
}

.user-role {
  font-size: 0.7em;
  color: var(--color-danger);
  font-weight: 500;
  letter-spacing: 0.5px;
}

.logout-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s;
}

.logout-btn:hover {
  border-color: var(--color-danger);
  color: var(--color-danger);
  background: rgba(255, 82, 82, 0.08);
}
</style>
