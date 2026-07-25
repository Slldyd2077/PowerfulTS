<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { isAxiosError } from 'axios'
import { startLiveAudio, stopLiveAudio } from '@/api/music'
import { useMusicStore } from '@/stores/music'

type ShareState = 'idle' | 'requesting' | 'connecting' | 'live' | 'stopping'

const music = useMusicStore()
const state = ref<ShareState>('idle')
const elapsed = ref(0)
const levels = ref(Array.from({ length: 18 }, () => 0.08))

let capture: MediaStream | null = null
let recorder: MediaRecorder | null = null
let socket: WebSocket | null = null
let sessionId = ''
let elapsedTimer: ReturnType<typeof setInterval> | null = null
let audioContext: AudioContext | null = null
let animationFrame = 0
let stopping = false

const isBusy = computed(() => state.value !== 'idle' && state.value !== 'live')
const statusLabel = computed(() => ({
  idle: '等待授权',
  requesting: '等待系统授权',
  connecting: '正在接入机器人',
  live: '正在直播',
  stopping: '正在停止',
}[state.value]))

const elapsedLabel = computed(() => {
  const mins = Math.floor(elapsed.value / 60).toString().padStart(2, '0')
  const secs = (elapsed.value % 60).toString().padStart(2, '0')
  return `${mins}:${secs}`
})

function chooseMimeType(): string {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'video/webm;codecs=opus',
  ]
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || ''
}

function startMeter(stream: MediaStream) {
  audioContext = new AudioContext()
  const analyser = audioContext.createAnalyser()
  analyser.fftSize = 64
  analyser.smoothingTimeConstant = 0.78
  audioContext.createMediaStreamSource(stream).connect(analyser)
  const bins = new Uint8Array(analyser.frequencyBinCount)
  const draw = () => {
    analyser.getByteFrequencyData(bins)
    levels.value = levels.value.map((_, index) => {
      const bin = bins[Math.min(bins.length - 1, index + 1)] || 0
      return Math.max(0.08, Math.min(1, bin / 190))
    })
    animationFrame = requestAnimationFrame(draw)
  }
  draw()
}

