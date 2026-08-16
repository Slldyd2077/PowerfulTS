<script setup lang="ts">
import { ref } from 'vue'
import { getFriendRequests, respondFriendRequest, type FriendRequestInfo } from '@/api/social'
import { usePolling } from '@/composables/usePolling'
import { ElMessage } from 'element-plus'

const emit = defineEmits<{ changed: [] }>()

const requests = ref<FriendRequestInfo[]>([])
const handlingId = ref<number | null>(null)

async function fetchRequests() {
  try {
    const res = await getFriendRequests()
    requests.value = res.requests || []
  } catch (e) {
    console.warn('[social] 获取好友申请失败', e)
  }
}

usePolling(fetchRequests, 30000)

async function handleAction(request: FriendRequestInfo, action: 'accept' | 'reject') {
  handlingId.value = request.id
  try {
    const res = await respondFriendRequest(request.id, action)
    if (!res.success) {
      ElMessage.error(res.error || (action === 'accept' ? '接受失败' : '拒绝失败'))
      return
    }
    ElMessage.success(res.message || (action === 'accept' ? '已接受好友申请' : '已拒绝好友申请'))
    await fetchRequests()
    emit('changed')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '操作失败，请稍后重试')
  } finally {
    handlingId.value = null
  }
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const minutes = Math.floor((Date.now() - then) / 60000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时前`
  return `${Math.floor(hours / 24)} 天前`
}
</script>

<template>
  <div v-if="requests.length > 0" class="panel">
    <div class="panel-header">
      <div class="panel-title-group">
        <h2 class="panel-title">好友申请</h2>
        <span class="panel-sub label-mono">REQUESTS</span>
      </div>
      <span class="panel-badge mono">{{ requests.length }}</span>
    </div>

    <div class="requests-list">
      <div v-for="request in requests" :key="request.id" class="request-item">
        <div class="request-avatar">{{ request.requester_nickname.charAt(0) }}</div>
        <div class="request-info">
          <span class="request-name">{{ request.requester_nickname }}</span>
          <span class="request-time mono">{{ relativeTime(request.created_at) }}</span>
        </div>
        <div class="request-actions">
          <el-button
            type="success"
            plain
            size="small"
            :loading="handlingId === request.id"
            :disabled="handlingId !== null && handlingId !== request.id"
            title="接受好友申请"
            @click="handleAction(request, 'accept')"
          >
            接受
          </el-button>
          <el-button
            type="danger"
            plain
            size="small"
            :disabled="handlingId !== null"
            title="拒绝好友申请"
            @click="handleAction(request, 'reject')"
          >
            拒绝
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.panel {
  background: var(--gradient-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 16px 16px 12px;
  margin-bottom: 20px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-subtle);
}

.panel-title-group {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.panel-title {
  font-size: 0.95em;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.panel-sub {
  font-size: 0.6em;
  color: var(--text-muted);
}

.panel-badge {
  font-size: 0.8em;
  font-weight: 700;
  color: var(--color-warning);
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--color-warning);
  padding: 1px 9px;
  border-radius: 4px;
  line-height: 1.5;
}

.requests-list {
  display: flex;
  flex-direction: column;
}

.request-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.request-item:last-child {
  border-bottom: none;
}

.request-avatar {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  border-radius: var(--radius-sm);
  background: rgba(var(--color-primary-rgb), 0.1);
  border: 1px solid rgba(var(--color-primary-rgb), 0.24);
  color: var(--color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.78em;
  font-weight: 700;
}

.request-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.request-name {
  font-weight: 600;
  font-size: 0.86em;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.request-time {
  font-size: 0.62em;
  color: var(--text-muted);
}

.request-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

/* 移动端：操作按钮加大触摸区 */
@media (max-width: 768px) {
  .request-actions :deep(.el-button) {
    min-height: 36px;
    padding: 8px 14px;
  }
}
</style>
