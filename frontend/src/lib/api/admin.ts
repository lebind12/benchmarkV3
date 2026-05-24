import { apiUrl, apiUrlWithQuery } from '@/lib/api/base'

export interface ApiFootballSeason {
  year: number
  start: string | null
  end: string | null
  current: boolean
  coverage: {
    fixtures: boolean
    standings: boolean
    players: boolean
    top_scorers: boolean
    injuries: boolean
  }
}

export interface ApiFootballLeague {
  external_id: number
  name: string
  type: string
  logo_url: string | null
  country: {
    name: string | null
    code: string | null
    flag: string | null
  }
  seasons: ApiFootballSeason[]
  current_season?: number | null
  last_synced_at?: string | null
}

export interface AdminLeagueRef {
  external_id: number
  slug: string
  name: string
  name_ko: string | null
  short_name_ko: string | null
  type: string
  logo_url: string | null
  country_name: string | null
  current_season: number | null
}

export interface SyncTarget {
  id: number
  league: AdminLeagueRef
  season_year: number
  is_active: boolean
  include_details: boolean
  include_players: boolean
  include_standings: boolean
  fixture_limit: number | null
  created_at: string
  updated_at: string
}

export interface SyncTargetInput {
  league_external_id: number
  season_year: number
  is_active?: boolean
  include_details?: boolean
  include_players?: boolean
  include_standings?: boolean
  fixture_limit?: number | null
}

export interface SyncPlanSpec {
  league_external_id: number
  seasons: number[] | null
  include_details: boolean
  include_players: boolean
  include_standings: boolean
  fixture_limit: number | null
}

export interface ApiFootballCatalogSyncResult {
  api_count: number
  synced_count: number
  catalog_count: number
}

export interface WorkerLogLine {
  ts: string
  message: string
}

export interface WorkerRun {
  id: string
  worker_name: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  total_units: number
  completed_units: number
  progress_percent: number
  logs: WorkerLogLine[]
  result: Record<string, unknown> | null
  error: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

type QueryValue = string | number | null | undefined

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(detail || `HTTP ${res.status}`)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

function withQuery(path: string, params: Record<string, QueryValue>) {
  return apiUrlWithQuery(path, params)
}

export const adminApi = {
  searchApiFootballLeagues: (params: { search?: string | null; id?: number | null; country?: string | null }) =>
    requestJson<{ items: ApiFootballLeague[] }>(
      withQuery('/api/v1/admin/api-football/leagues', {
        search: params.search,
        id: params.id,
        country: params.country,
      }),
    ),

  syncApiFootballCatalog: (payload: {
    search?: string | null
    id?: number | null
    country?: string | null
    current?: boolean | null
  }) =>
    requestJson<ApiFootballCatalogSyncResult>('/api/v1/admin/api-football/leagues/sync', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  syncTargets: () => requestJson<{ items: SyncTarget[] }>('/api/v1/admin/sync-targets'),

  syncPlan: (fallbackDefaults = false) =>
    requestJson<{ specs: SyncPlanSpec[] }>(
      withQuery('/api/v1/admin/sync-targets/plan', { fallback_defaults: fallbackDefaults ? 'true' : 'false' }),
    ),

  createSyncTarget: (payload: SyncTargetInput) =>
    requestJson<SyncTarget>('/api/v1/admin/sync-targets', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  patchSyncTarget: (id: number, payload: Partial<Omit<SyncTargetInput, 'league_external_id' | 'season_year'>>) =>
    requestJson<SyncTarget>(`/api/v1/admin/sync-targets/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  deleteSyncTarget: (id: number) =>
    requestJson<void>(`/api/v1/admin/sync-targets/${id}`, { method: 'DELETE' }),

  runDailySync: (payload: { fallback_defaults?: boolean; fixture_limit?: number | null }) =>
    requestJson<WorkerRun>('/api/v1/admin/daily-sync/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  workerRun: (id: string) => requestJson<WorkerRun>(`/api/v1/admin/daily-sync/runs/${id}`),
}
