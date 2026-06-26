<script setup lang="ts">
import { ref, reactive, onMounted, onBeforeUnmount } from 'vue'
import { useMusicStore } from '@/stores/music'
import { ElMessage } from 'element-plus'
import EqualizerBars from '@/components/music/EqualizerBars.vue'
import type { Song } from '@/api/music'

const music = useMusicStore()
const keyword = ref('')
// 封面加载失败回退（B 站等封面偶尔因防盗链 / 域名失效而 404，避免破损图标）
const brokenCovers = reactive(new Set<string>())
function onCoverError(url?: string) {
  if (url) brokenCovers.add(url)
}

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
  // 新搜索：重置封面失败标记，让本轮结果封面重新尝试加载
  brokenCovers.clear()
  await music.search(keyword.value)
}

async function handlePlay(song: Song, queued = false) {
  try {
    // 透传完整 song 元数据：QQ 音乐入队后上游会丢失 name/coverUrl，后端用它回填队列
    await music.play(`id:${song.id}`, queued, song.platform, song)
    ElMessage.success(queued ? `加入队列: ${song.name}` : `正在播放: ${song.name}`)
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '播放失败')
  }
}

// 一体化搜索栏：聚焦态 + 「/」全局快捷键聚焦
const inputFocused = ref(false)
const inputEl = ref<HTMLInputElement | null>(null)

function clearKeyword() {
  keyword.value = ''
  inputEl.value?.focus()
}
function focusSearch() {
  inputEl.value?.focus()
}
function onGlobalKey(e: KeyboardEvent) {
  const t = e.target as HTMLElement | null
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
  if (e.ctrlKey || e.metaKey || e.altKey) return
  if (e.repeat) return
  if (e.key === '/') {
    e.preventDefault()
    focusSearch()
  }
}
onMounted(() => window.addEventListener('keydown', onGlobalKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onGlobalKey))
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

    <!-- 一体化搜索栏 -->
    <div class="search-row">
      <div class="search-bar" :class="{ focused: inputFocused }">
        <svg class="sb-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></svg>

        <input
          ref="inputEl"
          v-model="keyword"
          class="sb-input"
          type="text"
          aria-label="搜索歌曲"
          :placeholder="music.searchPlatform === 'all' ? '搜索网易云 / QQ / B站…' : `搜索 ${platforms.find((p) => p.value === music.searchPlatform)?.label}…`"
          @keyup.enter="handleSearch"
          @focus="inputFocused = true"
          @blur="inputFocused = false"
        />

        <button
          v-if="keyword && !music.searching"
          class="sb-clear"
          type="button"
          title="清空"
          @click="clearKeyword"
        >
          <svg viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
        <kbd v-else-if="!keyword && !inputFocused" class="sb-kbd" aria-hidden="true">/</kbd>

        <button
          class="sb-go"
          type="button"
          :disabled="!keyword.trim() || music.searching"
          :title="music.searching ? '搜索中…' : '搜索（回车）'"
          @click="handleSearch"
        >
          <span v-if="music.searching" class="sb-spin"></span>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></svg>
          <span class="sb-go-text">搜索</span>
        </button>
      </div>
    </div>

    <!-- 结果 -->
    <div class="results">
      <div v-if="music.searchResults.length === 0 && !music.searching" class="no-data">
        输入关键词搜索歌曲
      </div>

      <div v-if="music.searching" class="searching-row">
        <EqualizerBars class="searching-eq" :active="true" />
        <span>搜索中…</span>
        <span v-if="music.searchPlatform === 'all'" class="searching-hint label-mono">三平台并行</span>
      </div>

      <div
        v-for="(song, i) in music.searchResults"
        :key="song.platform + song.id"
        class="song-item row-scan animate-in"
        :style="{ animationDelay: Math.min(i, 12) * 0.04 + 's' }"
      >
        <img v-if="song.coverUrl && !brokenCovers.has(song.coverUrl)" :src="song.coverUrl" class="cover" loading="lazy" referrerpolicy="no-referrer" @error="onCoverError(song.coverUrl)" />
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
  transition: color 0.18s var(--ease-out-expo), border-color 0.18s var(--ease-out-expo), background 0.18s var(--ease-out-expo), transform 0.12s;
  white-space: nowrap;
}
.platform-tab:hover {
  background: var(--surface-4);
  color: var(--text-primary);
}
.platform-tab:active {
  transform: scale(0.96);
}
.platform-tab.active {
  background: var(--surface-4);
  border-color: var(--border-emphasis);
  color: var(--text-primary);
}

/* ── 一体化搜索栏 ── */
.search-row {
  margin-bottom: 14px;
}
.search-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 42px;
  padding: 0 0 0 13px;
  background: var(--surface-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  transition: border-color 0.2s var(--ease-out-expo), box-shadow 0.2s var(--ease-out-expo);
}
.search-bar.focused {
  border-color: var(--color-primary);
  box-shadow: var(--glow-primary);
}
.sb-icon {
  width: 17px;
  height: 17px;
  color: var(--text-muted);
  flex-shrink: 0;
  transition: color 0.2s;
}
.search-bar.focused .sb-icon {
  color: var(--text-secondary);
}
.sb-input {
  flex: 1;
  min-width: 0;
  height: 100%;
  background: transparent;
  border: 0;
  outline: 0;
  color: var(--text-primary);
  font-size: 0.9em;
  font-family: inherit;
}
.sb-input::placeholder {
  color: var(--text-muted);
}
.sb-clear {
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
}
.sb-clear svg {
  width: 14px;
  height: 14px;
}
.sb-clear:hover {
  color: var(--text-primary);
  background: var(--surface-4);
}
.sb-kbd {
  flex-shrink: 0;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.66em;
  color: var(--text-muted);
  border: 1px solid var(--border-emphasis);
  border-radius: 4px;
  padding: 1px 7px;
  line-height: 1.5;
}
.sb-go {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  height: 100%;
  padding: 0 16px;
  margin-left: auto;
  border: 0;
  border-radius: 0 calc(var(--radius-md) - 1px) calc(var(--radius-md) - 1px) 0;
  background: var(--gradient-brand);
  color: var(--text-inverse);
  font-weight: 600;
  font-size: 0.82em;
  letter-spacing: 0.02em;
  cursor: pointer;
  transition: filter 0.2s, opacity 0.2s, transform 0.12s;
}
.sb-go svg {
  width: 15px;
  height: 15px;
}
.sb-go:hover:not(:disabled) {
  filter: brightness(1.08);
}
.sb-go:active:not(:disabled) {
  transform: scale(0.98);
}
.sb-go:disabled {
  opacity: 0.45;
  cursor: default;
}
.sb-spin {
  width: 15px;
  height: 15px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  border-radius: 50%;
  animation: sb-spin 0.7s linear infinite;
}
@keyframes sb-spin {
  to {
    transform: rotate(360deg);
  }
}

/* ── 结果 ── */
.results {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 560px;
  overflow-y: auto;
}

.searching-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 10px;
  color: var(--text-secondary);
  font-size: 0.82em;
}
.searching-eq {
  color: var(--color-primary);
  height: 14px;
}
.searching-hint {
  font-size: 0.78em;
  color: var(--text-muted);
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
  transition: transform 0.28s var(--ease-out-expo);
}
.song-item:hover .cover {
  transform: scale(1.07);
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
