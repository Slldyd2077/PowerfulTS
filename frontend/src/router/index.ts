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

// 导航守卫：未登录跳转登录页；游客仅可访问监控面板
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('session_token')
  // 游客判定与真实 token 互斥：持有 token 时绝不视为游客
  const isGuest = !token && localStorage.getItem('guest_session') === 'true'
  const authenticated = !!token || isGuest

  if (to.meta.requiresAuth !== false && !authenticated) {
    next({ name: 'Login', query: { redirect: to.fullPath } })
    return
  }
  // 游客仅可访问监控面板（/）；音乐/好友等受限页重定向回首页
  if (isGuest && to.name !== 'Login' && to.name !== 'Dashboard') {
    next({ name: 'Dashboard' })
    return
  }
  next()
})

export default router
