import apiClient from './client'

export interface IntroTrack {
  /** 显示名（文件名去扩展名） */
  name: string
  /** 文件名（用于拼流式地址） */
  filename: string
}

/** 开屏背景音乐曲目列表（前端随机选曲）。目录为空时返回空数组。 */
export async function getIntroTracks(): Promise<IntroTrack[]> {
  const { data } = await apiClient.get<{ tracks: IntroTrack[] }>('/intro-music')
  return data.tracks ?? []
}

/** 曲目流式地址（直接作 <audio> 的 src，不经 axios；走 vite proxy 同源）。 */
export function introStreamUrl(filename: string): string {
  return `/api/intro-music/${encodeURIComponent(filename)}/stream`
}
