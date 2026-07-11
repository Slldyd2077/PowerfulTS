<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { login as apiLogin, register as apiRegister, getClientIp, sendCode, checkBinding } from '@/api/auth'
import { getIntroTracks, introStreamUrl, type IntroTrack } from '@/api/introMusic'
import { ElMessage } from 'element-plus'
import { View } from '@element-plus/icons-vue'

const router = useRouter()
const auth = useAuthStore()

const mode = ref<'login' | 'register'>('login')
const loading = ref(false)
const formVisible = ref(false)

// 登录表单
const loginForm = ref({ tsNickname: '', password: '' })

// 注册表单
const registerForm = ref({
  tsNickname: '',
  password: '',
  confirmPassword: '',
  code: '',
})
const codeSent = ref(false)
const codeCountdown = ref(0)

const canLogin = computed(() => loginForm.value.tsNickname.trim() && loginForm.value.password.trim())
// 后端 RegisterRequest.password 强制 min_length=8，前端同步约束，避免裸 422
const MIN_PASSWORD_LENGTH = 8
const passwordTooShort = computed(
  () =>
    registerForm.value.password.length > 0 &&
    registerForm.value.password.length < MIN_PASSWORD_LENGTH,
)
const canRegister = computed(() =>
  registerForm.value.tsNickname.trim() &&
  registerForm.value.password.length >= MIN_PASSWORD_LENGTH &&
  registerForm.value.password === registerForm.value.confirmPassword &&
  registerForm.value.code.trim(),
)

// ── 音频频谱可视化 ──
// 真实音频驱动（AnalyserNode）；无音乐或 AudioContext 尚未 running 时回退模拟律动。
const BAR_COUNT = 48
const canvasRef = ref<HTMLCanvasElement | null>(null)
let animFrameId = 0
let bars: number[] = []
let resizeHandler: (() => void) | null = null

// Web Audio 图：source → analyser → gain → destination
// analyser 位于 gain 之前，故静音（gain=0）时仍能拿到频率数据 → 频谱照常律动。
// 每个 <audio> 元素只能 createMediaElementSource 一次 → 用单元素 + 改 src 切歌。
let audioCtx: AudioContext | null = null
let analyser: AnalyserNode | null = null
let freqData: Uint8Array<ArrayBuffer> | null = null
let gainNode: GainNode | null = null
let sourceBound = false

// 默认播放音量（背景音乐不宜过大，范围 0–1）
const DEFAULT_VOLUME = 0.4
// 音量持久化 key（localStorage）
const VOLUME_KEY = 'intro_music_volume'

/** 从 localStorage 读取上次音量，缺失 / 非法时回退默认值。 */
function loadVolume(): number {
  try {
    const raw = localStorage.getItem(VOLUME_KEY)
    if (raw == null) return DEFAULT_VOLUME
    const v = Number(raw)
    return Number.isFinite(v) && v >= 0 && v <= 1 ? v : DEFAULT_VOLUME
  } catch {
    return DEFAULT_VOLUME
  }
}

/** 持久化音量到 localStorage（隐私模式等失败时静默忽略）。 */
function persistVolume(v: number) {
  try {
    localStorage.setItem(VOLUME_KEY, String(v))
  } catch {
    /* ignore */
  }
}

// 音频元素与播放状态
const audioRef = ref<HTMLAudioElement | null>(null)
const tracks = ref<IntroTrack[]>([])
const currentTrack = ref<IntroTrack | null>(null)
const hasRealAudio = ref(false) // AudioContext 进入 running → 频谱走真实数据
const volume = ref(loadVolume()) // 意图音量 0–1（持久化）；0 视为静音
let lastVolume = volume.value > 0 ? volume.value : DEFAULT_VOLUME // 静音前音量，用于恢复
const muted = ref(false) // 当前是否静音（autoplay 兜底 / 用户手动静音 / 音量拖到 0）
const soundHint = ref(false) // autoplay 兜底时提示「点此开声」

/** 频谱高度倍率：以默认音量为基准（=1.0）；静音或音量为 0 时为 0（频谱贴底不动）。 */
const spectrumScale = computed(() => {
  if (muted.value || volume.value <= 0) return 0
  return volume.value / DEFAULT_VOLUME
})

