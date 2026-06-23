<script setup lang="ts">
import { useMonitorStore } from '@/stores/monitor'

const monitor = useMonitorStore()
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <h2 class="panel-title">游戏统计</h2>
      <span class="panel-badge mono" data-mono>{{ monitor.gameStats.length }}</span>
    </div>

    <div v-if="monitor.gameStats.length === 0" class="no-data">
      <span v-if="monitor.loading" class="loading-shimmer">加载中...</span>
      <span v-else>暂无游戏数据</span>
    </div>

    <div v-else class="game-list">
      <div
        v-for="(game, i) in monitor.gameStats"
        :key="game.name"
        class="game-item"
        :style="{ animationDelay: i * 40 + 'ms' }"
      >
        <span class="game-rank mono" data-mono>{{ i + 1 }}</span>
        <div class="game-info">
          <span class="game-name">{{ game.name }}</span>
          <div class="game-bar-wrapper">
            <div
              class="game-bar"
              :style="{ width: `${Math.min(100, game.count * 20)}%` }"
            />
          </div>
        </div>
        <span class="game-count mono" data-mono>{{ game.count }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.panel {
  background: var(--gradient-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 20px;
  overflow-y: auto;
  max-height: 480px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.panel-title {
  font-size: 0.95em;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.panel-badge {
  font-size: 0.85em;
  font-weight: 700;
  color: var(--color-secondary);
  background: rgba(179, 136, 255, 0.08);
  padding: 2px 10px;
  border-radius: 20px;
}

.no-data {
  text-align: center;
  color: var(--text-muted);
  padding: 40px;
  font-size: 0.9em;
}

.loading-shimmer {
  background: linear-gradient(90deg, var(--text-muted), var(--text-secondary), var(--text-muted));
  background-size: 200% 100%;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: shimmer 1.5s infinite;
}

.game-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.game-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  transition: background 0.15s;
  animation: fade-in-up 0.3s var(--ease-out-expo) both;
}

.game-item:hover {
  background: var(--surface-4);
}

.game-rank {
  width: 22px;
  font-size: 0.75em;
  font-weight: 700;
  color: var(--text-muted);
  text-align: center;
  flex-shrink: 0;
}

.game-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.game-name {
  font-weight: 600;
  font-size: 0.9em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.game-bar-wrapper {
  height: 4px;
  background: rgba(255, 255, 255, 0.04);
  border-radius: 2px;
  overflow: hidden;
}

.game-bar {
  height: 100%;
  background: var(--gradient-brand);
  border-radius: 2px;
  transition: width 0.6s var(--ease-out-expo);
  min-width: 6px;
}

.game-count {
  font-weight: 700;
  font-size: 0.9em;
  min-width: 28px;
  text-align: right;
  color: var(--color-primary);
}
</style>
