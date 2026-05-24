import type {
  FixtureSummary,
  HotPlayer,
  Injury,
  LeagueRef,
  MetricKey,
  NewsItem,
  Period,
  StandingRow,
  TopPlayerRow,
  Transfer,
} from '@/types/home'
import { apiUrl, apiUrlWithQuery } from '@/lib/api/base'

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(apiUrl(url), { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return (await res.json()) as T
}

export const homeApi = {
  news: () => getJson<{ items: NewsItem[] }>('/api/v1/home/news'),
  hot:  () => getJson<{ items: HotPlayer[] }>('/api/v1/home/hot-players'),
  transfers: () => getJson<{ items: Transfer[] }>('/api/v1/home/transfers'),
  injuries:  () => getJson<{ items: Injury[] }>('/api/v1/home/injuries'),

  fixtures: (period: Period, leagueId: number | null, date?: string) => {
    return getJson<{
      items: FixtureSummary[]
      filters_applied: { period: Period; league_id?: number; date?: string }
    }>(apiUrlWithQuery('/api/v1/home/fixtures', { period, league_id: leagueId, date }))
  },

  standings: (leagueId: number) =>
    getJson<{ league: LeagueRef | null; season: number | null; rows: StandingRow[] }>(
      `/api/v1/home/standings?league_id=${leagueId}`,
    ),

  topPlayers: (leagueId: number, metric: MetricKey) =>
    getJson<{ league: LeagueRef | null; season: number; metric: MetricKey; rows: TopPlayerRow[] }>(
      `/api/v1/home/top-players?league_id=${leagueId}&metric=${metric}`,
    ),
}
