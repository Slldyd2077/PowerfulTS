<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useMusicStore } from '@/stores/music'
import { usePolling } from '@/composables/usePolling'
import { ElMessage } from 'element-plus'

const music = useMusicStore()

// 本地进度（每秒递增，轮询校正）
const localPosition = ref(0)
let tickTimer: number | null = null

onMounted(() => {
  music.fetchVolume()
  music.fetchQueue()
  music.fetchNowplaying()
})

usePolling(async () => {
  await music.fetchNowplaying()
  await music.fetchQueue()
}, 5000)

// 轮询到的 position 作为基准，校正本地
watch(() => music.nowplaying?.position, (pos) => {
  if (typeof pos === 'number') localPosition.value = pos
})

// 每秒递增（播放中）
tickTimer = window.setInterval(() => {
  if (music.nowplaying?.playing) {
    const len = music.nowplaying?.length || 0
    if (len <= 0 || localPosition.value < len) localPosition.value += 1
  }
}, 1000)
onUnmounted(() => { if (tickTimer) clearInterval(tickTimer) })

const title = computed(() => music.currentTitle || npShortTitle())
function npShortTitle(): string {
  const t = music.nowplaying?.title || ''
  if (!t) return ''
  try {
    const u = new URL(t)
    return (u.hostname.includes('126.net') ? '网易云' : u.hostname.includes('bilibili') || u.hostname.includes('bilivideo') ? 'B站' : u.hostname) + u.pathname.slice(-12)
  } catch {
    return t.length > 36 ? t.slice(0, 36) + '…' : t
  }
}

const length = computed(() => music.nowplaying?.length || 0)

function fmt(sec?: number): string {
  if (!sec || sec < 0) return '0:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

async function handleVolumeChange(val: number | number[]) {
  try { await music.updateVolume(val as number) } catch { ElMessage.error('音量设置失败') }
}
async function handlePause() { try { await music.pause() } catch { ElMessage.error('操作失败') } }
async function handleSkip() { try { await music.skip(); ElMessage.success('已跳过') } catch { ElMessage.error('跳过失败') } }
async function handleStop() { try { await music.stop(); ElMessage.success('已停止') } catch { ElMessage.error('停止失败') } }
async function handleClear() { try { await music.clear(); ElMessage.success('已清空队列') } catch { ElMessage.error('清空失败') } }

// 拖动进度条 seek
let seeking = false
function onSeekStart() { seeking = true }
async function onSeekChange(val: number | number[]) {
  if (!seeking) return
  seeking = false
  try {
    await music.seek(val as number)
    localPosition.value = val as number
  } catch { ElMessage.error('跳转失败') }
}

function trackTitle(item: Record<string, unknown>): string {
  return String(item.Title || item.title || item.Link || item.link || '(未知)')
}
</script>

<template>
  <div class="player">
    <!-- 当前播放 -->
    <div class="nowplaying" :class="{ playing: music.nowplaying?.playing }">
      <span class="np-icon">{{ music.nowplaying?.playing ? '🔊' : '⏸' }}</span>
      <div class="np-main">
        <div class="np-top">
          <span class="np-label">{{ music.nowplaying?.playing ? '正在播放' : '已暂停' }}</span>
          <span class="np-time">{{ fmt(localPosition) }} / {{ fmt(length) }}</span>
        </div>
        <span class="np-title">{{ title || '（空闲）' }}</span>
        <el-slider
          v-if="length > 0"
          :model-value="localPosition"
          :min="0"
          :max="length"
          :step="1"
          :show-tooltip="false"
          size="small"
          @input="onSeekStart"
          @change="onSeekChange"
        />
      </div>
    </div>

    <!-- 音量 -->
    <div class="volume-section">
      <div class="volume-header">
        <span>🔊 音量</span>
        <span class="volume-value">{{ music.volume }}%</span>
      </div>
      <el-slider v-model="music.volume" :min="0" :max="100" :show-tooltip="false" @change="handleVolumeChange" />
    </div>

    <!-- 控制按钮 -->
    <div class="controls">
      <el-button @click="handlePause" :type="music.nowplaying?.playing ? 'warning' : 'success'" plain>
        {{ music.nowplaying?.playing ? '⏸ 暂停' : '▶ 恢复' }}
      </el-button>
      <el-button @click="handleSkip" plain>⏭ 跳过</el-button>
      <el-button @click="handleStop" type="danger" plain>⏹ 停止</el-button>
      <el-button @click="handleClear" type="warning" plain>🗑 清空队列</el-button>
    </div>

    <!-- 播放队列 -->
    <div class="queue-section">
      <div class="queue-header">
        <span>📋 播放队列</span>
        <span class="queue-count">{{ music.queue.length }} 首</span>
      </div>
      <div class="queue-list">
        <div v-if="music.queue.length === 0" class="queue-empty">
          队列为空（当前播放显示在上方；点多首时排队在这里）
        </div>
        <div v-for="(item, idx) in music.queue" :key="idx" class="queue-item" :class="{ active: idx === music.currentIndex }">
          <span class="queue-index">{{ idx === music.currentIndex ? '▶' : idx + 1 }}</span>
          <span class="queue-title">{{ trackTitle(item) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.player { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--border-radius); padding: 20px; }

.nowplaying {
  display: flex; gap: 12px; padding: 12px 14px;
  background: rgba(0,0,0,0.2); border-radius: var(--radius-sm); margin-bottom: 16px;
  border-left: 3px solid var(--text-muted);
}
.nowplaying.playing { border-left-color: var(--color-primary); }
.np-icon { font-size: 1.4em; flex-shrink: 0; }
.np-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.np-top { display: flex; justify-content: space-between; align-items: center; }
.np-label { font-size: 0.64em; color: var(--text-muted); letter-spacing: 0.08em; text-transform: uppercase; }
.np-time { font-size: 0.66em; color: var(--text-muted); font-family: 'JetBrains Mono', monospace; }
.np-title { font-size: 0.88em; font-weight: 600; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.volume-section { margin-bottom: 16px; }
.volume-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.volume-value { font-weight: 700; color: var(--color-primary); }

.controls { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }

.queue-section { border-top: 1px solid var(--border-subtle); padding-top: 14px; }
.queue-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-size: 0.9em; font-weight: 600; color: var(--text-secondary); }
.queue-count { font-size: 0.8em; color: var(--text-muted); font-weight: 500; }
.queue-list { display: flex; flex-direction: column; gap: 3px; max-height: 240px; overflow-y: auto; }
.queue-empty { text-align: center; color: var(--text-muted); padding: 24px; font-size: 0.85em; font-style: italic; line-height: 1.6; }
.queue-item { display: flex; align-items: center; gap: 10px; padding: 7px 10px; border-radius: var(--radius-sm); transition: background 0.15s; }
.queue-item.active { background: rgba(45,212,191,0.1); border-left: 3px solid var(--color-primary); }
.queue-item:hover { background: var(--surface-4); }
.queue-index { width: 22px; flex-shrink: 0; text-align: center; font-size: 0.72em; color: var(--text-muted); font-family: 'JetBrains Mono', monospace; }
.queue-item.active .queue-index { color: var(--color-primary); font-size: 0.85em; }
.queue-title { font-size: 0.82em; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.queue-item.active .queue-title { color: var(--color-primary); font-weight: 600; }
</style>
