import { defineStore } from 'pinia'
import { homeApi } from '@/lib/api/home'
import type {
  AsyncSlice,
  FixtureSummary,
  HotPlayer,
  Injury,
  MetricKey,
  NewsItem,
  Period,
  StandingRow,
  TopPlayerRow,
  Transfer,
} from '@/types/home'

const ROTATE_MS = 10_000
const CUP_LEAGUES_WITHOUT_STANDINGS = new Set([48, 45])

export function hasHomeStandings(id: number): boolean {
  return !CUP_LEAGUES_WITHOUT_STANDINGS.has(id)
}

function newSlice<T>(): AsyncSlice<T> {
  return { status: 'idle', value: null, error: null, fetchedAt: null }
}

export function todayKstYmd(): string {
  const parts = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date())
  const y = parts.find((p) => p.type === 'year')?.value
  const m = parts.find((p) => p.type === 'month')?.value
  const d = parts.find((p) => p.type === 'day')?.value
  return `${y}-${m}-${d}`
}

export function shiftKstYmd(ymd: string, deltaDays: number): string {
  const [y, m, d] = ymd.split('-').map(Number)
  const dt = new Date(Date.UTC(y, m - 1, d))
  dt.setUTCDate(dt.getUTCDate() + deltaDays)
  const yy = dt.getUTCFullYear()
  const mm = String(dt.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(dt.getUTCDate()).padStart(2, '0')
  return `${yy}-${mm}-${dd}`
}

export const useHomeStore = defineStore('home', {
  state: () => ({
    cube: {
      activeFace: 0 as 0 | 1 | 2 | 3,
      paused: false,
      timerHandle: null as ReturnType<typeof setInterval> | null,
    },
    news: newSlice<NewsItem[]>(),
    hot: newSlice<HotPlayer[]>(),
    transfers: newSlice<Transfer[]>(),
    injuries: newSlice<Injury[]>(),
    fixtures: {
      filter: {
        league_id: null as number | null,
        period: 'day' as Period,
        date: todayKstYmd(),
      },
      data: newSlice<FixtureSummary[]>(),
    },
    standings: {
      league_id: 39,
      data: newSlice<StandingRow[]>(),
    },
    topPlayers: {
      league_id: 39,
      metric: 'goals' as MetricKey,
      data: newSlice<TopPlayerRow[]>(),
    },
  }),
  actions: {
    async bootstrap() {
      await Promise.all([
        this.fetchNews(),
        this.fetchHot(),
        this.fetchTransfers(),
        this.fetchInjuries(),
        this.fetchFixtures(),
        this.fetchStandings(),
        this.fetchTopPlayers(),
      ])
      this.startAutoRotate()
    },
    async _runSlice<T>(slice: AsyncSlice<T>, fn: () => Promise<T>) {
      slice.status = 'loading'
      slice.error = null
      try {
        slice.value = await fn()
        slice.status = 'ok'
        slice.fetchedAt = Date.now()
      } catch (e: any) {
        slice.status = 'error'
        slice.error = String(e?.message ?? e)
      }
    },
    fetchNews() { return this._runSlice(this.news, async () => (await homeApi.news()).items) },
    fetchHot() { return this._runSlice(this.hot, async () => (await homeApi.hot()).items) },
    fetchTransfers() { return this._runSlice(this.transfers, async () => (await homeApi.transfers()).items) },
    fetchInjuries() { return this._runSlice(this.injuries, async () => (await homeApi.injuries()).items) },
    fetchFixtures() {
      return this._runSlice(this.fixtures.data, async () =>
        (
          await homeApi.fixtures(
            this.fixtures.filter.period,
            this.fixtures.filter.league_id,
            this.fixtures.filter.date,
          )
        ).items,
      )
    },
    fetchStandings() {
      if (!hasHomeStandings(this.standings.league_id)) {
        this.standings.data.status = 'ok'
        this.standings.data.value = []
        this.standings.data.error = null
        this.standings.data.fetchedAt = Date.now()
        return Promise.resolve()
      }
      return this._runSlice(this.standings.data, async () =>
        (await homeApi.standings(this.standings.league_id)).rows,
      )
    },
    fetchTopPlayers() {
      return this._runSlice(this.topPlayers.data, async () =>
        (await homeApi.topPlayers(this.topPlayers.league_id, this.topPlayers.metric)).rows,
      )
    },
    setLeagueFilter(id: number | null) {
      this.fixtures.filter.league_id = id
      this.fetchFixtures()
    },
    setPeriod(p: Period) {
      this.fixtures.filter.period = p
      this.fetchFixtures()
    },
    setFixtureDate(ymd: string) {
      this.fixtures.filter.date = ymd
      this.fetchFixtures()
    },
    shiftFixtureDate(deltaDays: number) {
      this.fixtures.filter.date = shiftKstYmd(this.fixtures.filter.date, deltaDays)
      this.fetchFixtures()
    },
    resetFixtureDate() {
      this.fixtures.filter.date = todayKstYmd()
      this.fetchFixtures()
    },
    setStandingsLeague(id: number) {
      this.standings.league_id = id
      this.fetchStandings()
    },
    setTopPlayersLeague(id: number) {
      this.topPlayers.league_id = id
      this.fetchTopPlayers()
    },
    setTopPlayersMetric(m: MetricKey) {
      this.topPlayers.metric = m
      this.fetchTopPlayers()
    },
    resetFixtureFilters() {
      this.fixtures.filter = {
        league_id: null,
        period: 'day',
        date: todayKstYmd(),
      }
      this.fetchFixtures()
    },

    // Cube auto-rotation
    setFace(i: 0 | 1 | 2 | 3) {
      this.cube.activeFace = i
      this.restartTimer()
    },
    nextFace() {
      this.cube.activeFace = (((this.cube.activeFace + 1) % 4) as 0 | 1 | 2 | 3)
    },
    pauseAutoRotate() {
      this.cube.paused = true
      if (this.cube.timerHandle) {
        clearInterval(this.cube.timerHandle)
        this.cube.timerHandle = null
      }
    },
    resumeAutoRotate() {
      this.cube.paused = false
      this.startAutoRotate()
    },
    startAutoRotate() {
      if (this.cube.timerHandle || this.cube.paused) return
      this.cube.timerHandle = setInterval(() => this.nextFace(), ROTATE_MS)
    },
    restartTimer() {
      if (this.cube.timerHandle) {
        clearInterval(this.cube.timerHandle)
        this.cube.timerHandle = null
      }
      if (!this.cube.paused) this.startAutoRotate()
    },
    teardown() {
      if (this.cube.timerHandle) {
        clearInterval(this.cube.timerHandle)
        this.cube.timerHandle = null
      }
    },
  },
})
