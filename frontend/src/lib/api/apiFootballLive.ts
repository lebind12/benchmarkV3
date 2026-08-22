import { apiUrl } from '@/lib/api/base'

type ApiFootballEnvelope<T> = {
  response: T[]
  errors?: unknown
}

type ApiFootballTeamRef = {
  id?: number
  name?: string
  code?: string | null
  logo?: string | null
}

type ApiFootballFixtureItem = {
  fixture?: {
    id?: number
    status?: {
      long?: string
      short?: string
      elapsed?: number | null
      extra?: number | null
    }
    venue?: {
      name?: string | null
    }
  }
  league?: {
    id?: number
    name?: string
    season?: number
  }
  teams?: {
    home?: ApiFootballTeamRef
    away?: ApiFootballTeamRef
  }
  goals?: {
    home?: number | null
    away?: number | null
  }
}

type ApiFootballTeamItem = {
  team?: ApiFootballTeamRef
}

type ApiFootballEventItem = {
  time?: {
    elapsed?: number | null
    extra?: number | null
  }
  team?: ApiFootballTeamRef
  player?: {
    id?: number
    name?: string | null
  }
  assist?: {
    id?: number
    name?: string | null
  }
  type?: string | null
  detail?: string | null
  comments?: string | null
}

type ApiFootballLineupItem = {
  team?: ApiFootballTeamRef
  coach?: {
    id?: number
    name?: string | null
    photo?: string | null
  }
  formation?: string | null
  startXI?: Array<{
    player?: {
      id?: number
      name?: string | null
      number?: number | null
      pos?: string | null
      grid?: string | null
    }
  }>
  substitutes?: Array<{
    player?: {
      id?: number
      number?: number | null
    }
  }>
}

type ApiFootballStatisticsItem = {
  team?: ApiFootballTeamRef
  statistics?: Array<{
    type?: string | null
    value?: number | string | null
  }>
}

type ApiFootballFixturePlayerItem = {
  team?: ApiFootballTeamRef
  players?: Array<{
    player?: {
      id?: number
      name?: string | null
      photo?: string | null
    }
    statistics?: Array<{
      games?: {
        rating?: number | string | null
        minutes?: number | string | null
      }
      shots?: {
        total?: number | string | null
        on?: number | string | null
      }
      passes?: {
        total?: number | string | null
        accuracy?: number | string | null
        key?: number | string | null
      }
      tackles?: {
        total?: number | string | null
        blocks?: number | string | null
        interceptions?: number | string | null
      }
      duels?: {
        total?: number | string | null
        won?: number | string | null
      }
      dribbles?: {
        attempts?: number | string | null
        success?: number | string | null
      }
      fouls?: {
        drawn?: number | string | null
        committed?: number | string | null
      }
      cards?: {
        yellow?: number | string | null
        red?: number | string | null
      }
      goals?: {
        total?: number | string | null
        assists?: number | string | null
        saves?: number | string | null
        conceded?: number | string | null
      }
    }>
  }>
}

export type ApiFootballBroadcastEventKind =
  | 'goal'
  | 'own-goal'
  | 'penalty-missed'
  | 'goal-cancelled'
  | 'substitution'
  | 'yellow-card'
  | 'red-card'
  | 'var'
  | 'card'

export type ApiFootballBroadcastEvent = {
  id: string
  kind: ApiFootballBroadcastEventKind
  teamId?: number
  teamCode: string
  opponentCode?: string
  minute: string
  title: string
  detail: string
  playerId?: number
  player?: string
  playerShortName?: string
  playerNumber?: number
  playerPhotoUrl?: string
  assistId?: number
  assist?: string
  assistShortName?: string
  assistNumber?: number
  assistPhotoUrl?: string
  score?: string
  inPlayer?: string
  inPlayerShortName?: string
  inPlayerNumber?: number
  inPlayerPhotoUrl?: string
  outPlayer?: string
  outPlayerShortName?: string
  outPlayerNumber?: number
  outPlayerPhotoUrl?: string
  teamLogoUrl?: string
  statLabel?: string
  statValue?: string
}

export type ApiFootballBroadcastLineupPlayer = {
  id?: number
  no: number
  name: string
  longName?: string
  pos?: string
  grid?: string
  rating?: string
  photoUrl?: string
  minutes?: number
  shotsTotal?: number
  shotsOnGoal?: number
  passesTotal?: number
  passesAccurate?: number
  passesAccuracyPct?: number
  keyPasses?: number
  foulsCommitted?: number
  statGoals?: number
  statAssists?: number
  saves?: number
  goalsConceded?: number
  tacklesTotal?: number
  blocks?: number
  interceptions?: number
  duelsTotal?: number
  duelsWon?: number
  dribblesAttempts?: number
  dribblesSuccess?: number
  statYellowCards?: number
  statRedCards?: number
  eventSummary?: {
    goals: number
    ownGoals?: number
    yellowCards: number
    redCards: number
    cardLabel: string
  }
}

type ApiFootballBroadcastLineupPlayerStat = Partial<
  Pick<
    ApiFootballBroadcastLineupPlayer,
    | "minutes"
    | "rating"
    | "shotsTotal"
    | "shotsOnGoal"
    | "passesTotal"
    | "passesAccurate"
    | "passesAccuracyPct"
    | "keyPasses"
    | "foulsCommitted"
    | "statGoals"
    | "statAssists"
    | "saves"
    | "goalsConceded"
    | "tacklesTotal"
    | "blocks"
    | "interceptions"
    | "duelsTotal"
    | "duelsWon"
    | "dribblesAttempts"
    | "dribblesSuccess"
    | "statYellowCards"
    | "statRedCards"
  >
>

export type ApiFootballBroadcastCoach = {
  id?: number
  name: string
  longName?: string
  photoUrl?: string
}

export type ApiFootballBroadcastLineup = {
  teamId?: number
  name: string
  code: string
  primaryColor?: string | null
  secondaryColor?: string | null
  accentColor?: string | null
  scoreboardColorMode?: 'PRIMARY_LIGHT' | 'SECONDARY' | null
  shape: string
  coach?: ApiFootballBroadcastCoach
  players: ApiFootballBroadcastLineupPlayer[]
  substituteNumbers: Record<string, number>
}

export type ApiFootballBroadcastStat = {
  id?: string
  label: string
  home: string
  away: string
  homePct: number
  awayPct: number
}

export type ApiFootballBroadcastStandingRow = {
  rank: number
  team_id: number
  team_name: string
  team_code: string
  played: number
  win: number
  draw: number
  loss: number
  goals_for: number
  goals_against: number
  goal_diff: number
  points: number
}

export type ApiFootballBroadcastStandings = {
  group_name: string
  rows: ApiFootballBroadcastStandingRow[]
}

