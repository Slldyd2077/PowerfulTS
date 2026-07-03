<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { useMusicStore } from '@/stores/music'
import { ElMessage } from 'element-plus'
import EqualizerBars from '@/components/music/EqualizerBars.vue'
import SongRow from '@/components/music/SongRow.vue'
import type { Song, Playlist } from '@/api/music'

const music = useMusicStore()

const myPlatforms = [
  { value: 'netease', label: '网易云', color: '#e60026' },
  { value: 'qq', label: 'QQ音乐', color: '#31c27c' },
  { value: 'bilibili', label: 'B站', color: '#fb7299' },
] as const

// 歌单封面失败回退（切换平台时 clear，让新平台封面重新尝试）
const brokenCovers = reactive(new Set<string>())
function onCoverError(url?: string) {
  if (url) brokenCovers.add(url)
}

const expandedPlaylist = ref<string | null>(null)
const openSections = reactive<Record<string, boolean>>({ playlists: true, recommend: false, fm: false, biliPopular: true })

const active = computed(() => music.myActivePlatform)
const isLoggedIn = computed(() => !!music.platformStatus[active.value]?.loggedIn)
const playlists = computed(() => music.myPlaylists[active.value] || [])
const recommend = computed(() => music.myRecommend[active.value] || [])
const fm = computed(() => music.myFm[active.value] || [])

function selectPlatform(value: 'netease' | 'qq' | 'bilibili') {
  // 网易云/QQ 未登录禁止切换；B站热门无需登录
  if (value !== 'bilibili' && !music.platformStatus[value]?.loggedIn) {
    ElMessage.info('请先在右侧「平台账号」登录该平台')
    return
  }
  if (value !== music.myActivePlatform) {
    music.myActivePlatform = value
    brokenCovers.clear()
    expandedPlaylist.value = null
  }
}

/** 加载当前平台内容（歌单懒加载；网易云/QQ 需登录） */
function loadActive() {
  const p = active.value
  if (p === 'bilibili') {
    // 热门视频（无需登录）
    if (!music.bilibiliPopularLoaded && !music.myLoading['bilibili:popular']) {
      music.fetchBilibiliPopular()
    }
    // 收藏夹（需登录；active=bilibili 时 fetchMyPlaylists 走上游 B 站收藏夹端点）
    if (isLoggedIn.value && music.myPlaylists['bilibili'] === undefined && !music.myLoading['bilibili:playlists']) {
      music.fetchMyPlaylists('bilibili')
    }
    return
  }
  if (!isLoggedIn.value) return
  if (music.myPlaylists[p] === undefined && !music.myUnsupported[`${p}:playlists`] && !music.myLoading[`${p}:playlists`]) {
    music.fetchMyPlaylists(p)
  }
}

watch(() => active.value, () => loadActive(), { immediate: true })
// 登录态由 PlatformAccounts 异步写入 store，变 true 时触发加载
watch(() => isLoggedIn.value, (v) => { if (v) loadActive() })

async function togglePlaylist(pl: Playlist) {
  if (expandedPlaylist.value === pl.id) {
    expandedPlaylist.value = null
    return
  }
  expandedPlaylist.value = pl.id
  if (music.playlistSongs[pl.id] === undefined) {
    await music.fetchPlaylistSongs(pl.id, active.value)
  }
}

/** 整单加入队列（后端循环 add，上限 50 首） */
async function playAllPlaylist(pl: Playlist) {
  try {
    if (music.playlistSongs[pl.id] === undefined) {
      await music.fetchPlaylistSongs(pl.id, active.value)
    }
    const songs = music.playlistSongs[pl.id] || []
    if (songs.length === 0) {
      ElMessage.warning('该歌单暂无可播放的歌曲')
      return
    }
    const res = await music.enqueueAll(songs, active.value)
    ElMessage.success(`已加入 ${res.enqueued} 首到队列${res.failed ? `（${res.failed} 首失败）` : ''}`)
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '整单播放失败')
  }
}

function toggleSection(key: 'recommend' | 'fm') {
  openSections[key] = !openSections[key]
  if (openSections[key]) {
    const p = active.value
    if (key === 'recommend' && music.myRecommend[p] === undefined) music.fetchRecommend(p)
    if (key === 'fm' && music.myFm[p] === undefined) music.fetchPersonalFm(p)
  }
}

