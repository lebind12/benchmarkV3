import type {
  MatchDetail,
  TimelineEvent,
  TeamLineup,
  H2HFixture,
  TeamStat,
  LeagueStandingsPayload,
  TeamRecentMatchesPayload,
  MatchupInsightsPayload,
} from '@/types/fixtureDetail'
import { apiUrl } from '@/lib/api/base'

export interface MatchPreviewResponse {
  available: boolean
  markdown: string
  generatedAt: string
  fixtureId: number
  reason?: string | null
}

export class NotFoundError extends Error {
  constructor(public externalId: number) {
    super(`fixture ${externalId} not found`)
  }
}

export class ServerError extends Error {
  constructor(public externalId: number) {
    super(`fixture ${externalId} server error`)
  }
}

async function getJson<T>(externalId: number, path: string): Promise<T> {
  const res = await fetch(apiUrl(path), { headers: { Accept: 'application/json' } })
  if (res.status === 404) throw new NotFoundError(externalId)
  if (!res.ok) throw new ServerError(externalId)
  return (await res.json()) as T
}

function adminHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    Accept: 'application/json',
    'Content-Type': 'application/json',
  }
  if (typeof localStorage !== 'undefined') {
    const mockRole = localStorage.getItem('mockRole')
    if (mockRole) headers['X-Mock-Role'] = mockRole
  }
  return headers
}

export function getMatch(externalId: number): Promise<MatchDetail> {
  return getJson<MatchDetail>(externalId, `/api/v1/fixtures/${externalId}`)
}

export async function getEvents(
  externalId: number,
): Promise<{ events: TimelineEvent[] }> {
  return getJson<{ events: TimelineEvent[] }>(externalId, `/api/v1/fixtures/${externalId}/events`)
}

export async function getLineups(
  externalId: number,
): Promise<{ home: TeamLineup; away: TeamLineup }> {
  return getJson<{ home: TeamLineup; away: TeamLineup }>(externalId, `/api/v1/fixtures/${externalId}/lineups`)
}

export async function getH2H(
  externalId: number,
): Promise<{ h2h: H2HFixture[] }> {
  return getJson<{ h2h: H2HFixture[] }>(externalId, `/api/v1/fixtures/${externalId}/h2h?limit=5`)
}

export async function getTeamRecentMatches(
  externalId: number,
): Promise<TeamRecentMatchesPayload> {
  return getJson<TeamRecentMatchesPayload>(externalId, `/api/v1/fixtures/${externalId}/team-recent?limit=10`)
}

export async function getMatchupInsights(
  externalId: number,
): Promise<MatchupInsightsPayload> {
  return getJson<MatchupInsightsPayload>(externalId, `/api/v1/fixtures/${externalId}/matchup-insights?limit=10`)
}

export async function getStatistics(
  externalId: number,
): Promise<{ home: TeamStat; away: TeamStat }> {
  return getJson<{ home: TeamStat; away: TeamStat }>(externalId, `/api/v1/fixtures/${externalId}/statistics`)
}

export async function getLeagueStandings(
  externalId: number,
): Promise<LeagueStandingsPayload> {
  return getJson<LeagueStandingsPayload>(externalId, `/api/v1/fixtures/${externalId}/league-standings`)
}

export async function createMatchPreview(externalId: number): Promise<MatchPreviewResponse> {
  const res = await fetch(apiUrl(`/api/v1/broadcast/fixtures/${externalId}/match-preview`), {
    method: 'POST',
    headers: adminHeaders(),
    body: '{}',
  })
  if (res.status === 404) throw new NotFoundError(externalId)
  if (!res.ok) throw new ServerError(externalId)
  return (await res.json()) as MatchPreviewResponse
}
