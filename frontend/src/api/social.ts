import apiClient from './client'

export interface Friend {
  qq: string
  ts_nickname: string
  online_status: string
  game?: string
}

export interface FriendsResponse {
  logged_in: boolean
  friends: Friend[]
}

/** 获取好友列表 */
export async function getFriends(): Promise<FriendsResponse> {
  const token = localStorage.getItem('session_token') || ''
  const { data } = await apiClient.get('/friends', { params: { token } })
  return data
}

/** 添加好友 */
export async function addFriend(friendQq: string) {
  const token = localStorage.getItem('session_token') || ''
  const { data } = await apiClient.post('/friends/add', {
    friend_qq: friendQq,
    token,
  })
  return data
}

/** 删除好友 */
export async function deleteFriend(friendQq: string) {
  const token = localStorage.getItem('session_token') || ''
  const { data } = await apiClient.post('/friends/delete', {
    friend_qq: friendQq,
    token,
  })
  return data
}
