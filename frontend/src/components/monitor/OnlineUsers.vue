<script setup lang="ts">
import { useMonitorStore } from '@/stores/monitor'

const monitor = useMonitorStore()

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <h2 class="panel-title">在线用户</h2>
      <span class="panel-badge mono" data-mono>{{ monitor.onlineUsers.length }}</span>
    </div>

    <div v-if="monitor.onlineUsers.length === 0" class="no-data">
      <span v-if="monitor.loading" class="loading-shimmer">加载中...</span>
      <span v-else>暂无在线用户</span>
    </div>

    <div v-else class="user-list">
      <div
        v-for="user in monitor.onlineUsers"
        :key="user.nickname"
        class="user-item"
      >
        <div class="user-status">
          <span class="status-indicator"></span>
        </div>
        <div class="user-name">
          <span class="nickname">{{ user.nickname }}</span>
          <span v-if="user.game && user.game !== '未选择游戏'" class="game-tag">{{ user.game }}</span>
        </div>
        <span class="user-channel">{{ user.channel }}</span>
        <span class="user-time mono" data-mono>{{ formatDuration(user.online_time) }}</span>
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
  color: var(--color-primary);
  background: rgba(0, 229, 255, 0.08);
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

.user-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.user-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: var(--radius-sm);
  transition: background 0.15s;
}

.user-item:hover {
  background: var(--surface-4);
}

.user-status {
  flex-shrink: 0;
}

.status-indicator {
  display: block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-success);
  box-shadow: 0 0 6px rgba(105, 240, 174, 0.4);
}

.user-name {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.nickname {
  font-weight: 600;
  font-size: 0.9em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.game-tag {
  font-size: 0.72em;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 20px;
  background: rgba(105, 240, 174, 0.1);
  color: var(--color-success);
  white-space: nowrap;
}

.user-channel {
  color: var(--text-muted);
  font-size: 0.8em;
  min-width: 90px;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-time {
  color: var(--color-secondary);
  font-size: 0.82em;
  min-width: 50px;
  text-align: right;
  font-weight: 500;
}
</style>
