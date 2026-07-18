import apiClient from './client'

/** Steam 在线状态视图（state 文本与 TS 监控对齐：游戏中/在线/离线/忙碌/离开…） */
export interface SteamStatus {
  online: boolean
  state: string
  current_game: string | null
  persona_state?: number
}

/** 账号的 Steam 绑定摘要 */
export interface SteamBinding {
  bound: boolean
  steamid64: string | null
  persona: string | null
  avatar_url: string | null
  profile_url: string | null
  bound_at: string | null
}

/** GET /steam/me 返回（绑定信息 + 实时状态） */
export interface SteamMeResponse extends SteamBinding {
  status: SteamStatus | null
}

/** 游戏库条目 */
export interface SteamGame {
  appid: number
  name: string
  playtime_forever_hours: number
  playtime_2weeks_hours: number
  icon_url: string
}

/** 好友 Steam 状态条目 */
export interface SteamFriend {
  account_id: number
  ts_nickname: string
  bound: boolean
  persona: string | null
  avatar_url: string | null
  status: SteamStatus | null
}

/** 共同游戏条目 */
export interface CommonGame {
  appid: number
  name: string
  my_hours: number
  friend_hours: number
  icon_url: string
}

/** 排行榜条目 */
export interface LeaderboardEntry {
  account_id: number
  ts_nickname: string
  persona: string | null
  avatar_url: string | null
  hours: number
  game_count?: number
}

/** 获取 Steam OpenID 跳转 URL */
export async function getSteamAuthUrl(): Promise<{ url: string }> {
  const { data } = await apiClient.post('/steam/auth/url')
  return data
}

/** 解绑 Steam */
export async function unbindSteam(): Promise<{ success: boolean }> {
  const { data } = await apiClient.delete('/steam/auth')
  return data
}

/** 我的 Steam 概况（绑定信息 + 在线状态/当前游戏） */
export async function getSteamMe(): Promise<SteamMeResponse> {
  const { data } = await apiClient.get('/steam/me')
  return data
}

/** 我的游戏库（按时长降序） */
export async function getMySteamGames(): Promise<{ games: SteamGame[] }> {
  const { data } = await apiClient.get('/steam/me/games')
  return data
}

/** 好友的 Steam 在线状态列表 */
export async function getSteamFriends(): Promise<{ friends: SteamFriend[] }> {
  const { data } = await apiClient.get('/steam/friends')
  return data
}

/** 与某好友的共同游戏 */
export async function getCommonGames(friendAccountId: number): Promise<{
  friend_nickname: string
  friend_persona: string | null
  common_games: CommonGame[]
  total: number
}> {
  const { data } = await apiClient.get(`/steam/friends/${friendAccountId}/common-games`)
  return data
}

/** 全服 Steam 玩家排行；game=appid 时按单游戏时长 */
export async function getSteamLeaderboard(game?: string): Promise<{
  entries: LeaderboardEntry[]
  game: string | null
}> {
  const { data } = await apiClient.get('/steam/leaderboard', { params: game ? { game } : {} })
  return data
}
