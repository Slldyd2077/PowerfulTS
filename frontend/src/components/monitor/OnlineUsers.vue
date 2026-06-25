<script setup lang="ts">
import { computed, reactive } from 'vue'
import { useMonitorStore } from '@/stores/monitor'
import type { OnlineUser } from '@/api/monitor'

const monitor = useMonitorStore()

/** 在线时长的最大值（用于迷你条比例，真实派生） */
const maxTime = computed(() =>
  monitor.onlineUsers.reduce((m, u) => Math.max(m, u.online_time), 0) || 1,
)

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function timeRatio(seconds: number): number {
  return Math.min(100, Math.round((seconds / maxTime.value) * 100))
}

/* 行唯一键：昵称在 TS3 不保证唯一，拼接索引区分 */
function rowKey(user: OnlineUser, index: number): string {
  return (user.nickname || 'user') + '-' + index
}

/* 点击用户行 → 声纳 ping（语音服务器里「ping 一个人」的趣味隐喻）
   用递增计数器做 sonar 的 :key：每次点击都重新挂载元素，CSS 动画从头重播；
   按行键独立，同名用户互不干扰；无 setTimeout，无悬空定时器/泄漏。 */
const sonarKey = reactive<Record<string, number>>({})

function onPing(user: OnlineUser, index: number) {
  const k = rowKey(user, index)
  sonarKey[k] = (sonarKey[k] || 0) + 1
}
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <div class="panel-title-group">
        <h2 class="panel-title">在线用户</h2>
        <span class="panel-sub label-mono">ROSTER</span>
      </div>
      <span class="panel-badge mono">{{ monitor.onlineUsers.length }}</span>
    </div>

    <div v-if="monitor.onlineUsers.length === 0" class="no-data">
      <span v-if="monitor.loading" class="loading-shimmer">采集中…</span>
      <span v-else>暂无在线用户</span>
    </div>

    <template v-else>
      <!-- 列头 -->
      <div class="row col-head label-mono">
        <span class="col-user">用户</span>
        <span class="col-channel">频道</span>
        <span class="col-time">时长</span>
      </div>

      <div class="user-list">
        <div
          v-for="(user, index) in monitor.onlineUsers"
          :key="rowKey(user, index)"
          class="row user-item row-scan"
          title="点击 Ping 用户"
          @click="onPing(user, index)"
        >
          <!-- 声纳涟漪：从状态点位置向外扩散 -->
          <span
            v-if="sonarKey[rowKey(user, index)]"
            :key="sonarKey[rowKey(user, index)]"
            class="sonar"
          ></span>
          <div class="col-user user-cell">
            <span class="status-indicator"></span>
            <div class="user-meta">
              <span class="nickname">{{ user.nickname }}</span>
              <span v-if="user.game && user.game !== '未选择游戏'" class="game-tag">{{ user.game }}</span>
            </div>
          </div>
          <span class="col-channel user-channel">{{ user.channel || '—' }}</span>
          <div class="col-time time-cell">
            <div class="time-bar-track">
              <div class="time-bar" :style="{ width: timeRatio(user.online_time) + '%' }" />
            </div>
            <span class="user-time mono">{{ formatDuration(user.online_time) }}</span>
          </div>
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

/* ── 行栅格：用户(flex) | 频道(固定) | 时长(固定) ── */
.row {
  display: grid;
  grid-template-columns: 1fr 110px 86px;
  gap: 10px;
  align-items: center;
}

.col-head {
  padding: 0 10px 8px;
  font-size: 0.58em;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border-subtle);
}

.col-user {
  min-width: 0;
}
.col-channel {
  text-align: right;
}
.col-time {
  text-align: right;
}

.user-list {
  display: flex;
  flex-direction: column;
}

.user-item {
  position: relative;
  padding: 9px 10px;
  border-bottom: 1px solid var(--border-subtle);
  cursor: pointer;
  transition: background 0.15s;
}
.user-item:last-child {
  border-bottom: none;
}
.user-item:hover {
  background: var(--surface-4);
}

/* 声纳涟漪：从状态点位置向外扩散 */
.sonar {
  position: absolute;
  left: 13px;
  top: 50%;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 1px solid var(--color-primary);
  pointer-events: none;
  animation: od-sonar 0.9s var(--ease-out-expo) forwards;
}

.user-cell {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}

.status-indicator {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-success);
}

.user-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.nickname {
  font-weight: 600;
  font-size: 0.88em;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.game-tag {
  font-size: 0.66em;
  font-weight: 500;
  padding: 1px 7px;
  border-radius: 3px;
  background: rgba(52, 211, 153, 0.1);
  color: var(--color-secondary);
  white-space: nowrap;
  flex-shrink: 0;
}

.user-channel {
  color: var(--text-muted);
  font-size: 0.78em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.time-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}

.time-bar-track {
  width: 64px;
  height: 2px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 1px;
  overflow: hidden;
}
.time-bar {
  height: 100%;
  background: var(--text-muted);
  border-radius: 1px;
  transition: width 0.6s var(--ease-out-expo);
}

.user-time {
  color: var(--text-secondary);
  font-size: 0.76em;
  font-weight: 500;
}
</style>