function initVisualizer() {
  const canvas = canvasRef.value
  if (!canvas) return

  const ctx = canvas.getContext('2d')
  if (!ctx) return

  bars = Array.from({ length: BAR_COUNT }, () => Math.random() * 0.3 + 0.1)

  resizeHandler = () => {
    const rect = canvas.getBoundingClientRect()
    canvas.width = rect.width * devicePixelRatio
    canvas.height = rect.height * devicePixelRatio
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.scale(devicePixelRatio, devicePixelRatio)
  }
  resizeHandler()
  window.addEventListener('resize', resizeHandler)

  const draw = () => {
    const w = canvas.getBoundingClientRect().width
    const h = canvas.getBoundingClientRect().height

    ctx.clearRect(0, 0, w, h)

    const gap = 3
    const barWidth = (w - gap * (BAR_COUNT - 1)) / BAR_COUNT
    const a = analyser
    const d = freqData
    const real = hasRealAudio.value && a !== null && d !== null
    if (real && a && d) a.getByteFrequencyData(d)

    // 频谱整体按音量等比例缩放：默认音量(0.4)=1.0，往上更高，静音/0 贴底不动
    const scale = spectrumScale.value

    for (let i = 0; i < BAR_COUNT; i++) {
      if (real && a && d) {
        // 前 BAR_COUNT 个 FFT bin 归一化 × 音量倍率
        const target = (d[i] / 255) * scale
        bars[i] += (target - bars[i]) * 0.5
      } else {
        // 模拟律动（无音乐 / context 未 running 时降级）× 音量倍率
        const target = (0.08 + Math.random() * 0.55) * scale
        bars[i] += (target - bars[i]) * 0.08 + (Math.random() - 0.5) * 0.02 * scale
      }
      bars[i] = Math.max(0, Math.min(0.95, bars[i]))

      const barHeight = bars[i] * h * 0.7
      const x = i * (barWidth + gap)
      const y = h - barHeight

      // 渐变色条
      const gradient = ctx.createLinearGradient(x, y, x, h)
      gradient.addColorStop(0, 'rgba(82, 147, 226, 0.95)')
      gradient.addColorStop(0.5, 'rgba(17, 108, 224, 0.5)')
      gradient.addColorStop(1, 'rgba(1, 30, 77, 0.16)')

      ctx.beginPath()
      ctx.roundRect(x, y, barWidth, barHeight, 2)
      ctx.fillStyle = gradient
      ctx.fill()

      // 顶部高亮点
      ctx.beginPath()
      ctx.roundRect(x, y, barWidth, Math.min(3, barHeight), 2)
      ctx.fillStyle = 'rgba(82, 147, 226, 1)'
      ctx.fill()
    }

    animFrameId = requestAnimationFrame(draw)
  }

  draw()
}

/** 建立 Web Audio 图（每个 audio 元素仅一次）。 */
function ensureAudioGraph() {
  const audio = audioRef.value
  if (!audio || sourceBound) return
  const Ctor =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!Ctor) return

  audioCtx = new Ctor()
  const src = audioCtx.createMediaElementSource(audio)
  analyser = audioCtx.createAnalyser()
  analyser.fftSize = 128 // frequencyBinCount = 64，取前 48
  analyser.smoothingTimeConstant = 0.8
  freqData = new Uint8Array(analyser.frequencyBinCount)
  gainNode = audioCtx.createGain()
  gainNode.gain.value = muted.value ? 0 : volume.value

  src.connect(analyser)
  analyser.connect(gainNode)
  gainNode.connect(audioCtx.destination)
  sourceBound = true

  // context 进入 running（通常用户首次交互后）→ 频谱切真实律动
  audioCtx.onstatechange = () => {
    if (audioCtx?.state === 'running') hasRealAudio.value = true
  }

  // 监听首次任意交互，尽早 resume context（频谱更快开始真实律动，仍保持当前静音态）
  document.addEventListener('pointerdown', onFirstInteraction, { once: true })
  document.addEventListener('keydown', onFirstInteraction, { once: true })
}

function onFirstInteraction() {
  audioCtx?.resume().catch(() => {})
  document.removeEventListener('pointerdown', onFirstInteraction)
  document.removeEventListener('keydown', onFirstInteraction)
}

/** 随机选曲（避免连续重复同一首）。 */
function pickRandomTrack(exclude?: string | null): IntroTrack | null {
  const pool = tracks.value
  if (pool.length === 0) return null
  if (pool.length === 1) return pool[0]
  let next = pool[Math.floor(Math.random() * pool.length)]
  if (next.filename === exclude) {
    next = pool[(pool.indexOf(next) + 1) % pool.length]
  }
  return next
}

