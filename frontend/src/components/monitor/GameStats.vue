<script setup lang="ts">
import { computed } from 'vue'
import { useMonitorStore } from '@/stores/monitor'

const monitor = useMonitorStore()

const maxCount = computed(() =>
  monitor.gameStats.reduce((m, g) => Math.max(m, g.count), 0) || 1,
)

const totalCount = computed(() =>
  monitor.gameStats.reduce((s, g) => s + g.count, 0) || 1,
)

function barWidth(count: number): number {
  return Math.min(100, Math.round((count / maxCount.value) * 100))
}

function percent(count: number): number {
  return Math.round((count / totalCount.value) * 100)
}
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <div class="panel-title-group">
        <h2 class="panel-title">游戏分布</h2>
        <span class="panel-sub label-mono">RANKING</span>
      </div>
      <span class="panel-badge mono">{{ monitor.gameStats.length }}</span>
    </div>

    <div v-if="monitor.gameStats.length === 0" class="no-data">
      <span v-if="monitor.loading" class="loading-shimmer">采集中…</span>
      <span v-else>暂无游戏数据</span>
    </div>

    <template v-else>
      <div class="row col-head label-mono">
        <span class="col-rank">#</span>
        <span class="col-game">游戏</span>
        <span class="col-bar"></span>
        <span class="col-count">人数</span>
      </div>

      <div class="game-list">
        <div
          v-for="(game, i) in monitor.gameStats"
          :key="(game.name || 'game') + '-' + i"
          class="row game-item row-scan"
        >
          <span class="col-rank game-rank mono">{{ String(i + 1).padStart(2, '0') }}</span>
          <span class="col-game game-name">{{ game.name }}</span>
          <div class="col-bar">
            <div class="bar-track">
              <div class="bar-fill" :style="{ width: barWidth(game.count) + '%' }" />
            </div>
            <span class="pct mono">{{ percent(game.count) }}%</span>
          </div>
          <span class="col-count game-count mono">{{ game.count }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.panel {
  background: var(--gradient-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 16px 16px 8px;
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
  padding: 40px;
  font-size: 0.9em;
}

/* ── 行栅格：排名 | 游戏 | 条 | 计数 ── */
.row {
  display: grid;
  grid-template-columns: 30px 1fr 1fr 38px;
  gap: 10px;
  align-items: center;
}

.col-head {
  padding: 0 8px 8px;
  font-size: 0.58em;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border-subtle);
}
.col-rank {
  text-align: left;
}
.col-game {
  min-width: 0;
}
.col-count {
  text-align: right;
}

.game-list {
  display: flex;
  flex-direction: column;
}

.game-item {
  padding: 10px 8px;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.15s;
}
.game-item:last-child {
  border-bottom: none;
}
.game-item:hover {
  background: var(--surface-4);
}

.game-rank {
  font-size: 0.72em;
  font-weight: 600;
  color: var(--text-muted);
}

.game-name {
  font-weight: 600;
  font-size: 0.86em;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.col-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.bar-track {
  flex: 1;
  height: 4px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 2px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  background: rgba(148, 163, 184, 0.45);
  border-radius: 2px;
  transition: width 0.6s var(--ease-out-expo);
  min-width: 3px;
}

.pct {
  font-size: 0.64em;
  color: var(--text-secondary);
  flex-shrink: 0;
  width: 30px;
  text-align: right;
}

.game-count {
  font-weight: 700;
  font-size: 0.84em;
  color: var(--text-primary);
}
</style>
