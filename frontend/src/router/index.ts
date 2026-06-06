import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { defineComponent, h } from 'vue'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import {
  BROADCAST_FIXTURE_QUERY_PARAM,
  BROADCAST_LEGACY_FIXTURE_QUERY_PARAM,
} from '@/lib/broadcastQuery'
import { useAuthStore } from '@/stores/auth'

const PlaceholderView = {
  template: '<main style="padding:24px"><h2>{{ title }}</h2><p>(placeholder)</p></main>',
  props: ['title'],
}

const NotFound = defineComponent({
  name: 'NotFound',
  setup() {
    return () =>
      h(
        'div',
        { 'data-testid': 'not-found' },
        '존재하지 않는 경기입니다 → 메인으로',
      )
  },
})

type BroadcastRouteTarget = {
  params: Record<string, unknown>
  query: Record<string, unknown>
}

function queryValues(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.flatMap((item) => queryValues(item))
  }

  if (typeof value === 'string' && value.length > 0) return [value]
  if (typeof value === 'number' || typeof value === 'boolean') return [String(value)]
  return []
}

function buildBroadcastPageUrl(fileName: string, to: BroadcastRouteTarget) {
  const query = new URLSearchParams()
  const fixture =
    to.params.externalId
    ?? queryValues(to.query[BROADCAST_FIXTURE_QUERY_PARAM])[0]
    ?? queryValues(to.query[BROADCAST_LEGACY_FIXTURE_QUERY_PARAM])[0]

  if (fixture != null) {
    query.set(BROADCAST_FIXTURE_QUERY_PARAM, String(fixture))
  }

  Object.entries(to.query).forEach(([key, value]) => {
    if (
      key === BROADCAST_FIXTURE_QUERY_PARAM
      || key === BROADCAST_LEGACY_FIXTURE_QUERY_PARAM
    ) {
      return
    }

    queryValues(value).forEach((item) => {
      query.append(key, item)
    })
  })

  const suffix = query.toString()
  return `/${fileName}${suffix ? `?${suffix}` : ''}`
}

function openBroadcast(to: BroadcastRouteTarget) {
  if (!isAdminRouteAllowed()) return { name: 'not-found' }
  if (typeof window === 'undefined') return false
  window.location.assign(buildBroadcastPageUrl('broadcast.html', to))
  return false
}

function openBroadcastProgram(to: BroadcastRouteTarget) {
  if (!isAdminRouteAllowed()) return { name: 'not-found' }
  if (typeof window === 'undefined') return false
  window.location.assign(buildBroadcastPageUrl('broadcast-program.html', to))
  return false
}

function isAdminRouteAllowed() {
  const auth = useAuthStore()
  auth.hydrateFromMock()
  return auth.isAdmin
}

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: DefaultLayout,
    children: [
      { path: '', name: 'home', component: () => import('@/views/ui-review/UiReviewHomeView.vue') },
      { path: 'fixtures', name: 'fixtures', component: () => import('@/views/ui-review/UiReviewFixturesView.vue') },
      {
        path: 'fixtures/:externalId(\\d+)',
        name: 'fixture-detail',
        component: () => import('@/views/ui-review/UiReviewFixturePreviewView.vue'),
        meta: { title: '매치' },
      },
      { path: 'standings', name: 'standings', component: () => import('@/views/StandingsView.vue') },
      { path: 'teams', name: 'teams', component: () => import('@/views/ui-review/UiReviewTeamsView.vue') },
      { path: 'teams/:slug', name: 'team-detail', component: () => import('@/views/TeamDetailView.vue') },
      { path: 'players', name: 'players', component: () => import('@/views/ui-review/UiReviewPlayersView.vue') },
      { path: 'players/:slug', name: 'player-detail', component: () => import('@/views/PlayerDetailView.vue') },
      { path: 'stats', name: 'stats', component: () => import('@/views/ui-review/UiReviewStatsView.vue') },
      { path: 'news', name: 'news', component: () => import('@/views/ui-review/UiReviewNewsView.vue') },
      { path: 'ui-review', redirect: '/ui-review/home' },
      {
        path: 'ui-review/home',
        name: 'ui-review-home',
        component: () => import('@/views/ui-review/UiReviewHomeView.vue'),
        meta: { title: '홈 비교' },
      },
      {
        path: 'ui-review/players',
        name: 'ui-review-players',
        component: () => import('@/views/ui-review/UiReviewPlayersView.vue'),
        meta: { title: '선수 후보' },
      },
      {
        path: 'ui-review/teams',
        name: 'ui-review-teams',
        component: () => import('@/views/ui-review/UiReviewTeamsView.vue'),
        meta: { title: '팀 후보' },
      },
      {
        path: 'ui-review/stats',
        name: 'ui-review-stats',
        component: () => import('@/views/ui-review/UiReviewStatsView.vue'),
        meta: { title: '스탯 후보' },
      },
      {
        path: 'ui-review/fixtures',
        name: 'ui-review-fixtures',
        component: () => import('@/views/ui-review/UiReviewFixturesView.vue'),
        meta: { title: '경기 일정 후보' },
      },
      {
        path: 'ui-review/fixtures/:externalId(\\d+)',
        name: 'ui-review-fixture-detail',
        component: () => import('@/views/ui-review/UiReviewFixturePreviewView.vue'),
        meta: { title: '경기 상세 후보' },
      },
      {
        path: 'ui-review/news',
        name: 'ui-review-news',
        component: () => import('@/views/ui-review/UiReviewNewsView.vue'),
        meta: { title: '뉴스 후보' },
      },
      {
        path: 'admin',
        name: 'admin',
        beforeEnter: () => (isAdminRouteAllowed() ? true : { name: 'not-found' }),
        component: () => import('@/views/AdminView.vue'),
      },
      { path: 'broadcast', name: 'broadcast', beforeEnter: openBroadcast, component: PlaceholderView, props: { title: '방송' } },
      {
        path: 'broadcast/fixtures/:externalId(\\d+)',
        name: 'broadcast-fixture',
        beforeEnter: openBroadcast,
        component: PlaceholderView,
        props: { title: '방송' },
      },
      {
        path: 'broadcast/program/fixtures/:externalId(\\d+)',
        name: 'broadcast-program-fixture',
        beforeEnter: openBroadcastProgram,
        component: PlaceholderView,
        props: { title: '중계 화면' },
      },
      { path: 'auth/login', name: 'login', component: PlaceholderView, props: { title: '로그인' } },
      { path: 'auth/signup', name: 'signup', component: () => import('@/views/SignupView.vue') },
      { path: 'not-found', name: 'not-found', component: NotFound },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/not-found',
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  },
})
