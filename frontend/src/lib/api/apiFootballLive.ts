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
      }
    }>
  }>
}

export type ApiFootballBroadcastEventKind =
  | 'goal'
  | 'own-goal'
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
}

export type ApiFootballBroadcastLineup = {
  teamId?: number
  name: string
  code: string
  shape: string
  players: ApiFootballBroadcastLineupPlayer[]
  substituteNumbers: Record<string, number>
}

export type ApiFootballBroadcastStat = {
  label: string
  home: string
  away: string
  homePct: number
  awayPct: number
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
  venue: string
  lineups: ApiFootballBroadcastLineup[]
  playerRatings: Record<string, string>
  stats: ApiFootballBroadcastStat[]
  events: ApiFootballBroadcastEvent[]
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
  return import.meta.env.VITE_BROADCAST_USE_API_FOOTBALL === 'true' || Boolean(API_FOOTBALL_KEY)
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
) {
  return lineups.map((lineup) => ({
    ...lineup,
    players: lineup.players.map((player) => ({
      ...player,
      rating: player.id !== undefined ? playerRatings.get(player.id) ?? player.rating : player.rating,
      photoUrl: player.id !== undefined ? playerPhotos.get(player.id) ?? player.photoUrl : player.photoUrl,
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
  })

  return lineups.map((lineup) => ({
    teamId: lineup.team?.id,
    name: lineup.team?.name ?? '미정 팀',
    code: compactCode(lineup.team?.code),
    shape: lineup.formation ?? '4-3-3',
    players: (lineup.startXI ?? []).slice(0, 11).map(normalizeLineupPlayer),
    substituteNumbers: buildSubstituteNumberMap(lineup.substitutes),
  }))
}

const statTypeMap = new Map([
  ['Ball Possession', '점유율'],
  ['Total Shots', '전체슈팅'],
  ['Shots on Goal', '유효슈팅'],
  ['Corner Kicks', '코너킥'],
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
    lineups: normalizeLineups(lineups, playerRatings, playerPhotos),
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
      coach_ids: [],
      coach_names: [],
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
  const translatedLineups = snapshot.lineups.map((lineup) => ({
    ...lineup,
    name: translatedName(teamTranslations, lineup.teamId, teamNameTranslations, lineup.name),
    code: translatedShortName(teamTranslations, lineup.teamId, teamNameTranslations, lineup.name),
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
    lineups: refreshLineupRatings(previousSnapshot.lineups, playerRatings, playerPhotos),
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

  return applyBroadcastTranslations({
    ...previousSnapshot,
    lineups: normalizeLineups(lineups, playerRatingMapFromSnapshot(previousSnapshot)),
  })
}

export async function fetchApiFootballBroadcastSnapshot(
  fixtureId: number,
): Promise<ApiFootballBroadcastSnapshot> {
  return fetchApiFootballBroadcastInitialSnapshot(fixtureId)
}

export async function fetchApiFootballFirstLiveFixture(): Promise<ApiFootballBroadcastSnapshot> {
  const [fixture] = await apiFootballGet<ApiFootballFixtureItem>('/fixtures', { live: 'all' })
  if (!fixture?.fixture?.id) {
    throw new Error('현재 사용 가능한 API-Football 라이브 경기가 없습니다')
  }

  return fetchApiFootballBroadcastInitialSnapshot(fixture.fixture.id)
}
