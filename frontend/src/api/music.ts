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
  songId: string
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
export async function playMusic(query: string, queue = false, platform?: string, meta?: Partial<Song>, botId?: string) {
  const payload: Record<string, unknown> = { query, queue }
  if (platform) payload.platform = platform
  if (meta) payload.meta = meta
  const { data } = await apiClient.post('/music/play', payload, botId ? { params: { botId } } : undefined)
  return data
}

/** 暂停 */
export async function pauseMusic(botId?: string) {
  const { data } = await apiClient.post('/music/pause', undefined, botId ? { params: { botId } } : undefined)
  return data
}

/** 恢复 */
export async function resumeMusic(botId?: string) {
  const { data } = await apiClient.post('/music/resume', undefined, botId ? { params: { botId } } : undefined)
  return data
}

/** 下一首 */
export async function nextMusic(botId?: string) {
  const { data } = await apiClient.post('/music/next', undefined, botId ? { params: { botId } } : undefined)
  return data
}

/** 停止 */
export async function stopMusic(botId?: string) {
  const { data } = await apiClient.post('/music/stop', undefined, botId ? { params: { botId } } : undefined)
  return data
}

/** 跳转进度 */
export async function seekMusic(position: number, botId?: string) {
  const { data } = await apiClient.post('/music/seek', { position }, botId ? { params: { botId } } : undefined)
  return data
}

/** 设置音量 */
export async function setVolume(volume: number, botId?: string) {
  const { data } = await apiClient.post('/music/volume', { volume }, botId ? { params: { botId } } : undefined)
  return data
}

/** 播放模式 */
export async function setMode(mode: string, botId?: string) {
  const { data } = await apiClient.post('/music/mode', { mode }, botId ? { params: { botId } } : undefined)
  return data
}

/** 清空队列 */
export async function clearQueue(botId?: string) {
  const { data } = await apiClient.post('/music/clear', undefined, botId ? { params: { botId } } : undefined)
  return data
}

/** 当前播放 */
export async function getNowplaying(botId?: string): Promise<NowPlaying> {
  const { data } = await apiClient.get('/music/nowplaying', botId ? { params: { botId } } : undefined)
  return data
}

/** 播放队列 */
export async function getQueue(botId?: string) {
  const { data } = await apiClient.get('/music/queue', botId ? { params: { botId } } : undefined)
  return data
}

/** 移除队列中指定位置的单曲（0-based 索引） */
export async function removeQueueItem(index: number, botId?: string) {
  const { data } = await apiClient.delete(`/music/queue/${index}`, botId ? { params: { botId } } : undefined)
  return data
}

// ───────────────────────── bot 实例管理 ─────────────────────────

/** bot 实例信息（后端归一化后） */
export interface BotInfo {
  id: string
  name: string
  status: 'connected' | 'offline'
  playing: boolean
  paused: boolean
  default?: boolean
}

/** 创建 bot 的请求体 */
export interface BotCreate {
  name: string
  nickname: string
  serverAddress: string
  serverPort: number
  defaultChannel: string
  channelPassword: string
  serverPassword: string
}

/** bot 列表 */
export async function getBots(): Promise<{ bots: BotInfo[] }> {
  const { data } = await apiClient.get('/music/bots')
  return data
}

/** 创建 bot（identity 自动生成，不自动连接） */
export async function createBot(payload: BotCreate): Promise<BotInfo> {
  const { data } = await apiClient.post('/music/bots', payload)
  return data
}

/** 启动 bot（连接 TS） */
export async function startBot(botId: string) {
  const { data } = await apiClient.post(`/music/bots/${botId}/start`)
  return data
}

/** 停止 bot */
export async function stopBot(botId: string) {
  const { data } = await apiClient.post(`/music/bots/${botId}/stop`)
  return data
}

/** 删除 bot */
export async function deleteBot(botId: string) {
  const { data } = await apiClient.delete(`/music/bots/${botId}`)
  return data
}

// ───────────────────────── 我的音乐 / 歌单 ─────────────────────────

/** 歌单 */
export interface Playlist {
  id: string
  name: string
  coverUrl?: string
  songCount?: number
  platform?: string
}

/** 歌单/列表类接口的统一返回（承载 unsupported 语义：501=该平台不支持此功能） */
export interface PlaylistResult {
  ok: boolean
  unsupported?: boolean
  data: Playlist[] | Song[]
  error?: string
}

/** 批量入队结果 */
export interface EnqueueResult {
  ok: boolean
  enqueued: number
  failed: number
}

/** 用户歌单（自建+收藏） */
export async function getMyPlaylists(platform: string): Promise<PlaylistResult> {
  const { data } = await apiClient.get('/music/my/playlists', { params: { platform } })
  return data
}

/** 歌单内歌曲 */
export async function getPlaylistSongs(playlistId: string, platform: string): Promise<PlaylistResult> {
  const { data } = await apiClient.get(`/music/my/playlist/${playlistId}/songs`, { params: { platform } })
  return data
}

/** 每日推荐 */
export async function getRecommendSongs(platform: string): Promise<PlaylistResult> {
  const { data } = await apiClient.get('/music/my/recommend/songs', { params: { platform } })
  return data
}

/** 私人 FM */
export async function getPersonalFm(platform: string): Promise<PlaylistResult> {
  const { data } = await apiClient.get('/music/my/personal-fm', { params: { platform } })
  return data
}

/** B 站热门视频（无需登录） */
export async function getBilibiliPopular(limit = 20): Promise<PlaylistResult> {
  const { data } = await apiClient.get('/music/my/bilibili-popular', { params: { limit } })
  return data
}

/** 批量入队（整单播放）；后端循环 add 最多 50 首，单独放宽超时到 30s */
export async function enqueueSongs(platform: string | undefined, songs: Song[], botId?: string): Promise<EnqueueResult> {
  const { data } = await apiClient.post('/music/my/enqueue', { platform, songs }, { timeout: 30000, params: botId ? { botId } : undefined })
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