export type ApiFootballLiveGroupStandingRow = {
  rank: number
  teamId?: number
  teamName: string
  teamCode: string
  played: number
  win: number
  draw: number
  loss: number
  goalsFor: number
  goalsAgainst: number
  goalDiff: number
  points: number
  isPlayingNow: boolean
  liveFixtureId?: number | null
}

export type ApiFootballLiveGroupFixture = {
  fixtureId?: number | null
  homeTeamId: number
  awayTeamId: number
  homeName: string
  awayName: string
  status: string
  elapsed?: number | null
  score: string
}

export type ApiFootballLiveGroupGoalEvent = {
  eventKey: string
  fixtureId?: number | null
  clock: string
  minute?: number | null
  teamId?: number | null
  teamName: string
  opponentName?: string | null
  playerId?: number | null
  playerName?: string | null
  eventType: string
  detail: string
  score: string
  message: string
}

export type ApiFootballLiveGroupStandingsResponse = {
  available: boolean
  fixtureId: number
  leagueId?: number | null
  season?: number | null
  groupName: string
  source?: string
  generatedAt: string
  cached: boolean
  liveFixtures: ApiFootballLiveGroupFixture[]
  groupGoalEvents?: ApiFootballLiveGroupGoalEvent[]
  rows: ApiFootballLiveGroupStandingRow[]
  limitations: string[]
}

export type ApiFootballBroadcastMomentum = {
  available: boolean
  home: number
  away: number
  trend: 'home' | 'away' | 'balanced' | 'unavailable'
  intensity: 'low' | 'medium' | 'high'
  dominance?: 'low' | 'medium' | 'high'
  tempo?: 'low' | 'medium' | 'high'
  activity?: number
  reasons: string[]
  history?: Array<{
    elapsed?: number | null
    extra?: number | null
    minuteKey?: number | null
    displayMinute?: string | null
    value: number
    home?: number
    away?: number
    activity?: number
    dominance?: number
  }>
  updatedAt: string
}

type ApiLeagueStandingsTeam = {
  external_id: number
  name: string
  short_name_ko?: string | null
  name_ko?: string | null
}

type ApiLeagueStandingsRow = {
  rank: number
  team: ApiLeagueStandingsTeam
  played: number
  win: number
  draw: number
  loss: number
  goals_for: number
  goals_against: number
  goal_diff: number
  points: number
}

type ApiLeagueStandingsResponse = {
  group_name?: string | null
  rows?: ApiLeagueStandingsRow[]
}

export type ApiFootballBroadcastSnapshot = {
  fixtureId: number
  leagueId?: number
  leagueName: string
  leagueShortName?: string
  season?: number
  home: string
  away: string
  homeId?: number
  awayId?: number
  homeCode: string
  awayCode: string
  homeEnglishCode: string
  awayEnglishCode: string
  homeLogoUrl?: string
  awayLogoUrl?: string
  score: string
  clock: string
  addedTime: string
  status: string
  kickoffAt?: string | null
  venue: string
  standings?: ApiFootballBroadcastStandings
  lineups: ApiFootballBroadcastLineup[]
  playerRatings: Record<string, string>
  playerStats?: Record<string, ApiFootballBroadcastLineupPlayerStat>
  stats: ApiFootballBroadcastStat[]
  programStats?: Record<string, ApiFootballBroadcastStat[]>
  events: ApiFootballBroadcastEvent[]
  momentum?: ApiFootballBroadcastMomentum
}

export type ApiFootballAiReviewResponse = {
  available: boolean
  reason?: string
  minimumMinute?: number
  currentMaxMinute?: number | null
  message?: string
  cached?: boolean
  reviewBasis?: {
    status?: string | null
    clock?: string | null
    minute?: number | null
    phase?: string | null
    phaseLabel?: string | null
    matchClockLabel?: string | null
    generatedAt?: string | null
  }
  commentary?: {
    headline?: string
    oneLineSummary?: string
    mainCommentary?: string
    limitations?: string[]
    [key: string]: unknown
  }
}

type BroadcastTranslationValue = {
  name_ko?: string | null
  short_name_ko?: string | null
}

type BroadcastTranslationResponse = {
  leagues?: Record<string, BroadcastTranslationValue>
  league_names?: Record<string, BroadcastTranslationValue>
  teams?: Record<string, BroadcastTranslationValue>
  team_names?: Record<string, BroadcastTranslationValue>
  players?: Record<string, BroadcastTranslationValue>
  player_names?: Record<string, BroadcastTranslationValue>
  coaches?: Record<string, BroadcastTranslationValue>
  coach_names?: Record<string, BroadcastTranslationValue>
}

const API_FOOTBALL_BASE_URL =
  import.meta.env.VITE_API_FOOTBALL_BASE_URL
  ?? (import.meta.env.API_FOOTBALL_HOST
    ? `https://${import.meta.env.API_FOOTBALL_HOST}`
    : 'https://v3.football.api-sports.io')
const API_FOOTBALL_KEY =
  import.meta.env.VITE_API_FOOTBALL_KEY
  ?? import.meta.env.API_FOOTBALL_KEY
  ?? import.meta.env.APIKEY

export const API_FOOTBALL_LIVE_POLL_MS = Number.parseInt(
  import.meta.env.VITE_API_FOOTBALL_POLL_MS ?? '10000',
  10,
)
export const API_FOOTBALL_LINEUPS_REFRESH_MS = Number.parseInt(
  import.meta.env.VITE_API_FOOTBALL_LINEUPS_REFRESH_MS ?? '120000',
  10,
)

export function shouldUseApiFootballLive(): boolean {
  return true
}

function broadcastProgramHeaders() {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (typeof localStorage !== 'undefined') {
    const mockRole = localStorage.getItem('mockRole')
    if (mockRole) headers['X-Mock-Role'] = mockRole
  }
  return headers
}

async function fetchBroadcastProgramSnapshot(path: string): Promise<ApiFootballBroadcastSnapshot> {
  const response = await fetch(apiUrl(path), {
    headers: broadcastProgramHeaders(),
  })

  if (!response.ok) {
    throw new Error(`방송 프로그램 스냅샷 요청 실패: ${response.status}`)
  }

  return (await response.json()) as ApiFootballBroadcastSnapshot
}

function requireApiFootballKey(): string {
  if (!API_FOOTBALL_KEY) {
    throw new Error('VITE_API_FOOTBALL_KEY is required for broadcast live API-Football mode')
  }

  return API_FOOTBALL_KEY
}

