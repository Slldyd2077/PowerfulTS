<script setup lang="ts">
import { ref } from 'vue'
import { useMusicStore } from '@/stores/music'
import { ElMessage } from 'element-plus'

const music = useMusicStore()
const keyword = ref('')

const platforms = [
  { value: 'all', label: '全部' },
  { value: 'netease', label: '网易云' },
  { value: 'qq', label: 'QQ音乐' },
  { value: 'bilibili', label: 'B站' },
] as const

const platformLabels: Record<string, string> = {
  netease: '网易云',
  qq: 'QQ音乐',
  bilibili: 'B站',
}
const platformColors: Record<string, string> = {
  netease: '#e60026',
  qq: '#31c27c',
  bilibili: '#fb7299',
}

async function handleSearch() {
  if (!keyword.value.trim()) return
  await music.search(keyword.value)
}

async function handlePlay(song: { id: string; name: string; platform?: string }, queued = false) {
  try {
    await music.play(`id:${song.id}`, queued, song.platform)
    ElMessage.success(queued ? `加入队列: ${song.name}` : `正在播放: ${song.name}`)
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '播放失败')
  }
}
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <div class="panel-title-group">
        <h2 class="panel-title">点歌</h2>
        <span class="panel-sub label-mono">SEARCH</span>
      </div>
    </div>

    <!-- 平台切换 -->
    <div class="platform-tabs">
      <button
        v-for="p in platforms"
        :key="p.value"
        class="platform-tab"
        :class="{ active: music.searchPlatform === p.value }"
        @click="music.searchPlatform = p.value"
      >
        {{ p.label }}
      </button>
    </div>

    <!-- 搜索框 -->
    <div class="search-row">
      <el-input
        v-model="keyword"
        :placeholder="music.searchPlatform === 'all' ? '搜索网易云 / QQ / B站…' : `搜索 ${platforms.find((p) => p.value === music.searchPlatform)?.label}…`"
        size="large"
        clearable
        @keyup.enter="handleSearch"
      >
        <template #append>
          <el-button :loading="music.searching" @click="handleSearch">搜索</el-button>
        </template>
      </el-input>
    </div>

    <!-- 结果 -->
    <div class="results">
      <div v-if="music.searchResults.length === 0 && !music.searching" class="no-data">
        输入关键词搜索歌曲
      </div>
      <div v-if="music.searching" class="loading-shimmer">搜索中…{{ music.searchPlatform === 'all' ? '（三平台并行）' : '' }}</div>

      <div
        v-for="song in music.searchResults"
        :key="song.platform + song.id"
        class="song-item row-scan"
      >
        <img v-if="song.coverUrl" :src="song.coverUrl" class="cover" loading="lazy" referrerpolicy="no-referrer" />
        <span v-else class="cover cover--fallback" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M9 17V7l8-1.5v7" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/><circle cx="6.5" cy="17" r="2"/><circle cx="14" cy="15" r="2"/></svg>
        </span>

        <div class="song-info">
          <div class="song-name-row">
            <span class="song-name">{{ song.name }}</span>
            <span
              v-if="song.platform && platformColors[song.platform]"
              class="platform-dot"
              :style="{ background: platformColors[song.platform] }"
              :title="platformLabels[song.platform] || song.platform"
            ></span>
          </div>
          <span class="song-artist">{{ song.artist }}{{ song.album ? ' · ' + song.album : '' }}</span>
        </div>

        <div class="song-actions">
          <button class="act act--play" title="播放" @click="handlePlay(song, false)">
            <svg viewBox="0 0 24 24"><path d="M8 5.5v13l11-6.5z" fill="currentColor"/></svg>
          </button>
          <button class="act" title="加入队列" @click="handlePlay(song, true)">
            <svg viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.panel {
  background: var(--gradient-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 18px;
}

.panel-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-subtle);
}
.panel-title-group {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.panel-title {
  font-size: 1em;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}
.panel-sub {
  font-size: 0.66em;
  color: var(--text-muted);
}

/* 平台切换 */
.platform-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 14px;
}
.platform-tab {
  padding: 5px 14px;
  border: 1px solid var(--border-default);
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.78em;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
  white-space: nowrap;
}
.platform-tab:hover {
  background: var(--surface-4);
  color: var(--text-primary);
}
.platform-tab.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--text-inverse);
}

.search-row {
  margin-bottom: 14px;
}

.results {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 560px;
  overflow-y: auto;
}

.song-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.15s;
}
.song-item:hover {
  background: var(--surface-4);
}

.cover {
  width: 44px;
  height: 44px;
  border-radius: 6px;
  flex-shrink: 0;
  object-fit: cover;
  background: var(--surface-4);
}
.cover--fallback {
  display: grid;
  place-items: center;
  color: var(--text-muted);
}
.cover--fallback svg {
  width: 22px;
  height: 22px;
}

.song-info {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
  flex: 1;
}
.song-name-row {
  display: flex;
  align-items: center;
  gap: 7px;
}
.song-name {
  font-weight: 600;
  font-size: 0.86em;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.platform-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.song-artist {
  font-size: 0.72em;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.song-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s;
}
.song-item:hover .song-actions,
.song-item:focus-within .song-actions {
  opacity: 1;
}
@media (hover: none) {
  .song-actions {
    opacity: 1;
  }
}

.act {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  border: 1px solid var(--border-emphasis);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s, background 0.15s, transform 0.12s;
}
.act svg {
  width: 15px;
  height: 15px;
}
.act:hover {
  color: var(--color-primary);
  border-color: var(--color-primary);
}
.act:active {
  transform: scale(0.92);
}
.act--play {
  border: none;
  background: var(--gradient-brand);
  color: var(--text-inverse);
}
.act--play:hover {
  color: var(--text-inverse);
  border: none;
  filter: brightness(1.08);
}

.no-data {
  text-align: center;
  color: var(--text-muted);
  padding: 36px;
  font-size: 0.86em;
}
</style>
