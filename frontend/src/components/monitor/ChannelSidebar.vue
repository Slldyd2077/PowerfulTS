<script setup lang="ts">
import { ref } from 'vue'
import { getChannels, type ChannelData } from '@/api/monitor'
import { usePolling } from '@/composables/usePolling'

const channels = ref<Record<string, string>>({})
const channelCount = ref(0)

async function fetchChannels() {
  try {
    const data: ChannelData = await getChannels()
    channels.value = data.channels || {}
    channelCount.value = data.count || 0
  } catch {
    // 静默
  }
}

usePolling(fetchChannels, 30000)
</script>

<template>
  <div class="channel-sidebar">
    <div class="sidebar-header">
      <h2 class="sidebar-title">频道</h2>
      <span class="sidebar-badge mono" data-mono>{{ channelCount }}</span>
    </div>

    <div class="channel-list">
      <div
        v-for="(name, cid) in channels"
        :key="cid"
        class="channel-item"
      >
        <span class="channel-icon">#</span>
        <span class="channel-name">{{ name }}</span>
      </div>

      <div v-if="channelCount === 0" class="no-data">加载中...</div>
    </div>
  </div>
</template>

<style scoped>
.channel-sidebar {
  background: var(--gradient-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 20px;
  overflow-y: auto;
  max-height: 100%;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.sidebar-title {
  font-size: 0.95em;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.sidebar-badge {
  font-size: 0.85em;
  font-weight: 700;
  color: var(--color-accent);
  background: rgba(255, 171, 0, 0.08);
  padding: 2px 10px;
  border-radius: 20px;
}

.channel-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.channel-item {
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  gap: 8px;
  transition: background 0.15s;
}

.channel-item:hover {
  background: var(--surface-4);
}

.channel-icon {
  color: var(--text-muted);
  font-weight: 700;
  font-size: 0.85em;
  flex-shrink: 0;
  width: 18px;
  text-align: center;
}

.channel-name {
  font-weight: 500;
  color: var(--text-secondary);
  font-size: 0.85em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.no-data {
  text-align: center;
  color: var(--text-muted);
  padding: 30px;
  font-size: 0.9em;
}
</style>