async function apiFootballGet<T>(
  path: string,
  params: Record<string, string | number | boolean | null | undefined>,
): Promise<T[]> {
  const url = new URL(path, API_FOOTBALL_BASE_URL)

  Object.entries(params).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== '') {
      url.searchParams.set(key, String(value))
    }
  })

  const res = await fetch(url, {
    headers: {
      Accept: 'application/json',
      'x-apisports-key': requireApiFootballKey(),
    },
  })

  if (!res.ok) {
    throw new Error(`API-Football 요청 실패: ${res.status} ${res.statusText}`)
  }

  const data = (await res.json()) as ApiFootballEnvelope<T>
  return data.response ?? []
}

function usableCode(code: string | null | undefined) {
  const trimmed = code?.trim()
  if (!trimmed || trimmed.length < 2) return undefined
  return trimmed.toUpperCase()
}

function compactCode(code: string | null | undefined, fallback = '') {
  return usableCode(code) ?? fallback
}

function scoreFromFixture(fixture: ApiFootballFixtureItem) {
  const home = fixture.goals?.home ?? 0
  const away = fixture.goals?.away ?? 0
  return `${home} : ${away}`
}

function clockFromFixture(fixture: ApiFootballFixtureItem) {
  const elapsed = fixture.fixture?.status?.elapsed
  if (elapsed === null || elapsed === undefined) return '00:00'
  return `${String(elapsed).padStart(2, '0')}:00`
}

function addedTimeFromFixture(fixture: ApiFootballFixtureItem) {
  return `+${fixture.fixture?.status?.extra ?? 0}`
}

function statusFromFixture(fixture: ApiFootballFixtureItem) {
  const status = fixture.fixture?.status
  const short = status?.short?.toUpperCase()
  const long = status?.long
  const statusMap: Record<string, string> = {
    TBD: '미정',
    NS: '경기 전',
    '1H': '전반',
    HT: '하프타임',
    '2H': '후반',
    ET: '연장',
    BT: '휴식',
    P: '승부차기',
    SUSP: '중단',
    INT: '중단',
    FT: '종료',
    AET: '연장 종료',
    PEN: '승부차기 종료',
    PST: '연기',
    CANC: '취소',
    ABD: '중단',
    AWD: '몰수',
    WO: '몰수',
    LIVE: '라이브',
  }

  return (short ? statusMap[short] : undefined) ?? long ?? '라이브'
}

function minuteFromEvent(event: ApiFootballEventItem) {
  const elapsed = event.time?.elapsed ?? 0
  const extra = event.time?.extra
  return extra ? `${elapsed}+${extra}'` : `${elapsed}'`
}

function valueToString(value: number | string | null | undefined) {
  if (value === null || value === undefined) return '0'
  return String(value)
}

function parseStatNumber(value: string) {
  const parsed = Number.parseFloat(value.replace('%', ''))
  return Number.isFinite(parsed) ? parsed : 0
}

function pairedPct(home: string, away: string) {
  const homeValue = parseStatNumber(home)
  const awayValue = parseStatNumber(away)

  if (home.includes('%') || away.includes('%')) {
    return {
      homePct: Math.max(0, Math.min(100, homeValue)),
      awayPct: Math.max(0, Math.min(100, awayValue)),
    }
  }

  const total = homeValue + awayValue
  if (total <= 0) {
    return { homePct: 50, awayPct: 50 }
  }

  return {
    homePct: Math.round((homeValue / total) * 100),
    awayPct: Math.round((awayValue / total) * 100),
  }
}

function eventKind(event: ApiFootballEventItem): ApiFootballBroadcastEventKind | undefined {
  const type = (event.type ?? '').toLowerCase()
  const detail = (event.detail ?? '').toLowerCase()

  if (type.includes('goal') && detail.includes('miss') && detail.includes('penalty')) return 'penalty-missed'
  if (type.includes('goal') && (detail.includes('cancel') || detail.includes('disallow'))) return 'goal-cancelled'
  if (type.includes('goal') && detail.includes('own')) return 'own-goal'
  if (type.includes('goal')) return 'goal'
  if (type.includes('subst')) return 'substitution'
  if (type.includes('var')) return 'var'
  if (type.includes('card') && detail.includes('red')) return 'red-card'
  if (type.includes('card') && detail.includes('yellow')) return 'yellow-card'
  if (type.includes('card')) return 'card'

  return undefined
}

function eventTitle(kind: ApiFootballBroadcastEventKind) {
  if (kind === 'goal') return '득점'
  if (kind === 'own-goal') return '자책골'
  if (kind === 'penalty-missed') return '페널티킥 실축'
  if (kind === 'goal-cancelled') return '득점 취소'
  if (kind === 'substitution') return '선수 교체'
  if (kind === 'yellow-card') return '경고'
  if (kind === 'red-card') return '퇴장'
  if (kind === 'var') return 'VAR 판독'
  return '카드'
}

function eventDetail(kind: ApiFootballBroadcastEventKind, event: ApiFootballEventItem) {
  const rawDetail = event.comments?.trim() || event.detail?.trim() || event.type?.trim()
  const detail = rawDetail?.toLowerCase()
  const detailMap: Record<string, string> = {
    'normal goal': '필드골',
    'own goal': '자책골',
    penalty: '페널티킥',
    'missed penalty': '페널티킥 실축',
    'yellow card': '옐로카드',
    'red card': '레드카드',
    'second yellow card': '경고 누적 퇴장',
    substitution: '선수 교체',
    'goal cancelled': '득점 취소',
    'goal disallowed': '득점 취소',
    'goal confirmed': '득점 인정',
    'penalty confirmed': '페널티킥 확정',
    'penalty cancelled': '페널티킥 취소',
    'card upgrade': '카드 격상',
    'card reviewed': '카드 판독',
    'red card cancelled': '퇴장 취소',
  }

  if (detail && detailMap[detail]) return detailMap[detail]
  if (kind === 'goal') return '득점 상황'
  if (kind === 'own-goal') return '자책골'
  if (kind === 'penalty-missed') return '페널티킥 실축'
  if (kind === 'goal-cancelled') return '득점 취소'
  if (kind === 'substitution') return '선수 교체'
  if (kind === 'yellow-card') return '옐로카드'
  if (kind === 'red-card') return '레드카드'
  if (kind === 'card') return '카드'
  if (kind === 'var') return rawDetail ?? 'VAR 판독'
  return rawDetail ?? '카드'
}

function eventIdPart(value: unknown, fallback = '0') {
  const text = value === undefined || value === null || value === '' ? fallback : String(value)
  return text.trim().replace(/\s+/g, '_')
}

function stableEventId(event: ApiFootballEventItem) {
  return [
    eventIdPart(event.time?.elapsed),
    eventIdPart(event.time?.extra),
    eventIdPart(event.type, 'event'),
    eventIdPart(event.detail, 'detail'),
    eventIdPart(event.team?.id, 'team'),
    eventIdPart(event.player?.id, 'player'),
    eventIdPart(event.assist?.id, 'assist'),
  ].join('-')
}

