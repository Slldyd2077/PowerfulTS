import apiClient from './client'

export interface LoginResponse {
  success: boolean
  token?: string
  ts_nickname?: string
  qq_number?: string
  is_admin?: boolean
  error?: string
}

export interface SessionData {
  qq_number: string
  ts_nickname: string
  is_admin: boolean
  steam_id?: string
}

export interface SessionResponse {
  success: boolean
  session_data?: SessionData
  is_admin?: boolean
  error?: string
}

/** 登录 */
export async function login(qqNumber: string, password: string, ip: string = 'unknown'): Promise<LoginResponse> {
  const { data } = await apiClient.post('/auth/login', {
    qq_number: qqNumber,
    password,
    ip,
  })
  return data
}

/** 注册 */
export async function register(qqNumber: string, password: string, tsNickname: string, ip: string = 'unknown') {
  const { data } = await apiClient.post('/auth/register', {
    qq_number: qqNumber,
    password,
    ts_nickname: tsNickname,
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

/** 发送验证码 */
export async function sendCode(qqNumber: string, tsNickname: string) {
  const { data } = await apiClient.post('/auth/send_code', {
    qq_number: qqNumber,
    ts_nickname: tsNickname,
  })
  return data
}

/** 验证验证码 */
export async function verifyCode(qqNumber: string, code: string, tsNickname: string) {
  const { data } = await apiClient.post('/auth/verify_code', {
    qq_number: qqNumber,
    code,
    ts_nickname: tsNickname,
  })
  return data
}

/** 检查 QQ 绑定 */
export async function checkBinding(qqNumber: string) {
  const { data } = await apiClient.get('/auth/check_binding', { params: { qq_number: qqNumber } })
  return data
}

/** 检查 TS 用户是否在线 */
export async function checkOnline(tsNickname: string) {
  const { data } = await apiClient.post('/auth/check_online', { ts_nickname: tsNickname })
  return data
}

/** 检查 TS 昵称绑定状态 */
export async function checkTsBinding(tsNickname: string, qqNumber: string) {
  const { data } = await apiClient.post('/auth/check_ts_binding', {
    ts_nickname: tsNickname,
    qq_number: qqNumber,
  })
  return data
}
