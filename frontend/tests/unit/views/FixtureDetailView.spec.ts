import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import FixtureDetailView from '@/views/FixtureDetailView.vue'
import match1000001 from '@/mocks/data/fixture-detail/match.1000001.json'
import events1000001 from '@/mocks/data/fixture-detail/events.1000001.json'
import lineups1000001 from '@/mocks/data/fixture-detail/lineups.1000001.json'

function jsonResponse(body: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify(body), {
    status: init?.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
}

function stubFixtureDetailFetch() {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost')
    if (url.pathname === '/api/v1/fixtures/1000001') return jsonResponse(match1000001)
    if (url.pathname === '/api/v1/fixtures/1000001/events') return jsonResponse(events1000001)
    if (url.pathname === '/api/v1/fixtures/1000001/lineups') return jsonResponse(lineups1000001)
    return jsonResponse({ error: 'unhandled test route' }, { status: 500 })
  }))
}

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/fixtures/:externalId(\\d+)',
        name: 'fixture-detail',
        component: FixtureDetailView,
      },
      {
        path: '/not-found',
        name: 'not-found',
        component: { template: '<div data-testid="not-found">404</div>' } as never,
      },
      {
        path: '/players/:slug',
        name: 'player-detail',
        component: { template: '<div />' } as never,
      },
      {
        path: '/teams/:slug',
        name: 'team-detail',
        component: { template: '<div />' } as never,
      },
    ],
  })
}

describe('FixtureDetailView', () => {
  beforeEach(() => {
    stubFixtureDetailFetch()
  })

  it('binds data-league to root once match loads', async () => {
    const router = makeRouter()
    router.push('/fixtures/1000001')
    await router.isReady()
    const w = mount(FixtureDetailView, {
      global: { plugins: [createPinia(), router] },
    })
    await flushPromises()
    await flushPromises()
    const root = w.find('[data-testid=fixture-detail-root]')
    expect(root.exists()).toBe(true)
    expect(root.attributes('data-league')).toBe('premier-league')
  })

  it('does not have data-league while match still loading', async () => {
    const router = makeRouter()
    router.push('/fixtures/1000001')
    await router.isReady()
    const w = mount(FixtureDetailView, {
      global: { plugins: [createPinia(), router] },
    })
    const root = w.find('[data-testid=fixture-detail-root]')
    expect(root.attributes('data-league')).toBeUndefined()
  })
})
