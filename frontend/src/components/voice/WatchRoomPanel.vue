<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useVoiceChannels } from '@/composables/useVoiceChannels'
import { useWatchRoom } from '@/composables/useWatchRoom'
import { applyPlayback, playbackPosition } from '@/services/watch-playback'
import { useAuthStore } from '@/stores/auth'

const { botCid, botOnline, currentChannel } = useVoiceChannels()
const auth = useAuthStore()
const { connected, joining, error, peerId, room, isOwner, isHost, localStream, remoteStream,
  sharingPending, serverOffset, join, leave, startSync, startScreen, stopShare, publish, transferHost, setReady, pauseRoom, setOptions } = useWatchRoom()
const source = ref<'direct' | 'site'>('site')
const url = ref('')
const video = ref<HTMLVideoElement | null>(null)
const extensionReady = ref(false)
const extensionStatus = ref('')
const fullscreen = ref(false)
const needsPlay = ref(false)
const autoplayBlocked = ref(false)
const buffering = ref(false)
const nextHost = ref('')
const waitForMembers = ref(true)
const allowMemberPause = ref(true)
const live = ref(false)
const share = computed(() => room.value.share)
const ownerName = computed(() => room.value.peers.find(peer => peer.id === share.value?.owner)?.nickname)
const hostName = computed(() => room.value.peers.find(peer => peer.id === room.value.host)?.nickname)
const hostCandidates = computed(() => room.value.peers.filter(peer => peer.id !== peerId.value))
let tick: number | undefined
let bridgeTick: number | undefined
let applying = false
let applyingUntil = 0
let extensionVideoSeen = 0
let extensionVideoReady = false
let lastExtensionSeen = 0

watch([botCid, botOnline, () => auth.token], () => { if (connected.value || joining.value) leave() })
watch([localStream, remoteStream, share], async () => {
  await nextTick()
  if (video.value && share.value?.kind === 'screen') {
    video.value.srcObject = isOwner.value ? localStream.value : remoteStream.value
    if (video.value.srcObject) {
      try { await video.value.play(); needsPlay.value = false }
      catch { needsPlay.value = true }
    }
  }
})
watch(() => share.value?.id, () => {
  needsPlay.value = false
  autoplayBlocked.value = false
  buffering.value = false
  extensionStatus.value = ''
})
watch([share, connected], () => { updateExtension(); void syncVideo() })

