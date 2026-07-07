<script setup lang="ts">
import { computed, watch, ref, reactive, onMounted, onUnmounted } from 'vue'
import { useMusicStore } from '@/stores/music'
import { usePolling } from '@/composables/usePolling'
import { ElMessage } from 'element-plus'
import EqualizerBars from '@/components/music/EqualizerBars.vue'

const music = useMusicStore()

onMounted(async () => {
  await music.fetchBots()
  music.fetchNowplaying()
  music.fetchQueue()
})

// 3 秒轮询：当前播放 + 队列
usePolling(async () => {
  await music.fetchNowplaying()
  await music.fetchQueue()
}, 3000)

// 本地进度计时器
let tickTimer: number | null = null
const dragging = ref(false)
const lastTitle = ref('')
// 封面加载失败回退（B 站等封面偶尔因防盗链 / 域名失效而 404，避免破损图标）
const brokenCovers = reactive(new Set<string>())
function onCoverError(url?: string) {
  if (url) brokenCovers.add(url)
}

// 换歌时重置进度
watch(() => music.nowplaying?.title, (title) => {
  if (title && title !== lastTitle.value) {
    music.localPosition = 0
    lastTitle.value = title
    // 换歌：重置封面失败标记，让新歌封面重新尝试加载（避免旧 url 残留导致永久回退）
    brokenCovers.clear()
  }
})

// TSMusicBot 不返回 position，只在有效正数时校正（seek 后）
watch(() => music.nowplaying?.position, (pos) => {
  if (typeof pos === 'number' && pos > 0 && !dragging.value) {
    music.localPosition = pos
  }
})

// 每秒递增
tickTimer = window.setInterval(() => {
  if (music.nowplaying?.playing && !dragging.value) {
    const len = effDur.value || 0
    if (len <= 0 || music.localPosition < len) {
      music.localPosition += 1
    }
  }
}, 1000)
onUnmounted(() => { if (tickTimer) clearInterval(tickTimer) })

const np = computed(() => music.nowplaying)
const isPlaying = computed(() => !!np.value?.playing && !np.value?.paused)
// 实际播放时长：试听片段=试听秒数，完整=duration（effectiveDuration 缺失回退 duration）
const effDur = computed(() => np.value?.effectiveDuration || np.value?.duration)
// 试听片段：effectiveDuration 存在且短于完整 duration
const isTrial = computed(
  () => !!(np.value?.effectiveDuration && np.value?.duration && np.value.effectiveDuration < np.value.duration),
)
const statusText = computed(() =>
  isPlaying.value ? '正在播放' : np.value?.paused ? '已暂停' : '空闲',
)

