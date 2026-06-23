import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getSession, logout as apiLogout, type SessionData } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('session_token'))
  const user = ref<SessionData | null>(null)
  const loading = ref(false)

  const isLoggedIn = computed(() => !!token.value && !!user.value)
  const isAdmin = computed(() => user.value?.is_admin === true)
  const nickname = computed(() => user.value?.ts_nickname || '')

  /** 登录成功后设置 token */
  function setToken(newToken: string) {
    token.value = newToken
    localStorage.setItem('session_token', newToken)
  }

  /** 设置用户信息 */
  function setUser(sessionData: SessionData) {
    user.value = sessionData
  }

  /** 恢复会话（应用启动时调用） */
  async function restoreSession(): Promise<boolean> {
    if (!token.value) return false

    try {
      const res = await getSession(token.value)
      if (res.success && res.session_data) {
        user.value = res.session_data
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

  /** 清除会话 */
  function clearSession() {
    token.value = null
    user.value = null
    localStorage.removeItem('session_token')
  }

  return {
    token,
    user,
    loading,
    isLoggedIn,
    isAdmin,
    nickname,
    setToken,
    setUser,
    restoreSession,
    logout,
    clearSession,
  }
})
