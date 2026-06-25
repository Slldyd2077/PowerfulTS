<script setup lang="ts">
import { ref } from 'vue'
import { getChannels, type ChannelData } from '@/api/monitor'
import { usePolling } from '@/composables/usePolling'

const channels = ref<Record<string, string>>({})
const channelCount = ref(0)
const loaded = ref(false)

async function fetchChannels() {
  try {
    const data: ChannelData = await getChannels()
    channels.value = data.channels || {}
    channelCount.value = data.count || 0
    loaded.value = true
  } catch (e) {
    console.warn('[monitor] 获取频道失败', e)
  }
}

usePolling(fetchChannels, 30000)
</script>

<template>
  <div class="channel-sidebar">
    <div class="sidebar-header">
      <div class="panel-title-group">
        <h2 class="sidebar-title">频道</h2>
        <span class="sidebar-sub label-mono">CHANNELS</span>
      </div>
      <span class="sidebar-badge mono">{{ channelCount }}</span>
    </div>

    <div v-if="channelCount === 0" class="no-data">
      <span v-if="!loaded" class="loading-shimmer">采集中…</span>
      <span v-else>暂无频道</span>
    </div>

    <div v-else class="channel-list">
      <div
        v-for="(name, cid) in channels"
        :key="cid"
        class="channel-item row-scan"
      >
        <span class="channel-hash mono">#</span>
        <span class="channel-name">{{ name }}</span>
        <span class="channel-id mono">{{ cid }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.channel-sidebar {
  background: var(--gradient-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 16px 16px 12px;
  overflow-y: auto;
  max-height: 100%;
}

.sidebar-header {
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

.sidebar-title {
  font-size: 0.95em;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.sidebar-sub {
  font-size: 0.6em;
  color: var(--text-muted);
}

.sidebar-badge {
  font-size: 0.8em;
  font-weight: 700;
  color: var(--text-secondary);
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border-default);
  padding: 1px 9px;
  border-radius: 4px;
  line-height: 1.5;
}

.channel-list {
  display: flex;
  flex-direction: column;
}

.channel-item {
  padding: 8px 8px;
  display: grid;
  grid-template-columns: 16px 1fr auto;
  gap: 8px;
  align-items: center;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.15s;
}
.channel-item:last-child {
  border-bottom: none;
}
.channel-item:hover {
  background: var(--surface-4);
}

.channel-hash {
  color: var(--text-muted);
  font-weight: 600;
  font-size: 0.82em;
}

.channel-name {
  font-weight: 500;
  color: var(--text-secondary);
  font-size: 0.84em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.channel-id {
  font-size: 0.62em;
  color: var(--text-muted);
  opacity: 0.7;
}

.no-data {
  text-align: center;
  color: var(--text-muted);
  padding: 30px;
  font-size: 0.9em;
}
</style>
