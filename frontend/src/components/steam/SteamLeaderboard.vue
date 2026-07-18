<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getSteamLeaderboard, type LeaderboardEntry } from '@/api/steam'

const entries = ref<LeaderboardEntry[]>([])
const loading = ref(false)

async function fetchLeaderboard() {
  loading.value = true
  try {
    const res = await getSteamLeaderboard()
    entries.value = res.entries || []
  } catch {
    entries.value = []
  } finally {
    loading.value = false
  }
}

onMounted(fetchLeaderboard)

const MEDALS = ['🥇', '🥈', '🥉']
</script>

<template>
  <div class="leaderboard panel">
    <div class="panel-header">
      <div class="panel-title-group">
        <h2 class="panel-title">全服游戏时长榜</h2>
        <span class="panel-sub label-mono">RANKING</span>
      </div>
      <button class="refresh-btn" @click="fetchLeaderboard" :disabled="loading">刷新</button>
    </div>

    <div v-if="loading && entries.length === 0" class="no-data">加载中…</div>
    <div v-else-if="entries.length === 0" class="no-data">暂无已绑定 Steam 的玩家</div>

    <div v-else class="rank-list">
      <div v-for="(e, i) in entries" :key="e.account_id" class="rank-row">
        <span class="rank-no mono">{{ i < 3 ? MEDALS[i] : i + 1 }}</span>
        <img v-if="e.avatar_url" :src="e.avatar_url" class="rank-avatar" :alt="e.persona || ''" />
        <div v-else class="rank-avatar rank-avatar--fallback">{{ e.ts_nickname.charAt(0) }}</div>
        <div class="rank-info">
          <span class="rank-name">{{ e.persona || e.ts_nickname }}</span>
          <span v-if="e.game_count != null" class="rank-sub mono">{{ e.game_count }} 款游戏</span>
        </div>
        <span class="rank-hours mono">{{ e.hours }}h</span>
      </div>
    </div>
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
.refresh-btn {
  padding: 3px 12px;
  border: 1px solid var(--border-emphasis);
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.72em;
  cursor: pointer;
}
.refresh-btn:hover {
  color: var(--color-primary);
  border-color: var(--color-primary);
}
.refresh-btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.no-data {
  text-align: center;
  color: var(--text-muted);
  padding: 24px;
  font-size: 0.86em;
}

.rank-list {
  display: flex;
  flex-direction: column;
}
.rank-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 4px;
  border-bottom: 1px solid var(--border-subtle);
}
.rank-row:last-child {
  border-bottom: none;
}
.rank-no {
  width: 26px;
  flex-shrink: 0;
  text-align: center;
  font-size: 0.86em;
  font-weight: 700;
  color: var(--text-secondary);
}
.rank-avatar {
  width: 30px;
  height: 30px;
  border-radius: 7px;
  object-fit: cover;
  flex-shrink: 0;
  border: 1px solid var(--border-default);
}
.rank-avatar--fallback {
  display: grid;
  place-items: center;
  background: rgba(var(--color-primary-rgb), 0.1);
  border: 1px solid rgba(var(--color-primary-rgb), 0.24);
  color: var(--color-primary);
  font-size: 0.8em;
  font-weight: 700;
}
.rank-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.rank-name {
  font-size: 0.84em;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rank-sub {
  font-size: 0.62em;
  color: var(--text-muted);
}
.rank-hours {
  flex-shrink: 0;
  font-size: 0.78em;
  font-weight: 700;
  color: var(--color-primary);
}
</style>
