import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/',
    component: () => import('@/components/layout/AppLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'Dashboard',
        component: () => import('@/views/DashboardView.vue'),
      },
      {
        path: 'music',
        name: 'Music',
        component: () => import('@/views/MusicView.vue'),
      },
      {
        path: 'voice',
        name: 'Voice',
        component: () => import('@/views/VoiceCallView.vue'),
      },
      {
        path: 'friends',
        name: 'Friends',
        component: () => import('@/views/FriendsView.vue'),
      },
      {
        path: 'steam',
        name: 'Steam',
        component: () => import('@/views/SteamView.vue'),
      },
      {
        path: 'admin',
        name: 'Admin',
        component: () => import('@/views/AdminView.vue'),
        meta: { requiresAdmin: true },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/NotFoundView.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 导航守卫：未登录跳转登录页；游客只可访问管理面板与网页通话。
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('session_token')
  // 游客现在持有短时后端 token；guest_session 只用于前端路由呈现。
  const isGuest = !!token && localStorage.getItem('guest_session') === 'true'
  const authenticated = !!token || isGuest

  if (to.meta.requiresAuth !== false && !authenticated) {
    next({ name: 'Login', query: { redirect: to.fullPath } })
    return
  }
  // 游客可查看面板并使用网页通话；音乐/好友/Steam/管理仍受限。
  if (isGuest && !['Login', 'Dashboard', 'Voice'].includes(String(to.name))) {
    next({ name: 'Dashboard' })
    return
  }
  next()
})

export default router