type EventPlayerMeta = {
  number?: number
  photoUrl?: string
}

function buildEventPlayerMetaMap(
  lineups: ApiFootballLineupItem[],
  playerPhotos: Map<number, string>,
) {
  const meta = new Map<number, EventPlayerMeta>()

  const upsert = (id: number | undefined, number?: number | null) => {
    if (id === undefined) return
    const previous = meta.get(id) ?? {}
    meta.set(id, {
      ...previous,
      number: number ?? previous.number,
      photoUrl: playerPhotos.get(id) ?? previous.photoUrl,
    })
  }

  lineups.forEach((lineup) => {
    ;(lineup.startXI ?? []).forEach((entry) => {
      upsert(entry.player?.id, entry.player?.number)
    })
    ;(lineup.substitutes ?? []).forEach((entry) => {
      upsert(entry.player?.id, entry.player?.number)
    })
  })

  playerPhotos.forEach((photoUrl, id) => {
    const previous = meta.get(id) ?? {}
    meta.set(id, { ...previous, photoUrl })
  })

  return meta
}

function buildEventPlayerMetaMapFromBroadcastLineups(
  lineups: ApiFootballBroadcastLineup[],
  playerPhotos: Map<number, string>,
) {
  const meta = new Map<number, EventPlayerMeta>()

  lineups.forEach((lineup) => {
    lineup.players.forEach((player) => {
      if (player.id === undefined) return
      meta.set(player.id, {
        number: player.no,
        photoUrl: playerPhotos.get(player.id) ?? player.photoUrl,
      })
    })
  })

  playerPhotos.forEach((photoUrl, id) => {
    const previous = meta.get(id) ?? {}
    meta.set(id, { ...previous, photoUrl })
  })

  return meta
}

function normalizeEvents(
  fixture: ApiFootballFixtureItem,
  events: ApiFootballEventItem[],
  teamCodes: { home?: string, away?: string },
  playerMeta = new Map<number, EventPlayerMeta>(),
): ApiFootballBroadcastEvent[] {
  const homeCode = compactCode(teamCodes.home ?? fixture.teams?.home?.code, 'Home')
  const awayCode = compactCode(teamCodes.away ?? fixture.teams?.away?.code, 'Away')
  const homeId = fixture.teams?.home?.id
  const awayId = fixture.teams?.away?.id

  return events.flatMap((event) => {
    const kind = eventKind(event)
    if (!kind) return []

    const teamCode = event.team?.id === awayId ? awayCode : homeCode
    const opponentCode = event.team?.id === awayId ? homeCode : awayCode
    const playerMetaEntry = event.player?.id !== undefined ? playerMeta.get(event.player.id) : undefined
    const assistMetaEntry = event.assist?.id !== undefined ? playerMeta.get(event.assist.id) : undefined
    const teamLogoUrl = event.team?.logo
      ?? (event.team?.id === homeId
        ? fixture.teams?.home?.logo
        : event.team?.id === awayId
          ? fixture.teams?.away?.logo
          : undefined)

    return {
      id: stableEventId(event),
      kind,
      teamId: event.team?.id,
      teamCode,
      opponentCode,
      teamLogoUrl: teamLogoUrl ?? undefined,
      minute: minuteFromEvent(event),
      title: eventTitle(kind),
      detail: eventDetail(kind, event),
      playerId: event.player?.id,
      player: event.player?.name ?? undefined,
      playerNumber: playerMetaEntry?.number,
      playerPhotoUrl: playerMetaEntry?.photoUrl,
      assistId: event.assist?.id,
      assist: event.assist?.name ?? undefined,
      assistNumber: assistMetaEntry?.number,
      assistPhotoUrl: assistMetaEntry?.photoUrl,
      score: kind === 'goal' || kind === 'own-goal' ? scoreFromFixture(fixture) : undefined,
      inPlayer: kind === 'substitution' ? event.assist?.name ?? undefined : undefined,
      inPlayerNumber: kind === 'substitution' ? assistMetaEntry?.number : undefined,
      inPlayerPhotoUrl: kind === 'substitution' ? assistMetaEntry?.photoUrl : undefined,
      outPlayer: kind === 'substitution' ? event.player?.name ?? undefined : undefined,
      outPlayerNumber: kind === 'substitution' ? playerMetaEntry?.number : undefined,
      outPlayerPhotoUrl: kind === 'substitution' ? playerMetaEntry?.photoUrl : undefined,
    }
  })
}

function normalizeRating(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === '') return undefined

  const parsed = Number.parseFloat(String(value))
  return Number.isFinite(parsed) ? parsed.toFixed(1) : undefined
}

function normalizePlayerStatNumber(value: number | string | null | undefined): number | undefined {
  if (value === null || value === undefined || value === '') return undefined
  const parsed = Number.parseFloat(String(value))
  return Number.isFinite(parsed) ? parsed : undefined
}

function buildPlayerStatMap(fixturePlayers: ApiFootballFixturePlayerItem[]) {
  const statsById = new Map<number, ApiFootballBroadcastLineupPlayerStat>()

  fixturePlayers.forEach((teamPlayers) => {
    ;(teamPlayers.players ?? []).forEach((entry) => {
      const id = entry.player?.id
      const stat = entry.statistics?.[0]
      const games = stat?.games

      if (id === undefined) return
      const passesTotal = normalizePlayerStatNumber(stat?.passes?.total)
      const passesAccurate = normalizePlayerStatNumber(stat?.passes?.accuracy)
      const passesAccuracyPct =
        passesTotal !== undefined && passesTotal > 0 && passesAccurate !== undefined
          ? Math.round((passesAccurate / passesTotal) * 100)
          : undefined

      statsById.set(id, {
        minutes: games ? normalizePlayerStatNumber(games.minutes) : undefined,
        rating: games ? normalizeRating(games.rating) : undefined,
        shotsTotal: normalizePlayerStatNumber(stat?.shots?.total),
        shotsOnGoal: normalizePlayerStatNumber(stat?.shots?.on),
        passesTotal,
        passesAccurate,
        passesAccuracyPct,
        keyPasses: normalizePlayerStatNumber(stat?.passes?.key),
        foulsCommitted: normalizePlayerStatNumber(stat?.fouls?.committed),
        statGoals: normalizePlayerStatNumber(stat?.goals?.total),
        statAssists: normalizePlayerStatNumber(stat?.goals?.assists),
        saves: normalizePlayerStatNumber(stat?.goals?.saves),
        goalsConceded: normalizePlayerStatNumber(stat?.goals?.conceded),
        tacklesTotal: normalizePlayerStatNumber(stat?.tackles?.total),
        blocks: normalizePlayerStatNumber(stat?.tackles?.blocks),
        interceptions: normalizePlayerStatNumber(stat?.tackles?.interceptions),
        duelsTotal: normalizePlayerStatNumber(stat?.duels?.total),
        duelsWon: normalizePlayerStatNumber(stat?.duels?.won),
        dribblesAttempts: normalizePlayerStatNumber(stat?.dribbles?.attempts),
        dribblesSuccess: normalizePlayerStatNumber(stat?.dribbles?.success),
        statYellowCards: normalizePlayerStatNumber(stat?.cards?.yellow),
        statRedCards: normalizePlayerStatNumber(stat?.cards?.red),
      })
    })
  })

  return statsById
}

