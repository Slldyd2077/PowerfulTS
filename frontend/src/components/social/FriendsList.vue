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
  } catch {
    // 静默
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
    await deleteFriend(friend.qq)
    ElMessage.success('已删除好友')
    await fetchFriends()
  } catch {
    // 取消或失败
  }
}
</script>

<template>
  <div class="panel">
    <h2 class="panel-title">
      👥 好友列表
      <el-tag v-if="loggedIn" size="small" type="info">{{ friends.length }}</el-tag>
    </h2>

    <div v-if="!loggedIn" class="login-prompt">
      <p>请先登录查看好友列表</p>
    </div>

    <div v-else-if="friends.length === 0" class="no-data">
      暂无好友，快去添加吧
    </div>

    <div v-else class="friends-list">
      <div
        v-for="friend in friends"
        :key="friend.qq"
        class="friend-item"
        @contextmenu.prevent="handleDelete(friend)"
      >
        <div class="friend-info">
          <span class="friend-name">{{ friend.ts_nickname }}</span>
          <span
            class="friend-status"
            :class="{
              'status-online': friend.online_status === '在线',
              'status-gaming': friend.online_status === '游戏中',
              'status-offline': friend.online_status === '离线',
            }"
          >
            {{ friend.online_status }}
          </span>
        </div>
        <span v-if="friend.game" class="friend-game">🎮 {{ friend.game }}</span>
      </div>
    </div>

    <p class="hint">右键点击好友可以删除</p>
  </div>
</template>

<style scoped>
.panel {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  padding: 20px;
}

.panel-title {
  font-size: 1.1em;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-primary);
}

.login-prompt,
.no-data {
  text-align: center;
  color: var(--text-muted);
  padding: 30px;
  font-style: italic;
}

.friends-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.friend-item {
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 8px;
  transition: background 0.2s;
  cursor: context-menu;
}

.friend-item:hover {
  background: var(--bg-card-hover);
}

.friend-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.friend-name {
  font-weight: 600;
}

.friend-status {
  font-size: 0.85em;
  padding: 2px 8px;
  border-radius: 10px;
}

.status-online {
  background: #00c85330;
  color: #00c853;
}

.status-gaming {
  background: #7b2cbf30;
  color: #7b2cbf;
}

.status-offline {
  color: var(--text-muted);
}

.friend-game {
  display: block;
  margin-top: 4px;
  font-size: 0.85em;
  color: var(--color-primary);
}

.hint {
  text-align: center;
  margin-top: 12px;
  font-size: 0.75em;
  color: var(--text-muted);
}
</style>
