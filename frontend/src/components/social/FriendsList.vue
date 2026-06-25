<script setup lang="ts">
import { ref } from 'vue'
import { getFriends, deleteFriend, type Friend } from '@/api/social'
import { usePolling } from '@/composables/usePolling'
import { ElMessage, ElMessageBox } from 'element-plus'

const friends = ref<Friend[]>([])
const loggedIn = ref(false)

async function fetchFriends() {
  try {
    const res = await getFriends()
    loggedIn.value = res.logged_in
    friends.value = res.friends || []
  } catch (e) {
    console.warn('[social] 获取好友失败', e)
  }
}

usePolling(fetchFriends, 30000)

async function handleDelete(friend: Friend) {
  try {
    await ElMessageBox.confirm(
      `确定删除好友 ${friend.ts_nickname}？`,
      '删除好友',
      { type: 'warning' },
    )
    await deleteFriend(friend.ts_nickname)
    ElMessage.success('已删除好友')
    await fetchFriends()
  } catch {
    // 取消或失败
  }
}
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <div class="panel-title-group">
        <h2 class="panel-title">好友列表</h2>
        <span class="panel-sub label-mono">FRIENDS</span>
      </div>
      <span v-if="loggedIn" class="panel-badge mono">{{ friends.length }}</span>
    </div>

    <div v-if="!loggedIn" class="no-data">
      请先登录查看好友列表
    </div>

    <div v-else-if="friends.length === 0" class="no-data">
      暂无好友，快去添加吧
    </div>

    <div v-else class="friends-list">
      <div
        v-for="friend in friends"
        :key="friend.ts_nickname"
        class="friend-item"
        @contextmenu.prevent="handleDelete(friend)"
      >
        <div class="friend-avatar">{{ friend.ts_nickname.charAt(0) }}</div>
        <div class="friend-info">
          <span class="friend-name">{{ friend.ts_nickname }}</span>
          <span v-if="friend.game" class="friend-game mono">{{ friend.game }}</span>
        </div>
        <span
          class="friend-status"
          :class="{
            'status-online': friend.online_status === '在线',
            'status-gaming': friend.online_status === '游戏中',
            'status-offline': friend.online_status === '离线',
          }"
        >
          <span class="status-pip"></span>{{ friend.online_status }}
        </span>
      </div>
    </div>

    <p class="hint mono">右键点击好友可删除</p>
  </div>
</template>

<style scoped>
.panel {
  background: var(--gradient-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 16px 16px 12px;
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
  color: var(--text-secondary);
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border-default);
  padding: 1px 9px;
  border-radius: 4px;
  line-height: 1.5;
}

.no-data {
  text-align: center;
  color: var(--text-muted);
  padding: 30px;
  font-size: 0.88em;
}

.friends-list {
  display: flex;
  flex-direction: column;
}

.friend-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 8px;
  border-bottom: 1px solid var(--border-subtle);
  cursor: context-menu;
  transition: background 0.15s;
}
.friend-item:last-child {
  border-bottom: none;
}
.friend-item:hover {
  background: var(--surface-4);
}

.friend-avatar {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  border-radius: var(--radius-sm);
  background: rgba(45, 212, 191, 0.1);
  border: 1px solid rgba(45, 212, 191, 0.2);
  color: var(--color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.78em;
  font-weight: 700;
}

.friend-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.friend-name {
  font-weight: 600;
  font-size: 0.86em;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.friend-game {
  font-size: 0.62em;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.friend-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
  font-size: 0.66em;
  font-weight: 500;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.04em;
}

.status-pip {
  width: 5px;
  height: 5px;
  border-radius: 50%;
}

.status-online {
  color: var(--color-success);
}
.status-online .status-pip {
  background: var(--color-success);
}

.status-gaming {
  color: var(--color-primary);
}
.status-gaming .status-pip {
  background: var(--color-primary);
}

.status-offline {
  color: var(--text-muted);
}
.status-offline .status-pip {
  background: var(--text-muted);
}

.hint {
  text-align: center;
  margin-top: 10px;
  font-size: 0.62em;
  color: var(--text-muted);
  letter-spacing: 0.06em;
}
</style>