/** 切歌：改 src（不重建 audio 元素，保留已建的 source 节点）。 */
function loadTrack(track: IntroTrack) {
  const audio = audioRef.value
  if (!audio) return
  currentTrack.value = track
  audio.src = introStreamUrl(track.filename)
  audio.load()
}

/** 尝试播放并 resume context；返回是否成功（不抛错）。 */
async function tryPlay(): Promise<boolean> {
  const audio = audioRef.value
  if (!audio) return false
  try {
    if (audioCtx?.state === 'suspended') await audioCtx.resume()
    await audio.play()
    return true
  } catch {
    return false
  }
}

/** 播放结束 → 随机换下一首（切歌失败则静音兜底，避免频谱卡死，与 onMounted 三段式一致）。 */
async function onTrackEnded() {
  const next = pickRandomTrack(currentTrack.value?.filename ?? null)
  if (!next) return
  loadTrack(next)
  const ok = await tryPlay()
  if (!ok) {
    if (gainNode) gainNode.gain.setValueAtTime(0, audioCtx?.currentTime ?? 0)
    const a = audioRef.value
    if (a) a.muted = true
    await tryPlay()
  }
}

/** 把 GainNode 平滑过渡到「当前应有效果音量」（muted ? 0 : volume）。 */
function applyGain(duration = 0.15) {
  if (!audioCtx || !gainNode) return
  const now = audioCtx.currentTime
  const target = muted.value ? 0 : volume.value
  const g = gainNode.gain
  g.cancelScheduledValues(now)
  g.setValueAtTime(g.value, now)
  g.linearRampToValueAtTime(target, now + duration)
}

/** 音量滑块输入：持久化 + 同步静音态 + 应用增益。 */
function onVolumeInput() {
  const v = volume.value
  persistVolume(v)
  if (v > 0) {
    lastVolume = v
    if (muted.value) {
      muted.value = false
      soundHint.value = false
    }
  } else {
    muted.value = true
  }
  applyGain(0.1)
}

/** 静音 ↔ 开声切换（用 GainNode 做平滑淡入淡出）。 */
async function toggleSound() {
  const audio = audioRef.value
  if (!audio) return
  if (muted.value) {
    // 开声：恢复上次音量并淡入
    muted.value = false
    soundHint.value = false
    audio.muted = false
    if (volume.value <= 0) {
      volume.value = lastVolume || DEFAULT_VOLUME
      persistVolume(volume.value)
    }
    if (audioCtx?.state === 'suspended') await audioCtx.resume()
    await audio.play().catch(() => {})
    applyGain(0.5)
  } else {
    // 静音：淡出
    muted.value = true
    applyGain(0.3)
  }
}

// ── 入场动画 + 频谱 + 随机背景音乐 ──
onMounted(async () => {
  requestAnimationFrame(() => {
    formVisible.value = true
  })
  initVisualizer()

  // 加载曲目（失败 / 为空 → 频谱保持模拟律动）
  try {
    tracks.value = await getIntroTracks()
  } catch {
    tracks.value = []
  }

  const first = pickRandomTrack()
  if (first && audioRef.value) {
    ensureAudioGraph()
    loadTrack(first)

    // Autoplay 三段式：先试有声自动播放
    muted.value = false
    const ok = await tryPlay()
    if (ok) {
      // 有声播放成功（高 Media Engagement 用户 / 已交互）
    } else {
      // 浏览器拒绝有声 autoplay → 静音播放（频谱照常律动）+ 显示开声按钮
      muted.value = true
      soundHint.value = true
      if (gainNode) gainNode.gain.setValueAtTime(0, audioCtx?.currentTime ?? 0)
      audioRef.value.muted = true // 兜过浏览器 autoplay 策略
      await tryPlay()
    }
  }
})

onUnmounted(() => {
  cancelAnimationFrame(animFrameId)
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
  document.removeEventListener('pointerdown', onFirstInteraction)
  document.removeEventListener('keydown', onFirstInteraction)
  const audio = audioRef.value
  if (audio) {
    audio.pause()
    audio.removeAttribute('src')
    audio.load()
  }
  if (audioCtx) audioCtx.onstatechange = null
  audioCtx?.close().catch(() => {})
})

/** 以游客身份进入（仅可访问监控面板） */
function handleGuest() {
  auth.enterAsGuest()
  router.push('/')
}