/** 播放/加入队列（与点歌面板同一入口，行为一致） */
async function handlePlay(song: Song, queued = false) {
  try {
    await music.play(`id:${song.id}`, queued, song.platform || active.value, song)
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
        <h2 class="panel-title">我的音乐</h2>
        <span class="panel-sub label-mono">MY MUSIC</span>
      </div>
    </div>

    <!-- 平台 tab -->
    <div class="platform-tabs">
      <button
        v-for="p in myPlatforms"
        :key="p.value"
        class="platform-tab"
        :class="{ active: active === p.value, disabled: p.value !== 'bilibili' && !music.platformStatus[p.value]?.loggedIn }"
        @click="selectPlatform(p.value)"
      >
        <span class="pt-label">{{ p.label }}</span>
        <span v-if="p.value !== 'bilibili' && !music.platformStatus[p.value]?.loggedIn" class="pt-lock">未登录</span>
      </button>
    </div>

    <div class="my-content">
      <!-- B站：收藏夹（登录后）+ 热门视频 -->
      <template v-if="active === 'bilibili'">
        <!-- 我的收藏夹 -->
        <section v-if="isLoggedIn" class="section">
          <div class="section-head" @click="openSections.playlists = !openSections.playlists">
            <span class="section-title">我的收藏夹</span>
            <span class="section-count mono">{{ playlists.length }}</span>
            <svg class="section-arrow" :class="{ open: openSections.playlists }" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </div>
          <div v-show="openSections.playlists" class="section-body">
            <div v-if="music.myLoading['bilibili:playlists']" class="loading-row">
              <EqualizerBars class="loading-eq" :active="true" /><span>加载中…</span>
            </div>
            <div v-else-if="playlists.length === 0" class="no-data">暂无收藏夹</div>
            <div v-else class="playlist-list">
              <div v-for="pl in playlists" :key="pl.id" class="playlist-item">
                <div class="playlist-row" :class="{ expanded: expandedPlaylist === pl.id }" @click="togglePlaylist(pl)">
                  <img
                    v-if="pl.coverUrl && !brokenCovers.has(pl.coverUrl)"
                    :src="pl.coverUrl"
                    class="pl-cover"
                    loading="lazy"
                    referrerpolicy="no-referrer"
                    @error="onCoverError(pl.coverUrl)"
                  />
                  <span v-else class="pl-cover pl-cover--fallback" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="currentColor"><path d="M9 17V7l8-1.5v7" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/><circle cx="6.5" cy="17" r="2"/><circle cx="14" cy="15" r="2"/></svg>
                  </span>
                  <div class="pl-info">
                    <span class="pl-name">{{ pl.name }}</span>
                    <span class="pl-count">{{ pl.songCount || 0 }} 个视频</span>
                  </div>
                  <button class="pl-enqueue" title="整单加入队列" @click.stop="playAllPlaylist(pl)">
                    <svg viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
                  </button>
                  <svg class="pl-arrow" :class="{ open: expandedPlaylist === pl.id }" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
                </div>
                <!-- 展开的视频 -->
                <div v-if="expandedPlaylist === pl.id" class="playlist-songs">
                  <div v-if="music.myLoading[`song:${pl.id}`]" class="loading-row">
                    <EqualizerBars class="loading-eq" :active="true" /><span>加载中…</span>
                  </div>
                  <div v-else-if="(music.playlistSongs[pl.id] || []).length === 0" class="no-data">暂无视频</div>
                  <SongRow
                    v-for="s in (music.playlistSongs[pl.id] || [])"
                    :key="s.id"
                    :song="s"
                    @play="handlePlay"
                  />
                </div>
              </div>
            </div>
          </div>
        </section>
        <div v-else class="no-data">登录 B 站后可查看收藏夹</div>

        <!-- 热门视频 -->
        <section class="section">
          <div class="section-head" @click="openSections.biliPopular = !openSections.biliPopular">
            <span class="section-title">热门视频</span>
            <svg class="section-arrow" :class="{ open: openSections.biliPopular }" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </div>
          <div v-show="openSections.biliPopular" class="section-body">
            <div v-if="music.myLoading['bilibili:popular']" class="loading-row">
              <EqualizerBars class="loading-eq" :active="true" /><span>加载中…</span>
            </div>
            <div v-else-if="music.bilibiliPopular.length === 0" class="no-data">暂无热门视频</div>
            <SongRow v-for="s in music.bilibiliPopular" :key="s.id" :song="s" @play="handlePlay" />
          </div>
        </section>
      </template>

      <!-- 网易云/QQ 未登录 -->
      <div v-else-if="!isLoggedIn" class="no-data">
        请先在右侧「平台账号」登录{{ myPlatforms.find((p) => p.value === active)?.label }}
      </div>

      <!-- 网易云/QQ 已登录：三块折叠分区 -->
      <template v-else>
        <!-- 我的歌单 -->
        <section class="section">
          <div class="section-head" @click="openSections.playlists = !openSections.playlists">
            <span class="section-title">我的歌单</span>
            <span class="section-count mono">{{ playlists.length }}</span>
            <svg class="section-arrow" :class="{ open: openSections.playlists }" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </div>
          <div v-show="openSections.playlists" class="section-body">
            <div v-if="music.myLoading[`${active}:playlists`]" class="loading-row">
              <EqualizerBars class="loading-eq" :active="true" /><span>加载中…</span>
            </div>
            <div v-else-if="playlists.length === 0" class="no-data">暂无歌单</div>
            <div v-else class="playlist-list">
              <div v-for="pl in playlists" :key="pl.id" class="playlist-item">
                <div class="playlist-row" :class="{ expanded: expandedPlaylist === pl.id }" @click="togglePlaylist(pl)">
                  <img
                    v-if="pl.coverUrl && !brokenCovers.has(pl.coverUrl)"
                    :src="pl.coverUrl"
                    class="pl-cover"
                    loading="lazy"
                    referrerpolicy="no-referrer"
                    @error="onCoverError(pl.coverUrl)"
                  />
                  <span v-else class="pl-cover pl-cover--fallback" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="currentColor"><path d="M9 17V7l8-1.5v7" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/><circle cx="6.5" cy="17" r="2"/><circle cx="14" cy="15" r="2"/></svg>
                  </span>
                  <div class="pl-info">
                    <span class="pl-name">{{ pl.name }}</span>
                    <span class="pl-count">{{ pl.songCount || 0 }} 首</span>
                  </div>
                  <button class="pl-enqueue" title="整单加入队列" @click.stop="playAllPlaylist(pl)">
                    <svg viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
                  </button>
                  <svg class="pl-arrow" :class="{ open: expandedPlaylist === pl.id }" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
                </div>
                <!-- 展开的歌曲 -->
                <div v-if="expandedPlaylist === pl.id" class="playlist-songs">
                  <div v-if="music.myLoading[`song:${pl.id}`]" class="loading-row">
                    <EqualizerBars class="loading-eq" :active="true" /><span>加载中…</span>
                  </div>
                  <div v-else-if="(music.playlistSongs[pl.id] || []).length === 0" class="no-data">暂无歌曲</div>
                  <SongRow
                    v-for="s in (music.playlistSongs[pl.id] || [])"
                    :key="s.id"
                    :song="s"
                    @play="handlePlay"
                  />
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 每日推荐 -->
        <section class="section">
          <div class="section-head" @click="toggleSection('recommend')">
            <span class="section-title">每日推荐</span>
            <svg class="section-arrow" :class="{ open: openSections.recommend }" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </div>
          <div v-show="openSections.recommend" class="section-body">
            <div v-if="music.myUnsupported[`${active}:recommend`]" class="no-data">该平台不支持每日推荐</div>
            <div v-else-if="music.myLoading[`${active}:recommend`]" class="loading-row">
              <EqualizerBars class="loading-eq" :active="true" /><span>加载中…</span>
            </div>
            <div v-else-if="recommend.length === 0" class="no-data">暂无推荐</div>
            <SongRow v-for="s in recommend" :key="s.id" :song="s" @play="handlePlay" />
          </div>
        </section>

        <!-- 私人 FM -->
        <section class="section">
          <div class="section-head" @click="toggleSection('fm')">
            <span class="section-title">私人 FM</span>
            <button v-if="openSections.fm && fm.length > 0" class="fm-refresh" @click.stop="music.fetchPersonalFm(active)">
              <svg viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 11-3-6.7"/><path d="M21 4v5h-5"/></svg>
              换一批
            </button>
            <svg class="section-arrow" :class="{ open: openSections.fm }" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </div>
          <div v-show="openSections.fm" class="section-body">
            <div v-if="music.myUnsupported[`${active}:fm`]" class="no-data">该平台不支持私人 FM</div>
            <div v-else-if="music.myLoading[`${active}:fm`]" class="loading-row">
              <EqualizerBars class="loading-eq" :active="true" /><span>加载中…</span>
            </div>
            <div v-else-if="fm.length === 0" class="no-data">暂无歌曲</div>
            <SongRow v-for="s in fm" :key="s.id" :song="s" @play="handlePlay" />
          </div>
        </section>
      </template>
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
.panel-title-group { display: flex; align-items: baseline; gap: 8px; }
.panel-title { font-size: 1em; font-weight: 600; color: var(--text-primary); margin: 0; }
.panel-sub { font-size: 0.66em; color: var(--text-muted); }

.platform-tabs { display: flex; gap: 6px; margin-bottom: 14px; }
.platform-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
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
.platform-tab:hover { background: var(--surface-4); color: var(--text-primary); }
.platform-tab.active {
  background: rgba(var(--color-primary-rgb), 0.12);
  border-color: rgba(var(--color-primary-rgb), 0.45);
  color: var(--color-primary);
  font-weight: 600;
}
.platform-tab.disabled { opacity: 0.45; cursor: not-allowed; }
.platform-tab.disabled:hover { background: transparent; color: var(--text-muted); }
.pt-lock { font-size: 0.85em; color: var(--text-muted); }

.my-content { display: flex; flex-direction: column; gap: 4px; }

.loading-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 10px;
  color: var(--text-secondary);
  font-size: 0.82em;
}
.loading-eq { color: var(--color-primary); height: 14px; }
.no-data {
  text-align: center;
  color: var(--text-muted);
  padding: 22px 10px;
  font-size: 0.82em;
}

.section { border-top: 1px solid var(--border-subtle); padding: 6px 0; }
.section:first-child { border-top: none; }
.section-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 6px;
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: background 0.15s;
}
.section-head:hover { background: var(--surface-4); }
.section-title { font-size: 0.84em; font-weight: 600; color: var(--text-primary); }
.section-count { font-size: 0.66em; color: var(--text-muted); }
.section-arrow {
  width: 14px;
  height: 14px;
  color: var(--text-muted);
  margin-left: auto;
  transition: transform 0.2s var(--ease-out-expo);
  transform: rotate(-90deg);
}
.section-arrow.open { transform: rotate(0); }
.section-body { padding: 2px 0 6px; }