function buildPlayerRatingMap(fixturePlayers: ApiFootballFixturePlayerItem[]) {
  const ratings = new Map<number, string>()
  fixturePlayers.forEach((teamPlayers) => {
    ;(teamPlayers.players ?? []).forEach((entry) => {
      const id = entry.player?.id
      const rating = normalizeRating(entry.statistics?.find((stat) => stat.games?.rating)?.games?.rating)
      if (id !== undefined && rating) {
        ratings.set(id, rating)
      }
    })
  })
  return ratings
}

function buildPlayerPhotoMap(fixturePlayers: ApiFootballFixturePlayerItem[]) {
  const photos = new Map<number, string>()
  fixturePlayers.forEach((teamPlayers) => {
    ;(teamPlayers.players ?? []).forEach((entry) => {
      const id = entry.player?.id
      const photo = entry.player?.photo?.trim()
      if (id !== undefined && photo) {
        photos.set(id, photo)
      }
    })
  })
  return photos
}

function mergePlayerRatingMap(
  previousSnapshot: ApiFootballBroadcastSnapshot,
  fixturePlayers: ApiFootballFixturePlayerItem[],
) {
  const ratings = playerRatingMapFromSnapshot(previousSnapshot)
  buildPlayerRatingMap(fixturePlayers).forEach((rating, id) => {
    ratings.set(id, rating)
  })
  return ratings
}

function refreshLineupRatings(
  lineups: ApiFootballBroadcastLineup[],
  playerRatings: Map<number, string>,
  playerPhotos = new Map<number, string>(),
  playerStats = new Map<number, ApiFootballBroadcastLineupPlayerStat>(),
) {
  return lineups.map((lineup) => ({
    ...lineup,
    players: lineup.players.map((player) => ({
      ...player,
      rating: player.id !== undefined ? playerRatings.get(player.id) ?? player.rating : player.rating,
      photoUrl: player.id !== undefined ? playerPhotos.get(player.id) ?? player.photoUrl : player.photoUrl,
      ...((player.id !== undefined ? playerStats.get(player.id) : undefined) ?? {}),
    })),
  }))
}

function buildSubstituteNumberMap(substitutes: ApiFootballLineupItem['substitutes']) {
  return Object.fromEntries(
    (substitutes ?? []).flatMap((entry) => {
      const id = entry.player?.id
      const number = entry.player?.number
      if (id === undefined || number === null || number === undefined) {
        return []
      }

      return [[String(id), number]]
    }),
  )
}

function normalizeLineups(
  lineups: ApiFootballLineupItem[],
  playerRatings: Map<number, string>,
  playerPhotos = new Map<number, string>(),
  playerStats = new Map<number, ApiFootballBroadcastLineupPlayerStat>(),
): ApiFootballBroadcastLineup[] {
  const normalizeLineupPlayer = (
    entry: {
      player?: {
        id?: number
        name?: string | null
        number?: number | null
        pos?: string | null
        grid?: string | null
      }
    },
    index: number,
  ): ApiFootballBroadcastLineupPlayer => ({
    id: entry.player?.id,
    no: entry.player?.number ?? index + 1,
    name: entry.player?.name ?? `선수 ${index + 1}`,
    longName: entry.player?.name ?? `선수 ${index + 1}`,
    pos: entry.player?.pos ?? undefined,
    grid: entry.player?.grid ?? undefined,
    rating: entry.player?.id !== undefined ? playerRatings.get(entry.player.id) : undefined,
    photoUrl: entry.player?.id !== undefined ? playerPhotos.get(entry.player.id) : undefined,
    ...((entry.player?.id !== undefined ? playerStats.get(entry.player.id) : undefined) ?? {}),
  })

  const normalizeCoach = (
    coach: ApiFootballLineupItem['coach'],
  ): ApiFootballBroadcastCoach | undefined => {
    if (!coach?.name) return undefined

    return {
      id: coach.id,
      name: coach.name,
      longName: coach.name,
      photoUrl: coach.photo ?? undefined,
    }
  }

  return lineups.map((lineup) => ({
    teamId: lineup.team?.id,
    name: lineup.team?.name ?? '미정 팀',
    code: compactCode(lineup.team?.code),
    shape: lineup.formation ?? '4-3-3',
    coach: normalizeCoach(lineup.coach),
    players: (lineup.startXI ?? []).slice(0, 11).map(normalizeLineupPlayer),
    substituteNumbers: buildSubstituteNumberMap(lineup.substitutes),
  }))
}

const statTypeMap = new Map([
  ['Ball Possession', '점유율'],
  ['expected_goals', 'xG'],
  ['Expected Goals', 'xG'],
  ['Total Shots', '전체슈팅'],
  ['Shots on Goal', '유효슈팅'],
  ['Shots insidebox', '박스안슈팅'],
  ['Shots outsidebox', '박스밖슈팅'],
  ['Blocked Shots', '블록슈팅'],
  ['Goalkeeper Saves', '세이브'],
  ['Corner Kicks', '코너킥'],
  ['Total passes', '전체패스'],
  ['Passes accurate', '패스성공'],
  ['Passes %', '패스성공률'],
  ['Yellow Cards', '옐로카드'],
  ['Red Cards', '레드카드'],
  ['Fouls', '파울'],
  ['Offsides', '오프사이드'],
])

function normalizeStatistics(statistics: ApiFootballStatisticsItem[]): ApiFootballBroadcastStat[] {
  const [homeStats, awayStats] = statistics
  if (!homeStats?.statistics?.length && !awayStats?.statistics?.length) {
    return []
  }

  const homeMap = new Map(
    (homeStats?.statistics ?? []).map((stat) => [stat.type ?? '', valueToString(stat.value)]),
  )
  const awayMap = new Map(
    (awayStats?.statistics ?? []).map((stat) => [stat.type ?? '', valueToString(stat.value)]),
  )

  return Array.from(statTypeMap.entries()).flatMap(([apiType, label]) => {
    if (!homeMap.has(apiType) && !awayMap.has(apiType)) {
      return []
    }

    const home = homeMap.get(apiType) ?? '0'
    const away = awayMap.get(apiType) ?? '0'
    const pct = pairedPct(home, away)

    return [{
      label,
      home,
      away,
      homePct: pct.homePct,
      awayPct: pct.awayPct,
    }]
  })
}

