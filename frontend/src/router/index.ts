import { createRouter, createWebHistory } from 'vue-router'

// UI 리다이렉트는 편의일 뿐 권한이 아니다. 실제 접근 제어는 서버의
// require_preview_admin이 한다.
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/admin/runs' },
    {
      path: '/admin/login',
      name: 'admin-login',
      component: () => import('@/views/AdminLoginView.vue'),
    },
    {
      path: '/admin/runs',
      name: 'preview-runs',
      component: () => import('@/features/match-preview/PreviewRunsView.vue'),
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/views/NotFoundView.vue'),
    },
  ],
})

export default router