.fm-refresh {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border: 1px solid var(--border-emphasis);
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.72em;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}
.fm-refresh svg { width: 12px; height: 12px; }
.fm-refresh:hover { color: var(--color-primary); border-color: var(--color-primary); }

.playlist-list { display: flex; flex-direction: column; }
.playlist-item { border-bottom: 1px solid var(--border-subtle); }
.playlist-item:last-child { border-bottom: none; }
.playlist-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 6px;
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: background 0.15s;
}
.playlist-row:hover { background: var(--surface-4); }
.playlist-row.expanded { background: var(--surface-4); }
.playlist-row.expanded .pl-name { color: var(--color-primary); }
.pl-cover {
  width: 40px;
  height: 40px;
  border-radius: 6px;
  flex-shrink: 0;
  object-fit: cover;
  background: var(--surface-4);
}
.pl-cover--fallback { display: grid; place-items: center; color: var(--text-muted); }
.pl-cover--fallback svg { width: 20px; height: 20px; }
.pl-info { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.pl-name {
  font-size: 0.84em;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pl-count { font-size: 0.66em; color: var(--text-muted); }
.pl-enqueue {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  border: 1px solid var(--border-emphasis);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  flex-shrink: 0;
  transition: color 0.15s, border-color 0.15s;
}
.pl-enqueue svg { width: 14px; height: 14px; }
.pl-enqueue:hover { color: var(--color-primary); border-color: var(--color-primary); }
.pl-arrow {
  width: 14px;
  height: 14px;
  color: var(--text-muted);
  flex-shrink: 0;
  transition: transform 0.2s var(--ease-out-expo);
  transform: rotate(-90deg);
}
.pl-arrow.open { transform: rotate(0); }
.playlist-songs {
  margin: 4px 0 8px 12px;
  padding: 6px 4px 6px 12px;
  border-left: 2px solid var(--color-primary);
  background: var(--surface-3);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}

/* 移动端：平台 tab 允许换行、收缩展开歌曲的缩进 */
@media (max-width: 768px) {
  .panel { padding: 14px; }
  .platform-tabs { flex-wrap: wrap; }
  .playlist-songs { margin-left: 6px; padding-left: 8px; }
}
</style>