async function fetchTeamCode(teamId: number | undefined) {
  if (teamId === undefined) return undefined

  const [team] = await apiFootballGet<ApiFootballTeamItem>('/teams', { id: teamId })
  return usableCode(team?.team?.code)
}

async function resolveFixtureTeamCodes(fixture: ApiFootballFixtureItem) {
  const homeFixtureCode = usableCode(fixture.teams?.home?.code)
  const awayFixtureCode = usableCode(fixture.teams?.away?.code)
  const [homeApiCode, awayApiCode] = await Promise.all([
    homeFixtureCode ? Promise.resolve(homeFixtureCode) : fetchTeamCode(fixture.teams?.home?.id),
    awayFixtureCode ? Promise.resolve(awayFixtureCode) : fetchTeamCode(fixture.teams?.away?.id),
  ])

  return {
    home: homeApiCode,
    away: awayApiCode,
  }
}

function normalizeSnapshot(
  fixture: ApiFootballFixtureItem,
  events: ApiFootballEventItem[],
  lineups: ApiFootballLineupItem[],
  statistics: ApiFootballStatisticsItem[],
  fixturePlayers: ApiFootballFixturePlayerItem[],
  teamCodes: { home?: string, away?: string },
): ApiFootballBroadcastSnapshot {
  const home = fixture.teams?.home?.name ?? '홈'
  const away = fixture.teams?.away?.name ?? '원정'
  const playerRatings = buildPlayerRatingMap(fixturePlayers)
  const playerPhotos = buildPlayerPhotoMap(fixturePlayers)
  const playerStats = buildPlayerStatMap(fixturePlayers)
  const eventPlayerMeta = buildEventPlayerMetaMap(lineups, playerPhotos)
  const homeEnglishCode = compactCode(teamCodes.home ?? fixture.teams?.home?.code, 'Home')
  const awayEnglishCode = compactCode(teamCodes.away ?? fixture.teams?.away?.code, 'Away')

  return {
    fixtureId: fixture.fixture?.id ?? 0,
    leagueId: fixture.league?.id,
    leagueName: fixture.league?.name ?? 'API-Football 라이브',
    season: fixture.league?.season,
    home,
    away,
    homeId: fixture.teams?.home?.id,
    awayId: fixture.teams?.away?.id,
    homeCode: homeEnglishCode,
    awayCode: awayEnglishCode,
    homeEnglishCode,
    awayEnglishCode,
    homeLogoUrl: fixture.teams?.home?.logo ?? undefined,
    awayLogoUrl: fixture.teams?.away?.logo ?? undefined,
    score: scoreFromFixture(fixture),
    clock: clockFromFixture(fixture),
    addedTime: addedTimeFromFixture(fixture),
    status: statusFromFixture(fixture),
    venue: fixture.fixture?.venue?.name ?? '라이브 경기장',
    lineups: normalizeLineups(lineups, playerRatings, playerPhotos, playerStats),
    playerStats: Object.fromEntries(
      Array.from(playerStats.entries()).map(([id, stat]) => [String(id), stat]),
    ),
    playerRatings: Object.fromEntries(playerRatings),
    stats: normalizeStatistics(statistics),
    events: normalizeEvents(fixture, events, teamCodes, eventPlayerMeta),
  }
}

function uniqueNumbers(values: Array<number | undefined>): number[] {
  return [...new Set(values.filter((value): value is number => Number.isSafeInteger(value)))]
}

function uniqueNames(values: Array<string | undefined>): string[] {
  return [...new Set(values.map((value) => value?.trim()).filter((value): value is string => Boolean(value)))]
}

function normalizeNameKey(value: string | undefined) {
  return value?.trim().toLowerCase() ?? ''
}

function translatedName(
  translations: Record<string, BroadcastTranslationValue> | undefined,
  externalId: number | undefined,
  nameTranslations: Record<string, BroadcastTranslationValue> | undefined,
  fallback: string,
) {
  return (
    (externalId !== undefined ? translations?.[String(externalId)]?.name_ko : undefined)
    ?? nameTranslations?.[normalizeNameKey(fallback)]?.name_ko
    ?? fallback
  )
}

function translatedShortName(
  translations: Record<string, BroadcastTranslationValue> | undefined,
  externalId: number | undefined,
  nameTranslations: Record<string, BroadcastTranslationValue> | undefined,
  fallback: string,
) {
  const row = (
    externalId !== undefined
      ? translations?.[String(externalId)]
      : undefined
  ) ?? nameTranslations?.[normalizeNameKey(fallback)]
  return row?.short_name_ko ?? row?.name_ko ?? fallback
}

async function fetchBroadcastTranslations(
  snapshot: ApiFootballBroadcastSnapshot,
): Promise<BroadcastTranslationResponse | null> {
  const lineupPlayers = snapshot.lineups.flatMap((lineup) => lineup.players)
  const lineupCoaches = snapshot.lineups.flatMap((lineup) => lineup.coach ? [lineup.coach] : [])
  const playerIds = uniqueNumbers([
    ...lineupPlayers.map((player) => player.id),
    ...snapshot.events.flatMap((event) => [event.playerId, event.assistId]),
  ])

  const response = await fetch(apiUrl('/api/v1/broadcast/translations'), {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      league_ids: uniqueNumbers([snapshot.leagueId]),
      league_names: uniqueNames([snapshot.leagueName]),
      team_ids: uniqueNumbers([snapshot.homeId, snapshot.awayId, ...snapshot.lineups.map((lineup) => lineup.teamId)]),
      team_names: uniqueNames([snapshot.home, snapshot.away, ...snapshot.lineups.map((lineup) => lineup.name)]),
      player_ids: playerIds,
      player_names: uniqueNames([
        ...lineupPlayers.map((player) => player.name),
        ...snapshot.events.flatMap((event) => [event.player, event.assist, event.inPlayer, event.outPlayer]),
      ]),
      coach_ids: uniqueNumbers(lineupCoaches.map((coach) => coach.id)),
      coach_names: uniqueNames(lineupCoaches.map((coach) => coach.name)),
    }),
  })

  if (!response.ok) {
    throw new Error(`방송 번역 요청 실패: ${response.status}`)
  }

  return (await response.json()) as BroadcastTranslationResponse
}

