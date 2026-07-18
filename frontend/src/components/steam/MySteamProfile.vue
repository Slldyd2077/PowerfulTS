<script setup lang="ts">
import { ref, watch } from 'vue'
import { getMySteamGames, type SteamMeResponse, type SteamGame } from '@/api/steam'

const props = defineProps<{ me: SteamMeResponse | null }>()

const games = ref<SteamGame[]>([])
const loadingGames = ref(false)

async function fetchGames() {
  if (!props.me?.bound) {
    games.value = []
    return
  }
  loadingGames.value = true
  try {
    const res = await getMySteamGames()
    games.value = res.games || []
  } catch {
    games.value = []
  } finally {
    loadingGames.value = false
  }
}

// 绑定/解绑后 me.bound 变化 → 重拉游戏库
watch(() => props.me?.bound, (bound) => {
  if (bound) fetchGames()
  else games.value = []
}, { immediate: true })

function statusClass(state: string | undefined): string {
  if (state === '游戏中') return 'is-gaming'
  if (state === '在线' || state === '忙碌' || state === '离开' || state === '打瞌睡' || state === '想交易' || state === '想玩游戏') return 'is-online'
  return 'is-offline'
}
</script>

<template>
  <div class="my-profile panel">
    <div class="panel-header">
      <div class="panel-title-group">
        <h2 class="panel-title">我的 Steam</h2>
        <span class="panel-sub label-mono">PROFILE</span>
      </div>
      <button class="refresh-btn" @click="fetchGames" :disabled="loadingGames">刷新</button>
    </div>

    <!-- 未绑定占位 -->
    <div v-if="!props.me?.bound" class="no-data">绑定 Steam 后查看你的在线状态与游戏库</div>

    <template v-else>
      <!-- 在线状态 -->
      <div class="status-row">
        <span class="status-pip" :class="statusClass(props.me?.status?.state)"></span>
        <span class="status-state" :class="statusClass(props.me?.status?.state)">
          {{ props.me?.status?.state || '未知' }}
        </span>
        <span v-if="props.me?.status?.current_game" class="status-game mono">
          正在玩 {{ props.me.status.current_game }}
        </span>
      </div>

      <!-- 游戏库 -->
      <div class="games-section">
        <div class="section-title">游戏库 · 共 {{ games.length }} 款</div>
        <div v-if="loadingGames" class="no-data">加载中…</div>
        <div v-else-if="games.length === 0" class="no-data">暂无游戏数据（可能资料未公开）</div>
        <div v-else class="games-list">
          <div v-for="g in games.slice(0, 30)" :key="g.appid" class="game-row">
            <img v-if="g.icon_url" :src="g.icon_url" class="game-icon" :alt="g.name" loading="lazy" />
            <div v-else class="game-icon game-icon--fallback"></div>
            <span class="game-name" :title="g.name">{{ g.name }}</span>
            <span class="game-hours mono">
              {{ g.playtime_forever_hours }}h
              <span v-if="g.playtime_2weeks_hours > 0" class="game-recent">近两周 {{ g.playtime_2weeks_hours }}h</span>
            </span>
          </div>
        </div>
        <p v-if="games.length > 30" class="hint mono">仅显示前 30 款，按总时长排序</p>
      </div>
    </template>
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
  padding: 20px;
  font-size: 0.84em;
}

.status-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 2px 12px;
}
.status-pip {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.status-pip.is-gaming { background: var(--color-primary); }
.status-pip.is-online { background: var(--color-success); }
.status-pip.is-offline { background: var(--text-muted); }
.status-state {
  font-weight: 600;
  font-size: 0.88em;
}
.status-state.is-gaming { color: var(--color-primary); }
.status-state.is-online { color: var(--color-success); }
.status-state.is-offline { color: var(--text-muted); }
.status-game {
  font-size: 0.72em;
  color: var(--text-secondary);
}

.section-title {
  font-size: 0.72em;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 8px;
  letter-spacing: 0.04em;
}

.games-list {
  display: flex;
  flex-direction: column;
}
.game-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 4px;
  border-bottom: 1px solid var(--border-subtle);
}
.game-row:last-child {
  border-bottom: none;
}
.game-icon {
  width: 26px;
  height: 26px;
  border-radius: 5px;
  object-fit: cover;
  flex-shrink: 0;
  background: var(--surface-3);
}
.game-icon--fallback {
  border: 1px solid var(--border-default);
}
.game-name {
  flex: 1;
  min-width: 0;
  font-size: 0.82em;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.game-hours {
  flex-shrink: 0;
  font-size: 0.74em;
  color: var(--color-primary);
  font-weight: 600;
}
.game-recent {
  margin-left: 6px;
  color: var(--text-muted);
  font-weight: 400;
}

.hint {
  text-align: center;
  margin-top: 10px;
  font-size: 0.62em;
  color: var(--text-muted);
}
</style>
