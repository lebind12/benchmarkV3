import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { defineComponent, h } from 'vue'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import {
  BROADCAST_FIXTURE_QUERY_PARAM,
  BROADCAST_LEGACY_FIXTURE_QUERY_PARAM,
} from '@/lib/broadcastQuery'

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
  if (typeof window === 'undefined') return false
  window.location.assign(buildBroadcastPageUrl('broadcast.html', to))
  return false
}

function openBroadcastProgram(to: BroadcastRouteTarget) {
  if (typeof window === 'undefined') return false
  window.location.assign(buildBroadcastPageUrl('broadcast-program.html', to))
  return false
}

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: DefaultLayout,
    children: [
      { path: '', name: 'home', component: () => import('@/views/HomeView.vue') },
      { path: 'fixtures', name: 'fixtures', component: () => import('@/views/FixturesView.vue') },
      {
        path: 'fixtures/:externalId(\\d+)',
        name: 'fixture-detail',
        component: () => import('@/views/FixtureDetailView.vue'),
        meta: { title: '매치' },
      },
      { path: 'standings', name: 'standings', component: () => import('@/views/StandingsView.vue') },
      { path: 'teams', name: 'teams', component: () => import('@/views/TeamsView.vue') },
      { path: 'teams/:slug', name: 'team-detail', component: () => import('@/views/TeamDetailView.vue') },
      { path: 'players', name: 'players', component: () => import('@/views/PlayersView.vue') },
      { path: 'players/:slug', name: 'player-detail', component: () => import('@/views/PlayerDetailView.vue') },
      { path: 'stats', name: 'stats', component: () => import('@/views/StatsView.vue') },
      { path: 'news', name: 'news', component: () => import('@/views/NewsView.vue') },
      { path: 'admin', name: 'admin', component: () => import('@/views/AdminView.vue') },
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
