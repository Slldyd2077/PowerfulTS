<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { login as apiLogin, register as apiRegister, getClientIp, sendCode, checkBinding, checkOnline, verifyCode } from '@/api/auth'
import { ElMessage } from 'element-plus'

const router = useRouter()
const auth = useAuthStore()

const mode = ref<'login' | 'register'>('login')
const loading = ref(false)
const formVisible = ref(false)

// 登录表单
const loginForm = ref({ qq: '', password: '' })

// 注册表单
const registerForm = ref({
  qq: '',
  password: '',
  confirmPassword: '',
  tsNickname: '',
  code: '',
})
const codeSent = ref(false)
const codeCountdown = ref(0)

const canLogin = computed(() => loginForm.value.qq.trim() && loginForm.value.password.trim())
const canRegister = computed(() =>
  registerForm.value.qq.trim() &&
  registerForm.value.password.trim() &&
  registerForm.value.password === registerForm.value.confirmPassword &&
  registerForm.value.tsNickname.trim(),
)

// ── 音频频谱可视化 ──
const canvasRef = ref<HTMLCanvasElement | null>(null)
let animFrameId = 0
let bars: number[] = []

function initVisualizer() {
  const canvas = canvasRef.value
  if (!canvas) return

  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const BAR_COUNT = 48
  bars = Array.from({ length: BAR_COUNT }, () => Math.random() * 0.3 + 0.1)

  const resize = () => {
    const rect = canvas.getBoundingClientRect()
    canvas.width = rect.width * devicePixelRatio
    canvas.height = rect.height * devicePixelRatio
    ctx.scale(devicePixelRatio, devicePixelRatio)
  }

  resize()
  window.addEventListener('resize', resize)

  const draw = () => {
    const w = canvas.getBoundingClientRect().width
    const h = canvas.getBoundingClientRect().height

    ctx.clearRect(0, 0, w, h)

    const gap = 3
    const barWidth = (w - gap * (BAR_COUNT - 1)) / BAR_COUNT

    for (let i = 0; i < BAR_COUNT; i++) {
      // 有机的随机运动
      const target = 0.08 + Math.random() * 0.55
      bars[i] += (target - bars[i]) * 0.08 + (Math.random() - 0.5) * 0.02
      bars[i] = Math.max(0.04, Math.min(0.85, bars[i]))

      const barHeight = bars[i] * h * 0.7
      const x = i * (barWidth + gap)
      const y = h - barHeight

      // 渐变色条
      const gradient = ctx.createLinearGradient(x, y, x, h)
      gradient.addColorStop(0, 'rgba(0, 229, 255, 0.9)')
      gradient.addColorStop(0.5, 'rgba(0, 229, 255, 0.4)')
      gradient.addColorStop(1, 'rgba(179, 136, 255, 0.15)')

      ctx.beginPath()
      ctx.roundRect(x, y, barWidth, barHeight, 2)
      ctx.fillStyle = gradient
      ctx.fill()

      // 顶部高亮点
      ctx.beginPath()
      ctx.roundRect(x, y, barWidth, Math.min(3, barHeight), 2)
      ctx.fillStyle = 'rgba(0, 229, 255, 1)'
      ctx.fill()
    }

    animFrameId = requestAnimationFrame(draw)
  }

  draw()

  onUnmounted(() => {
    cancelAnimationFrame(animFrameId)
    window.removeEventListener('resize', resize)
  })
}

// ── 入场动画 ──
onMounted(() => {
  requestAnimationFrame(() => {
    formVisible.value = true
  })
  initVisualizer()
})