function fmt(sec?: number): string {
  if (!sec || sec < 0) return '0:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

// seek — @input 持续更新位置（滑块跟手），@change 松手后发给后端
function onSeekInput(val: number | number[]) {
  dragging.value = true
  music.localPosition = val as number
}
async function onSeekEnd(val: number | number[]) {
  dragging.value = false
  try { await music.seek(val as number) } catch { ElMessage.error('跳转失败') }
}

// 音量：拖动时实时更新显示，松手后发送
function onVolumeInput(val: number | number[]) {
  music.volume = val as number
}
async function onVolumeChange(val: number | number[]) {
  try { await music.updateVolume(val as number) } catch { ElMessage.error('音量设置失败') }
}
const volLevel = computed<'mute' | 'low' | 'high'>(() => {
  if (music.volume <= 0) return 'mute'
  return music.volume < 50 ? 'low' : 'high'
})

async function handlePause() {
  try { np.value?.paused ? await music.resume() : await music.pause() } catch { ElMessage.error('操作失败') }
}
async function handleNext() { try { await music.next() } catch { ElMessage.error('操作失败') } }
async function handleStop() { try { await music.stop() } catch { ElMessage.error('操作失败') } }
async function handleClear() { try { await music.clear(); ElMessage.success('已清空队列') } catch {} }
async function handleRemove(index: number) { try { await music.removeQueueAt(index) } catch { ElMessage.error('移除失败') } }
async function handlePlayAt(index: number) { try { await music.playQueueAt(index) } catch { ElMessage.error('切换失败') } }

// ── 队列长按拖动调序 ──
const QUEUE_ROW_H = 56 // 队列项大致高度（封面 + padding）
const pressTimer = ref<number | null>(null)
const draggingIdx = ref<number | null>(null)    // 正在拖动的 index
const dragOverIdx = ref<number | null>(null)    // 指针悬停的目标 index
const pressStartY = ref(0)
const dragOffsetY = ref(0)                       // 拖动项跟随指针的 translateY
const didDrag = ref(false)                       // 本次交互是否真拖动过（抑制随后的 click）

function onQueuePointerDown(e: PointerEvent, i: number) {
  if (e.button !== 0) return // 仅主键 / 触摸
  pressStartY.value = e.clientY
  didDrag.value = false
  if (pressTimer.value) clearTimeout(pressTimer.value)
  pressTimer.value = window.setTimeout(() => {
    draggingIdx.value = i
    ;(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId)
  }, 450)
}
function onQueuePointerMove(e: PointerEvent) {
  // 移动超过阈值则取消长按定时器（避免误触进入拖动）
  if (pressTimer.value && Math.abs(e.clientY - pressStartY.value) > 10) {
    clearTimeout(pressTimer.value)
    pressTimer.value = null
  }
  if (draggingIdx.value === null) return
  didDrag.value = true
  const listEl = (e.currentTarget as HTMLElement).parentElement
  if (!listEl) return
  const relY = e.clientY - listEl.getBoundingClientRect().top + listEl.scrollTop
  const n = music.queue.length
  let target = Math.floor(relY / QUEUE_ROW_H)
  target = Math.max(0, Math.min(n - 1, target))
  dragOverIdx.value = target
  dragOffsetY.value = e.clientY - pressStartY.value
}
function onQueuePointerUp(e: PointerEvent) {
  if (pressTimer.value) { clearTimeout(pressTimer.value); pressTimer.value = null }
  if (draggingIdx.value !== null) {
    const from = draggingIdx.value
    const to = dragOverIdx.value
    ;(e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId)
    draggingIdx.value = null
    dragOverIdx.value = null
    dragOffsetY.value = 0
    if (to !== null && to !== from) {
      music.moveQueueItem(from, to).catch(() => ElMessage.error('调序失败'))
    }
  }
}
// 每个项的 transform：拖动项跟随指针 + 放大，其余项按目标位置让位
function queueItemStyle(i: number): Record<string, string> | undefined {
  if (draggingIdx.value === null) return undefined
  if (i === draggingIdx.value) {
    return { transform: `translateY(${dragOffsetY.value}px) scale(1.04)`, 'z-index': '5' }
  }
  const from = draggingIdx.value
  const to = dragOverIdx.value
  let off = 0
  if (to !== null && from !== to) {
    if (from < to) off = i > from && i <= to ? -QUEUE_ROW_H : 0
    else off = i >= to && i < from ? QUEUE_ROW_H : 0
  }
  return off ? { transform: `translateY(${off}px)` } : undefined
}
function onQueueClick(i: number) {
  if (didDrag.value) { didDrag.value = false; return } // 拖动结束的 pointerup 会顺带触发 click，抑制掉
  handlePlayAt(i)
}

// 播放模式：单控件循环切换
const MODES = [
  { value: 'seq', label: '顺序播放' },
  { value: 'loop', label: '列表循环' },
  { value: 'random', label: '随机播放' },
  { value: 'rloop', label: '随机循环' },
] as const
const currentMode = computed(() => MODES.find((m) => m.value === music.playMode) ?? MODES[0])
function cycleMode() {
  const i = MODES.findIndex((m) => m.value === music.playMode)
  music.setMode(MODES[(i + 1) % MODES.length].value)
}

// ── 音质选择 ──
const qualityLoading = ref(false)

// 当前播放歌曲的平台（用于音质选项）
const currentPlatform = computed<'netease' | 'qq' | 'bilibili' | 'kugou' | null>(() => {
  const p = np.value?.platform
  if (p === 'netease' || p === 'qq' || p === 'bilibili' || p === 'kugou') return p
  return null
})

// 当前平台的音质选项（根据 VIP 状态过滤）
const qualityOptions = computed(() => {
  if (!currentPlatform.value) return []
  const platformStatus = music.platformStatus[currentPlatform.value]
  const isVip = !!platformStatus?.nickname?.toLowerCase().includes('vip') || false
  return music.getAvailableQualities(currentPlatform.value, isVip)
})

// 当前音质标签
const qualityLabel = computed(() => {
  if (!currentPlatform.value) return '音质'
  const q = music.quality[currentPlatform.value]
  const opt = qualityOptions.value.find((o) => o.value === q)
  return opt?.label || '音质'
})

async function cycleQuality() {
  if (!currentPlatform.value || qualityLoading.value) return
  const opts = qualityOptions.value
  if (opts.length === 0) return

  // 循环到下一个
  const currentQ = music.quality[currentPlatform.value] || opts[0].value
  const i = opts.findIndex((o) => o.value === currentQ)
  const next = opts[(i + 1) % opts.length]

  qualityLoading.value = true
  try {
    await music.setQuality(next.value, currentPlatform.value)
  } finally {
    qualityLoading.value = false
  }
}

// 用 id+platform 精确判断队列中哪首是当前播放（歌名匹配会误判同名/翻唱）
const npSong = computed(() => {
  const np = music.nowplaying
  if (!np?.songId) return null
  return { id: String(np.songId), platform: (np.platform || '') }
})
function isCurrent(item: { id?: string; platform?: string }): boolean {
  const cur = npSong.value
  return !!cur && String(item.id ?? '') === cur.id && (item.platform || '') === cur.platform
}
</script>

<template>
  <div class="player">
    <div class="panel-header">
      <div class="panel-title-group">
        <h2 class="panel-title">播放器</h2>
        <span class="panel-sub label-mono">NOW PLAYING</span>
      </div>
    </div>

    <!-- Now Playing Hero -->
    <div class="np-hero" :class="{ playing: isPlaying }">
      <div class="np-cover-wrap">
        <img v-if="np?.cover && !brokenCovers.has(np.cover)" :src="np.cover" class="np-cover" referrerpolicy="no-referrer" @error="onCoverError(np.cover)" />
        <div v-else class="np-cover np-cover--fallback" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M9 17.5V6l10-2v8.5" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/><circle cx="6.5" cy="17.5" r="2.5"/><circle cx="16" cy="14.5" r="2.5"/></svg>
        </div>
      </div>

      <div class="np-meta">
        <div class="np-status">
          <span class="np-dot" :class="{ on: isPlaying, paused: np?.paused }"></span>
          <span class="np-status-text label-mono">{{ statusText }}</span>
        </div>
        <div class="np-title-row">
          <span class="np-title">{{ np?.title || '尚未播放' }}</span>
          <span v-if="np?.vip" class="vip-badge" title="VIP / 版权受限：非会员仅能试听片段">VIP</span>
          <span v-if="isTrial" class="trial-badge" title="试听片段：非会员仅能播放前 {{ fmt(effDur) }}">试听</span>
        </div>
        <span class="np-artist">{{ np?.artist || '在左侧搜索并点歌' }}</span>

        <div class="scrubber">
          <span class="time mono">{{ fmt(music.localPosition) }}</span>
          <el-slider
            v-if="effDur"
            :model-value="music.localPosition"
            :min="0"
            :max="effDur"
            :step="1"
            :show-tooltip="false"
            size="small"
            @input="onSeekInput"
            @change="onSeekEnd"
          />
          <div v-else class="scrubber-track"></div>
          <span class="time mono">{{ fmt(effDur) }}</span>
        </div>
      </div>
    </div>

    <!-- Transport -->
    <div class="transport">
      <button class="ctrl" title="停止" @click="handleStop">
        <svg viewBox="0 0 24 24"><rect x="6.5" y="6.5" width="11" height="11" rx="2.5" fill="currentColor"/></svg>
      </button>
      <button class="ctrl ctrl--play" :title="isPlaying ? '暂停' : '播放'" @click="handlePause">
        <svg v-if="isPlaying" viewBox="0 0 24 24"><rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor"/><rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor"/></svg>
        <svg v-else viewBox="0 0 24 24"><path d="M8 5.5v13l11-6.5z" fill="currentColor"/></svg>
      </button>
      <button class="ctrl" title="下一首" @click="handleNext">
        <svg viewBox="0 0 24 24"><path d="M5 5.5v13l9-6.5z" fill="currentColor"/><rect x="16" y="5" width="3" height="14" rx="1" fill="currentColor"/></svg>
      </button>
    </div>

    <!-- Secondary：模式 + 音质 + 音量 -->
    <div class="secondary">
      <button class="mode-pill" :title="'切换播放模式（当前：' + currentMode.label + '）'" @click="cycleMode">
        <svg v-if="currentMode.value === 'seq'" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"><path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/></svg>
        <svg v-else-if="currentMode.value === 'loop'" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M17 2l4 4-4 4"/><path d="M3 11V9a4 4 0 014-4h14"/><path d="M7 22l-4-4 4-4"/><path d="M21 13v2a4 4 0 01-4 4H3"/></svg>
        <svg v-else viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M16 3h5v5"/><path d="M4 20L21 3"/><path d="M21 16v5h-5"/><path d="M15 15l6 6"/><path d="M4 4l5 5"/></svg>
        <span>{{ currentMode.label }}</span>
      </button>

      <button
        v-if="currentPlatform"
        class="mode-pill quality-pill"
        :title="'切换音质（当前：' + qualityLabel + '）'"
        :disabled="qualityLoading || qualityOptions.length <= 1"
        :class="{ loading: qualityLoading }"
        @click="cycleQuality"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
        </svg>
        <span>{{ qualityLabel }}</span>
      </button>

      <div class="vol">
        <svg v-if="volLevel === 'mute'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9v6h4l5 4V5L8 9z" fill="currentColor" stroke="none"/><path d="M16 9.5l4 5M20 9.5l-4 5"/></svg>
        <svg v-else-if="volLevel === 'low'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9v6h4l5 4V5L8 9z" fill="currentColor" stroke="none"/><path d="M16 8.5a4 4 0 010 7"/></svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9v6h4l5 4V5L8 9z" fill="currentColor" stroke="none"/><path d="M16 8.5a4 4 0 010 7"/><path d="M18.5 6a7 7 0 010 12"/></svg>
        <el-slider
          :model-value="music.volume"
          :min="0"
          :max="100"
          :show-tooltip="false"
          size="small"
          @input="onVolumeInput"
          @change="onVolumeChange"
        />
        <span class="vol-val mono">{{ music.volume }}</span>
      </div>
    </div>

    <!-- Queue -->
    <div class="queue-section">
      <div class="queue-header">
        <div class="q-title-group">
          <span>播放队列</span>
          <span class="label-mono q-kicker">QUEUE</span>
        </div>
        <div class="q-actions">
          <span class="q-count mono">{{ music.queue.length }}</span>
          <button class="q-clear" :disabled="music.queue.length === 0" title="清空队列" @click="handleClear">
            <svg viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13"/></svg>
          </button>
        </div>
      </div>

      <div class="queue-list">
        <div v-if="music.queue.length === 0" class="queue-empty">
          队列为空 — 搜索后点「加入队列」
        </div>
        <div
          v-for="(item, i) in music.queue"
          :key="(item.platform || '') + ':' + (item.id || i)"
          class="queue-item row-scan"
          :class="{ current: isCurrent(item), dragging: draggingIdx === i }"
          :style="queueItemStyle(i)"
          :title="isCurrent(item) ? '正在播放' : '点击播放 / 长按拖动调序'"
          @click="onQueueClick(i)"
          @pointerdown="onQueuePointerDown($event, i)"
          @pointermove="onQueuePointerMove($event)"
          @pointerup="onQueuePointerUp($event)"
          @pointercancel="onQueuePointerUp($event)"
        >
          <span class="q-idx mono">{{ String(i + 1).padStart(2, '0') }}</span>
          <img v-if="item.coverUrl && !brokenCovers.has(item.coverUrl)" :src="item.coverUrl" class="q-cover" referrerpolicy="no-referrer" @error="onCoverError(item.coverUrl)" />
          <span v-else class="q-cover q-cover--fallback" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M9 17V7l8-1.5v7" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/><circle cx="6.5" cy="17" r="2"/><circle cx="14" cy="15" r="2"/></svg>
          </span>
          <div class="q-meta">
            <div class="q-name-row">
              <span class="q-name">{{ item.name }}</span>
              <span v-if="item.vip" class="vip-badge" title="VIP / 版权受限：非会员仅能试听片段">VIP</span>
            </div>
            <span class="q-artist">{{ item.artist }}</span>
          </div>
          <EqualizerBars v-if="isCurrent(item)" class="q-eq" :active="isPlaying" />
          <span v-else-if="item.duration" class="q-dur mono">{{ fmt(item.duration) }}</span>
          <button class="q-remove" title="移除" @click.stop="handleRemove(i)">
            <svg viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.player {
  background: var(--gradient-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 4px;
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

/* ── Now Playing Hero ── */
.np-hero {
  display: flex;
  gap: 14px;
}

.np-cover-wrap {
  position: relative;
  flex-shrink: 0;
  width: 124px;
  height: 124px;
  border-radius: var(--radius-md);
  overflow: hidden;
  box-shadow: 0 0 0 1px var(--border-emphasis);
  transition: box-shadow 0.3s var(--ease-out-expo);
}
.np-hero.playing .np-cover-wrap {
  box-shadow: 0 0 0 1px rgba(45, 212, 191, 0.5), 0 0 22px -6px rgba(45, 212, 191, 0.45);
}
.np-cover {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.np-cover--fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--surface-4);
  color: var(--text-muted);
}
.np-cover--fallback svg {
  width: 38px;
  height: 38px;
}

.np-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.np-status {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 2px;
}
.np-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-muted);
  flex-shrink: 0;
}
.np-dot.on {
  background: var(--color-primary);
  animation: pulse-glow 2s ease-in-out infinite;
}
.np-dot.paused {
  background: var(--color-accent);
}
.np-status-text {
  font-size: 0.6em;
  color: var(--text-muted);
}