function websocketUrl(path: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${path}`
}

function waitForSocket(ws: WebSocket): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error('实时音频连接超时')), 10000)
    ws.addEventListener('open', () => {
      window.clearTimeout(timer)
      resolve()
    }, { once: true })
    ws.addEventListener('error', () => {
      window.clearTimeout(timer)
      reject(new Error('无法建立实时音频连接'))
    }, { once: true })
  })
}

async function startShare() {
  if (!music.activeBotId) {
    ElMessage.warning('请先选择一个音乐机器人')
    return
  }
  if (!navigator.mediaDevices?.getDisplayMedia || typeof MediaRecorder === 'undefined') {
    ElMessage.error('当前浏览器不支持应用音频共享，请使用最新版 Chrome 或 Edge')
    return
  }

  state.value = 'requesting'
  try {
    const options = {
      video: true,
      audio: { suppressLocalAudioPlayback: false },
      systemAudio: 'include',
      windowAudio: 'window',
      selfBrowserSurface: 'exclude',
    } as DisplayMediaStreamOptions
    capture = await navigator.mediaDevices.getDisplayMedia(options)
    const audioTracks = capture.getAudioTracks()
    if (audioTracks.length === 0) {
      throw new Error('没有检测到共享音频，请重新选择窗口并勾选“共享音频”')
    }

    const mimeType = chooseMimeType()
    if (!mimeType) throw new Error('当前浏览器没有可用的 Opus/WebM 实时编码器')
    const audioOnly = new MediaStream(audioTracks)
    try { startMeter(audioOnly) } catch { /* 频谱是可选增强，不阻断实际推流 */ }

    state.value = 'connecting'
    const session = await startLiveAudio(mimeType, music.activeBotId)
    sessionId = session.sessionId
    socket = new WebSocket(websocketUrl(session.uploadPath))
    await waitForSocket(socket)

    recorder = new MediaRecorder(audioOnly, { mimeType, audioBitsPerSecond: 128000 })
    recorder.addEventListener('dataavailable', (event) => {
      if (event.data.size > 0 && socket?.readyState === WebSocket.OPEN) {
        socket.send(event.data)
      }
    })
    recorder.addEventListener('error', () => {
      if (!stopping) void stopShare('音频编码器已停止')
    })
    socket.addEventListener('close', () => {
      if (!stopping && state.value === 'live') void stopShare('与服务器的实时连接已断开')
    })
    capture.getTracks().forEach((track) => {
      track.addEventListener('ended', () => {
        if (!stopping && state.value === 'live') void stopShare('系统已停止共享')
      }, { once: true })
    })

    recorder.start(250)
    elapsed.value = 0
    elapsedTimer = setInterval(() => elapsed.value += 1, 1000)
    state.value = 'live'
    ElMessage.success('电脑音频已接入当前频道')
  } catch (error) {
    const apiDetail = isAxiosError(error) && typeof error.response?.data?.detail === 'string'
      ? error.response.data.detail
      : ''
    const message = apiDetail || (error instanceof Error ? error.message : '无法开始电脑音频共享')
    const cancelled = error instanceof DOMException && error.name === 'NotAllowedError'
    await cleanup(true)
    if (!cancelled) ElMessage.error(message)
    else ElMessage.info('已取消音频共享')
  }
}

async function cleanup(notifyServer: boolean) {
  stopping = true
  state.value = 'stopping'
  if (elapsedTimer) clearInterval(elapsedTimer)
  elapsedTimer = null
  if (animationFrame) cancelAnimationFrame(animationFrame)
  animationFrame = 0

  if (recorder && recorder.state !== 'inactive') recorder.stop()
  recorder = null
  capture?.getTracks().forEach((track) => track.stop())
  capture = null
  socket?.close(1000, 'user stopped')
  socket = null
  await audioContext?.close().catch(() => undefined)
  audioContext = null
  levels.value = levels.value.map(() => 0.08)

  const id = sessionId
  sessionId = ''
  if (notifyServer && id) await stopLiveAudio(id).catch(() => undefined)
  state.value = 'idle'
  stopping = false
}

async function stopShare(message?: string) {
  if (stopping || state.value === 'idle') return
  await cleanup(true)
  ElMessage.info(message || '电脑音频共享已停止')
}

watch(() => music.activeBotId, (next, previous) => {
  if (previous && next !== previous && state.value !== 'idle') {
    void stopShare('切换机器人后，电脑音频共享已停止')
  }
})

onBeforeUnmount(() => {
  if (state.value !== 'idle') void cleanup(true)
})
</script>

<template>
  <section class="live-panel" :class="{ 'is-live': state === 'live' }">
    <div class="signal-rail" aria-hidden="true">
      <span
        v-for="(_, index) in levels"
        :key="index"
        class="signal-bar"
        :style="{ transform: `scaleY(${levels[index]})` }"
      />
    </div>

    <div class="live-copy">
      <div class="eyebrow">
        <span class="status-dot" />
        LIVE INPUT · {{ statusLabel }}
        <span v-if="state === 'live'" class="elapsed">{{ elapsedLabel }}</span>
      </div>
      <h2>共享电脑音频</h2>
      <p v-if="state !== 'live'">选择需要共享的音频窗口并勾选共享音频，授权后才会发送到当前机器人。</p>
      <p v-else>音频正在发送到「{{ music.activeBot?.name || '当前机器人' }}」，系统停止共享时会自动断开。</p>
    </div>

    <div class="live-actions">
      <button
        v-if="state !== 'live'"
        class="share-button"
        :disabled="isBusy || !music.activeBotId"
        @click="startShare"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5.5h16v10H4zM8 19h8M12 15.5V19"/><path d="M9 10.5c1.7-1.7 4.3-1.7 6 0M10.8 12.3c.7-.7 1.7-.7 2.4 0"/></svg>
        {{ isBusy ? statusLabel : '选择应用并开始' }}
      </button>
      <button v-else class="stop-button" @click="stopShare()">
        <span class="stop-icon" />
        停止共享
      </button>
      <span class="privacy-note">每次都需要你的明确授权</span>
    </div>

    <div class="feedback-warning">
      <span>避免回声</span>
      如果选择“整个屏幕”，TeamSpeak 的声音也可能被录回；优先选择需要共享音频的应用窗口。
    </div>
  </section>
</template>

<style scoped>
.live-panel {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px 24px;
  overflow: hidden;
  padding: 20px 22px 18px 28px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background:
    linear-gradient(90deg, rgba(17, 108, 224, 0.12), transparent 46%),
    var(--gradient-surface);
  transition: border-color .25s, box-shadow .25s;
}
.live-panel::after {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image: linear-gradient(90deg, rgba(148, 190, 242, .035) 1px, transparent 1px);
  background-size: 36px 100%;
  mask-image: linear-gradient(90deg, black, transparent 72%);
}
.live-panel.is-live {
  border-color: rgba(var(--color-success-rgb), .34);
  box-shadow: 0 0 0 1px rgba(var(--color-success-rgb), .06), 0 14px 44px -34px var(--color-success);
}
.signal-rail {
  position: absolute;
  z-index: 2;
  left: 0;
  top: 0;
  bottom: 0;
  width: 7px;
  display: flex;
  align-items: stretch;
  gap: 1px;
  flex-direction: column;
  padding: 3px 0;
  background: rgba(82, 147, 226, .08);
}
.signal-bar {
  flex: 1;
  min-height: 2px;
  transform-origin: center;
  background: var(--color-primary);
  transition: transform 80ms linear, background .25s;
}
.is-live .signal-bar { background: var(--color-success); }
.live-copy, .live-actions, .feedback-warning { position: relative; z-index: 3; }
.eyebrow {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 7px;
  color: var(--color-primary);
  font: 600 .64em/1 ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: .12em;
}
.is-live .eyebrow { color: var(--color-success); }
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 0 4px rgba(var(--color-primary-rgb), .1);
}
.is-live .status-dot { animation: live-pulse 1.5s ease-out infinite; }
.elapsed { color: var(--text-muted); letter-spacing: .05em; }
h2 { margin: 0 0 5px; color: var(--text-primary); font-size: 1.05em; letter-spacing: -.015em; }
p { max-width: 620px; margin: 0; color: var(--text-secondary); font-size: .78em; line-height: 1.65; }
.live-actions { display: flex; min-width: 188px; align-items: flex-end; justify-content: center; flex-direction: column; gap: 7px; }
.share-button, .stop-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-width: 188px;
  min-height: 38px;
  padding: 8px 14px;
  border-radius: var(--radius-sm);
  font-size: .76em;
  font-weight: 650;
  cursor: pointer;
  transition: transform .15s, filter .15s, opacity .15s;
}
.share-button { border: 1px solid rgba(var(--color-primary-rgb), .45); color: #fff; background: var(--gradient-brand); }
.share-button svg { width: 16px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
.stop-button { border: 1px solid rgba(var(--color-danger-rgb), .38); color: var(--color-danger); background: rgba(var(--color-danger-rgb), .08); }
.share-button:hover:not(:disabled), .stop-button:hover { filter: brightness(1.1); transform: translateY(-1px); }
.share-button:disabled { opacity: .45; cursor: not-allowed; }
.stop-icon { width: 9px; height: 9px; border-radius: 2px; background: currentColor; }
.privacy-note { color: var(--text-muted); font-size: .62em; }
.feedback-warning {
  grid-column: 1 / -1;
  padding-top: 11px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: .67em;
  line-height: 1.5;
}
.feedback-warning span { margin-right: 8px; color: var(--color-accent); font-weight: 650; }
@keyframes live-pulse {
  0% { box-shadow: 0 0 0 0 rgba(var(--color-success-rgb), .42); }
  70%, 100% { box-shadow: 0 0 0 7px rgba(var(--color-success-rgb), 0); }
}
@media (max-width: 680px) {
  .live-panel { grid-template-columns: 1fr; padding: 18px 16px 16px 22px; }
  .live-actions { align-items: stretch; min-width: 0; }
  .share-button, .stop-button { width: 100%; min-width: 0; }
  .privacy-note { text-align: center; }
}
@media (prefers-reduced-motion: reduce) {
  .is-live .status-dot { animation: none; }
}
</style>
