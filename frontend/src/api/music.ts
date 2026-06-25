import apiClient from './client'

export interface Song {
  song_id: string
  song_name: string
  artist: string
  album?: string
  song_url?: string
}

export interface MusicSearchResult {
  keyword: string
  count: number
  results: Song[]
}

/** 搜索歌曲 */
export async function searchMusic(keyword: string, limit: number = 10): Promise<MusicSearchResult> {
  const { data } = await apiClient.get('/music/search', { params: { keyword, limit } })
  return data
}

/** 播放歌曲 */
export async function playMusic(songId: string) {
  const token = localStorage.getItem('session_token') || ''
  const { data } = await apiClient.post('/music/play', { song_id: songId, token })
  return data
}

/** 暂停/恢复 */
export async function pauseMusic() {
  const token = localStorage.getItem('session_token') || ''
  const { data } = await apiClient.post('/music/pause', { token })
  return data
}

/** 跳过 */
export async function skipMusic() {
  const token = localStorage.getItem('session_token') || ''
  const { data } = await apiClient.post('/music/skip', { token })
  return data
}

/** 停止 */
export async function stopMusic() {
  const token = localStorage.getItem('session_token') || ''
  const { data } = await apiClient.post('/music/stop', { token })
  return data
}

/** 获取音量 */
export async function getVolume(): Promise<number> {
  const { data } = await apiClient.get('/music/volume')
  return data.volume ?? 50
}

/** 设置音量 */
export async function setVolume(volume: number) {
  const { data } = await apiClient.post('/music/volume', { volume })
  return data
}

/** 呼叫强基计划（音乐电台） */
export async function callRadio() {
  const token = localStorage.getItem('session_token') || ''
  const { data } = await apiClient.post('/music/call_radio', { token })
  return data
}

/** 获取播放队列（TS3AudioBot 当前队列） */
export async function getQueue() {
  const { data } = await apiClient.get('/music/queue')
  return data
}

/** 清空播放队列 */
export async function clearQueue() {
  const token = localStorage.getItem('session_token') || ''
  const { data } = await apiClient.post('/music/clear', { token })
  return data
}

/** 当前播放状态 */
export async function getNowplaying() {
  const { data } = await apiClient.get('/music/nowplaying')
  return data
}

/** 跳转播放进度（秒） */
export async function seekMusic(position: number) {
  const token = localStorage.getItem('session_token') || ''
  const { data } = await apiClient.post('/music/seek', { position: String(Math.floor(position)), token })
  return data
}

/** 搜索网易云音乐（后端调本地网易云 API :3000，取 URL 交 TS3AudioBot 播放） */
export async function searchNetease(keyword: string, limit = 10): Promise<MusicSearchResult> {
  const { data } = await apiClient.get('/music/netease/search', { params: { keyword, limit } })
  return {
    keyword: data.keyword,
    count: data.count,
    results: (data.results || []).map((s: { song_id: string; name: string; artist: string; album?: string }) => ({
      song_id: s.song_id,
      song_name: s.name,
      artist: s.artist,
      album: s.album,
    })),
  }
}

/** 播放网易云音乐（取可播放 URL → TS3AudioBot 标准 play） */
export async function playNetease(songId: string) {
  const token = localStorage.getItem('session_token') || ''
  const { data } = await apiClient.post('/music/netease/play', { song_id: songId, token })
  return data
}

// ───────────────────────── 网易云账号（扫码登录 + 我的歌单）─────────────────────────

/** 生成扫码登录 key */
export async function neteaseQrKey() {
  const { data } = await apiClient.get('/music/netease/qr/key')
  return data
}
/** 生成二维码图片 */
export async function neteaseQrCreate(unikey: string) {
  const { data } = await apiClient.post('/music/netease/qr/create', { unikey })
  return data
}
/** 轮询扫码状态（803=已登录, 带 cookie） */
export async function neteaseQrCheck(unikey: string) {
  const { data } = await apiClient.post('/music/netease/qr/check', { unikey })
  return data
}
/** 绑定网易云 cookie 到当前账号 */
export async function neteaseBind(cookie: string) {
  const { data } = await apiClient.post('/music/netease/bind', { cookie })
  return data
}
/** 我的网易云歌单 */
export async function neteaseMyPlaylists() {
  const { data } = await apiClient.get('/music/netease/my/playlists')
  return data
}
/** 歌单内歌曲（播放清单） */
export async function neteasePlaylistTracks(playlistId: string) {
  const { data } = await apiClient.post('/music/netease/playlist/tracks', { playlist_id: playlistId })
  return data
}
