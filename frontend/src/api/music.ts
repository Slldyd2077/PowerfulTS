import apiClient from './client'

export interface Song {
  id: string
  name: string
  artist: string
  album?: string
  duration?: number
  coverUrl?: string
  platform?: string
  /** VIP/版权受限：非会员仅能试听片段（上游 fee/pay 标记） */
  vip?: boolean
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
  /** 实际播放时长（试听=片段秒数，完整=duration）；缺失回退 duration */
  effectiveDuration?: number
  position: number
  cover: string
  platform: string
  /** VIP/版权受限（来自搜索元数据回填；上游 currentSong 不自带） */
  vip?: boolean
}

/** 搜索歌曲（botId 指定 bot → 用该 bot 的平台 cookie 搜索） */
export async function searchMusic(q: string, platform?: string, botId?: string): Promise<MusicSearchResult> {
  const params: Record<string, string> = { q }
  if (platform) params.platform = platform
  if (botId) params.botId = botId
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

/** 跳转到队列指定位置播放（0-based 索引，不清空队列） */
export async function playQueueAt(index: number, botId?: string) {
  const { data } = await apiClient.post(`/music/queue/${index}/play`, undefined, botId ? { params: { botId } } : undefined)
  return data
}

/** 拖动调序：移动队列项到新位置（0-based 索引） */
export async function moveQueueItem(from: number, to: number, botId?: string) {
  const { data } = await apiClient.post(`/music/queue/${from}/move`, { to }, botId ? { params: { botId } } : undefined)
  return data
}

/** 共享 bot 给好友（owner，按好友 TS 昵称） */
export async function shareBot(botId: string, friendTsNickname: string) {
  const { data } = await apiClient.post(`/music/bots/${botId}/share`, { friendTsNickname })
  return data
}

/** 撤销共享（owner） */
export async function unshareBot(botId: string, friendAccountId: number) {
  const { data } = await apiClient.delete(`/music/bots/${botId}/share/${friendAccountId}`)
  return data
}

/** 我共享出去的 bot（按 bot 聚合，含共享给谁） */
export interface MyShare {
  botId: string
  sharedTo: { accountId: number; nickname: string }[]
}
export async function getMyShares() {
  const { data } = await apiClient.get('/music/bots/my-shares')
  return data as { shares: MyShare[] }
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
  shared?: boolean       // 好友共享给我的 bot（非自己拥有）
  ownerNickname?: string // 共享 bot 的主人昵称
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

/** bot 实例列表 */
export async function getBots(): Promise<{ bots: BotInfo[] }> {
  const { data } = await apiClient.get('/music/bots')
  return data
}

/** 创建 bot（identity 自动生成，不自动连接） */
export async function createBot(payload: BotCreate): Promise<BotInfo> {
  const { data } = await apiClient.post('/music/bots', payload)
  return data
}

/** 更新 bot 配置（连接类字段需先停止 bot 再改） */
export async function updateBot(botId: string, payload: Partial<BotCreate>) {
  const { data } = await apiClient.put(`/music/bots/${botId}`, payload)
  return data
}

/** 获取 bot 配置（编辑表单预填） */
export async function getBotConfig(botId: string): Promise<Partial<BotCreate>> {
  const { data } = await apiClient.get(`/music/bots/${botId}/config`)
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

/** 播放跟随开关（点击播放时 bot 自动移到你的 TS 频道，默认开启） */
export async function getFollowSetting(): Promise<{ enabled: boolean }> {
  const { data } = await apiClient.get('/music/follow-setting')
  return data
}

/** 更新播放跟随开关 */
export async function setFollowSetting(enabled: boolean): Promise<{ enabled: boolean }> {
  const { data } = await apiClient.put('/music/follow-setting', { enabled })
  return data
}

// ───────────────────────── bot 行为 / 外观设置 ─────────────────────────

/** 全局 bot 行为设置 */
export interface BotSettings {
  /** 频道无人多少分钟后自动断开，0=禁用 */
  idleTimeoutMinutes: number
  /** 频道无人时自动暂停 */
  autoPauseOnEmpty: boolean
}

/** per-bot profile 开关（头像/昵称/描述等 6 字段） */
export interface BotProfile {
  avatarEnabled: boolean
  descriptionEnabled: boolean
  nicknameEnabled: boolean
  awayStatusEnabled: boolean
  channelDescEnabled: boolean
  nowPlayingMsgEnabled: boolean
}

/** 读取全局 bot 行为设置 */
export async function getBotSettings(): Promise<BotSettings> {
  const { data } = await apiClient.get('/music/bot-settings')
  return data
}

/** 更新全局 bot 行为设置（仅传需要改的字段） */
export async function setBotSettings(payload: Partial<BotSettings>): Promise<BotSettings> {
  const { data } = await apiClient.put('/music/bot-settings', payload)
  return data
}

/** 读取 per-bot profile 开关 */
export async function getBotProfile(botId: string): Promise<BotProfile> {
  const { data } = await apiClient.get(`/music/bots/${botId}/profile`)
  return data
}

/** 更新 per-bot profile 开关（仅传需要改的字段；上游立即生效） */
export async function setBotProfile(botId: string, payload: Partial<BotProfile>): Promise<BotProfile> {
  const { data } = await apiClient.put(`/music/bots/${botId}/profile`, payload)
  return data
}

/**
 * 获取 bot 固定头像（Blob）。后端 avatar 端点需 X-Session-Token，
 * <img src> 无法带 header，故用 blob + URL.createObjectURL 在前端展示。
 * 404（未设置固定头像）会 reject，调用方捕获即可。
 */
export async function getBotAvatarBlob(botId: string): Promise<Blob> {
  const { data } = await apiClient.get(`/music/bots/${botId}/avatar`, { responseType: 'blob' })
  return data
}

/** 上传/替换 bot 固定头像（data:image/(png|jpeg|webp);base64,...，≤200KB） */
export async function setBotAvatar(botId: string, dataUrl: string) {
  const { data } = await apiClient.put(`/music/bots/${botId}/avatar`, { dataUrl })
  return data
}

/** 移除 bot 固定头像 */
export async function deleteBotAvatar(botId: string) {
  const { data } = await apiClient.delete(`/music/bots/${botId}/avatar`)
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

/** 用户歌单（自建+收藏，per-bot） */
export async function getMyPlaylists(platform: string, botId?: string): Promise<PlaylistResult> {
  const params: Record<string, string> = { platform }
  if (botId) params.botId = botId
  const { data } = await apiClient.get('/music/my/playlists', { params })
  return data
}

/** 歌单内歌曲（per-bot） */
export async function getPlaylistSongs(playlistId: string, platform: string, botId?: string): Promise<PlaylistResult> {
  const params: Record<string, string> = { platform }
  if (botId) params.botId = botId
  const { data } = await apiClient.get(`/music/my/playlist/${playlistId}/songs`, { params })
  return data
}

/** 每日推荐（per-bot） */
export async function getRecommendSongs(platform: string, botId?: string): Promise<PlaylistResult> {
  const params: Record<string, string> = { platform }
  if (botId) params.botId = botId
  const { data } = await apiClient.get('/music/my/recommend/songs', { params })
  return data
}

/** 私人 FM（per-bot） */
export async function getPersonalFm(platform: string, botId?: string): Promise<PlaylistResult> {
  const params: Record<string, string> = { platform }
  if (botId) params.botId = botId
  const { data } = await apiClient.get('/music/my/personal-fm', { params })
  return data
}

/** B 站热门视频（无需登录，per-bot） */
export async function getBilibiliPopular(limit = 20, botId?: string): Promise<PlaylistResult> {
  const params: Record<string, string> = { limit: String(limit) }
  if (botId) params.botId = botId
  const { data } = await apiClient.get('/music/my/bilibili-popular', { params })
  return data
}

/** 批量入队（整单播放）；后端循环 add 最多 50 首，单独放宽超时到 30s */
export async function enqueueSongs(platform: string | undefined, songs: Song[], botId?: string): Promise<EnqueueResult> {
  const { data } = await apiClient.post('/music/my/enqueue', { platform, songs }, { timeout: 30000, params: botId ? { botId } : undefined })
  return data
}

// ───────────────────────── 平台账号登录 ─────────────────────────

/** 获取某平台登录状态（per-bot：该 bot 的平台登录态） */
export async function getAuthStatus(platform: string, botId?: string) {
  const params: Record<string, string> = { platform }
  if (botId) params.botId = botId
  const { data } = await apiClient.get('/music/auth/status', { params })
  return data
}

/** 获取某平台登录二维码（per-bot；botId 走 query，后端 BotIdQuery 读取） */
export async function getQrcode(platform: string, botId?: string) {
  const { data } = await apiClient.post('/music/auth/qrcode', { platform }, botId ? { params: { botId } } : undefined)
  return data
}

/** 轮询二维码扫码状态（confirmed 时 fork 自动持久化平台 cookie） */
export async function getQrcodeStatus(key: string, platform: string, botId?: string) {
  const params: Record<string, string> = { key, platform }
  if (botId) params.botId = botId
  const { data } = await apiClient.get('/music/auth/qrcode/status', { params })
  return data as { status: 'waiting' | 'scanned' | 'confirmed' | 'expired' }
}

/** 手动设置某平台 cookie（per-bot：绑定到该 bot；botId 走 query） */
export async function setCookie(platform: string, cookie: string, botId?: string) {
  const { data } = await apiClient.post('/music/auth/cookie', { platform, cookie }, botId ? { params: { botId } } : undefined)
  return data
}

/** 退出某平台登录（清除该 bot 的平台 cookie） */
export async function logoutPlatform(platform: string, botId?: string) {
  const params: Record<string, string> = { platform }
  if (botId) params.botId = botId
  const { data } = await apiClient.delete('/music/auth/cookie', { params })
  return data
}