.np-title {
  font-size: 1.16em;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.25;
  letter-spacing: -0.01em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.np-title-row {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}
.vip-badge {
  flex-shrink: 0;
  font-size: 0.5em;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #f5a623;
  background: rgba(245, 166, 35, 0.12);
  border: 1px solid rgba(245, 166, 35, 0.4);
  border-radius: 3px;
  padding: 0 4px;
  line-height: 1.6;
}
.trial-badge {
  flex-shrink: 0;
  font-size: 0.5em;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #60a5fa;
  background: rgba(96, 165, 250, 0.12);
  border: 1px solid rgba(96, 165, 250, 0.4);
  border-radius: 3px;
  padding: 0 4px;
  line-height: 1.6;
}
.np-artist {
  font-size: 0.78em;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 6px;
}

.scrubber {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 2px;
}
.scrubber .el-slider {
  flex: 1;
}
.scrubber-track {
  flex: 1;
  height: 3px;
  border-radius: 2px;
  background: rgba(255, 255, 255, 0.06);
}
.time {
  font-size: 0.66em;
  color: var(--text-muted);
  flex-shrink: 0;
}

/* ── Transport ── */
.transport {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 18px;
  padding: 10px 0 12px;
  border-bottom: 1px solid var(--border-subtle);
}
.ctrl {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  border: 1px solid var(--border-emphasis);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: color 0.18s, border-color 0.18s, background 0.18s, transform 0.12s;
}
.ctrl svg {
  width: 18px;
  height: 18px;
}
.ctrl:hover {
  color: var(--color-primary);
  border-color: var(--color-primary);
}
.ctrl:active {
  transform: scale(0.93);
}
.ctrl--play {
  width: 56px;
  height: 56px;
  border: none;
  background: var(--gradient-brand);
  color: var(--text-inverse);
  box-shadow: var(--glow-primary-strong);
}
.ctrl--play svg {
  width: 22px;
  height: 22px;
}
.ctrl--play:hover {
  color: var(--text-inverse);
  border: none;
  filter: brightness(1.08);
}

/* ── Secondary：模式 + 音量 ── */
.secondary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 14px;
  padding: 12px 0 4px;
}
.mode-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border: 1px solid var(--border-emphasis);
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.74em;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.18s, border-color 0.18s;
}
.mode-pill svg {
  width: 15px;
  height: 15px;
}
.mode-pill:hover {
  color: var(--color-primary);
  border-color: var(--color-primary);
}
.mode-pill:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.quality-pill.loading {
  animation: pulse 1s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.vol {
  display: flex;
  align-items: center;
  gap: 9px;
  flex: 1 1 140px;
  min-width: 120px;
  color: var(--text-secondary);
}
.vol svg {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}
.vol .el-slider {
  flex: 1;
}
.vol-val {
  font-size: 0.68em;
  color: var(--text-muted);
  flex-shrink: 0;
  min-width: 18px;
  text-align: right;
}

/* ── Queue ── */
.queue-section {
  margin-top: 10px;
  padding-top: 12px;
  border-top: 1px solid var(--border-subtle);
}
.queue-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.q-title-group {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 0.86em;
  font-weight: 600;
  color: var(--text-primary);
}
.q-kicker {
  font-size: 0.66em;
  color: var(--text-muted);
}
.q-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.q-count {
  font-size: 0.74em;
  color: var(--text-secondary);
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border-default);
  padding: 1px 8px;
  border-radius: 4px;
}
.q-clear {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.18s, border-color 0.18s, background 0.18s;
}
.q-clear svg {
  width: 15px;
  height: 15px;
}
.q-clear:hover:not(:disabled) {
  color: var(--color-danger);
  border-color: var(--color-danger);
  background: rgba(248, 113, 113, 0.06);
}
.q-clear:disabled {
  opacity: 0.35;
  cursor: default;
}

