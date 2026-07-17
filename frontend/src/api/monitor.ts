import apiClient from './client'

export interface OnlineUser {
  nickname: string
  game: string
  online_time: number
  channel: string
}

export interface StatsData {
  running_time: number
  total_users: number
  online_users: number
  gaming_users: number
  games: Record<string, number>
  online_list: OnlineUser[]
  server_host?: string
  server_port?: number
  last_update?: string
  monitor_running?: boolean
  mining_users?: string[]
  mining_pools?: Record<string, string[]>
}

export interface ChannelData {
  channels: ChannelInfo[]
  count: number
}

export interface ChannelInfo {
  cid: number
  pid: number
  channel_order: number
  name: string
  depth: number
}

/** 获取 TS3 服务器统计 */
export async function getStats(): Promise<StatsData> {
  const { data } = await apiClient.get('/stats')
  return data
}

/** 获取频道列表 */
export async function getChannels(): Promise<ChannelData> {
  const { data } = await apiClient.get('/channels')
  return data
}
