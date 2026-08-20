import apiClient from './client'

export interface LoginResponse {
  success: boolean
  token?: string
  ts_nickname?: string
  is_admin?: boolean
  error?: string
}

export interface GuestSessionResponse extends LoginResponse {
  role: 'guest'
  expires_in: number
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

export interface RegisterOptions {
  code?: string
  ip?: string
  inviteToken?: string
  qqNumber?: string
}

export interface InvitationInspection {
  valid: boolean
  inviter_nickname?: string
  expires_at?: string
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

/** 分配一个短时、仅限网页通话的游客身份。昵称由后端生成，不能冒用成员。 */
export async function createGuestSession(): Promise<GuestSessionResponse> {
  const { data } = await apiClient.post('/auth/guest')
  return data
}

/** 注册。普通注册使用 TS 验证码，邀请注册改用 inviteToken + qqNumber。 */
export async function register(
  tsNickname: string,
  password: string,
  options: RegisterOptions,
) {
  const payload: Record<string, string> = {
    ts_nickname: tsNickname,
    password,
    ip: options.ip ?? 'unknown',
  }
  if (options.code) payload.code = options.code
  if (options.inviteToken) payload.invite_token = options.inviteToken
  if (options.qqNumber) payload.qq_number = options.qqNumber

  const { data } = await apiClient.post('/auth/register', {
    ...payload,
  })
  return data
}

/** 在提交注册前检查邀请是否仍有效；token 仅放在请求体，避免进入访问日志。 */
export async function inspectInvitation(token: string): Promise<InvitationInspection> {
  const { data } = await apiClient.post('/auth/invitations/inspect', { token })
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
