import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  createGuestSession,
  getSession,
  logout as apiLogout,
  type SessionData,
} from '@/api/auth'

const GUEST_STORAGE_KEY = 'guest_session'

export const useAuthStore = defineStore('auth', () => {
  const storedToken = localStorage.getItem('session_token')
  const token = ref<string | null>(storedToken)
  const user = ref<SessionData | null>(null)
  const isGuest = ref<boolean>(
    !!storedToken && localStorage.getItem(GUEST_STORAGE_KEY) === 'true',
  )
  const loading = ref(false)

  // 游客持有后端签发的短时 token；后端按 role 把它限制在网页通话接口。
  const isLoggedIn = computed(() => (!!token.value && !!user.value) || isGuest.value)
  const isAdmin = computed(() => user.value?.is_admin === true)
  const nickname = computed(() => user.value?.ts_nickname || '')
  const role = computed(() => user.value?.role || '')

  /** 登录成功后设置 token */
  function setToken(newToken: string) {
    token.value = newToken
    localStorage.setItem('session_token', newToken)
    // 真实登录必然清除游客态：token 与 guest 互斥
    isGuest.value = false
    localStorage.removeItem(GUEST_STORAGE_KEY)
  }

  /** 设置用户信息 */
  function setUser(sessionData: SessionData) {
    user.value = sessionData
  }

  /** 以服务端分配的临时身份进入；Token 只授权监控与网页通话。 */
  async function enterAsGuest() {
    const session = await createGuestSession()
    if (!session.success || !session.token || !session.ts_nickname) {
      throw new Error(session.error || '无法分配游客身份')
    }
    token.value = session.token
    isGuest.value = true
    user.value = {
      ts_nickname: session.ts_nickname,
      is_admin: false,
      role: 'guest',
    }
    localStorage.setItem('session_token', session.token)
    localStorage.setItem(GUEST_STORAGE_KEY, 'true')
  }

  /** 恢复会话（应用启动时调用） */
  async function restoreSession(): Promise<boolean> {
    // 旧版无 Token 游客态不能再用于网页通话，直接清理并重新申请。
    if (!token.value) {
      localStorage.removeItem(GUEST_STORAGE_KEY)
      isGuest.value = false
      return false
    }

    try {
      const res = await getSession(token.value)
      if (res.success && res.session_data) {
        user.value = res.session_data
        isGuest.value = res.session_data.role === 'guest'
        if (isGuest.value) {
          localStorage.setItem(GUEST_STORAGE_KEY, 'true')
        } else {
          localStorage.removeItem(GUEST_STORAGE_KEY)
        }
        return true
      }
    } catch {
      // 会话无效
    }

    clearSession()
    return false
  }

  /** 登出 */
  async function logout() {
    if (token.value) {
      try {
        await apiLogout(token.value)
      } catch {
        // 静默失败
      }
    }
    clearSession()
  }

  /** 清除会话（含游客态） */
  function clearSession() {
    token.value = null
    user.value = null
    isGuest.value = false
    localStorage.removeItem('session_token')
    localStorage.removeItem(GUEST_STORAGE_KEY)
  }

  return {
    token,
    user,
    isGuest,
    loading,
    isLoggedIn,
    isAdmin,
    nickname,
    role,
    setToken,
    setUser,
    enterAsGuest,
    restoreSession,
    logout,
    clearSession,
  }
})
