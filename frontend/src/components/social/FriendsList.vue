<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue'
import { getFriends, deleteFriend, updateFriendNotify, type Friend } from '@/api/social'
import { usePolling } from '@/composables/usePolling'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { ElMessage, ElMessageBox } from 'element-plus'

const { isMobile } = useBreakpoint()
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
      friend.relation_status === 'pending'
        ? `确定撤回发送给 ${friend.ts_nickname} 的好友申请？`
        : `确定删除好友 ${friend.ts_nickname}？`,
      friend.relation_status === 'pending' ? '撤回申请' : '删除好友',
      { type: 'warning' },
    )
  } catch {
    return // 用户取消确认
  }
  try {
    await deleteFriend(friend.ts_nickname)
    ElMessage.success(friend.relation_status === 'pending' ? '已撤回申请' : '已删除好友')
    await fetchFriends()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '删除好友失败')
  }
}

async function toggleNotify(friend: Friend, enabled: boolean | string | number) {
  const next = !!enabled
  const previous = friend.notify_online
  friend.notify_online = next
  try {
    const res = await updateFriendNotify(friend.account_id, next)
    if (!res.success) throw new Error(res.error || '设置失败')
    ElMessage.success(next ? `已开启 ${friend.ts_nickname} 的上线提醒` : `已关闭 ${friend.ts_nickname} 的上线提醒`)
  } catch (e) {
    friend.notify_online = previous
    ElMessage.error(e instanceof Error ? e.message : '设置失败')
  }
}

/* 移动端长按删除：按住约 550ms 触发，移动 / 抬起 / 离开则取消（无悬空定时器） */
const pressingName = ref<string | null>(null)
let pressTimer: number | null = null

function startPress(friend: Friend) {
  if (!isMobile.value) return
  pressingName.value = friend.ts_nickname
  pressTimer = window.setTimeout(() => {
    pressingName.value = null
    pressTimer = null
    handleDelete(friend)
  }, 550)
}
function cancelPress() {
  if (pressTimer !== null) {
    clearTimeout(pressTimer)
    pressTimer = null
  }
  pressingName.value = null
}
onBeforeUnmount(() => {
  if (pressTimer !== null) clearTimeout(pressTimer)
})
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
        :class="{ pressing: pressingName === friend.ts_nickname }"
        @contextmenu.prevent="handleDelete(friend)"
        @touchstart.passive="startPress(friend)"
        @touchend="cancelPress"
        @touchmove="cancelPress"
        @touchcancel="cancelPress"
      >
        <div class="friend-avatar">{{ friend.ts_nickname.charAt(0) }}</div>
        <div class="friend-info">
          <span class="friend-name">
            {{ friend.ts_nickname }}
            <span v-if="friend.relation_status === 'pending'" class="relation-tag relation-pending">已申请</span>
            <span v-else-if="friend.mutual" class="relation-tag relation-mutual" title="对方也加了你为好友">互关</span>
            <span v-else class="relation-tag relation-single" title="对方还没加你">单向</span>
          </span>
          <span v-if="friend.game" class="friend-game mono">{{ friend.game }}</span>
        </div>
        <el-switch
          v-if="friend.relation_status === 'friend'"
          :model-value="friend.notify_online"
          size="small"
          class="notify-switch"
          :title="`${friend.ts_nickname} 上线提醒`"
          @change="(value: boolean | string | number) => toggleNotify(friend, value)"
          @click.stop
        />
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

    <p class="hint mono">{{ isMobile ? '长按好友可删除' : '右键点击好友可删除' }}</p>
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
  background: rgba(var(--color-primary-rgb), 0.1);
  border: 1px solid rgba(var(--color-primary-rgb), 0.24);
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
  display: flex;
  align-items: center;
  gap: 5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.relation-tag {
  font-size: 0.7em;
  font-weight: 600;
  padding: 0 4px;
  border-radius: 3px;
  line-height: 1.6;
  flex-shrink: 0;
}
.relation-mutual { color: var(--color-success); border: 1px solid var(--color-success); }
.relation-single { color: var(--text-muted); border: 1px solid var(--border-emphasis); }
.relation-pending { color: var(--color-warning); border: 1px solid var(--color-warning); }
.notify-switch { flex-shrink: 0; }

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

/* 移动端：长按删除的红色渐变反馈 + 禁用系统长按选区菜单 */
.friend-item.pressing {
  background: rgba(248, 113, 113, 0.12);
}
@media (max-width: 768px) {
  .friend-item,
  .friend-item * {
    -webkit-touch-callout: none;
    -webkit-user-select: none;
    user-select: none;
  }
}
</style>