function reportVideo(event?: Event): void {
  if (!video.value || share.value?.source !== 'direct') return
  if (event?.type === 'play') autoplayBlocked.value = false
  setReady(video.value.readyState >= 3 && !buffering.value && !video.value.seeking && !autoplayBlocked.value)
  if (!isOwner.value) {
    if (event?.type === 'pause' && !share.value.paused && share.value.allowMemberPause) pauseRoom()
    return
  }
  const userPause = event?.type === 'pause' && !share.value.paused
  const userPlay = event?.type === 'play' && share.value.requestedPaused && !share.value.waiting.length
  if ((applying || Date.now() < applyingUntil) && !userPause && !userPlay) return
  if (share.value.waiting.length) return
  const paused = event && ['play', 'pause', 'ended'].includes(event.type) ? video.value.paused : share.value.requestedPaused
  publish(video.value.currentTime, paused, video.value.playbackRate)
}
async function syncVideo(): Promise<void> {
  if (share.value?.source !== 'direct' || !video.value || video.value.readyState < 1 || applying) return
  const target = playbackPosition(share.value, Date.now() + serverOffset.value)
  if (video.value.paused === share.value.paused && video.value.playbackRate === share.value.rate
    && (isOwner.value || Math.abs(video.value.currentTime - target) <= 0.8)) return
  applying = true
  applyingUntil = Date.now() + 250
  try {
    await applyPlayback(video.value, share.value, Date.now() + serverOffset.value)
    needsPlay.value = autoplayBlocked.value
  } catch { needsPlay.value = true; autoplayBlocked.value = true }
  finally { applying = false; applyingUntil = Date.now() + 250 }
}
function updateExtension(): void {
  const value = share.value
  window.postMessage({ channel: 'powerfults-watch', direction: 'to-extension',
    type: 'state', mode: connected.value && value?.kind === 'sync' && value.source === 'site'
      ? (isOwner.value ? 'host' : 'viewer') : 'idle',
    url: value?.url ?? '', position: value ? playbackPosition(value, Date.now() + serverOffset.value) : 0,
    paused: value?.paused ?? true, rate: value?.rate ?? 1,
    requestedPaused: value?.requestedPaused ?? true, waiting: !!value?.waiting.length,
    allowMemberPause: value?.allowMemberPause ?? false,
  }, window.location.origin)
}
function bridgeMessage(event: MessageEvent): void {
  if (event.source !== window || event.origin !== window.location.origin) return
  const message = event.data
  if (message?.channel !== 'powerfults-watch' || message.direction !== 'from-extension') return
  lastExtensionSeen = Date.now()
  extensionReady.value = true
  if (message.type === 'status') extensionStatus.value = typeof message.message === 'string' ? message.message : ''
  if (message.type === 'video') {
    extensionVideoSeen = Date.now()
    extensionVideoReady = message.ready === true
    if (share.value?.source === 'site') setReady(extensionVideoReady)
    if (!share.value && typeof message.url === 'string') url.value = message.url
    if (connected.value && isOwner.value && share.value?.source === 'site'
      && typeof message.position === 'number' && Number.isFinite(message.position)
      && typeof message.paused === 'boolean' && typeof message.rate === 'number') {
      if (!share.value.waiting.length) publish(message.position, message.paused, message.rate)
    }
    if (message.userPaused === true && !isOwner.value && share.value?.allowMemberPause) pauseRoom()
  }
}
async function resumePlayback(): Promise<void> {
  try {
    await video.value?.play()
    needsPlay.value = false
    autoplayBlocked.value = false
    reportVideo()
    await syncVideo()
  } catch { error.value = '播放被浏览器阻止，请直接点击视频播放按钮' }
}
async function toggleFullscreen(): Promise<void> {
  const element = video.value as (HTMLVideoElement & { webkitEnterFullscreen?: () => void }) | null
  if (!element) return
  try {
    if (document.fullscreenElement) await document.exitFullscreen()
    else if (element.requestFullscreen) await element.requestFullscreen()
    else if (element.webkitEnterFullscreen) element.webkitEnterFullscreen()
    else error.value = '当前浏览器不支持全屏，请使用视频自带的全屏按钮'
  } catch { error.value = '无法进入全屏，请点击视频自带的全屏按钮' }
}
function onFullscreenChange(): void { fullscreen.value = document.fullscreenElement === video.value }
onMounted(() => {
  window.addEventListener('message', bridgeMessage)
  document.addEventListener('fullscreenchange', onFullscreenChange)
  bridgeTick = window.setInterval(() => {
    updateExtension()
    extensionReady.value = Date.now() - lastExtensionSeen < 5000
    if (share.value?.source === 'site') setReady(extensionVideoReady && Date.now() - extensionVideoSeen < 4000)
    if (share.value?.source === 'direct') reportVideo()
  }, 1000)
  tick = window.setInterval(() => {
    void syncVideo()
  }, 2000)
})
onBeforeUnmount(() => {
  window.clearInterval(tick)
  window.clearInterval(bridgeTick)
  window.removeEventListener('message', bridgeMessage)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  window.postMessage({ channel: 'powerfults-watch', direction: 'to-extension', type: 'state', mode: 'idle' }, window.location.origin)
})
</script>

