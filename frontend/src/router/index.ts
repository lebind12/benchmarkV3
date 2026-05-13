import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { defineComponent, h } from 'vue'
import DefaultLayout from '@/layouts/DefaultLayout.vue'

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

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: DefaultLayout,
    children: [
      { path: '', name: 'home', component: () => import('@/views/HomeView.vue') },
      { path: 'fixtures', name: 'fixtures', component: PlaceholderView, props: { title: '경기' } },
      {
        path: 'fixtures/:externalId(\\d+)',
        name: 'fixture-detail',
        component: () => import('@/views/FixtureDetailView.vue'),
        meta: { title: '매치' },
      },
      { path: 'standings', name: 'standings', component: PlaceholderView, props: { title: '순위' } },
      { path: 'teams', name: 'teams', component: PlaceholderView, props: { title: '팀' } },
      { path: 'teams/:slug', name: 'team-detail', component: PlaceholderView, props: { title: '팀 상세' } },
      { path: 'players', name: 'players', component: PlaceholderView, props: { title: '선수' } },
      { path: 'players/:slug', name: 'player-detail', component: PlaceholderView, props: { title: '선수 상세' } },
      { path: 'stats', name: 'stats', component: PlaceholderView, props: { title: '스탯' } },
      { path: 'broadcast', name: 'broadcast', component: PlaceholderView, props: { title: '방송' } },
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
