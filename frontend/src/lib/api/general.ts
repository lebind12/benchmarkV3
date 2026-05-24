import type {
  FixtureSummary,
  LeagueRef,
  MetricKey,
  NewsItem,
  Period,
  PlayerRef,
  StandingRow,
  TeamRef,
  TopPlayerRow,
} from '@/types/home'
import { apiUrl, apiUrlWithQuery } from '@/lib/api/base'

export interface LeagueListItem extends LeagueRef {
  season: number | null
}

export interface StandingGroup {
  group_name: string | null
  rows: StandingRow[]
}

export interface TournamentFixture {
  external_id: number
  match_no?: number | null
  round: string
  kickoff_at: string | null
  status_short: string
  goals_home: number | null
  goals_away: number | null
  score_pen_home: number | null
  score_pen_away: number | null
  home_winner: boolean | null
  away_winner: boolean | null
  home: TeamRef | null
  away: TeamRef | null
}

export interface TournamentRound {
  round_label: string
  rounds: string[]
  round_order: number
  slot_count: number
  fixture_count: number
  from_template: boolean
  fixtures: TournamentFixture[]
}

export interface TournamentTemplateRound {
  round_label: string
  slot_count: number
}

export interface TournamentPayload {
  has_tournament: boolean
  template_rounds: TournamentTemplateRound[]
  rounds: TournamentRound[]
}

export interface StandingsPayload {
  league: LeagueRef | null
  season: number | null
  rows: StandingRow[]
  groups: StandingGroup[]
  tournament?: TournamentPayload | null
}

export interface TeamListItem {
  team: TeamRef
  league: LeagueRef
  country: string | null
  founded: number | null
  rank: number | null
  points: number | null
  played: number | null
}

export interface BasicPlayerRef {
  external_id: number
  slug: string
  name_ko: string | null
  name: string
  photo_url: string | null
}

export interface CoachRef {
  external_id: number | null
  slug: string
  name_ko: string | null
  short_name_ko: string | null
  name: string
  photo_url: string | null
}

export interface CoachListItem {
  coach: CoachRef
  team: TeamRef
  league: LeagueRef
  last_seen_at: string | null
}

export interface TeamSquadRow {
  player: BasicPlayerRef
  position: string | null
  appearances: number | null
  goals: number | null
  assists: number | null
}

export interface TeamDetailPayload {
  team: TeamRef
  country: string | null
  founded: number | null
  coach: { coach: CoachRef; league: LeagueRef | null; last_seen_at: string | null } | null
  venue: { name: string; city: string | null; capacity: number | null } | null
  leagues: { league: LeagueRef; season: number }[]
  fixtures: FixtureSummary[]
  squad: TeamSquadRow[]
}

export interface PlayerListItem {
  player: PlayerRef
  position: string | null
  appearances: number | null
  minutes: number | null
  rating: number | null
  goals: number | null
  assists: number | null
  yellow_cards: number | null
  red_cards: number | null
  metric_value: number
}

export interface PlayerDetailPayload {
  player: BasicPlayerRef
  profile: {
    firstname: string | null
    lastname: string | null
    age: number | null
    birth_date: string | null
    birth_place: string | null
    birth_country: string | null
    nationality: string | null
    height_cm: number | null
    weight_kg: number | null
  }
  current_team: TeamRef | null
  season_stats: {
    season: number
    league: LeagueRef
    team: TeamRef
    position: string | null
    appearances: number | null
    minutes: number | null
    rating: number | null
    goals: number | null
    assists: number | null
    yellow_cards: number | null
    red_cards: number | null
  }[]
}

export interface StatsPayload {
  league_id: number
  leaders: Record<MetricKey, { league: LeagueRef | null; season: number | null; metric: MetricKey; rows: TopPlayerRow[] }>
  standings: StandingsPayload
}

type QueryValue = string | number | null | undefined

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(apiUrl(path), { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return (await res.json()) as T
}

function withQuery(path: string, params: Record<string, QueryValue>): string {
  return apiUrlWithQuery(path, params)
}

export const generalApi = {
  leagues: () => getJson<{ items: LeagueListItem[] }>('/api/v1/leagues'),

  fixtures: (params: { leagueId?: number | null; period: Period; date?: string | null; teamSlug?: string | null; limit?: number }) =>
    getJson<{ items: FixtureSummary[]; filters_applied: Record<string, unknown> }>(
      withQuery('/api/v1/fixtures', {
        league_id: params.leagueId,
        period: params.period,
        date: params.date,
        team_slug: params.teamSlug,
        limit: params.limit,
      }),
    ),

  standings: (leagueId: number) =>
    getJson<StandingsPayload>(withQuery('/api/v1/standings', { league_id: leagueId })),

  teams: (params: { leagueId?: number | null; query?: string | null; limit?: number }) =>
    getJson<{ items: TeamListItem[] }>(
      withQuery('/api/v1/teams', {
        league_id: params.leagueId,
        query: params.query,
        limit: params.limit,
      }),
    ),

  team: (slug: string) => getJson<TeamDetailPayload>(`/api/v1/teams/${slug}`),

  players: (params: { leagueId?: number | null; query?: string | null; metric: MetricKey; limit?: number }) =>
    getJson<{ items: PlayerListItem[]; coaches: CoachListItem[]; metric: MetricKey }>(
      withQuery('/api/v1/players', {
        league_id: params.leagueId,
        query: params.query,
        metric: params.metric,
        limit: params.limit,
      }),
    ),

  player: (slug: string) => getJson<PlayerDetailPayload>(`/api/v1/players/${slug}`),

  coaches: (params: { leagueId?: number | null; limit?: number }) =>
    getJson<{ items: CoachListItem[] }>(
      withQuery('/api/v1/coaches', {
        league_id: params.leagueId,
        limit: params.limit,
      }),
    ),

  stats: (leagueId: number) =>
    getJson<StatsPayload>(withQuery('/api/v1/stats', { league_id: leagueId })),

  news: (limit = 30) =>
    getJson<{ items: NewsItem[] }>(withQuery('/api/v1/news', { limit })),
}