.queue-list {
  display: flex;
  flex-direction: column;
  max-height: 240px;
  overflow-y: auto;
}
.queue-empty {
  text-align: center;
  color: var(--text-muted);
  padding: 26px 10px;
  font-size: 0.8em;
}
.queue-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.15s, transform 0.15s var(--ease-out-expo);
  cursor: pointer;
  touch-action: none; /* 长按拖动优先（队列短，触摸滚动受限可接受） */
  user-select: none;
}
.queue-item.dragging {
  background: var(--surface-4);
  box-shadow: 0 10px 26px rgba(0, 0, 0, 0.45);
  cursor: grabbing;
  transition: none; /* 拖动时跟随指针，不要过渡 */
}
.queue-item:last-child {
  border-bottom: none;
}
.queue-item:hover {
  background: var(--surface-4);
}
.queue-item.current .q-name {
  color: var(--color-primary);
}
.q-idx {
  font-size: 0.66em;
  color: var(--text-muted);
  width: 18px;
  flex-shrink: 0;
  text-align: right;
}
.q-cover {
  width: 34px;
  height: 34px;
  border-radius: 5px;
  flex-shrink: 0;
  object-fit: cover;
}
.q-cover--fallback {
  display: grid;
  place-items: center;
  background: var(--surface-4);
  color: var(--text-muted);
}
.q-cover--fallback svg {
  width: 17px;
  height: 17px;
}
.q-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.q-name {
  font-size: 0.8em;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.q-name-row {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}
.q-artist {
  font-size: 0.68em;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.q-eq {
  color: var(--color-primary);
  height: 12px;
  flex-shrink: 0;
}
.q-dur {
  font-size: 0.66em;
  color: var(--text-muted);
  flex-shrink: 0;
}
.q-remove {
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s, background 0.15s;
}
.q-remove svg {
  width: 14px;
  height: 14px;
}
.queue-item:hover .q-remove,
.queue-item:has(:focus-visible) .q-remove {
  opacity: 1;
}
.q-remove:hover {
  color: var(--color-danger);
  background: rgba(248, 113, 113, 0.1);
}
@media (hover: none) {
  .q-remove {
    opacity: 0.6;
  }
}

/* ── 移动端：封面 / 间距收缩 ── */
@media (max-width: 768px) {
  .player { padding: 14px; }
  .np-hero { gap: 12px; }
  .np-cover-wrap { width: 96px; height: 96px; }
  .np-title { font-size: 1.04em; }
  .scrubber { gap: 8px; }
  .transport { gap: 14px; }
  .queue-list { max-height: 280px; }
}

/* 小屏：进一步缩小封面、隐藏队列序号让位标题 */
@media (max-width: 480px) {
  .np-cover-wrap { width: 80px; height: 80px; }
  .np-cover--fallback svg { width: 30px; height: 30px; }
  .q-idx { display: none; }
  .secondary { justify-content: center; }
}
</style>
