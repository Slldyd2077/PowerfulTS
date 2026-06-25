<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import {
  neteaseQrKey, neteaseQrCreate, neteaseQrCheck, neteaseBind,
  neteaseMyPlaylists, neteasePlaylistTracks,
} from '@/api/music'
import { useMusicStore } from '@/stores/music'
import { ElMessage } from 'element-plus'

const music = useMusicStore()

interface Playlist { id: string; name: string; track_count: number; cover?: string }
interface Track { song_id: string; name: string; artist: string }

const bound = ref(false)
const nickname = ref('')
const qrImg = ref('')
const qrStatus = ref('')
const loading = ref(false)
const playlists = ref<Playlist[]>([])
const tracks = ref<Track[]>([])
const currentPlaylist = ref<Playlist | null>(null)

let unikey = ''
let pollTimer: number | null = null

async function startLogin() {
  loading.value = true
  try {
    const keyRes = await neteaseQrKey()
    unikey = keyRes.unikey
    const qrRes = await neteaseQrCreate(unikey)
    qrImg.value = qrRes.qrimg
    qrStatus.value = '请用网易云 APP 扫码'
    startPolling()
  } catch (e: unknown) {
    ElMessage.error('生成二维码失败')
  } finally {
    loading.value = false
  }
}

function startPolling() {
  stopPolling()
  pollTimer = window.setInterval(async () => {
    try {
      const res = await neteaseQrCheck(unikey)
      if (res.code === 801) qrStatus.value = '等待扫码…'
      else if (res.code === 802) qrStatus.value = '已扫码，请在手机确认'
      else if (res.code === 803) {
        qrStatus.value = '登录成功'
        stopPolling()
        await bindAndLoad(res.cookie)
      }
    } catch {
      // 静默重试
    }
  }, 2000)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

async function bindAndLoad(cookie: string) {
  try {
    const res = await neteaseBind(cookie)
    bound.value = true
    nickname.value = res.nickname
    qrImg.value = ''
    await loadPlaylists()
    ElMessage.success(`已登录: ${res.nickname}`)
  } catch (e: unknown) {
    ElMessage.error('绑定失败，请重试')
  }
}

async function loadPlaylists() {
  try {
    const res = await neteaseMyPlaylists()
    playlists.value = res.playlists || []
  } catch {
    playlists.value = []
  }
}

async function openPlaylist(p: Playlist) {
  currentPlaylist.value = p
  try {
    const res = await neteasePlaylistTracks(p.id)
    tracks.value = res.tracks || []
  } catch {
    tracks.value = []
  }
}

async function playTrack(songId: string, name: string) {
  try {
    await music.play(songId, `${name}`)  // 经 store，记歌名 + source=netease
    ElMessage.success(`加入队列: ${name}`)
  } catch {
    ElMessage.error('播放失败（可能版权限制或队列满）')
  }
}

onMounted(() => {
  // 尝试加载已绑定的歌单（若已登录）
  loadPlaylists().then(() => {
    if (playlists.value.length > 0) bound.value = true
  }).catch(() => { /* 未绑定，忽略 */ })
})

onUnmounted(stopPolling)
</script>

<template>
  <div class="netease-account">
    <!-- 未登录：扫码 -->
    <div v-if="!bound" class="login-area">
      <div v-if="!qrImg" class="login-prompt">
        <span class="login-icon">🎵</span>
        <p class="login-title">登录网易云音乐</p>
        <p class="login-desc">登录后可查看你的歌单 / 收藏<br />并直接点歌到 TS 频道</p>
        <el-button type="primary" :loading="loading" @click="startLogin">扫码登录</el-button>
      </div>
      <div v-else class="qr-area">
        <img :src="qrImg" alt="网易云登录二维码" class="qr-img" />
        <p class="qr-status">{{ qrStatus }}</p>
        <el-button link size="small" @click="startLogin">刷新二维码</el-button>
      </div>
    </div>

    <!-- 已登录：我的歌单 + 播放清单 -->
    <div v-else class="bound-area">
      <div class="bound-header">
        <span class="bound-nick">{{ nickname || '网易云' }}</span>
        <el-button link size="small" @click="bound = false; qrImg = ''">切换账号</el-button>
      </div>

      <!-- 歌单列表 -->
      <div v-if="!currentPlaylist" class="playlists">
        <p class="section-label label-mono">我的歌单</p>
        <div
          v-for="p in playlists"
          :key="p.id"
          class="playlist-item"
          @click="openPlaylist(p)"
        >
          <img v-if="p.cover" :src="p.cover" class="pl-cover" />
          <span v-else class="pl-cover pl-cover--fallback">♪</span>
          <div class="pl-info">
            <span class="pl-name">{{ p.name }}</span>
            <span class="pl-count">{{ p.track_count }} 首</span>
          </div>
        </div>
      </div>

      <!-- 歌单详情（播放清单） -->
      <div v-else class="tracks">
        <div class="tracks-header">
          <el-button link size="small" @click="currentPlaylist = null; tracks = []">← 返回歌单</el-button>
          <span class="tracks-title">{{ currentPlaylist.name }}</span>
        </div>
        <div
          v-for="t in tracks"
          :key="t.song_id"
          class="track-item"
          @click="playTrack(t.song_id, t.name)"
        >
          <span class="track-name">{{ t.name }}</span>
          <span class="track-artist">{{ t.artist }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.netease-account {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.login-area { padding: 8px 0; }
.login-prompt { text-align: center; padding: 16px 0; }
.login-icon { font-size: 2.2em; display: block; margin-bottom: 10px; opacity: 0.7; }
.login-title { font-weight: 600; color: var(--text-secondary); margin: 0 0 6px; }
.login-desc { font-size: 0.8em; color: var(--text-muted); line-height: 1.6; margin: 0 0 14px; }

.qr-area { text-align: center; }
.qr-img { width: 180px; height: 180px; border-radius: 8px; }
.qr-status { font-size: 0.85em; color: var(--color-primary); margin: 8px 0; }

.bound-area { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.bound-header {
  display: flex; justify-content: space-between; align-items: center;
  padding-bottom: 10px; border-bottom: 1px solid var(--border-subtle); margin-bottom: 10px;
}
.bound-nick { font-weight: 600; color: var(--text-primary); font-size: 0.9em; }

.section-label { font-size: 0.6em; color: var(--text-muted); letter-spacing: 0.1em; }

.playlists, .tracks { display: flex; flex-direction: column; gap: 4px; overflow-y: auto; flex: 1; min-height: 0; }

.playlist-item {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 6px; border-radius: var(--radius-sm); cursor: pointer; transition: background 0.15s;
}
.playlist-item:hover { background: var(--surface-4); }
.pl-cover { width: 36px; height: 36px; border-radius: 6px; object-fit: cover; flex-shrink: 0; }
.pl-cover--fallback {
  display: flex; align-items: center; justify-content: center;
  background: rgba(45,212,191,0.1); color: var(--color-primary); font-size: 1em;
}
.pl-info { display: flex; flex-direction: column; min-width: 0; gap: 1px; }
.pl-name { font-size: 0.82em; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pl-count { font-size: 0.66em; color: var(--text-muted); }

.tracks-header {
  display: flex; align-items: center; gap: 8px; padding-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle); margin-bottom: 6px;
}
.tracks-title { font-size: 0.82em; color: var(--text-secondary); font-weight: 600; }
.track-item {
  display: flex; flex-direction: column; gap: 1px;
  padding: 6px 8px; border-radius: var(--radius-sm); cursor: pointer; transition: background 0.15s;
}
.track-item:hover { background: var(--surface-4); }
.track-name { font-size: 0.8em; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.track-artist { font-size: 0.64em; color: var(--text-muted); }
</style>
