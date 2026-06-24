import apiClient from './client'

export interface Friend {
  ts_nickname: string
  online_status: string
  game?: string
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
