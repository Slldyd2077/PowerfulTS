import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getSession, logout as apiLogout, type SessionData } from '@/api/auth'

// 游客虚拟用户：不持有真实 token，仅用于访问免鉴权的监控面板
const GUEST_USER: SessionData = { ts_nickname: '游客', is_admin: false, role: 'guest' }
const GUEST_STORAGE_KEY = 'guest_session'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('session_token'))
  const user = ref<SessionData | null>(null)
  const isGuest = ref<boolean>(localStorage.getItem(GUEST_STORAGE_KEY) === 'true')
  const loading = ref(false)

  // 游客也算已登录（让 AppLayout 正常渲染）；游客无 token，受保护接口天然 401
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

  /** 以游客身份进入（仅可访问监控面板，无真实会话） */
  function enterAsGuest() {
    isGuest.value = true
    user.value = GUEST_USER
    localStorage.setItem(GUEST_STORAGE_KEY, 'true')
    // 游客态不带真实 token：token 与 guest 互斥
    token.value = null
    localStorage.removeItem('session_token')
  }

  /** 恢复会话（应用启动时调用） */
  async function restoreSession(): Promise<boolean> {
    // 无 token：若为游客则恢复虚拟用户
    if (!token.value) {
      if (isGuest.value) {
        user.value = GUEST_USER
        return true
      }
      return false
    }

    try {
      const res = await getSession(token.value)
      if (res.success && res.session_data) {
        user.value = res.session_data
        // 真实会话有效：清除可能残留的游客态（自愈多标签页 / 旧数据残留）
        if (isGuest.value) {
          isGuest.value = false
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
