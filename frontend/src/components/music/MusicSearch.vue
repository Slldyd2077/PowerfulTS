<script setup lang="ts">
import { ref } from 'vue'
import { useMusicStore } from '@/stores/music'
import { ElMessage } from 'element-plus'

const music = useMusicStore()
const keyword = ref('')

async function handleSearch() {
  if (!keyword.value.trim()) return
  await music.search(keyword.value)
}

async function handlePlay(songId: string, songName: string) {
  try {
    await music.play(songId, songName)
    ElMessage.success(`正在播放: ${songName}`)
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '播放失败')
  }
}
</script>

<template>
  <div class="panel">
    <h2 class="panel-title">🎵 点歌</h2>

    <!-- 音源切换 -->
    <div class="source-row">
      <el-radio-group v-model="music.source" size="small">
        <el-radio-button value="netease">网易云</el-radio-button>
        <el-radio-button value="default">默认</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 搜索框 -->
    <div class="search-row">
      <el-input
        v-model="keyword"
        placeholder="搜索歌曲名或歌手..."
        size="large"
        clearable
        @keyup.enter="handleSearch"
      >
        <template #append>
          <el-button :loading="music.searching" @click="handleSearch">搜索</el-button>
        </template>
      </el-input>
    </div>

    <!-- 搜索结果 -->
    <div class="results">
      <div v-if="music.searchResults.length === 0 && !music.searching" class="no-data">
        输入关键词搜索歌曲
      </div>
      <div v-if="music.searching" class="loading">搜索中...</div>

      <div
        v-for="song in music.searchResults"
        :key="song.song_id"
        class="song-item"
      >
        <div class="song-info">
          <span class="song-name">{{ song.song_name }}</span>
          <span class="song-artist">{{ song.artist }}</span>
        </div>
        <el-button
          type="warning"
          size="small"
          plain
          @click="handlePlay(song.song_id, song.song_name)"
        >
          播放
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.panel {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  padding: 20px;
}

.panel-title {
  font-size: 1.1em;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-primary);
}

.source-row {
  margin-bottom: 12px;
}

.search-row {
  margin-bottom: 16px;
}

.results {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 360px;
  overflow-y: auto;
}

.song-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 8px;
  transition: background 0.2s;
}

.song-item:hover {
  background: var(--bg-card-hover);
}

.song-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.song-name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.song-artist {
  font-size: 0.85em;
  color: var(--text-secondary);
}

.no-data {
  text-align: center;
  color: var(--text-muted);
  padding: 30px;
  font-style: italic;
}

.loading {
  text-align: center;
  color: var(--text-secondary);
  padding: 20px;
}
</style>
