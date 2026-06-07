import type { LeagueSlug } from '@/types/home'

export const LEAGUE_ID_TO_SLUG: Record<number, LeagueSlug> = {
  1: 'world-cup-2026',
  39: 'premier-league',
  2: 'champions-league',
  3: 'europa-league',
  48: 'carabao-cup',
  45: 'fa-cup',
}

export const LEAGUE_TOKEN: Record<LeagueSlug, string> = {
  'premier-league': 'epl',
  'champions-league': 'ucl',
  'europa-league': 'uel',
  'carabao-cup': 'carabao',
  'fa-cup': 'fa',
  'world-cup': 'wc',
  'world-cup-2026': 'wc',
}

export const LEAGUE_SHORT_KO: Record<LeagueSlug, string> = {
  'premier-league': 'EPL',
  'champions-league': 'UCL',
  'europa-league': 'UEL',
  'carabao-cup': '카라바오',
  'fa-cup': 'FA',
  'world-cup': '월드컵',
  'world-cup-2026': '월드컵',
}

export interface LeagueOption {
  id: number | null
  label: string
  slug: LeagueSlug | null
  logoUrl: string | null
}

export type FixtureLeagueFilterId = number | null | 'other'

export interface FixtureLeagueOption {
  id: FixtureLeagueFilterId
  label: string
  slug: LeagueSlug | null
  logoUrl: string | null
}

export interface CompetitionLeagueOption extends LeagueOption {
  id: number
  slug: LeagueSlug
}

export function leagueLogoUrl(id: number | null | undefined): string | null {
  if (id == null) return null
  return `https://media.api-sports.io/football/leagues/${id}.png`
}

export const HOME_LEAGUE_TABS: LeagueOption[] = [
  { id: null, label: '전체', slug: null, logoUrl: null },
  { id: 1, label: '월드컵', slug: 'world-cup-2026', logoUrl: leagueLogoUrl(1) },
  { id: 39, label: 'EPL', slug: 'premier-league', logoUrl: leagueLogoUrl(39) },
  { id: 2, label: 'UCL', slug: 'champions-league', logoUrl: leagueLogoUrl(2) },
  { id: 3, label: 'UEL', slug: 'europa-league', logoUrl: leagueLogoUrl(3) },
  { id: 48, label: '카라바오', slug: 'carabao-cup', logoUrl: leagueLogoUrl(48) },
  { id: 45, label: 'FA', slug: 'fa-cup', logoUrl: leagueLogoUrl(45) },
]

export const HOME_FIXTURE_LEAGUE_TABS: FixtureLeagueOption[] = [
  ...HOME_LEAGUE_TABS,
  { id: 'other', label: '기타', slug: null, logoUrl: null },
]

export const HOME_COMPETITION_OPTIONS: CompetitionLeagueOption[] = HOME_LEAGUE_TABS.filter(
  (league): league is CompetitionLeagueOption => league.id != null && league.slug != null,
)

export const HOME_FIXTURE_PRIMARY_LEAGUE_IDS = new Set(
  HOME_COMPETITION_OPTIONS.map((league) => league.id),
)

export function isPrimaryHomeFixtureLeague(id: number): boolean {
  return HOME_FIXTURE_PRIMARY_LEAGUE_IDS.has(id)
}

export function slugFromId(id: number | null | undefined): LeagueSlug | null {
  if (id == null) return null
  return LEAGUE_ID_TO_SLUG[id] ?? null
}

export function leagueVar(
  slug: LeagueSlug | null,
  kind: 'primary' | 'secondary' | 'accent' | 'on-primary',
): string {
  if (!slug) return 'var(--muted, #888)'
  const token = LEAGUE_TOKEN[slug]
  if (!token) return 'var(--muted, #888)'
  return `var(--league-${token}-${kind})`
}