/** 登录 */
async function handleLogin() {
  if (!canLogin.value) return
  loading.value = true
  try {
    const ip = await getClientIp()
    const result = await apiLogin(loginForm.value.tsNickname, loginForm.value.password, ip)
    if (result.success && result.token) {
      auth.setToken(result.token)
      auth.setUser({
        ts_nickname: result.ts_nickname || '',
        is_admin: result.is_admin || false,
      })
      ElMessage.success(`欢迎回来，${result.ts_nickname}！`)
      const redirect = (router.currentRoute.value.query.redirect as string) || '/'
      router.push(redirect)
    } else {
      ElMessage.error(result.error || '登录失败')
    }
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '网络错误')
  } finally {
    loading.value = false
  }
}

/** 发送验证码 */
async function handleSendCode() {
  if (!registerForm.value.tsNickname.trim()) {
    ElMessage.warning('请先填写 TS 昵称')
    return
  }

  try {
    const bind = await checkBinding(registerForm.value.tsNickname)
    if (bind.bound) {
      ElMessage.info('该昵称已注册，请直接登录')
      mode.value = 'login'
      loginForm.value.tsNickname = registerForm.value.tsNickname
      return
    }

    const codeRes = await sendCode(registerForm.value.tsNickname)
    if (codeRes.success) {
      ElMessage.success('验证码已通过 TS 私聊发送')
    } else {
      ElMessage.error(codeRes.error || '验证码发送失败')
      return
    }
    codeSent.value = true

    codeCountdown.value = 60
    const timer = setInterval(() => {
      codeCountdown.value--
      if (codeCountdown.value <= 0) clearInterval(timer)
    }, 1000)
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '发送验证码失败')
  }
}

