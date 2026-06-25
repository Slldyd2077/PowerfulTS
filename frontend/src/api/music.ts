import apiClient from './client'

export interface Song {
  id: string
  name: string
  artist: string
  album?: string
  duration?: number
  coverUrl?: string
  platform?: string
}

export interface MusicSearchResult {
  count: number
  results: Song[]
}

export interface NowPlaying {
  playing: boolean
  paused: boolean
  volume: number
  playMode: string
  title: string
  artist: string
  album: string
  duration: number
  position: number
  cover: string
  platform: string
}

/** 搜索歌曲（可指定平台） */
export async function searchMusic(q: string, platform?: string): Promise<MusicSearchResult> {
  const params: Record<string, string> = { q }
  if (platform) params.platform = platform
  const { data } = await apiClient.get('/music/search', { params })
  return data
}

/** 播放（query=歌名 或 'id:xxx'） */
export async function playMusic(query: string, queue = false, platform?: string) {
  const payload: Record<string, unknown> = { query, queue }
  if (platform) payload.platform = platform
  const { data } = await apiClient.post('/music/play', payload)
  return data
}

/** 暂停 */
export async function pauseMusic() {
  const { data } = await apiClient.post('/music/pause')
  return data
}

/** 恢复 */
export async function resumeMusic() {
  const { data } = await apiClient.post('/music/resume')
  return data
}

/** 下一首 */
export async function nextMusic() {
  const { data } = await apiClient.post('/music/next')
  return data
}

/** 停止 */
export async function stopMusic() {
  const { data } = await apiClient.post('/music/stop')
  return data
}

/** 跳转进度 */
export async function seekMusic(position: number) {
  const { data } = await apiClient.post('/music/seek', { position })
  return data
}

/** 设置音量 */
export async function setVolume(volume: number) {
  const { data } = await apiClient.post('/music/volume', { volume })
  return data
}

/** 播放模式 */
export async function setMode(mode: string) {
  const { data } = await apiClient.post('/music/mode', { mode })
  return data
}

/** 清空队列 */
export async function clearQueue() {
  const { data } = await apiClient.post('/music/clear')
  return data
}

/** 当前播放 */
export async function getNowplaying(): Promise<NowPlaying> {
  const { data } = await apiClient.get('/music/nowplaying')
  return data
}

/** 播放队列 */
export async function getQueue() {
  const { data } = await apiClient.get('/music/queue')
  return data
}

// ───────────────────────── 平台账号登录 ─────────────────────────

/** 获取某平台登录状态 */
export async function getAuthStatus(platform: string) {
  const { data } = await apiClient.get('/music/auth/status', { params: { platform } })
  return data
}

/** 获取某平台登录二维码 */
export async function getQrcode(platform: string) {
  const { data } = await apiClient.post('/music/auth/qrcode', { platform })
  return data
}

/** 手动设置某平台 cookie */
export async function setCookie(platform: string, cookie: string) {
  const { data } = await apiClient.post('/music/auth/cookie', { platform, cookie })
  return data
}