async function applyBroadcastTranslations(
  snapshot: ApiFootballBroadcastSnapshot,
): Promise<ApiFootballBroadcastSnapshot> {
  let translations: BroadcastTranslationResponse | null = null
  try {
    translations = await fetchBroadcastTranslations(snapshot)
  } catch (error) {
    console.error('Failed to fetch broadcast Korean translations', error)
    return snapshot
  }

  const teamTranslations = translations?.teams
  const teamNameTranslations = translations?.team_names
  const playerTranslations = translations?.players
  const playerNameTranslations = translations?.player_names
  const leagueTranslations = translations?.leagues
  const leagueNameTranslations = translations?.league_names
  const coachTranslations = translations?.coaches
  const coachNameTranslations = translations?.coach_names
  const translatedLineups = snapshot.lineups.map((lineup) => ({
    ...lineup,
    name: translatedName(teamTranslations, lineup.teamId, teamNameTranslations, lineup.name),
    code: translatedShortName(teamTranslations, lineup.teamId, teamNameTranslations, lineup.name),
    coach: lineup.coach
      ? {
          ...lineup.coach,
          longName: translatedName(
            coachTranslations,
            lineup.coach.id,
            coachNameTranslations,
            lineup.coach.longName ?? lineup.coach.name,
          ),
          name: translatedShortName(
            coachTranslations,
            lineup.coach.id,
            coachNameTranslations,
            lineup.coach.name,
          ),
        }
      : undefined,
    players: lineup.players.map((player) => ({
      ...player,
      longName: translatedName(playerTranslations, player.id, playerNameTranslations, player.longName ?? player.name),
      name: translatedShortName(playerTranslations, player.id, playerNameTranslations, player.name),
    })),
  }))
  const translatedHomeCode = translatedShortName(
    teamTranslations,
    snapshot.homeId,
    teamNameTranslations,
    snapshot.home,
  )
  const translatedAwayCode = translatedShortName(
    teamTranslations,
    snapshot.awayId,
    teamNameTranslations,
    snapshot.away,
  )

  const translatedEvents = snapshot.events.map((event) => ({
    ...event,
    teamCode: translatedShortName(
      teamTranslations,
      event.teamId,
      teamNameTranslations,
      event.teamCode,
    ),
    opponentCode: event.teamId === snapshot.homeId
      ? translatedAwayCode
      : event.teamId === snapshot.awayId
        ? translatedHomeCode
        : event.opponentCode,
    player: event.player
      ? translatedName(playerTranslations, event.playerId, playerNameTranslations, event.player)
      : undefined,
    assist: event.assist
      ? translatedName(playerTranslations, event.assistId, playerNameTranslations, event.assist)
      : undefined,
    playerShortName: event.player
      ? translatedShortName(playerTranslations, event.playerId, playerNameTranslations, event.player)
      : undefined,
    assistShortName: event.assist
      ? translatedShortName(playerTranslations, event.assistId, playerNameTranslations, event.assist)
      : undefined,
    inPlayer: event.inPlayer
      ? translatedName(playerTranslations, event.assistId, playerNameTranslations, event.inPlayer)
      : event.inPlayer,
    inPlayerShortName: event.inPlayer
      ? translatedShortName(playerTranslations, event.assistId, playerNameTranslations, event.inPlayer)
      : event.inPlayer,
    outPlayer: event.outPlayer
      ? translatedName(playerTranslations, event.playerId, playerNameTranslations, event.outPlayer)
      : event.outPlayer,
    outPlayerShortName: event.outPlayer
      ? translatedShortName(playerTranslations, event.playerId, playerNameTranslations, event.outPlayer)
      : event.outPlayer,
  }))

  return {
    ...snapshot,
    leagueName: translatedName(
      leagueTranslations,
      snapshot.leagueId,
      leagueNameTranslations,
      snapshot.leagueName,
    ),
    leagueShortName: translatedShortName(
      leagueTranslations,
      snapshot.leagueId,
      leagueNameTranslations,
      snapshot.leagueName,
    ),
    home: translatedName(teamTranslations, snapshot.homeId, teamNameTranslations, snapshot.home),
    away: translatedName(teamTranslations, snapshot.awayId, teamNameTranslations, snapshot.away),
    homeCode: translatedHomeCode,
    awayCode: translatedAwayCode,
    lineups: translatedLineups,
    events: translatedEvents,
  }
}

export async function fetchApiFootballBroadcastInitialSnapshot(
  fixtureId: number,
): Promise<ApiFootballBroadcastSnapshot> {
  const [fixture] = await apiFootballGet<ApiFootballFixtureItem>('/fixtures', { id: fixtureId })
  if (!fixture) {
    throw new Error(`API-Football 경기 ${fixtureId}를 찾을 수 없습니다`)
  }

  const [events, lineups, statistics, fixturePlayers, teamCodes] = await Promise.all([
    apiFootballGet<ApiFootballEventItem>('/fixtures/events', { fixture: fixtureId }),
    apiFootballGet<ApiFootballLineupItem>('/fixtures/lineups', { fixture: fixtureId }),
    apiFootballGet<ApiFootballStatisticsItem>('/fixtures/statistics', { fixture: fixtureId }),
    apiFootballGet<ApiFootballFixturePlayerItem>('/fixtures/players', { fixture: fixtureId }),
    resolveFixtureTeamCodes(fixture),
  ])

  return applyBroadcastTranslations(normalizeSnapshot(fixture, events, lineups, statistics, fixturePlayers, teamCodes))
}

