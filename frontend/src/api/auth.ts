import apiClient from './client'

export interface LoginResponse {
  success: boolean
  token?: string
  ts_nickname?: string
  is_admin?: boolean
  error?: string
}

export interface SessionData {
  ts_nickname: string
  is_admin: boolean
  role?: string
}

export interface SessionResponse {
  success: boolean
  session_data?: SessionData
  is_admin?: boolean
  error?: string
}

/** 登录（TS 昵称 + 密码） */
export async function login(tsNickname: string, password: string, ip: string = 'unknown'): Promise<LoginResponse> {
  const { data } = await apiClient.post('/auth/login', {
    ts_nickname: tsNickname,
    password,
    ip,
  })
  return data
}

/** 注册（TS 昵称 + 密码 + 验证码；需先 sendCode 在 TS 私聊收码） */
export async function register(tsNickname: string, password: string, code: string, ip: string = 'unknown') {
  const { data } = await apiClient.post('/auth/register', {
    ts_nickname: tsNickname,
    password,
    code,
    ip,
  })
  return data
}

/** 获取当前会话 */
export async function getSession(token: string): Promise<SessionResponse> {
  const { data } = await apiClient.post('/auth/get_session', { token })
  return data
}

/** 登出 */
export async function logout(token: string) {
  const { data } = await apiClient.post('/auth/logout', { token })
  return data
}

/** 获取客户端 IP */
export async function getClientIp(): Promise<string> {
  const { data } = await apiClient.get('/auth/get_ip')
  return data.ip || 'unknown'
}

/** 发送验证码（向在线 TS 客户端私聊下发） */
export async function sendCode(tsNickname: string) {
  const { data } = await apiClient.post('/auth/send_code', { ts_nickname: tsNickname })
  return data
}

/** 校验验证码（可选；register 已内置校验） */
export async function verifyCode(tsNickname: string, code: string) {
  const { data } = await apiClient.post('/auth/verify_code', { ts_nickname: tsNickname, code })
  return data
}

/** 检查昵称是否已注册 */
export async function checkBinding(tsNickname: string) {
  const { data } = await apiClient.get('/auth/check_binding', { params: { ts_nickname: tsNickname } })
  return data
}

/** 检查 TS 用户是否在线 */
export async function checkOnline(tsNickname: string) {
  const { data } = await apiClient.post('/auth/check_online', { ts_nickname: tsNickname })
  return data
}
