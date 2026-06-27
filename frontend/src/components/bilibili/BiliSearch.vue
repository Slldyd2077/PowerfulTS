<script setup lang="ts">
import { ref } from 'vue'
import { useBiliStore } from '@/stores/bilibili'
import { cleanTitle, picUrl } from '@/api/bilibili'
import { ElMessage } from 'element-plus'

const bili = useBiliStore()
const keyword = ref('')

async function handleSearch() {
  if (!keyword.value.trim()) return
  await bili.search(keyword.value)
}

async function handlePlay(bvid: string) {
  const video = bili.results.find((v) => v.bvid === bvid)
  if (!video) return
  try {
    await bili.play(video)
    ElMessage.success(`正在播放: ${cleanTitle(video.title).slice(0, 20)}`)
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '播放失败')
  }
}
</script>

<template>
  <div class="panel">
    <h2 class="panel-title">📺 B站点播</h2>

    <div class="search-row">
      <el-input
        v-model="keyword"
        placeholder="搜索 B 站视频…"
        size="large"
        clearable
        @keyup.enter="handleSearch"
      >
        <template #append>
          <el-button :loading="bili.searching" @click="handleSearch">搜索</el-button>
        </template>
      </el-input>
    </div>

    <div class="results">
      <div v-if="bili.results.length === 0 && !bili.searching" class="no-data">
        输入关键词搜索 B 站视频
      </div>
      <div v-if="bili.searching" class="loading">搜索中…</div>

      <div
        v-for="v in bili.results"
        :key="v.bvid"
        class="video-card"
        :class="{ active: bili.playingBvid === v.bvid }"
      >
        <div class="thumb-wrap">
          <img v-if="v.pic" :src="picUrl(v.pic)" class="thumb" loading="lazy" />
          <span v-if="v.duration" class="duration">{{ v.duration }}</span>
        </div>
        <div class="info">
          <span class="title">{{ cleanTitle(v.title) }}</span>
          <span class="meta">
            <span class="author">{{ v.author }}</span>
          </span>
        </div>
        <el-button
          :type="bili.playingBvid === v.bvid ? 'success' : 'primary'"
          size="small"
          plain
          @click="handlePlay(v.bvid)"
        >
          {{ bili.playingBvid === v.bvid ? '播放中' : '播放' }}
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

.search-row {
  margin-bottom: 16px;
}

.results {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 420px;
  overflow-y: auto;
}

.video-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid transparent;
  border-radius: 8px;
  transition: all 0.2s;
}

.video-card:hover {
  background: var(--bg-card-hover);
  border-color: var(--border-color);
}

.video-card.active {
  border-color: var(--el-color-primary);
  background: rgba(64, 158, 255, 0.08);
}

.thumb-wrap {
  position: relative;
  flex-shrink: 0;
  width: 128px;
  height: 72px;
  border-radius: 6px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.3);
}

.thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.duration {
  position: absolute;
  right: 4px;
  bottom: 4px;
  padding: 1px 5px;
  font-size: 0.72em;
  color: #fff;
  background: rgba(0, 0, 0, 0.72);
  border-radius: 3px;
}

.info {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  flex: 1;
}

.title {
  font-size: 0.92em;
  font-weight: 600;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.meta {
  font-size: 0.8em;
  color: var(--text-secondary);
}

.no-data,
.loading {
  text-align: center;
  color: var(--text-muted);
  padding: 30px;
}

.loading {
  font-style: italic;
}

/* 移动端：收缩缩略图与内边距、结果随页面滚动 */
@media (max-width: 768px) {
  .panel { padding: 14px; }
  .thumb-wrap { width: 104px; height: 58px; }
  .results { max-height: none; }
}

@media (max-width: 480px) {
  .thumb-wrap { width: 88px; height: 50px; }
  .video-card { gap: 10px; padding: 6px; }
}
</style>
