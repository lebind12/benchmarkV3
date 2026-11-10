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
      // MP-03 경기 선택 화면. 저장된 목록만 읽고, 수집은 관리자가 조건을 넣고
      // 직접 실행할 때만 일어난다. 이 라우트가 없어 실제 브라우저에서 열 수 없었다.
      path: '/admin/fixtures',
      name: 'preview-fixtures',
      component: () => import('@/features/match-preview/FixtureSelector.vue'),
    },
    {
      // MP-05 섹션 실행 화면. 저장된 경기 선택 → 섹션 실행 → 본문·근거 확인 →
      // 사용자의 승인. 승인은 이 화면에서 사용자가 직접 눌러야만 만들어진다.
      path: '/admin/sections',
      name: 'preview-sections',
      component: () => import('@/features/match-preview/SectionRunView.vue'),
    },
    {
      // MP-09 독자용 프리뷰. 관리자 진입 경로(/admin/preview/:runId)이며, 같은 실행의
      // 진단은 이 화면의 접힌 영역에서 별도 API로 연다. 공개 홈 경로가 아니다.
      path: '/admin/preview/:runId',
      name: 'preview-reader',
      component: () => import('@/features/match-preview/MatchPreviewRoute.vue'),
    },
    {
      // MP-08 운영 지표. 표에서 실행을 고르면 실행 검사 화면으로 이동한다.
      // 연결은 MP-04의 얇은 wrapper가 맡는다(MP-08 파일은 그대로 둔다).
      path: '/admin/metrics',
      name: 'preview-metrics',
      component: () => import('@/features/match-preview/AdminMetricsRoute.vue'),
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/views/NotFoundView.vue'),
    },
  ],
})

export default router
