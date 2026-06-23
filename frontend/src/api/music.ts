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