<template>
  <section class="watch-panel">
    <div class="panel-heading">
      <div>
        <h2>一起看 · 屏幕共享</h2>
        <p>{{ connected ? `${currentChannel?.name || '当前频道'} · ${room.peers.length} 人已加入共享` : '和当前通话频道的成员一起看视频或共享画面' }}</p>
      </div>
      <button v-if="connected" type="button" @click="leave">退出共享</button>
      <button v-else type="button" :disabled="!botOnline || !botCid || joining" @click="join()">{{ joining ? '连接中…' : '加入共享房间' }}</button>
    </div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="!botOnline" class="hint">先加入上方的网页通话，再加入共享房间。切频道或挂断时自动退出共享。</p>

    <template v-if="connected">
      <div v-if="isHost" class="host-transfer">
        <label>转交房主<select v-model="nextHost"><option value="">选择同频道成员</option><option v-for="peer in hostCandidates" :key="peer.id" :value="peer.id">{{ peer.nickname }}</option></select></label>
        <button type="button" :disabled="!hostCandidates.some(peer => peer.id === nextHost)" @click="transferHost(nextHost); nextHost = ''">转交</button>
        <p class="hint">转交同步观看会保留视频进度；转交屏幕共享会结束当前画面，由新房主选择自己的窗口。</p>
      </div>
      <p v-else-if="room.host" class="hint">房主：{{ hostName }}。需要分享自己的内容时，请房主转交权限。</p>
      <div v-if="!share && (!room.host || isHost)" class="share-controls">
        <label>观看方式
          <select v-model="source">
            <option value="site">网站视频（配套浏览器扩展）</option>
            <option value="direct">视频直链（MP4 / WebM 等）</option>
          </select>
        </label>
        <label>视频地址<input v-model="url" type="url" placeholder="https://…" maxlength="2048" /></label>
        <div class="watch-options">
          <label><input v-model="live" type="checkbox" />这是直播（不等待成员缓冲）</label>
          <label><input v-model="waitForMembers" type="checkbox" :disabled="live" />等待成员加载完成</label>
          <label><input v-model="allowMemberPause" type="checkbox" />允许成员暂停</label>
        </div>
        <div class="actions">
          <button type="button" :disabled="!url.trim() || sharingPending || (source === 'site' && !extensionReady)" @click="startSync(url.trim(), source, { live, waitForMembers, allowMemberPause })">发起同步观看</button>
          <button type="button" :disabled="sharingPending" @click="startScreen">{{ sharingPending ? '正在选择共享内容…' : '共享屏幕 / 窗口' }}</button>
        </div>
      </div>
      <p v-else-if="!share" class="hint">等待房主开始共享…</p>
      <div v-if="share" class="active-share">
        <div class="share-heading">
          <span>{{ ownerName }} 正在{{ share.kind === 'screen' ? '共享画面' : '同步视频' }}</span>
          <button v-if="isOwner" type="button" @click="stopShare">停止共享</button>
        </div>
        <template v-if="share.kind === 'sync'">
          <div v-if="isHost" class="watch-options">
            <label><input type="checkbox" :checked="share.waitForMembers" :disabled="share.live" @change="setOptions(($event.target as HTMLInputElement).checked, share.allowMemberPause)" />等待成员加载完成{{ share.live ? '（直播不适用）' : '' }}</label>
            <label><input type="checkbox" :checked="share.allowMemberPause" @change="setOptions(share.waitForMembers, ($event.target as HTMLInputElement).checked)" />允许成员暂停</label>
          </div>
          <div class="actions">
            <button v-if="isHost || share.allowMemberPause" type="button" @click="pauseRoom()">暂停房间</button>
            <button v-if="isHost" type="button" @click="pauseRoom(false)">继续播放</button>
          </div>
          <p v-if="share.waiting.length" class="waiting" role="status">等待 {{ share.waiting.map(member => `${member.nickname}（${member.reason === 'offline' ? '掉线，等待重连 20 秒' : '正在加载'}）`).join('、') }}。加载完成后按房主的播放状态继续。</p>
          <p v-else-if="share.requestedPaused" class="hint">房间已暂停，由房主继续播放。</p>
        </template>
        <video v-if="share.kind === 'screen'" ref="video" class="shared-video" autoplay playsinline :muted="isOwner" controls />
        <video v-else-if="share.source === 'direct'" :key="share.id" ref="video" class="shared-video" :src="share.url" controls playsinline preload="metadata"
          @play="reportVideo" @pause="reportVideo" @seeked="reportVideo" @ratechange="reportVideo" @ended="reportVideo" @canplay="buffering = false; reportVideo($event)"
          @loadedmetadata="syncVideo()"
          @waiting="buffering = true; reportVideo()" @playing="buffering = false; reportVideo()" @error="error = '无法播放这个视频地址，请确认它是浏览器可播放的直链；网站视频请选择扩展模式'" />
        <div v-else class="site-watch">
          <a :href="share.url" target="_blank" rel="noopener noreferrer">打开平台播放器 · 弹幕 / 清晰度 / 全屏 ↗</a>
          <p>{{ isOwner ? '在视频页面播放、暂停、拖动进度或调整倍速，房间成员会跟随。' : '在视频页面启用配套扩展后，播放进度会跟随分享者。首次播放可能需要点击视频。' }}</p>
          <p>在平台原生播放器里，全屏、弹幕、清晰度、字幕和音量均可独立调整；房间只同步进度、倍速和暂停状态。</p>
        </div>
        <button v-if="share.kind === 'screen' || share.source === 'direct'" type="button" @click="toggleFullscreen">{{ fullscreen ? '退出全屏' : '全屏观看' }}</button>
        <button v-if="needsPlay" type="button" @click="resumePlayback">点击开始播放 / 开启声音</button>
        <p v-if="share.kind === 'screen' && !isOwner && !remoteStream" class="hint">正在建立画面连接…</p>
      </div>
      <p v-if="!share || share.source === 'site'" class="hint">
        网站同步：下载<a href="/watch-extension.zip" download>Chrome / Edge 扩展</a>，解压后在扩展管理页开启开发者模式并「加载已解压的扩展程序」。
        在本页点击扩展的「连接通话页」，再在视频标签页点击「连接视频页」。
        {{ extensionReady ? '扩展已连接。' : '扩展尚未连接。' }}
      </p>
      <p v-if="extensionStatus && (!share || share.source === 'site')" class="hint" role="status">{{ extensionStatus }}</p>
      <p class="hint">同步观看只发送进度，每人使用自己的账号及播放权限。屏幕共享需 HTTPS，音频取决于浏览器与所选窗口；受保护的视频可能无法捕获。</p>
    </template>
  </section>