/** 注册 */
async function handleRegister() {
  if (registerForm.value.password.length < MIN_PASSWORD_LENGTH) {
    ElMessage.warning('密码至少需要 8 位')
    return
  }
  if (!canRegister.value) return
  loading.value = true
  try {
    const ip = await getClientIp()
    const res = await apiRegister(
      registerForm.value.tsNickname,
      registerForm.value.password,
      registerForm.value.code,
      ip,
    )
    if (res.success) {
      ElMessage.success('注册成功，请登录')
      mode.value = 'login'
      loginForm.value.tsNickname = registerForm.value.tsNickname
    } else {
      ElMessage.error(res.error || '注册失败')
    }
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <!-- ═══ 左面板：沉浸式视觉 ═══ -->
    <div class="panel-visual">
      <!-- 噪点纹理 -->
      <div class="noise-layer"></div>

      <!-- 音频频谱 -->
      <canvas ref="canvasRef" class="spectrum-canvas"></canvas>

      <!-- 开屏随机背景音乐（隐藏 audio 元素） -->
      <audio ref="audioRef" class="intro-audio" preload="auto" @ended="onTrackEnded"></audio>

      <!-- 静音 / 开声切换 + 悬停音量滑块 -->
      <div v-if="tracks.length > 0" class="sound-control" :class="{ hint: soundHint }">
        <button
          class="sound-toggle"
          :title="muted ? '点击开启声音' : '静音'"
          @click="toggleSound"
        >
          <span class="sound-icon">{{ muted ? '🔇' : '🔊' }}</span>
        </button>
        <div class="volume-popover">
          <input
            v-model.number="volume"
            type="range"
            min="0"
            max="1"
            step="0.01"
            class="volume-slider"
            aria-label="背景音乐音量"
            @input="onVolumeInput"
          />
          <span class="volume-value">{{ Math.round(volume * 100) }}</span>
        </div>
      </div>

      <!-- 品牌层 -->
      <div class="brand-layer">
        <img class="brand-logo" src="/logo-mark.svg" alt="PowerfulTS" />
        <h1 class="brand-title">
          <span class="brand-title-line">Powerful</span>
          <span class="brand-title-line brand-title-accent">TS</span>
        </h1>
        <p class="brand-tagline">TeamSpeak 监控面板</p>
        <div class="brand-meta">
          <span class="meta-dot"></span>
          实时语音
        </div>
      </div>

      <!-- 底部装饰线 -->
      <div class="bottom-line"></div>
    </div>

    <!-- ═══ 右面板：表单区 ═══ -->
    <div class="panel-form" :class="{ visible: formVisible }">
      <div class="form-wrapper">
        <!-- 模式切换指示器 -->
        <div class="mode-indicator">
          <div class="mode-track">
            <div class="mode-thumb" :class="{ right: mode === 'register' }"></div>
          </div>
          <button class="mode-btn" :class="{ active: mode === 'login' }" @click="mode = 'login'">登录</button>
          <button class="mode-btn" :class="{ active: mode === 'register' }" @click="mode = 'register'">注册</button>
        </div>

        <!-- 登录表单 -->
        <Transition name="form" mode="out-in">
          <div v-if="mode === 'login'" key="login" class="form-body">
            <div class="form-header">
              <h2 class="form-title">欢迎回来</h2>
              <p class="form-desc">登录以查看服务器状态和在线用户</p>
            </div>

            <el-form @submit.prevent="handleLogin" label-position="top" class="styled-form">
              <div class="field-group field-1">
                <label class="field-label">TS 昵称</label>
                <el-input
                  v-model="loginForm.tsNickname"
                  placeholder="请输入 TS 昵称"
                  size="large"
                  prefix-icon="User"
                />
              </div>
              <div class="field-group field-2">
                <label class="field-label">密码</label>
                <el-input
                  v-model="loginForm.password"
                  type="password"
                  placeholder="请输入密码"
                  size="large"
                  show-password
                  prefix-icon="Lock"
                  @keyup.enter="handleLogin"
                />
              </div>
              <div class="field-group field-3">
                <button
                  type="submit"
                  class="submit-btn"
                  :class="{ loading }"
                  :disabled="!canLogin || loading"
                  @click.prevent="handleLogin"
                >
                  <span class="btn-text">{{ loading ? '正在登录...' : '登 录' }}</span>
                  <span class="btn-shimmer"></span>
                </button>
              </div>
            </el-form>

            <!-- 游客入口 -->
            <div class="guest-entry field-group field-7">
              <div class="divider-or">
                <span class="divider-line"></span>
                <span class="divider-text label-mono">或</span>
                <span class="divider-line"></span>
              </div>
              <button class="guest-btn" @click="handleGuest">
                <el-icon class="guest-icon"><View /></el-icon>
                <span>以游客身份浏览</span>
              </button>
              <p class="guest-hint">仅可查看服务器监控面板</p>
            </div>
          </div>

          <!-- 注册表单 -->
          <div v-else key="register" class="form-body">
            <div class="form-header">
              <h2 class="form-title">创建账号</h2>
              <p class="form-desc">使用 TS 昵称注册，验证码通过 TS 私聊发送</p>
            </div>

            <el-form @submit.prevent="handleRegister" label-position="top" class="styled-form">
              <div class="field-group field-1">
                <label class="field-label">TS 昵称</label>
                <el-input v-model="registerForm.tsNickname" placeholder="TS 服务器中的昵称" size="large" />
              </div>
              <div class="field-group field-3">
                <label class="field-label">密码</label>
                <el-input
                  v-model="registerForm.password"
                  type="password"
                  placeholder="至少 8 位字符"
                  size="large"
                  show-password
                />
                <p class="field-hint" :class="{ 'field-hint--error': passwordTooShort }">
                  {{
                    passwordTooShort
                      ? `密码至少 8 位（当前 ${registerForm.password.length} 位）`
                      : '至少 8 位字符'
                  }}
                </p>
              </div>
              <div class="field-group field-4">
                <label class="field-label">确认密码</label>
                <el-input
                  v-model="registerForm.confirmPassword"
                  type="password"
                  placeholder="再次输入密码"
                  size="large"
                  show-password
                />
              </div>
              <div class="field-group field-5">
                <label class="field-label">验证码（发送到 TS 私聊）</label>
                <div class="code-row">
                  <el-input v-model="registerForm.code" placeholder="6 位验证码" size="large" maxlength="6" />
                  <button
                    class="code-btn"
                    :disabled="codeCountdown > 0 || !registerForm.tsNickname.trim()"
                    @click="handleSendCode"
                  >
                    {{ codeCountdown > 0 ? `${codeCountdown}s` : '获取验证码' }}
                  </button>
                </div>
              </div>
              <div class="field-group field-6">
                <button
                  type="submit"
                  class="submit-btn"
                  :class="{ loading }"
                  :disabled="!canRegister || loading"
                  @click.prevent="handleRegister"
                >
                  <span class="btn-text">{{ loading ? '正在注册...' : '注 册' }}</span>
                  <span class="btn-shimmer"></span>
                </button>
              </div>
            </el-form>
          </div>
        </Transition>
      </div>

      <!-- 底部版权 -->
      <div class="form-footer">
        <span>Powered by PowerfulTS</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════
   登录页：沉浸式分屏布局
   左 55% 视觉 + 右 45% 表单
   ═══════════════════════════════════════ */

.login-page {
  height: 100vh;
  width: 100%;
  display: flex;
  overflow: hidden;
  background: var(--surface-0);
}

/* ────────── 左面板：视觉 ────────── */
.panel-visual {
  position: relative;
  width: 55%;
  background: linear-gradient(160deg, #030812 0%, #071329 46%, #0a2140 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

/* 噪点层 */
.noise-layer {
  position: absolute;
  inset: 0;
  opacity: 0.035;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  background-size: 200px;
  pointer-events: none;
}

/* 音频频谱 Canvas */
.spectrum-canvas {
  position: absolute;
  bottom: 0;
  left: 0;
  width: 100%;
  height: 55%;
  pointer-events: none;
  opacity: 0.85;
}

/* 隐藏的开屏背景音乐元素 */
.intro-audio {
  display: none;
}

/* 静音 / 开声按钮 + 悬停音量滑块容器 */
.sound-control {
  position: absolute;
  left: 28px;
  bottom: 28px;
  z-index: 4;
  display: flex;
  align-items: center;
  gap: 10px;
}

.sound-toggle {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  border: 1px solid rgba(82, 147, 226, 0.28);
  background: rgba(3, 8, 18, 0.58);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color 0.25s var(--ease-out-expo), box-shadow 0.25s var(--ease-out-expo), transform 0.2s var(--ease-out-expo);
}

.sound-toggle:hover {
  border-color: rgba(82, 147, 226, 0.55);
  box-shadow: 0 0 18px rgba(17, 108, 224, 0.24);
  transform: translateY(-1px);
}

.sound-toggle:active {
  transform: translateY(0);
}

.sound-icon {
  font-size: 1.05em;
  line-height: 1;
}

/* 悬停弹出的音量滑块（按钮右侧） */
.volume-popover {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: rgba(3, 8, 18, 0.68);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(82, 147, 226, 0.22);
  border-radius: 100px;
  opacity: 0;
  transform: translateX(8px) scale(0.96);
  transform-origin: left center;
  pointer-events: none;
  transition: opacity 0.2s var(--ease-out-expo), transform 0.2s var(--ease-out-expo);
}

.sound-control:hover .volume-popover {
  opacity: 1;
  transform: translateX(0) scale(1);
  pointer-events: auto;
}

.volume-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 96px;
  height: 4px;
  border-radius: 2px;
  background: linear-gradient(90deg, rgba(82, 147, 226, 0.72), rgba(17, 108, 224, 0.14));
  outline: none;
  cursor: pointer;
}

.volume-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #5293e2;
  border: none;
  box-shadow: 0 0 8px rgba(82, 147, 226, 0.62);
  cursor: pointer;
}

.volume-slider::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #5293e2;
  border: none;
  box-shadow: 0 0 8px rgba(82, 147, 226, 0.62);
  cursor: pointer;
}

.volume-value {
  font-size: 0.72em;
  color: var(--text-muted);
  min-width: 26px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* autoplay 兜底态：按钮高亮脉动，提示用户点击开声 */
.sound-control.hint .sound-toggle {
  border-color: rgba(82, 147, 226, 0.58);
  animation: sound-hint-pulse 2s ease-in-out infinite;
}

@keyframes sound-hint-pulse {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(82, 147, 226, 0.35);
  }
  50% {
    box-shadow: 0 0 18px 4px rgba(82, 147, 226, 0.22);
  }
}

/* 品牌层 */
.brand-layer {
  position: relative;
  z-index: 2;
  text-align: left;
  padding: 0 48px;
  margin-top: -8vh;
}

.brand-logo {
  width: 82px;
  height: 82px;
  margin-bottom: 24px;
  border-radius: 20px;
  padding: 5px;
  background: linear-gradient(145deg, #f8fbff, #dbeafe);
  border: 1px solid rgba(148, 190, 242, 0.42);
  box-shadow: 0 14px 36px rgba(1, 30, 77, 0.5), inset 0 0 0 1px rgba(255, 255, 255, 0.72);
  animation: badge-pulse 3s ease-in-out infinite;
}

@keyframes badge-pulse {
  0%, 100% { box-shadow: 0 10px 30px rgba(1, 30, 77, 0.42), 0 0 0 0 rgba(82, 147, 226, 0.18); }
  50% { box-shadow: 0 12px 34px rgba(1, 30, 77, 0.5), 0 0 22px 4px rgba(82, 147, 226, 0.16); }
}

.brand-title {
  font-size: clamp(3rem, 5vw, 4.5rem);
  font-weight: 800;
  line-height: 1.05;
  letter-spacing: -2px;
  margin-bottom: 12px;
}

.brand-title-line {
  display: block;
  color: #eceff1;
}

.brand-title-accent {
  background: linear-gradient(135deg, #78aef0 0%, #116ce0 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.brand-tagline {
  font-size: 1.1em;
  color: var(--text-secondary);
  font-weight: 400;
  letter-spacing: 2px;
  margin-bottom: 24px;
}

.brand-meta {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 0.82em;
  color: var(--text-muted);
  padding: 6px 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 100px;
}

.meta-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-success);
  animation: dot-blink 2s ease-in-out infinite;
}

@keyframes dot-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.bottom-line {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--color-primary), var(--color-secondary), transparent);
  opacity: 0.4;
}

