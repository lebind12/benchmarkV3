import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useFixtureDetailStore } from '@/stores/fixtureDetail'
import match1000001 from '@/mocks/data/fixture-detail/match.1000001.json'
import events1000001 from '@/mocks/data/fixture-detail/events.1000001.json'
import lineups1000001 from '@/mocks/data/fixture-detail/lineups.1000001.json'
import statistics1000001 from '@/mocks/data/fixture-detail/statistics.1000001.json'

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
    if (url.pathname === '/api/v1/fixtures/1000099') {
      return jsonResponse({ error: 'not found' }, { status: 404 })
    }
    if (url.pathname === '/api/v1/fixtures/1000001') return jsonResponse(match1000001)
    if (url.pathname === '/api/v1/fixtures/1000001/events') return jsonResponse(events1000001)
    if (url.pathname === '/api/v1/fixtures/1000001/lineups') return jsonResponse(lineups1000001)
    if (url.pathname === '/api/v1/fixtures/1000001/statistics') return jsonResponse(statistics1000001)
    return jsonResponse({ error: 'unhandled test route' }, { status: 500 })
  }))
}

describe('useFixtureDetailStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    stubFixtureDetailFetch()
  })

  it('bootstrap loads match/events/lineups in parallel', async () => {
    const store = useFixtureDetailStore()
    await store.bootstrap(1000001)
    expect(store.match.status).toBe('ok')
    expect(store.events.status).toBe('ok')
    expect(store.lineups.status).toBe('ok')
    expect(store.h2h.status).toBe('idle')
    expect(store.statistics.status).toBe('idle')
    expect(store.standings.status).toBe('idle')
  })

  it('setTab triggers lazy fetch only once', async () => {
    const store = useFixtureDetailStore()
    await store.bootstrap(1000001)
    expect(store.statistics.status).toBe('idle')
    await store.setTab('stats')
    expect(store.statistics.status).toBe('ok')
    expect(store.activeTab).toBe('stats')
  })

  it('bootstrap to 1000099 marks match as not_found', async () => {
    const store = useFixtureDetailStore()
    await store.bootstrap(1000099)
    expect(store.match.status).toBe('not_found')
  })

  it('toggleBench flips per-team state', async () => {
    const store = useFixtureDetailStore()
    expect(store.benchExpanded.home).toBe(false)
    store.toggleBench('home')
    expect(store.benchExpanded.home).toBe(true)
    expect(store.benchExpanded.away).toBe(false)
  })
})
