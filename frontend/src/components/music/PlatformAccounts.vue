<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import QRCode from 'qrcode'
import { getAuthStatus, getQrcode, getQrcodeStatus, setCookie, logoutPlatform } from '@/api/music'
import { ElMessage } from 'element-plus'
import { useMusicStore } from '@/stores/music'

interface PlatformInfo {
  value: string
  label: string
  color: string
  icon: string
}

const platforms: PlatformInfo[] = [
  { value: 'netease', label: '网易云', color: '#e60026', icon: 'N' },
  { value: 'qq', label: 'QQ音乐', color: '#31c27c', icon: 'Q' },
  { value: 'bilibili', label: 'B站', color: '#fb7299', icon: 'B' },
  { value: 'kugou', label: '酷狗', color: '#009afb', icon: 'K' },
]

const music = useMusicStore()
// 登录态已提升到 store（供 MyMusic 置灰判断）；此处 status 为只读视图，模板沿用 status[p.value]
const status = computed(() => music.ownPlatformStatus)
const activePlatform = ref('')
const qrImg = ref('')
const currentQrKey = ref('') // 当前二维码 key（轮询 qrcode/status 用）
const loading = ref(false)
let pollTimer: number | null = null

async function startLogin(p: PlatformInfo) {
  if (!music.ownLibraryBotId) {
    ElMessage.warning('请先在「TS Bot」面板创建一个 Bot，再登录平台账号（平台账号绑定到 Bot 实例）')
    return
  }
  activePlatform.value = p.value
  loading.value = true
  qrImg.value = ''
  stopPolling()
  try {
    const res = await getQrcode(p.value, music.ownLibraryBotId)
    currentQrKey.value = res.key || ''
    // 优先用 API 返回的 qrImg；没有则用 qrUrl 本地生成二维码
    if (res.qrImg) {
      qrImg.value = res.qrImg
    } else if (res.qrUrl) {
      qrImg.value = await QRCode.toDataURL(res.qrUrl, { width: 200, margin: 1 })
    }
    if (qrImg.value) {
      startPolling(p.value)
    } else {
      throw new Error('no qr data')
    }
  } catch {
    ElMessage.error(`${p.label} 二维码获取失败`)
    activePlatform.value = ''
  } finally {
    loading.value = false
  }
}