/* ────────── 右面板：表单 ────────── */
.panel-form {
  position: relative;
  width: 45%;
  background: var(--surface-1);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: 40px;
  /* 入场动画 */
  opacity: 0;
  transform: translateX(30px);
  transition: opacity 0.6s var(--ease-out-expo), transform 0.6s var(--ease-out-expo);
}

.panel-form.visible {
  opacity: 1;
  transform: translateX(0);
}

/* 左边缘装饰线 */
.panel-form::before {
  content: '';
  position: absolute;
  left: 0;
  top: 10%;
  bottom: 10%;
  width: 1px;
  background: linear-gradient(180deg, transparent, rgba(82, 147, 226, 0.16), rgba(17, 108, 224, 0.12), transparent);
}

.form-wrapper {
  width: 100%;
  max-width: 380px;
}

/* ── 模式切换 ── */
.mode-indicator {
  position: relative;
  display: flex;
  background: rgba(255, 255, 255, 0.04);
  border-radius: 10px;
  padding: 4px;
  margin-bottom: 36px;
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.mode-track {
  position: absolute;
  top: 4px;
  left: 4px;
  width: calc(50% - 4px);
  height: calc(100% - 8px);
  border-radius: 8px;
  transition: transform 0.35s var(--ease-spring);
}

.mode-thumb {
  width: 100%;
  height: 100%;
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(17, 108, 224, 0.18), rgba(82, 147, 226, 0.1));
  border: 1px solid rgba(82, 147, 226, 0.24);
  box-shadow: 0 0 18px rgba(17, 108, 224, 0.12);
}