export async function fetchApiFootballBroadcastTickSnapshot(
  fixtureId: number,
  previousSnapshot: ApiFootballBroadcastSnapshot,
): Promise<ApiFootballBroadcastSnapshot> {
  const [fixture] = await apiFootballGet<ApiFootballFixtureItem>('/fixtures', { id: fixtureId })
  if (!fixture) {
    throw new Error(`API-Football 경기 ${fixtureId}를 찾을 수 없습니다`)
  }

  const [events, statistics, fixturePlayers] = await Promise.all([
    apiFootballGet<ApiFootballEventItem>('/fixtures/events', { fixture: fixtureId }),
    apiFootballGet<ApiFootballStatisticsItem>('/fixtures/statistics', { fixture: fixtureId }),
    apiFootballGet<ApiFootballFixturePlayerItem>('/fixtures/players', { fixture: fixtureId }),
  ])
  const teamCodes = {
    home: previousSnapshot.homeEnglishCode,
    away: previousSnapshot.awayEnglishCode,
  }
  const playerRatings = mergePlayerRatingMap(previousSnapshot, fixturePlayers)
  const playerPhotos = buildPlayerPhotoMap(fixturePlayers)
  const playerStats = buildPlayerStatMap(fixturePlayers)
  const eventPlayerMeta = buildEventPlayerMetaMapFromBroadcastLineups(previousSnapshot.lineups, playerPhotos)
  const tickSnapshot: ApiFootballBroadcastSnapshot = {
    ...previousSnapshot,
    fixtureId: fixture.fixture?.id ?? previousSnapshot.fixtureId,
    leagueId: fixture.league?.id ?? previousSnapshot.leagueId,
    leagueName: fixture.league?.name ?? previousSnapshot.leagueName,
    season: fixture.league?.season ?? previousSnapshot.season,
    home: fixture.teams?.home?.name ?? previousSnapshot.home,
    away: fixture.teams?.away?.name ?? previousSnapshot.away,
    homeId: fixture.teams?.home?.id ?? previousSnapshot.homeId,
    awayId: fixture.teams?.away?.id ?? previousSnapshot.awayId,
    homeLogoUrl: fixture.teams?.home?.logo ?? previousSnapshot.homeLogoUrl,
    awayLogoUrl: fixture.teams?.away?.logo ?? previousSnapshot.awayLogoUrl,
    score: scoreFromFixture(fixture),
    clock: clockFromFixture(fixture),
    addedTime: addedTimeFromFixture(fixture),
    status: statusFromFixture(fixture),
    venue: fixture.fixture?.venue?.name ?? previousSnapshot.venue,
    lineups: refreshLineupRatings(previousSnapshot.lineups, playerRatings, playerPhotos, playerStats),
    playerStats: Object.fromEntries(
      Array.from(playerStats.entries()).map(([id, stat]) => [String(id), stat]),
    ),
    playerRatings: Object.fromEntries(playerRatings),
    stats: normalizeStatistics(statistics),
    events: normalizeEvents(fixture, events, teamCodes, eventPlayerMeta),
  }

  return applyBroadcastTranslations(tickSnapshot)
}

function playerRatingMapFromSnapshot(snapshot: ApiFootballBroadcastSnapshot) {
  const ratings = new Map<number, string>()
  Object.entries(snapshot.playerRatings).forEach(([id, rating]) => {
    const parsedId = Number.parseInt(id, 10)
    if (Number.isSafeInteger(parsedId) && rating) {
      ratings.set(parsedId, rating)
    }
  })
  return ratings
}

export async function fetchApiFootballBroadcastLineupsSnapshot(
  fixtureId: number,
  previousSnapshot: ApiFootballBroadcastSnapshot,
): Promise<ApiFootballBroadcastSnapshot> {
  const lineups = await apiFootballGet<ApiFootballLineupItem>('/fixtures/lineups', { fixture: fixtureId })
  if (lineups.length === 0) {
    return previousSnapshot
  }

  const teamColors = new Map(
    previousSnapshot.lineups
      .filter((lineup) => lineup.teamId !== undefined)
      .map((lineup) => [
        lineup.teamId as number,
        {
          primaryColor: lineup.primaryColor,
          secondaryColor: lineup.secondaryColor,
          accentColor: lineup.accentColor,
          scoreboardColorMode: lineup.scoreboardColorMode,
        },
      ]),
  )
  const refreshedLineups = normalizeLineups(
    lineups,
    playerRatingMapFromSnapshot(previousSnapshot),
  ).map((lineup) => ({
    ...lineup,
    primaryColor: lineup.teamId !== undefined
      ? teamColors.get(lineup.teamId)?.primaryColor ?? lineup.primaryColor
      : lineup.primaryColor,
    secondaryColor: lineup.teamId !== undefined
      ? teamColors.get(lineup.teamId)?.secondaryColor ?? lineup.secondaryColor
      : lineup.secondaryColor,
    accentColor: lineup.teamId !== undefined
      ? teamColors.get(lineup.teamId)?.accentColor ?? lineup.accentColor
      : lineup.accentColor,
    scoreboardColorMode: lineup.teamId !== undefined
      ? teamColors.get(lineup.teamId)?.scoreboardColorMode ?? lineup.scoreboardColorMode
      : lineup.scoreboardColorMode,
  }))

  return applyBroadcastTranslations({
    ...previousSnapshot,
    lineups: refreshedLineups,
  })
}

export async function fetchApiFootballBroadcastSnapshot(
  fixtureId: number,
): Promise<ApiFootballBroadcastSnapshot> {
  return fetchBroadcastProgramSnapshot(`/api/v1/broadcast/fixtures/${fixtureId}/program-snapshot`)
}

export async function fetchApiFootballAiReview(
  fixtureId: number,
  options: { forceRefresh?: boolean } = {},
): Promise<ApiFootballAiReviewResponse> {
  const response = await fetch(apiUrl(`/api/v1/broadcast/fixtures/${fixtureId}/ai-review`), {
    method: 'POST',
    headers: {
      ...broadcastProgramHeaders(),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ forceRefresh: options.forceRefresh === true }),
  })

  if (!response.ok) {
    throw new Error(`AI 경기리뷰 요청 실패: ${response.status}`)
  }

  return (await response.json()) as ApiFootballAiReviewResponse
}

export async function fetchApiFootballLiveGroupStandings(
  fixtureId: number,
): Promise<ApiFootballLiveGroupStandingsResponse> {
  const response = await fetch(apiUrl(`/api/v1/broadcast/fixtures/${fixtureId}/live-group-standings`), {
    headers: broadcastProgramHeaders(),
  })

  if (!response.ok) {
    throw new Error(`실시간 조별상황 요청 실패: ${response.status}`)
  }

  return (await response.json()) as ApiFootballLiveGroupStandingsResponse
}

export async function fetchFixtureStandings(
  fixtureId: number,
): Promise<ApiFootballBroadcastStandings | null> {
  const response = await fetch(apiUrl(`/api/v1/fixtures/${fixtureId}/league-standings`), {
    headers: { Accept: 'application/json' },
  })

  if (!response.ok) {
    return null
  }

  const payload = (await response.json()) as ApiLeagueStandingsResponse
  const rows = payload.rows

  if (!Array.isArray(rows) || rows.length === 0) {
    return null
  }

  return {
    group_name: payload.group_name ?? '',
    rows: rows.map((row) => ({
      rank: row.rank ?? 0,
      team_id: row.team?.external_id ?? 0,
      team_name: row.team?.name_ko ?? row.team?.name ?? '',
      team_code: row.team?.short_name_ko ?? row.team?.name_ko ?? row.team?.name ?? '',
      played: row.played ?? 0,
      win: row.win ?? 0,
      draw: row.draw ?? 0,
      loss: row.loss ?? 0,
      goals_for: row.goals_for ?? 0,
      goals_against: row.goals_against ?? 0,
      goal_diff: row.goal_diff ?? 0,
      points: row.points ?? 0,
    })),
  }
}

export async function fetchApiFootballFirstLiveFixture(): Promise<ApiFootballBroadcastSnapshot> {
  return fetchBroadcastProgramSnapshot('/api/v1/broadcast/program-snapshot/first-live')
}
