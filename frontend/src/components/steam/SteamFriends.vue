<script setup lang="ts">
import { ref } from 'vue'
import { getSteamFriends, type SteamFriend } from '@/api/steam'
import { usePolling } from '@/composables/usePolling'
import CommonGamesDialog from './CommonGamesDialog.vue'

const friends = ref<SteamFriend[]>([])
const dialogVisible = ref(false)
const dialogFriend = ref<SteamFriend | null>(null)

async function fetchFriends() {
  try {
    const res = await getSteamFriends()
    friends.value = res.friends || []
  } catch {
    /* 静默 */
  }
}

usePolling(fetchFriends, 60000)

function openCommon(friend: SteamFriend) {
  if (!friend.bound) return
  dialogFriend.value = friend
  dialogVisible.value = true
}

function statusClass(state: string | null | undefined): string {
  if (state === '游戏中') return 'is-gaming'
  if (state && state !== '离线') return 'is-online'
  return 'is-offline'
}
</script>

<template>
  <div class="steam-friends panel">
    <div class="panel-header">
      <div class="panel-title-group">
        <h2 class="panel-title">好友 Steam 状态</h2>
        <span class="panel-sub label-mono">FRIENDS</span>
      </div>
      <span class="panel-badge mono">{{ friends.length }}</span>
    </div>

    <div v-if="friends.length === 0" class="no-data">暂无好友，去好友列表添加吧</div>

    <div v-else class="friends-list">
      <div
        v-for="f in friends"
        :key="f.account_id"
        class="friend-item"
        :class="{ clickable: f.bound }"
        @click="openCommon(f)"
      >
        <img v-if="f.avatar_url" :src="f.avatar_url" class="friend-avatar" :alt="f.persona || ''" />
        <div v-else class="friend-avatar friend-avatar--fallback">{{ f.ts_nickname.charAt(0) }}</div>

        <div class="friend-info">
          <span class="friend-name">
            {{ f.ts_nickname }}
            <span v-if="f.persona" class="friend-persona mono">{{ f.persona }}</span>
          </span>
          <span v-if="!f.bound" class="friend-game mono unbound">未绑定 Steam</span>
          <span v-else-if="f.status?.current_game" class="friend-game mono">正在玩 {{ f.status.current_game }}</span>
          <span v-else-if="f.status?.state" class="friend-game mono">{{ f.status.state }}</span>
        </div>

        <span
          v-if="f.bound"
          class="friend-status"
          :class="statusClass(f.status?.state)"
        >
          <span class="status-pip"></span>{{ f.status?.state || '未知' }}
        </span>
      </div>
    </div>

    <p v-if="friends.some((f) => f.bound)" class="hint mono">点击已绑定好友查看共同游戏</p>

    <CommonGamesDialog v-model:visible="dialogVisible" :friend="dialogFriend" />
  </div>
</template>

<style scoped>
.panel {
  background: var(--gradient-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 16px;
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
}

.no-data {
  text-align: center;
  color: var(--text-muted);
  padding: 24px;
  font-size: 0.86em;
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
}
.friend-item:last-child {
  border-bottom: none;
}
.friend-item.clickable {
  cursor: pointer;
  transition: background 0.15s;
}
.friend-item.clickable:hover {
  background: var(--surface-4);
}
.friend-avatar {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  border-radius: 7px;
  object-fit: cover;
  border: 1px solid var(--border-default);
}
.friend-avatar--fallback {
  display: grid;
  place-items: center;
  background: rgba(var(--color-primary-rgb), 0.1);
  border: 1px solid rgba(var(--color-primary-rgb), 0.24);
  color: var(--color-primary);
  font-size: 0.8em;
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
  gap: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.friend-persona {
  font-size: 0.78em;
  color: var(--text-muted);
  font-weight: 400;
}
.friend-game {
  font-size: 0.64em;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.friend-game.unbound {
  color: var(--color-warning);
  opacity: 0.8;
}
.friend-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
  font-size: 0.66em;
  font-weight: 500;
  font-family: 'JetBrains Mono', monospace;
}
.friend-status .status-pip {
  width: 5px;
  height: 5px;
  border-radius: 50%;
}
.friend-status.is-gaming {
  color: var(--color-primary);
}
.friend-status.is-gaming .status-pip {
  background: var(--color-primary);
}
.friend-status.is-online {
  color: var(--color-success);
}
.friend-status.is-online .status-pip {
  background: var(--color-success);
}
.friend-status.is-offline {
  color: var(--text-muted);
}
.friend-status.is-offline .status-pip {
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