/** 登录 */
async function handleLogin() {
  if (!canLogin.value) return
  loading.value = true
  try {
    const ip = await getClientIp()
    const result = await apiLogin(loginForm.value.qq, loginForm.value.password, ip)
    if (result.success && result.token) {
      auth.setToken(result.token)
      auth.setUser({
        qq_number: result.qq_number || '',
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
  if (!registerForm.value.qq.trim() || !registerForm.value.tsNickname.trim()) {
    ElMessage.warning('请先填写 QQ 号和 TS 昵称')
    return
  }

  try {
    const bind = await checkBinding(registerForm.value.qq)
    if (bind.bound) {
      ElMessage.info('该 QQ 已绑定，请直接登录')
      mode.value = 'login'
      loginForm.value.qq = registerForm.value.qq
      return
    }

    const onlineRes = await checkOnline(registerForm.value.tsNickname)

    await sendCode(registerForm.value.qq, registerForm.value.tsNickname)
    ElMessage.success(onlineRes.online ? '验证码已发送到 QQ' : '验证码已发送（你当前不在线，点歌时需要 TS 在线）')
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
  if (!canRegister.value) return
  loading.value = true
  try {
    if (registerForm.value.code) {
      await verifyCode(registerForm.value.qq, registerForm.value.code, registerForm.value.tsNickname)
    }

    const ip = await getClientIp()
    const res = await apiRegister(
      registerForm.value.qq,
      registerForm.value.password,
      registerForm.value.tsNickname,
      ip,
    )
    if (res.success) {
      ElMessage.success('注册成功，请登录')
      mode.value = 'login'
      loginForm.value.qq = registerForm.value.qq
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

      <!-- 品牌层 -->
      <div class="brand-layer">
        <div class="brand-badge">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
            <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
            <line x1="12" y1="19" x2="12" y2="23"/>
            <line x1="8" y1="23" x2="16" y2="23"/>
          </svg>
        </div>
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
                <label class="field-label">QQ 号</label>
                <el-input
                  v-model="loginForm.qq"
                  placeholder="请输入 QQ 号"
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
          </div>

          <!-- 注册表单 -->
          <div v-else key="register" class="form-body">
            <div class="form-header">
              <h2 class="form-title">创建账号</h2>
              <p class="form-desc">绑定 QQ 和 TS 昵称以开始使用</p>
            </div>

            <el-form @submit.prevent="handleRegister" label-position="top" class="styled-form">
              <div class="field-group field-1">
                <label class="field-label">QQ 号</label>
                <el-input v-model="registerForm.qq" placeholder="请输入 QQ 号" size="large" />
              </div>
              <div class="field-group field-2">
                <label class="field-label">TS 昵称</label>
                <el-input v-model="registerForm.tsNickname" placeholder="TS 服务器中的昵称" size="large" />
              </div>
              <div class="field-group field-3">
                <label class="field-label">密码</label>
                <el-input v-model="registerForm.password" type="password" placeholder="设置密码" size="large" show-password />
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
                <label class="field-label">验证码（发送到 QQ 私信）</label>
                <div class="code-row">
                  <el-input v-model="registerForm.code" placeholder="6 位验证码" size="large" maxlength="6" />
                  <button
                    class="code-btn"
                    :disabled="codeCountdown > 0 || !registerForm.qq.trim() || !registerForm.tsNickname.trim()"
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
  background: linear-gradient(160deg, #060610 0%, #0a0a20 40%, #0d0d2b 100%);
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

/* 品牌层 */
.brand-layer {
  position: relative;
  z-index: 2;
  text-align: left;
  padding: 0 48px;
  margin-top: -8vh;
}

.brand-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: rgba(0, 229, 255, 0.1);
  border: 1px solid rgba(0, 229, 255, 0.2);
  color: var(--color-primary);
  margin-bottom: 28px;
  animation: badge-pulse 3s ease-in-out infinite;
}

@keyframes badge-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(0, 229, 255, 0.2); }
  50% { box-shadow: 0 0 20px 4px rgba(0, 229, 255, 0.1); }
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
  background: linear-gradient(135deg, #00e5ff 0%, #b388ff 100%);
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
  background: linear-gradient(180deg, transparent, rgba(0, 229, 255, 0.15), rgba(179, 136, 255, 0.15), transparent);
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
  background: linear-gradient(135deg, rgba(0, 229, 255, 0.15), rgba(179, 136, 255, 0.15));
  border: 1px solid rgba(0, 229, 255, 0.2);
  box-shadow: 0 0 16px rgba(0, 229, 255, 0.08);
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
  background: linear-gradient(135deg, #0097a7, #7c4dff);
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
  box-shadow: 0 4px 24px rgba(0, 229, 255, 0.25);
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
  border: 1px solid rgba(0, 229, 255, 0.2);
  border-radius: 6px;
  background: rgba(0, 229, 255, 0.06);
  color: var(--color-primary);
  font-size: 0.85em;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
}

.code-btn:hover:not(:disabled) {
  background: rgba(0, 229, 255, 0.12);
  border-color: rgba(0, 229, 255, 0.35);
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
    flex: 1;
    padding: 24px;
  }

  .panel-form::before {
    display: none;
  }

  .form-wrapper {
    max-width: 420px;
  }
}

@media (max-width: 480px) {
  .panel-visual {
    height: 28vh;
    min-height: 200px;
  }

  .brand-title {
    font-size: 1.8rem;
  }

  .brand-tagline {
    font-size: 0.9em;
  }

  .panel-form {
    padding: 20px 16px;
  }
}
</style>