.mode-thumb.right {
  transform: translateX(100%);
}

.mode-btn {
  position: relative;
  z-index: 1;
  flex: 1;
  padding: 10px 0;
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 0.9em;
  font-weight: 500;
  cursor: pointer;
  transition: color 0.3s;
  font-family: inherit;
}

.mode-btn.active {
  color: var(--text-primary);
}

/* ── 表单头部 ── */
.form-header {
  margin-bottom: 28px;
}

.form-title {
  font-size: 1.6em;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 6px;
  letter-spacing: -0.5px;
}

.form-desc {
  font-size: 0.88em;
  color: var(--text-muted);
}

/* ── 表单字段 ── */
.styled-form {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-hint {
  margin-top: 6px;
  font-size: 0.76em;
  color: var(--text-muted);
  opacity: 0.7;
}

.field-hint--error {
  color: rgba(248, 113, 113, 0.9);
  opacity: 1;
}

/* ── 游客入口 ── */
.guest-entry {
  margin-top: 30px;
}

.divider-or {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 18px;
}

.divider-line {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.08), transparent);
}

.divider-text {
  font-size: 0.72em;
  color: var(--text-muted);
  letter-spacing: 0.1em;
}

.guest-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  height: 44px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.02);
  color: var(--text-secondary);
  font-size: 0.9em;
  font-weight: 500;
  cursor: pointer;
  transition: border-color 0.25s var(--ease-out-expo), background 0.25s var(--ease-out-expo),
    color 0.25s var(--ease-out-expo), box-shadow 0.25s var(--ease-out-expo);
  font-family: inherit;
}

.guest-btn:hover {
  border-color: rgba(82, 147, 226, 0.4);
  background: rgba(82, 147, 226, 0.07);
  color: var(--text-primary);
  box-shadow: 0 0 18px rgba(17, 108, 224, 0.12);
}

.guest-icon {
  font-size: 16px;
}

.guest-hint {
  margin-top: 12px;
  text-align: center;
  font-size: 0.76em;
  color: var(--text-muted);
  opacity: 0.7;
}

.field-group {
  opacity: 0;
  transform: translateY(12px);
  animation: field-in 0.4s var(--ease-out-expo) forwards;
}

