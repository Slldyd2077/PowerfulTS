import apiClient from './client'

export interface Friend {
  ts_nickname: string
  online_status: string
  game?: string
  mutual?: boolean
}

export interface FriendsResponse {
  logged_in: boolean
  friends: Friend[]
}

/** 获取好友列表（含在线状态） */
export async function getFriends(): Promise<FriendsResponse> {
  const { data } = await apiClient.get('/friends')
  return data
}

/** 添加好友（按 TS 昵称） */
export async function addFriend(friendTsNickname: string) {
  const { data } = await apiClient.post('/friends/add', { friend_ts_nickname: friendTsNickname })
  return data
}

/** 删除好友（按 TS 昵称） */
export async function deleteFriend(friendTsNickname: string) {
  const { data } = await apiClient.post('/friends/delete', { friend_ts_nickname: friendTsNickname })
  return data
}

export interface FriendSettings {
  qq_number: string
  notify_friends_online: boolean
}

/** 获取好友上线提醒设置（QQ 绑定 + 开关） */
export async function getFriendSettings(): Promise<FriendSettings> {
  const { data } = await apiClient.get('/friends/settings')
  return data
}

/** 更新好友上线提醒设置 */
export async function updateFriendSettings(payload: Partial<FriendSettings>) {
  const { data } = await apiClient.post('/friends/settings', payload)
  return data
}
