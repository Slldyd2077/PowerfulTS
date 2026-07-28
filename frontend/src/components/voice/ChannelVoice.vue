<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useVoiceChannels } from '@/composables/useVoiceChannels'
import { stopLiveAudio } from '@/api/music'
import {
  closeVoiceSession,
  openVoiceSession,
  startVoiceDownlink,
  startVoiceMicrophone,
} from '@/api/voice'

const emit = defineEmits<{ (e: 'session-change'): void }>()

type SpeakerDecoder = {
  decoder: AudioDecoder
  timestamp: number
  lastSeen: number
}

const auth = useAuthStore()
// 通话身份由后端按登录账号开，前端只需要知道它开好了没有。
const voiceBotId = ref('')
const listening = ref(false)
const listenState = ref<'idle' | 'connecting' | 'live' | 'reconnecting'>('idle')
const listenError = ref('')
const microphoneLive = ref(false)
const microphoneState = ref<'idle' | 'requesting' | 'connecting' | 'live'>('idle')
const activeSpeakers = ref(0)
const speakingIds = ref<number[]>([])
const outputVolume = ref(85)
const microphoneVolume = ref(100)

const { roommates, refresh: refreshChannels } = useVoiceChannels()

// 每人音量按 TS 唯一昵称记，不按 clid：clid 每次重连都会变，按它记等于每次重进
// 频道都要重设一遍。localStorage 持久化，下次进来还是你调好的样子。
const SPEAKER_VOLUME_KEY = 'voice_speaker_volumes'
const speakerVolumes = ref<Record<string, number>>(loadSpeakerVolumes())

