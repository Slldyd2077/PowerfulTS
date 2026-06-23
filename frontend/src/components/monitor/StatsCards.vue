<script setup lang="ts">
import { computed } from 'vue'
import { useMonitorStore } from '@/stores/monitor'
import { User, Football, Timer, TrendCharts } from '@element-plus/icons-vue'

const monitor = useMonitorStore()

const cards = computed(() => [
  {
    label: '在线人数',
    value: monitor.stats?.online_users ?? 0,
    icon: User,
    color: '#00e5ff',
    glow: '0 0 24px rgba(0, 229, 255, 0.2)',
  },
  {
    label: '游戏中',
    value: monitor.stats?.gaming_users ?? 0,
    icon: Football,
    color: '#b388ff',
    glow: '0 0 24px rgba(179, 136, 255, 0.2)',
  },
  {
    label: '累计用户',
    value: monitor.stats?.total_users ?? 0,
    icon: TrendCharts,
    color: '#ffab00',
    glow: '0 0 24px rgba(255, 171, 0, 0.2)',
  },
  {
    label: '运行时长',
    value: formatTime(monitor.stats?.running_time ?? 0),
    icon: Timer,
    color: '#69f0ae',
    glow: '0 0 24px rgba(105, 240, 174, 0.2)',
  },
])

function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 24) return `${Math.floor(h / 24)}天${h % 24}时`
  return `${h}时${m}分`
}
</script>

<template>
  <div class="stats-row">
    <div
      v-for="(card, i) in cards"
      :key="card.label"
      class="stat-card animate-in"
      :class="'animate-delay-' + (i + 1)"
    >
      <div class="card-glow" :style="{ background: card.color }"></div>
      <div class="card-icon" :style="{ color: card.color }">
        <el-icon :size="22"><component :is="card.icon" /></el-icon>
      </div>
      <div class="card-body">
        <span class="card-label">{{ card.label }}</span>
        <span class="card-value mono" data-mono>{{ card.value }}</span>
      </div>
    </div>
  </div>

  <div class="update-bar" v-if="monitor.lastUpdate !== '--'">
    <span class="update-dot"></span>
    <span>最后更新: {{ monitor.lastUpdate }}</span>
    <span v-if="monitor.stats?.monitor_running === false" class="monitor-off">（监控未运行）</span>
  </div>
</template>

<style scoped>
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

@media (max-width: 900px) {
  .stats-row {
    grid-template-columns: repeat(2, 1fr);
  }
}

.stat-card {
  position: relative;
  background: var(--gradient-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 20px 18px;
  display: flex;
  align-items: center;
  gap: 14px;
  overflow: hidden;
  transition: transform 0.25s var(--ease-out-expo), box-shadow 0.25s;
}

.stat-card:hover {
  transform: translateY(-3px);
  border-color: var(--border-emphasis);
}

/* 辉光背景 */
.card-glow {
  position: absolute;
  top: -50%;
  right: -30%;
  width: 120px;
  height: 120px;
  border-radius: 50%;
  opacity: 0.06;
  filter: blur(40px);
  pointer-events: none;
}

.card-icon {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.04);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.card-body {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.card-label {
  font-size: 0.75em;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 1.5px;
  font-weight: 500;
}

.card-value {
  font-size: 1.7em;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
}

.update-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 12px;
  color: var(--text-muted);
  font-size: 0.78em;
  font-weight: 400;
}

.update-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--color-primary);
  opacity: 0.5;
  animation: pulse-glow 3s ease-in-out infinite;
}

.monitor-off {
  color: var(--color-danger);
  margin-left: 4px;
}
</style>
