import axios from 'axios'
import type { AxiosInstance } from 'axios'

const apiClient: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截：自动注入 token
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('session_token')
  if (token) {
    config.headers['X-Session-Token'] = token
  }
  return config
})

// 响应拦截：401 自动跳转登录
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('session_token')
      localStorage.removeItem('guest_session')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  },
)

export default apiClient
