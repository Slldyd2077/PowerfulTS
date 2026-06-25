<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import QRCode from 'qrcode'
import { getAuthStatus, getQrcode } from '@/api/music'
import { ElMessage } from 'element-plus'

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
]

const status = ref<Record<string, { loggedIn: boolean; nickname?: string }>>({})
const activePlatform = ref('')
const qrImg = ref('')
const loading = ref(false)
let pollTimer: number | null = null

async function fetchAllStatus() {
  for (const p of platforms) {
    try {
      const res = await getAuthStatus(p.value)
      status.value[p.value] = { loggedIn: !!res.loggedIn, nickname: res.nickname }
    } catch {
      status.value[p.value] = { loggedIn: false }
    }
  }
}

async function startLogin(p: PlatformInfo) {
  activePlatform.value = p.value
  loading.value = true
  qrImg.value = ''
  stopPolling()
  try {
    const res = await getQrcode(p.value)
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
      const res = await getAuthStatus(platform)
      if (res.loggedIn) {
        status.value[platform] = { loggedIn: true, nickname: res.nickname }
        qrImg.value = ''
        activePlatform.value = ''
        stopPolling()
        const p = platforms.find((x) => x.value === platform)
        ElMessage.success(`${p?.label} 登录成功`)
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
  stopPolling()
}

onMounted(fetchAllStatus)
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
        <button
          v-if="!status[p.value]?.loggedIn"
          class="login-btn"
          @click="startLogin(p)"
        >
          扫码登录
        </button>
        <span v-else class="logged-dot" :style="{ background: p.color }"></span>
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
  </div>
</template>

<style scoped>
.accounts {
  border-top: 1px solid var(--border-subtle);
  padding-top: 12px;
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

.logged-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
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
</style>