function startPolling(platform: string) {
  stopPolling()
  pollTimer = window.setInterval(async () => {
    try {
      const key = currentQrKey.value
      if (!key) return
      // 轮询扫码状态：fork 在 confirmed 时自动持久化平台 cookie
      const r = await getQrcodeStatus(key, platform, music.ownLibraryBotId)
      if (r.status === 'confirmed') {
        const auth = await getAuthStatus(platform, music.ownLibraryBotId)
        music.ownPlatformStatus[platform] = { loggedIn: !!auth.loggedIn, nickname: auth.nickname }
        if (music.libraryBotId === music.ownLibraryBotId) {
          music.platformStatus[platform] = { loggedIn: !!auth.loggedIn, nickname: auth.nickname }
        }
        qrImg.value = ''
        currentQrKey.value = ''
        activePlatform.value = ''
        stopPolling()
        const p = platforms.find((x) => x.value === platform)
        ElMessage.success(`${p?.label} 登录成功`)
      } else if (r.status === 'expired') {
        stopPolling()
        qrImg.value = ''
        currentQrKey.value = ''
        activePlatform.value = ''
        ElMessage.warning('二维码已过期，请重新获取')
      }
    } catch {
      // 静默
    }
  }, 2000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function closeQr() {
  activePlatform.value = ''
  qrImg.value = ''
  currentQrKey.value = ''
  stopPolling()
}

// Cookie 登录（扫码失败时的可靠替代：从浏览器导出 cookie 粘贴）
const showCookie = ref(false)
const cookiePlatform = ref('')
const cookieText = ref('')

const cookiePlaceholder = computed(() => {
  switch (cookiePlatform.value) {
    case 'bilibili':
      return 'SESSDATA=xxx; bili_jct=xxx; DedeUserID=xxx'
    case 'qq':
      return 'uin=xxx; qqmusic_key=xxx'
    case 'netease':
      return 'MUSIC_U=xxx; __csrf=xxx'
    default:
      return '粘贴 Cookie 字符串…'
  }
})

function openCookie(p: PlatformInfo) {
  if (!music.ownLibraryBotId) {
    ElMessage.warning('请先在「TS Bot」面板创建一个 Bot，再登录平台账号')
    return
  }
  cookiePlatform.value = p.value
  cookieText.value = ''
  showCookie.value = true
  stopPolling()
}
function closeCookie() {
  showCookie.value = false
  cookieText.value = ''
  cookiePlatform.value = ''
}
async function submitCookie() {
  const text = cookieText.value.trim()
  const plat = cookiePlatform.value
  if (!text || !plat) return
  loading.value = true
  try {
    await setCookie(plat, text, music.ownLibraryBotId)
    // 上游 /api/auth/cookie 总返回 success:true（仅表示已提交），真实登录态以 status.loggedIn 为准
    const res = await getAuthStatus(plat, music.ownLibraryBotId)
    // 写回 store，解除 MyMusic 的置灰
    music.ownPlatformStatus[plat] = { loggedIn: !!res.loggedIn, nickname: res.nickname }
    if (music.libraryBotId === music.ownLibraryBotId) {
      music.platformStatus[plat] = { loggedIn: !!res.loggedIn, nickname: res.nickname }
    }
    if (res.loggedIn) {
      const label = platforms.find((x) => x.value === plat)?.label
      ElMessage.success(`${label} Cookie 登录成功`)
      closeCookie()
    } else {
      ElMessage.warning('Cookie 已提交，但平台验证未通过——请检查 Cookie 是否有效/完整')
    }
  } catch {
    ElMessage.error('Cookie 提交失败')
  } finally {
    loading.value = false
  }
}

async function onLogout(p: PlatformInfo) {
  try {
    await logoutPlatform(p.value, music.ownLibraryBotId)
    // 写回 store，恢复 MyMusic 的置灰
    music.ownPlatformStatus[p.value] = { loggedIn: false }
    if (music.libraryBotId === music.ownLibraryBotId) music.platformStatus[p.value] = { loggedIn: false }
    ElMessage.success(`${p.label} 已退出登录`)
  } catch {
    ElMessage.error(`${p.label} 退出失败`)
  }
}

onMounted(() => music.fetchOwnPlatformStatus())
onUnmounted(stopPolling)
</script>

<template>
  <div class="accounts">
    <div class="accounts-header">
      <span class="title">平台账号</span>
    </div>

    <div class="platform-list">
      <div v-for="p in platforms" :key="p.value" class="platform-row">
        <div class="platform-icon" :style="{ background: p.color + '20', color: p.color }">
          {{ p.icon }}
        </div>
        <div class="platform-info">
          <span class="platform-name">{{ p.label }}</span>
          <span class="platform-status" :class="{ logged: status[p.value]?.loggedIn }">
            {{ status[p.value]?.loggedIn ? `✓ ${status[p.value]?.nickname || '已登录'}` : '未登录' }}
          </span>
        </div>
        <div v-if="!status[p.value]?.loggedIn" class="login-actions">
          <button class="login-btn" @click="startLogin(p)">扫码</button>
          <button class="login-btn login-btn--ghost" @click="openCookie(p)">Cookie</button>
        </div>
        <div v-else class="logout-actions">
          <span class="logged-dot" :style="{ background: p.color }"></span>
          <button class="logout-btn" @click="onLogout(p)">退出</button>
        </div>
      </div>
    </div>

    <!-- 二维码弹窗 -->
    <div v-if="activePlatform && qrImg" class="qr-overlay" @click.self="closeQr">
      <div class="qr-box">
        <img :src="qrImg" class="qr-img" alt="二维码" />
        <p class="qr-tip">用 {{ platforms.find((p) => p.value === activePlatform)?.label }} APP 扫码登录</p>
        <button class="qr-close" @click="closeQr">取消</button>
      </div>
    </div>

    <!-- Cookie 登录弹窗 -->
    <div v-if="showCookie" class="qr-overlay" @click.self="closeCookie">
      <div class="cookie-box">
        <h3 class="cookie-title">{{ platforms.find((p) => p.value === cookiePlatform)?.label }} Cookie 登录</h3>
        <p class="cookie-hint">
          从浏览器登录后导出 Cookie 字符串（如
          <span class="mono">SESSDATA=…; bili_jct=…</span>），粘贴到下方
        </p>
        <textarea v-model="cookieText" class="cookie-input" rows="5" :placeholder="cookiePlaceholder"></textarea>
        <div class="cookie-actions">
          <button class="qr-close" @click="closeCookie">取消</button>
          <button class="cookie-submit" :disabled="!cookieText.trim() || loading" @click="submitCookie">
            {{ loading ? '提交中…' : '提交并验证' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.accounts {
  border-top: 1px solid var(--border-subtle);
  padding-top: 12px;
  min-width: 0;
  max-width: 100%;
}

.accounts-header {
  margin-bottom: 10px;
}
.title {
  font-size: 0.8em;
  font-weight: 600;
  color: var(--text-secondary);
}

.platform-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.platform-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 4px;
  border-radius: var(--radius-sm);
}
.platform-row:hover {
  background: var(--surface-4);
}

.platform-icon {
  width: 30px;
  height: 30px;
  border-radius: 7px;
  display: grid;
  place-items: center;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.82em;
  font-weight: 700;
  flex-shrink: 0;
}

.platform-info {
  display: flex;
  flex-direction: column;
  gap: 1px;
  flex: 1;
  min-width: 0;
}
.platform-name {
  font-size: 0.78em;
  font-weight: 600;
  color: var(--text-primary);
}
.platform-status {
  font-size: 0.64em;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.platform-status.logged {
  color: var(--color-success);
}

.login-btn {
  padding: 3px 10px;
  border: 1px solid var(--color-primary);
  border-radius: 12px;
  background: transparent;
  color: var(--color-primary);
  font-size: 0.68em;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}
.login-btn:hover {
  background: var(--color-primary);
  color: #fff;
}
.login-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}
.login-btn--ghost {
  border-color: var(--border-emphasis);
  color: var(--text-secondary);
}
.login-btn--ghost:hover {
  background: var(--surface-4);
  color: var(--text-primary);
}

/* Cookie 登录弹窗 */
.cookie-box {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 22px;
  width: 380px;
  max-width: 90vw;
}
.cookie-title {
  margin: 0 0 6px;
  font-size: 0.95em;
  font-weight: 600;
  color: var(--text-primary);
}
.cookie-hint {
  margin: 0 0 12px;
  font-size: 0.72em;
  color: var(--text-muted);
  line-height: 1.5;
}
.cookie-hint .mono {
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-secondary);
}
.cookie-input {
  width: 100%;
  box-sizing: border-box;
  background: var(--surface-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  padding: 10px;
  color: var(--text-primary);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.74em;
  resize: vertical;
  outline: none;
}
.cookie-input:focus {
  border-color: var(--color-primary);
}
.cookie-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
}
.cookie-submit {
  padding: 5px 16px;
  border: 0;
  border-radius: 8px;
  background: var(--gradient-brand);
  color: var(--text-inverse);
  font-size: 0.78em;
  font-weight: 600;
  cursor: pointer;
}
.cookie-submit:disabled {
  opacity: 0.5;
  cursor: default;
}

.logged-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.logout-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.logout-btn {
  padding: 3px 11px;
  border: 1px solid var(--border-emphasis);
  border-radius: 10px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.66em;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s;
}

.logout-btn:hover {
  border-color: var(--color-danger);
  color: var(--color-danger);
}

/* 二维码弹窗 */
.qr-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: grid;
  place-items: center;
  z-index: 999;
}

.qr-box {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 24px;
  text-align: center;
}

.qr-img {
  width: 200px;
  height: 200px;
  border-radius: 8px;
}

.qr-tip {
  margin: 12px 0 10px;
  font-size: 0.82em;
  color: var(--text-secondary);
}

.qr-close {
  padding: 4px 16px;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  background: transparent;
  color: var(--text-muted);
  font-size: 0.78em;
  cursor: pointer;
}

/* 移动端：加大登录按钮触摸区、行允许折行 */
@media (max-width: 768px) {
  .login-btn { flex: 1; min-height: 40px; padding: 6px 12px; }
  .platform-row { flex-wrap: wrap; }
  .platform-info { flex-basis: calc(100% - 42px); }
  .login-actions,
  .logout-actions {
    width: 100%;
    padding-left: 40px;
  }
  .logout-actions { justify-content: flex-end; }
  .logout-btn { min-height: 40px; padding: 6px 16px; }
  .cookie-box { width: calc(100vw - 24px); max-width: none; padding: 18px; }
  .cookie-actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .cookie-actions button { min-width: 0; min-height: 42px; }
}
</style>
