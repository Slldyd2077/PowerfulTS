<script setup lang="ts">
import { ref } from 'vue'
import type { Song } from '@/api/music'

defineProps<{ song: Song }>()
const emit = defineEmits<{
  (e: 'play', song: Song, queued: boolean): void
}>()

// 单行封面失败回退（歌曲 URL 固定，失败一次回退即可；组件随 v-for key 重建时自动重置）
const coverFailed = ref(false)

function fmt(sec?: number): string {
  if (!sec || sec < 0) return ''
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}
</script>

<template>
  <div class="song-item row-scan">
    <img
      v-if="song.coverUrl && !coverFailed"
      :src="song.coverUrl"
      class="cover"
      loading="lazy"
      referrerpolicy="no-referrer"
      @error="coverFailed = true"
    />
    <span v-else class="cover cover--fallback" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="currentColor"><path d="M9 17V7l8-1.5v7" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/><circle cx="6.5" cy="17" r="2"/><circle cx="14" cy="15" r="2"/></svg>
    </span>

    <div class="song-info">
      <div class="song-name-row">
        <span class="song-name">{{ song.name }}</span>
        <span v-if="song.vip" class="vip-badge" title="VIP / 版权受限：非会员仅能试听片段">VIP</span>
      </div>
      <span class="song-artist">{{ song.artist }}{{ song.album ? ' · ' + song.album : '' }}</span>
    </div>

    <span v-if="song.duration" class="song-dur mono">{{ fmt(song.duration) }}</span>

    <div class="song-actions">
      <button class="act act--play" title="播放" @click="emit('play', song, false)">
        <svg viewBox="0 0 24 24"><path d="M8 5.5v13l11-6.5z" fill="currentColor"/></svg>
      </button>
      <button class="act" title="加入队列" @click="emit('play', song, true)">
        <svg viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
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
.song-item:hover { background: var(--surface-4); }
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
.cover--fallback svg { width: 22px; height: 22px; }
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
  gap: 6px;
  min-width: 0;
}
.song-name {
  font-weight: 600;
  font-size: 0.86em;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.vip-badge {
  flex-shrink: 0;
  font-size: 0.58em;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #f5a623;
  background: rgba(245, 166, 35, 0.12);
  border: 1px solid rgba(245, 166, 35, 0.4);
  border-radius: 3px;
  padding: 0 4px;
  line-height: 1.6;
}
.song-artist {
  font-size: 0.72em;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.song-dur {
  font-size: 0.66em;
  color: var(--text-muted);
  flex-shrink: 0;
}
.song-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s;
}
.song-item:hover .song-actions,
.song-item:has(:focus-visible) .song-actions { opacity: 1; }
@media (hover: none) { .song-actions { opacity: 1; } }
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
.act svg { width: 15px; height: 15px; }
.act:hover { color: var(--color-primary); border-color: var(--color-primary); }
.act:active { transform: scale(0.92); }
.act--play {
  border: none;
  background: var(--gradient-brand);
  color: var(--text-inverse);
}
.act--play:hover { color: var(--text-inverse); border: none; filter: brightness(1.08); }

/* 小屏：隐藏时长让位标题、放大操作按钮触摸区 */
@media (max-width: 480px) {
  .song-dur { display: none; }
  .act { width: 36px; height: 36px; }
}
</style>