function loadSpeakerVolumes(): Record<string, number> {
  try {
    const raw = localStorage.getItem(SPEAKER_VOLUME_KEY)
    const parsed = raw ? JSON.parse(raw) : {}
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function speakerVolume(nickname: string): number {
  return speakerVolumes.value[nickname] ?? 100
}
const displayName = computed(() => auth.nickname || '你')

const inputDevices = ref<MediaDeviceInfo[]>([])
const outputDevices = ref<MediaDeviceInfo[]>([])
const selectedInput = ref('')
const selectedOutput = ref('')
// setSinkId on AudioContext is Chromium-only; hide the picker where it is absent.
const canChooseOutput = typeof AudioContext !== 'undefined'
  && 'setSinkId' in AudioContext.prototype

// 4502 = TSMusicBot 没有下行接口（版本过旧），重连多少次都一样，直接收手。
// 4503（连不上）和 1011（流中途断）交给下面的有限次退避重连。
const PERMANENT_CLOSE_CODES = new Set([4502])
const MAX_RECONNECT_ATTEMPTS = 5

let audioContext: AudioContext | null = null
let workletNode: AudioWorkletNode | null = null
let outputGain: GainNode | null = null
let downlinkSocket: WebSocket | null = null
let reconnectTimer: number | null = null
let reconnectAttempt = 0
let listenGeneration = 0
const decoders = new Map<number, SpeakerDecoder>()

let microphone: MediaStream | null = null
let microphoneRecorder: MediaRecorder | null = null
let microphoneSocket: WebSocket | null = null
let microphoneSessionId = ''
let microphoneStopping = false
let microphoneGeneration = 0
// Own context for the uplink: the playback one is torn down on hang-up, and a
// closed context would take the microphone gain node down with it.
let microphoneContext: AudioContext | null = null
let microphoneGain: GainNode | null = null
let microphoneOutput: MediaStreamAudioDestinationNode | null = null

function websocketUrl(path: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${path}`
}

function errorText(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: string } | undefined)?.detail
    if (detail) return detail
    if (!error.response) return '连不上 PowerfulTS 后端，请确认后端已启动'
    return `${fallback}（HTTP ${error.response.status}）`
  }
  return error instanceof Error ? error.message : fallback
}

/** 关闭码 1006 表示浏览器连关闭帧都没收到，reason 一定是空的，得自己解释。 */
function closeText(event: CloseEvent): string {
  if (event.reason) return event.reason
  if (event.code === 1006) return '语音连接被中断（后端或音乐机器人不可达）'
  if (event.code === 1000) return '语音连接已关闭'
  return `语音连接已关闭（code ${event.code}）`
}

function waitForSocket(socket: WebSocket): Promise<void> {
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => reject(new Error('语音连接超时')), 10000)
    socket.addEventListener('open', () => {
      window.clearTimeout(timeout)
      resolve()
    }, { once: true })
    socket.addEventListener('error', () => {
      window.clearTimeout(timeout)
      reject(new Error('语音连接失败'))
    }, { once: true })
    socket.addEventListener('close', () => {
      window.clearTimeout(timeout)
      reject(new Error('语音连接在建立前已关闭'))
    }, { once: true })
  })
}

function closeDecoders() {
  for (const speaker of decoders.values()) {
    try { speaker.decoder.close() } catch { /* already closed */ }
  }
  decoders.clear()
  workletNode?.port.postMessage({ type: 'reset' })
  activeSpeakers.value = 0
}

function deliverPcm(clientId: number, frame: AudioData) {
  try {
    const left = new Float32Array(frame.numberOfFrames)
    frame.copyTo(left, { planeIndex: 0, format: 'f32-planar' })
    let right: Float32Array
    if (frame.numberOfChannels > 1) {
      right = new Float32Array(frame.numberOfFrames)
      frame.copyTo(right, { planeIndex: 1, format: 'f32-planar' })
    } else {
      right = left.slice()
    }
    const leftBuffer = left.buffer as ArrayBuffer
    const rightBuffer = right.buffer as ArrayBuffer
    workletNode?.port.postMessage(
      { type: 'pcm', clientId, left: leftBuffer, right: rightBuffer },
      [leftBuffer, rightBuffer],
    )
  } finally {
    frame.close()
  }
}

function getSpeakerDecoder(clientId: number): SpeakerDecoder {
  const existing = decoders.get(clientId)
  if (existing) return existing
  const decoder = new AudioDecoder({
    output: (frame) => deliverPcm(clientId, frame),
    error: (error) => console.warn(`TS voice decoder ${clientId} failed`, error),
  })
  decoder.configure({ codec: 'opus', sampleRate: 48000, numberOfChannels: 2 })
  const speaker = { decoder, timestamp: 0, lastSeen: performance.now() }
  decoders.set(clientId, speaker)
  return speaker
}

function decodeVoicePacket(buffer: ArrayBuffer) {
  if (buffer.byteLength <= 6) return
  const view = new DataView(buffer)
  if (view.getUint8(0) !== 1) return
  const codec = view.getUint8(1)
  if (codec !== 4 && codec !== 5) return
  const clientId = view.getUint16(2, false)
  const durationSamples = view.getUint16(4, false) || 960
  const duration = Math.round(durationSamples * 1_000_000 / 48000)
  const speaker = getSpeakerDecoder(clientId)
  speaker.lastSeen = performance.now()
  if (speaker.decoder.decodeQueueSize > 24) {
    speaker.timestamp += duration
    return
  }
  speaker.decoder.decode(new EncodedAudioChunk({
    type: 'key',
    timestamp: speaker.timestamp,
    duration,
    data: new Uint8Array(buffer, 6),
  }))
  speaker.timestamp += duration

  const now = performance.now()
  for (const [id, stale] of decoders) {
    if (now - stale.lastSeen > 10000) {
      try { stale.decoder.close() } catch { /* already closed */ }
      decoders.delete(id)
    }
  }
}

async function ensureAudioPipeline() {
  const Decoder = globalThis.AudioDecoder
  if (!Decoder) throw new Error('当前浏览器缺少 WebCodecs AudioDecoder')
  const support = await Decoder.isConfigSupported({
    codec: 'opus', sampleRate: 48000, numberOfChannels: 2,
  })
  if (!support.supported) throw new Error('当前浏览器不支持 WebCodecs Opus 解码')

  audioContext = new AudioContext({ latencyHint: 'interactive', sampleRate: 48000 })
  await audioContext.audioWorklet.addModule(
    new URL('../../workers/voice-player-worklet.js', import.meta.url),
  )
  workletNode = new AudioWorkletNode(audioContext, 'voice-player', {
    numberOfInputs: 0,
    numberOfOutputs: 1,
    outputChannelCount: [2],
  })
  outputGain = audioContext.createGain()
  outputGain.gain.value = outputVolume.value / 100
  workletNode.connect(outputGain).connect(audioContext.destination)
  if (selectedOutput.value) await applyOutputDevice()
  workletNode.port.onmessage = (event) => {
    if (event.data?.type !== 'activity') return
    activeSpeakers.value = event.data.active || 0
    speakingIds.value = event.data.speaking || []
  }
  pushAllSpeakerGains()
  await audioContext.resume()
}

/** 断线后自动续上；失败原因写进 listenError 并让面板一直显示，不再无声重连。 */
function scheduleReconnect(generation: number, reason: string) {
  listenState.value = 'reconnecting'
  listenError.value = `${reason} · 正在重连（第 ${reconnectAttempt + 1} 次）`
  const delay = Math.min(1000 * 2 ** reconnectAttempt++, 10000)
  reconnectTimer = window.setTimeout(() => {
    void connectDownlink(generation).catch((error) => {
      if (!listening.value || generation !== listenGeneration) return
      void failListening(errorText(error, '频道语音重连失败'))
    })
  }, delay)
}

async function failListening(message: string) {
  await stopListening()
  listenError.value = message
  ElMessage.error(message)
}

/**
 * 后端是先 accept 再去连 TSMusicBot 的，所以 open 只代表「PowerfulTS 收下了」；
 * 上游不可用会在 open 之后紧接着以 4502 关闭 —— 这条路径必须报错而不是重连。
 */
function connectDownlink(generation: number): Promise<void> {
  if (!voiceBotId.value || generation !== listenGeneration) return Promise.resolve()
  return startVoiceDownlink().then((session) => {
    if (generation !== listenGeneration) return
    return new Promise<void>((resolve, reject) => {
      const socket = new WebSocket(websocketUrl(session.streamPath))
      socket.binaryType = 'arraybuffer'
      downlinkSocket = socket
      let opened = false
      let healthyTimer = 0

      socket.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) decodeVoicePacket(event.data)
      }
      socket.onopen = () => {
        opened = true
        listenError.value = ''
        listenState.value = 'live'
        // open 本身不算成功（上游还没连），否则每次重连都会把计数清零，
        // 机器人一直不在时就成了无限重连。撑过 10 秒才算这条连接真的活着。
        healthyTimer = window.setTimeout(() => { reconnectAttempt = 0 }, 10000)
        resolve()
      }
      socket.onerror = () => socket.close()
      socket.onclose = (event) => {
        if (healthyTimer) window.clearTimeout(healthyTimer)
        if (downlinkSocket === socket) downlinkSocket = null
        closeDecoders()
        if (!listening.value || generation !== listenGeneration) {
          if (!opened) resolve()
          return
        }
        const reason = closeText(event)
        if (!opened) {
          reject(new Error(reason))
          return
        }
        if (PERMANENT_CLOSE_CODES.has(event.code) || reconnectAttempt >= MAX_RECONNECT_ATTEMPTS) {
          void failListening(reason)
          return
        }
        scheduleReconnect(generation, reason)
      }
    })
  })
}

async function startListening() {
  if (!voiceBotId.value) return
  listening.value = true
  listenState.value = 'connecting'
  listenError.value = ''
  reconnectAttempt = 0
  const generation = ++listenGeneration
  try {
    await ensureAudioPipeline()
    await connectDownlink(generation)
  } catch (error) {
    await failListening(errorText(error, '频道语音连接失败'))
  }
}

async function stopListening() {
  listening.value = false
  listenState.value = 'idle'
  listenGeneration++
  if (reconnectTimer) window.clearTimeout(reconnectTimer)
  reconnectTimer = null
  downlinkSocket?.close(1000, 'listener stopped')
  downlinkSocket = null
  closeDecoders()
  workletNode?.disconnect()
  outputGain?.disconnect()
  workletNode = null
  outputGain = null
  if (audioContext) await audioContext.close().catch(() => {})
  audioContext = null
}

function setOutputVolume() {
  if (outputGain && audioContext) {
    outputGain.gain.setTargetAtTime(outputVolume.value / 100, audioContext.currentTime, 0.015)
  }
}

/** 把某人的音量推给 worklet（增益按 clid 生效，设置按昵称保存）。 */
function setSpeakerVolume(client: { clid: number; nickname: string }, percent: number) {
  const next = { ...speakerVolumes.value }
  if (percent === 100) delete next[client.nickname]
  else next[client.nickname] = percent
  speakerVolumes.value = next
  try {
    localStorage.setItem(SPEAKER_VOLUME_KEY, JSON.stringify(next))
  } catch {
    /* 隐私模式下写不进去，本次会话内仍然生效 */
  }
  workletNode?.port.postMessage({ type: 'gain', clientId: client.clid, value: percent / 100 })
}

/** 建好管线或频道成员变动后，把已保存的音量重新灌一遍。 */
function pushAllSpeakerGains() {
  if (!workletNode) return
  for (const client of roommates.value) {
    workletNode.port.postMessage({
      type: 'gain',
      clientId: client.clid,
      value: speakerVolume(client.nickname) / 100,
    })
  }
}

function chooseMicrophoneMimeType(): string {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || ''
}

/**
 * Device labels stay blank until the user has granted microphone access once,
 * so this is re-run after getUserMedia and on every devicechange.
 */
async function refreshDevices() {
  if (!navigator.mediaDevices?.enumerateDevices) return
  try {
    const devices = await navigator.mediaDevices.enumerateDevices()
    inputDevices.value = devices.filter((d) => d.kind === 'audioinput')
    outputDevices.value = devices.filter((d) => d.kind === 'audiooutput')
    if (selectedInput.value && !inputDevices.value.some((d) => d.deviceId === selectedInput.value)) {
      selectedInput.value = ''
    }
    if (selectedOutput.value && !outputDevices.value.some((d) => d.deviceId === selectedOutput.value)) {
      selectedOutput.value = ''
    }
  } catch {
    /* 权限未授予时枚举可能失败，忽略即可 */
  }
}

function deviceLabel(device: MediaDeviceInfo, index: number, kind: string): string {
  return device.label || `${kind} ${index + 1}`
}

function setMicrophoneVolume() {
  if (microphoneGain && microphoneContext) {
    microphoneGain.gain.setTargetAtTime(
      microphoneVolume.value / 100, microphoneContext.currentTime, 0.015,
    )
  }
}

/** Route the raw mic through a gain node so the slider actually changes what is sent. */
function buildMicrophonePipeline(stream: MediaStream): MediaStream {
  microphoneContext = new AudioContext()
  const source = microphoneContext.createMediaStreamSource(stream)
  microphoneGain = microphoneContext.createGain()
  microphoneGain.gain.value = microphoneVolume.value / 100
  microphoneOutput = microphoneContext.createMediaStreamDestination()
  source.connect(microphoneGain).connect(microphoneOutput)
  return microphoneOutput.stream
}

async function applyOutputDevice() {
  if (!canChooseOutput || !audioContext) return
  try {
    await (audioContext as AudioContext & { setSinkId(id: string): Promise<void> })
      .setSinkId(selectedOutput.value)
  } catch {
    ElMessage.warning('无法切换到该播放设备')
  }
}

// Switching devices mid-call has to rebuild the capture chain to take effect.
async function onInputDeviceChange() {
  if (!microphoneLive.value) return
  await stopMicrophone()
  await startMicrophone()
}

async function startMicrophone() {
  if (!voiceBotId.value) return
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
    ElMessage.error('当前浏览器不支持麦克风实时通话')
    return
  }
  const generation = ++microphoneGeneration
  microphoneState.value = 'requesting'
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
        ...(selectedInput.value ? { deviceId: { exact: selectedInput.value } } : {}),
      },
    })
    if (generation !== microphoneGeneration) {
      for (const track of stream.getTracks()) track.stop()
      return
    }
    microphone = stream
    void refreshDevices() // labels only materialise once permission is granted
    const mimeType = chooseMicrophoneMimeType()
    if (!mimeType) throw new Error('浏览器没有可用的实时音频编码器')
    microphoneState.value = 'connecting'
    const session = await startVoiceMicrophone(mimeType)
    if (generation !== microphoneGeneration) {
      await stopLiveAudio(session.sessionId).catch(() => {})
      return
    }
    microphoneSessionId = session.sessionId
    microphoneSocket = new WebSocket(websocketUrl(session.uploadPath))
    await waitForSocket(microphoneSocket)
    if (generation !== microphoneGeneration) return
    microphoneSocket.addEventListener('close', () => {
      if (!microphoneStopping && microphoneLive.value) {
        void stopMicrophone('麦克风连接已中断')
      }
    }, { once: true })

    microphoneRecorder = new MediaRecorder(
      buildMicrophonePipeline(microphone), { mimeType, audioBitsPerSecond: 64000 },
    )
    microphoneRecorder.ondataavailable = (event) => {
      if (event.data.size && microphoneSocket?.readyState === WebSocket.OPEN) {
        microphoneSocket.send(event.data)
      }
    }
    microphoneRecorder.onerror = () => {
      if (!microphoneStopping) void stopMicrophone('麦克风编码器已停止')
    }
    microphoneRecorder.start(100)
    microphoneLive.value = true
    microphoneState.value = 'live'
  } catch (error) {
    await stopMicrophone()
    ElMessage.error(errorText(error, '无法开启麦克风'))
  }
}

async function stopMicrophone(message?: string) {
  if (microphoneStopping) return
  microphoneStopping = true
  microphoneGeneration++
  microphoneLive.value = false
  microphoneState.value = 'idle'
  if (microphoneRecorder?.state !== 'inactive') microphoneRecorder?.stop()
  microphoneRecorder = null
  for (const track of microphone?.getTracks() || []) track.stop()
  microphone = null
  microphoneGain?.disconnect()
  microphoneOutput?.disconnect()
  microphoneGain = null
  microphoneOutput = null
  if (microphoneContext) await microphoneContext.close().catch(() => {})
  microphoneContext = null
  microphoneSocket?.close(1000, 'microphone stopped')
  microphoneSocket = null
  const sessionId = microphoneSessionId
  microphoneSessionId = ''
  if (sessionId) await stopLiveAudio(sessionId).catch(() => {})
  microphoneStopping = false
  if (message) ElMessage.warning(message)
}

/**
 * One button for the whole call. Listening is the part that must succeed; the
 * microphone is best-effort, so a denied mic permission leaves you in the call
 * muted instead of dropping you out of it.
 */
const joining = ref(false)

async function joinCall() {
  if (joining.value) return
  joining.value = true
  listenError.value = ''
  try {
    // 后端按登录账号开通话身份：以你自己的昵称进服务器，挂断就离开。
    const session = await openVoiceSession()
    voiceBotId.value = session.botId
    emit('session-change')
    await refreshChannels() // 立刻拿到同频道成员，音量面板才有内容
  } catch (error) {
    listenError.value = errorText(error, '无法加入通话')
    ElMessage.error(listenError.value)
    return
  } finally {
    joining.value = false
  }

  await startListening()
  if (!listening.value) return
  await startMicrophone()
}

async function leaveCall() {
  await stopMicrophone()
  await stopListening()
  voiceBotId.value = ''
  try {
    await closeVoiceSession()
  } catch {
    /* 后端还有宽限期兜底，这里失败不必打扰用户 */
  }
  emit('session-change')
}

async function toggleMicrophone() {
  if (microphoneLive.value) {
    await stopMicrophone()
  } else {
    await startMicrophone()
  }
}

// 直接关标签页时没有机会调 leaveCall，但下行 WebSocket 会随页面一起断开，
// 后端看到断开就会在宽限期后把通话身份收回——不需要 sendBeacon（它也带不上
// X-Session-Token 请求头，发了后端也认不出是谁）。
// 有人进出频道、或重连后 clid 变了，都要把保存的音量重新对应上去。
watch(roommates, pushAllSpeakerGains)

onMounted(() => {
  void refreshDevices()
  navigator.mediaDevices?.addEventListener?.('devicechange', refreshDevices)
})

onBeforeUnmount(() => {
  navigator.mediaDevices?.removeEventListener?.('devicechange', refreshDevices)
  void leaveCall()
})
</script>

<template>
  <section class="voice-panel" :class="{ 'is-listening': listening, 'is-speaking': microphoneLive }">
    <div class="voice-heading">
      <div class="voice-mark" aria-hidden="true">
        <span /><span /><span /><span /><span />
      </div>
      <div>
        <div class="eyebrow">CHANNEL VOICE · {{ displayName }}</div>
        <h2>网页频道通话</h2>
        <p>
          你会以 <b>{{ displayName }}</b> 的身份出现在频道里，挂断后自动离开服务器。
          无需同时打开 TeamSpeak 客户端。
        </p>
      </div>
    </div>

    <div class="voice-status">
      <span class="status-pill" :class="listenState">
        <i />
        {{ listenState === 'live' ? `正在收听 · ${activeSpeakers} 人发言` : listenState === 'connecting' ? '正在连接' : listenState === 'reconnecting' ? '正在重连' : '尚未收听' }}
      </span>
      <span class="status-pill" :class="{ live: microphoneLive }">
        <i />
        {{ microphoneLive ? '麦克风已开启' : '麦克风已静音' }}
      </span>
    </div>

    <div class="voice-actions">
      <button
        v-if="!listening"
        class="join-button"
        type="button"
        :disabled="joining || listenState === 'connecting'"
        @click="joinCall"
      >
        <span class="button-icon">◖</span>
        {{ joining ? '正在进入服务器…' : listenState === 'connecting' ? '正在加入…' : '加入通话' }}
      </button>
      <button v-else class="leave-button" type="button" @click="leaveCall">
        <span class="button-icon">■</span> 挂断
      </button>

      <button
        v-if="listening"
        class="mic-toggle"
        :class="{ live: microphoneLive }"
        type="button"
        :disabled="microphoneState === 'requesting' || microphoneState === 'connecting'"
        @click="toggleMicrophone"
      >
        <span v-if="microphoneLive" class="live-ring" />
        <span v-else class="button-icon">●</span>
        {{ microphoneState === 'requesting' ? '等待授权' : microphoneState === 'connecting' ? '连接中'
          : microphoneLive ? '麦克风开启中 · 点击静音' : '已静音 · 点击说话' }}
      </button>
    </div>

    <div class="voice-settings">
      <label class="setting">
        <span class="setting-label">收听音量 <b>{{ outputVolume }}%</b></span>
        <input v-model.number="outputVolume" type="range" min="0" max="100" @input="setOutputVolume">
      </label>
      <label class="setting">
        <span class="setting-label">麦克风音量 <b>{{ microphoneVolume }}%</b></span>
        <input v-model.number="microphoneVolume" type="range" min="0" max="200" @input="setMicrophoneVolume">
      </label>
      <label class="setting">
        <span class="setting-label">麦克风设备</span>
        <select v-model="selectedInput" @change="onInputDeviceChange">
          <option value="">系统默认</option>
          <option v-for="(device, i) in inputDevices" :key="device.deviceId" :value="device.deviceId">
            {{ deviceLabel(device, i, '麦克风') }}
          </option>
        </select>
      </label>
      <label v-if="canChooseOutput" class="setting">
        <span class="setting-label">播放设备</span>
        <select v-model="selectedOutput" @change="applyOutputDevice">
          <option value="">系统默认</option>
          <option v-for="(device, i) in outputDevices" :key="device.deviceId" :value="device.deviceId">
            {{ deviceLabel(device, i, '扬声器') }}
          </option>
        </select>
      </label>
      <p v-if="!inputDevices.length || !inputDevices[0].label" class="setting-hint">
        设备名称要等浏览器授予过一次麦克风权限才会显示。
      </p>
    </div>

    <div v-if="listening" class="speaker-mixer">
      <div class="mixer-head">
        <span class="setting-label">频道里的人</span>
        <span class="mixer-hint">可以单独调每个人的音量</span>
      </div>
      <p v-if="!roommates.length" class="mixer-empty">这个频道现在只有你。</p>
      <ul v-else class="mixer-list">
        <li v-for="client in roommates" :key="client.clid" :class="{ talking: speakingIds.includes(client.clid) }">
          <span class="mixer-name">
            <i class="talk-dot" aria-hidden="true" />
            {{ client.nickname }}
          </span>
          <input
            type="range" min="0" max="200"
            :value="speakerVolume(client.nickname)"
            @input="setSpeakerVolume(client, Number(($event.target as HTMLInputElement).value))"
          >
          <b :class="{ muted: speakerVolume(client.nickname) === 0 }">
            {{ speakerVolume(client.nickname) === 0 ? '静音' : speakerVolume(client.nickname) + '%' }}
          </b>
        </li>
      </ul>
    </div>

    <p v-if="listenError" class="voice-error" role="alert">
      <span>连接失败</span>{{ listenError }}
    </p>

    <div class="voice-note">
      <span>回声保护已启用</span>
      建议使用耳机；网页通话时不要让同一设备上的 TeamSpeak 客户端同时进入该频道。
    </div>
  </section>
</template>

<style scoped>
.voice-panel {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px 28px;
  overflow: hidden;
  padding: 22px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background:
    radial-gradient(circle at 8% 0%, rgba(var(--color-primary-rgb), .12), transparent 36%),
    linear-gradient(145deg, var(--bg-card), rgba(var(--color-primary-rgb), .025));
  box-shadow: var(--shadow-card);
}
.voice-panel::after {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 4px;
  background: var(--gradient-brand);
  opacity: .68;
}
.is-speaking::after { background: var(--color-danger); box-shadow: 0 0 18px rgba(var(--color-danger-rgb), .45); }
.voice-heading { display: flex; gap: 15px; align-items: flex-start; min-width: 0; }
.voice-mark {
  display: flex;
  width: 42px;
  height: 42px;
  flex: 0 0 42px;
  align-items: center;
  justify-content: center;
  gap: 3px;
  border: 1px solid rgba(var(--color-primary-rgb), .28);
  border-radius: 12px;
  background: rgba(var(--color-primary-rgb), .08);
}
.voice-mark span { width: 2px; height: 9px; border-radius: 2px; background: var(--color-primary); }
.voice-mark span:nth-child(2), .voice-mark span:nth-child(4) { height: 18px; }
.voice-mark span:nth-child(3) { height: 26px; }
.is-listening .voice-mark span { animation: voice-wave .8s ease-in-out infinite alternate; }
.is-listening .voice-mark span:nth-child(2) { animation-delay: -.3s; }
.is-listening .voice-mark span:nth-child(3) { animation-delay: -.6s; }
.eyebrow { margin: 2px 0 7px; color: var(--color-primary); font: 600 .63em/1 ui-monospace, Consolas, monospace; letter-spacing: .11em; }
h2 { margin: 0 0 6px; color: var(--text-primary); font-size: 1.08em; letter-spacing: -.015em; }
p { margin: 0; color: var(--text-secondary); font-size: .76em; line-height: 1.6; }
.voice-status { display: flex; min-width: 0; align-items: flex-end; flex-direction: column; gap: 8px; }
.status-pill { display: inline-flex; align-items: center; gap: 7px; padding: 6px 9px; border: 1px solid var(--border-subtle); border-radius: 999px; color: var(--text-muted); background: var(--bg-elevated); font-size: .65em; }
.status-pill i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.status-pill.live { color: var(--color-success); border-color: rgba(var(--color-success-rgb), .28); }
.status-pill.connecting, .status-pill.reconnecting { color: var(--color-accent); }
.voice-settings {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 12px 18px;
  padding-top: 14px;
  border-top: 1px solid var(--border-subtle);
}
.setting { display: flex; min-width: 0; flex-direction: column; gap: 6px; }
.setting-label { color: var(--text-muted); font-size: .64em; font-weight: 600; }
.setting-label b { color: var(--text-secondary); font-variant-numeric: tabular-nums; }
.setting input[type="range"] { width: 100%; accent-color: var(--color-primary); }
.setting select {
  width: 100%;
  min-width: 0;
  padding: 6px 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--bg-elevated);
  color: var(--text-secondary);
  font-family: inherit;
  font-size: .68em;
}
.setting-hint { grid-column: 1 / -1; margin: 0; color: var(--text-muted); font-size: .62em; }

.speaker-mixer {
  grid-column: 1 / -1;
  padding-top: 14px;
  border-top: 1px solid var(--border-subtle);
}
.mixer-head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
.mixer-hint { color: var(--text-muted); font-size: .6em; }
.mixer-empty { margin: 0; color: var(--text-muted); font-size: .68em; }
.mixer-list { display: flex; margin: 0; padding: 0; flex-direction: column; gap: 8px; list-style: none; }
.mixer-list li {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(90px, 1.1fr) 46px;
  gap: 10px;
  align-items: center;
}
.mixer-name {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 7px;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: .7em;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.talk-dot { width: 5px; height: 5px; flex: none; border-radius: 50%; background: var(--border-default); transition: background .12s, box-shadow .12s; }
.talking .talk-dot { background: var(--color-success); box-shadow: 0 0 0 3px rgba(var(--color-success-rgb), .22); }
.talking .mixer-name { color: var(--text-primary); }
.mixer-list input[type="range"] { width: 100%; accent-color: var(--color-primary); }
.mixer-list b { color: var(--text-secondary); font-size: .64em; font-variant-numeric: tabular-nums; text-align: right; }
.mixer-list b.muted { color: var(--color-danger); }

@media (max-width: 680px) {
  .mixer-list li { grid-template-columns: minmax(0, 1fr) 44px; grid-template-areas: "name value" "range range"; }
  .mixer-name { grid-area: name; }
  .mixer-list b { grid-area: value; }
  .mixer-list input[type="range"] { grid-area: range; }
}
/* flex, not a 2-column grid: before joining there is only the one button. */
.voice-actions { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 10px; }
.voice-actions button { flex: 1 1 200px; }
.voice-actions button { min-height: 40px; border-radius: var(--radius-sm); font-size: .74em; font-weight: 650; cursor: pointer; transition: transform .15s, filter .15s, opacity .15s; }
.voice-actions button:hover:not(:disabled) { transform: translateY(-1px); filter: brightness(1.08); }
.voice-actions button:disabled { opacity: .5; cursor: wait; }
.join-button { border: 1px solid rgba(var(--color-primary-rgb), .42); color: #fff; background: var(--gradient-brand); }
.leave-button { border: 1px solid rgba(var(--color-danger-rgb), .38); color: #fff; background: linear-gradient(135deg, rgba(var(--color-danger-rgb), .9), rgba(var(--color-danger-rgb), .65)); }
.mic-toggle { border: 1px solid var(--border-subtle); color: var(--text-muted); background: var(--bg-elevated); }
.mic-toggle.live { border-color: rgba(var(--color-success-rgb), .42); color: var(--color-success); background: rgba(var(--color-success-rgb), .09); }
.button-icon { margin-right: 6px; font-size: .9em; }
.live-ring { display: inline-block; width: 7px; height: 7px; margin-right: 7px; border-radius: 50%; background: currentColor; box-shadow: 0 0 0 4px rgba(var(--color-success-rgb), .18); animation: mic-pulse 1.25s ease-out infinite; }
.voice-error {
  grid-column: 1 / -1;
  padding: 10px 12px;
  border: 1px solid rgba(var(--color-danger-rgb), .3);
  border-radius: var(--radius-sm);
  background: rgba(var(--color-danger-rgb), .07);
  color: var(--text-secondary);
  font-size: .7em;
  line-height: 1.6;
}
.voice-error span { margin-right: 8px; color: var(--color-danger); font-weight: 700; }
.voice-note { grid-column: 1 / -1; padding-top: 11px; border-top: 1px solid var(--border-subtle); color: var(--text-muted); font-size: .65em; line-height: 1.5; }
.voice-note span { margin-right: 8px; color: var(--color-success); font-weight: 650; }
@keyframes voice-wave { from { transform: scaleY(.45); } to { transform: scaleY(1); } }
@keyframes mic-pulse { 70%, 100% { box-shadow: 0 0 0 9px rgba(var(--color-success-rgb), 0); } }
@media (max-width: 680px) {
  .voice-panel { grid-template-columns: 1fr; padding: 18px; }
  .voice-status { align-items: flex-start; min-width: 0; }
  .voice-actions button { flex-basis: 100%; }
}
@media (prefers-reduced-motion: reduce) {
  .is-listening .voice-mark span, .live-ring { animation: none; }
}
</style>