</template>

<style scoped>
.watch-panel { padding: 18px 20px; border: 1px solid var(--border-subtle); border-radius: var(--radius-lg); background: var(--bg-card); box-shadow: var(--shadow-card); min-width: 0; }
.panel-heading, .share-heading, .actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
h2 { margin: 0; font-size: 0.98em; color: var(--text-primary); }
.panel-heading p, .hint, .site-watch p { font-size: 0.74em; line-height: 1.7; color: var(--text-secondary); }
button, select, input { font: inherit; font-size: 0.78em; border: 1px solid var(--border-subtle); border-radius: 6px; background: var(--bg-elevated); color: var(--text-primary); padding: 8px 10px; }
button { cursor: pointer; } button:disabled { opacity: 0.5; cursor: default; }
.share-controls { display: grid; gap: 12px; margin-top: 16px; }
label { display: grid; gap: 6px; font-size: 0.9em; color: var(--text-secondary); min-width: 0; }
input, select { width: 100%; box-sizing: border-box; min-width: 0; }
.actions { justify-content: flex-start; }
.active-share { margin-top: 16px; display: grid; gap: 12px; }
.host-transfer { margin-top: 12px; display: flex; flex-wrap: wrap; align-items: end; gap: 10px; }
.host-transfer .hint { width: 100%; margin: 0; }
.watch-options { display: flex; flex-wrap: wrap; gap: 10px; }
.watch-options label { display: flex; align-items: center; font-size: 0.75em; }
.watch-options input { width: auto; }
.waiting { font-size: 0.78em; line-height: 1.7; color: var(--color-accent); margin: 0; }
.share-heading { font-size: 0.85em; color: var(--text-primary); }
.shared-video { display: block; width: 100%; max-height: 60vh; border-radius: 8px; background: #000; }
.shared-video:fullscreen { width: 100vw; height: 100vh; max-height: none; border-radius: 0; object-fit: contain; }
.error { color: var(--color-danger, #ef6666); font-size: 0.8em; }
a { color: var(--color-accent); overflow-wrap: anywhere; }
@media (max-width: 768px) { .watch-panel { padding: 16px; } }
</style>