.field-1 { animation-delay: 0.15s; }
.field-2 { animation-delay: 0.22s; }
.field-3 { animation-delay: 0.29s; }
.field-4 { animation-delay: 0.36s; }
.field-5 { animation-delay: 0.43s; }
.field-6 { animation-delay: 0.50s; }

@keyframes field-in {
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.field-label {
  display: block;
  font-size: 0.82em;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

/* ── 提交按钮 ── */
.submit-btn {
  position: relative;
  width: 100%;
  height: 46px;
  margin-top: 12px;
  border: none;
  border-radius: 8px;
  background: linear-gradient(135deg, #0951ae, #5293e2);
  color: #fff;
  font-size: 0.95em;
  font-weight: 600;
  letter-spacing: 1px;
  cursor: pointer;
  overflow: hidden;
  transition: transform 0.2s, box-shadow 0.3s;
  font-family: inherit;
}

.submit-btn:not(:disabled):hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 26px rgba(17, 108, 224, 0.34);
}

.submit-btn:not(:disabled):active {
  transform: translateY(0);
}

.submit-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.submit-btn.loading {
  pointer-events: none;
}

.btn-text {
  position: relative;
  z-index: 1;
}

.btn-shimmer {
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.15), transparent);
  animation: btn-shimmer 2.5s ease-in-out infinite;
}

@keyframes btn-shimmer {
  0% { left: -100%; }
  50% { left: 100%; }
  100% { left: 100%; }
}

/* ── 验证码行 ── */
.code-row {
  display: flex;
  gap: 8px;
  width: 100%;
}

.code-row :deep(.el-input) {
  flex: 1;
}

.code-btn {
  white-space: nowrap;
  padding: 0 16px;
  height: 40px;
  border: 1px solid rgba(82, 147, 226, 0.24);
  border-radius: 6px;
  background: rgba(82, 147, 226, 0.08);
  color: var(--color-primary);
  font-size: 0.85em;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
}

.code-btn:hover:not(:disabled) {
  background: rgba(82, 147, 226, 0.14);
  border-color: rgba(82, 147, 226, 0.42);
}

.code-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ── 表单切换动画 ── */
.form-enter-active {
  animation: form-in 0.35s var(--ease-out-expo);
}

.form-leave-active {
  animation: form-out 0.2s var(--ease-out-expo);
}

@keyframes form-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes form-out {
  from {
    opacity: 1;
    transform: translateY(0);
  }
  to {
    opacity: 0;
    transform: translateY(-8px);
  }
}

/* ── 底部 ── */
.form-footer {
  position: absolute;
  bottom: 24px;
  font-size: 0.78em;
  color: var(--text-muted);
  opacity: 0.5;
}

/* ────────── 响应式 ────────── */
@media (max-width: 900px) {
  .login-page {
    flex-direction: column;
    height: auto;
    min-height: 100dvh;
    overflow-x: hidden;
    overflow-y: auto;
  }

  .panel-visual {
    width: 100%;
    height: 35vh;
    min-height: 240px;
  }

  .brand-layer {
    padding: 0 24px;
    margin-top: 0;
    text-align: center;
  }

  .brand-title {
    font-size: 2.4rem;
    letter-spacing: -1px;
  }

  .brand-meta {
    display: none;
  }

  .spectrum-canvas {
    height: 70%;
  }

  .panel-form {
    width: 100%;
    flex: none;
    min-height: 65dvh;
    justify-content: flex-start;
    padding: 24px;
  }

  .panel-form::before {
    display: none;
  }

  .form-wrapper {
    max-width: 420px;
  }

  .form-footer {
    position: static;
    margin-top: 28px;
    padding-bottom: max(8px, env(safe-area-inset-bottom));
  }
}

@media (max-width: 480px) {
  .panel-visual {
    height: 28vh;
    min-height: 200px;
  }

  .brand-title {
    font-size: 1.8rem;
    margin-bottom: 4px;
  }

  .brand-tagline {
    font-size: 0.9em;
    margin-bottom: 0;
  }

  .brand-logo {
    width: 66px;
    height: 66px;
    margin-bottom: 8px;
    border-radius: 16px;
    padding: 4px;
  }

  .panel-form {
    min-height: 72dvh;
    padding: 20px 16px 24px;
  }

  .mode-indicator { margin-bottom: 28px; }
  .form-header { margin-bottom: 22px; }
  .code-row { align-items: stretch; }
  .code-btn { min-height: 44px; padding: 0 12px; }
}
</style>
