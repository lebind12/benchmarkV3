<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import goalIconUrl from '@/assets/broadcast/goal-soccer-ball.svg?url'
import redCardIconUrl from '@/assets/broadcast/red-card.svg?url'
import substitutionIconUrl from '@/assets/broadcast/substitution.svg?url'
import yellowCardIconUrl from '@/assets/broadcast/yellow-card.svg?url'
import BroadcastStatsBoard from '@/components/broadcast/BroadcastStatsBoard.vue'
import {
  API_FOOTBALL_LIVE_POLL_MS,
  API_FOOTBALL_LINEUPS_REFRESH_MS,
  fetchApiFootballBroadcastInitialSnapshot,
  fetchApiFootballBroadcastLineupsSnapshot,
  fetchApiFootballBroadcastSnapshot,
  fetchApiFootballBroadcastTickSnapshot,
  fetchApiFootballFirstLiveFixture,
  shouldUseApiFootballLive,
  type ApiFootballBroadcastEvent,
  type ApiFootballBroadcastLineup,
  type ApiFootballBroadcastSnapshot,
} from '@/lib/api/apiFootballLive'
import {
  readBroadcastFixtureId,
  readBroadcastTeamColorMode,
} from '@/lib/broadcastQuery'

type LeagueSlug =
  | 'premier-league'
  | 'champions-league'
  | 'europa-league'
  | 'carabao-cup'
  | 'fa-cup'
  | 'world-cup-2026'

type Theme = {
  slug: LeagueSlug
  label: string
  panel: string
  panelAlt: string
  pitch: string
  pitchAlt: string
  border: string
  text: string
  muted: string
  accent: string
  accentAlt: string
  dark: string
}

type PlayerNode = {
  id?: number
  no: number | '?'
  name: string
  pos?: string
  grid?: string
  rating?: string
  x: number
  y: number
  goals: number
  yellowCard: boolean
  redCard: boolean
  substitution: 'none' | 'in' | 'out'
}

type PitchPoint = {
  x: number
  y: number
}

type FormationLayout = PitchPoint[]

type LineupSide = {
  name: string
  code: string
  primaryColor?: string | null
  secondaryColor?: string | null
  accentColor?: string | null
  shape: string
  players: PlayerNode[]
}

type BroadcastEventKind =
  | 'goal'
  | 'substitution'
  | 'yellow-card'
  | 'var'
  | 'stat'

type BroadcastEvent = {
  id: string
  kind: BroadcastEventKind
  teamCode: string
  opponentCode?: string
  minute: string
  title: string
  detail: string
  player?: string
  playerShortName?: string
  assist?: string
  assistShortName?: string
  score?: string
  inPlayer?: string
  inPlayerShortName?: string
  outPlayer?: string
  outPlayerShortName?: string
  statLabel?: string
  statValue?: string
}

type BroadcastMatch = {
  fixtureId: number
  leagueName: string
  leagueShortName?: string
  home: string
  away: string
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
  lineups: LineupSide[]
  stats: Array<{
    label: string
    home: string
    away: string
    homePct: number
    awayPct: number
  }>
  events: BroadcastEvent[]
}

type LiveStatus = 'loading' | 'ready' | 'error'
type TimeEditorKind = 'clock' | 'added'
type ActiveLineupPlayer = Omit<ApiFootballBroadcastLineup['players'][number], 'no'> & {
  no: number | '?'
}

const manualFormationLayouts: Record<string, FormationLayout> = {
  '3-4-3': [
    { x: 50, y: 88 },
    { x: 24, y: 72 },
    { x: 50, y: 68 },
    { x: 76, y: 72 },
    { x: 12, y: 50 },
    { x: 38, y: 53 },
    { x: 62, y: 53 },
    { x: 88, y: 50 },
    { x: 16, y: 24 },
    { x: 50, y: 16 },
    { x: 84, y: 24 },
  ],
  '3-5-2': [
    { x: 50, y: 88 },
    { x: 24, y: 72 },
    { x: 50, y: 68 },
    { x: 76, y: 72 },
    { x: 10, y: 50 },
    { x: 30, y: 53 },
    { x: 50, y: 56 },
    { x: 70, y: 53 },
    { x: 90, y: 50 },
    { x: 36, y: 18 },
    { x: 64, y: 18 },
  ],
  '3-4-2-1': [
    { x: 50, y: 88 },
    { x: 24, y: 72 },
    { x: 50, y: 68 },
    { x: 76, y: 72 },
    { x: 12, y: 51 },
    { x: 38, y: 54 },
    { x: 62, y: 54 },
    { x: 88, y: 51 },
    { x: 34, y: 30 },
    { x: 66, y: 30 },
    { x: 50, y: 14 },
  ],
  '4-3-3': [
    { x: 50, y: 88 },
    { x: 12, y: 72 },
    { x: 33, y: 73 },
    { x: 67, y: 73 },
    { x: 88, y: 72 },
    { x: 22, y: 49 },
    { x: 50, y: 57 },
    { x: 78, y: 49 },
    { x: 16, y: 25 },
    { x: 50, y: 16 },
    { x: 84, y: 25 },
  ],
  '4-2-3-1': [
    { x: 50, y: 88 },
    { x: 12, y: 73 },
    { x: 33, y: 74 },
    { x: 67, y: 74 },
    { x: 88, y: 73 },
    { x: 32, y: 54 },
    { x: 68, y: 54 },
    { x: 50, y: 37 },
    { x: 16, y: 21 },
    { x: 50, y: 14 },
    { x: 84, y: 21 },
  ],
  '4-1-4-1': [
    { x: 50, y: 88 },
    { x: 12, y: 72 },
    { x: 33, y: 73 },
    { x: 67, y: 73 },
    { x: 88, y: 72 },
    { x: 50, y: 58 },
    { x: 12, y: 42 },
    { x: 38, y: 42 },
    { x: 62, y: 42 },
    { x: 88, y: 42 },
    { x: 50, y: 15 },
  ],
  '4-3-1-2': [
    { x: 50, y: 88 },
    { x: 12, y: 72 },
    { x: 33, y: 73 },
    { x: 67, y: 73 },
    { x: 88, y: 72 },
    { x: 24, y: 51 },
    { x: 50, y: 55 },
    { x: 76, y: 51 },
    { x: 50, y: 34 },
    { x: 36, y: 17 },
    { x: 64, y: 17 },
  ],
  '4-4-2': [
    { x: 50, y: 88 },
    { x: 12, y: 72 },
    { x: 33, y: 73 },
    { x: 67, y: 73 },
    { x: 88, y: 72 },
    { x: 12, y: 49 },
    { x: 38, y: 52 },
    { x: 62, y: 52 },
    { x: 88, y: 49 },
    { x: 36, y: 17 },
    { x: 64, y: 17 },
  ],
  '4-5-1': [
    { x: 50, y: 88 },
    { x: 12, y: 72 },
    { x: 33, y: 73 },
    { x: 67, y: 73 },
    { x: 88, y: 72 },
    { x: 10, y: 48 },
    { x: 30, y: 51 },
    { x: 50, y: 55 },
    { x: 70, y: 51 },
    { x: 90, y: 48 },
    { x: 50, y: 15 },
  ],
  '5-2-3': [
    { x: 50, y: 88 },
    { x: 8, y: 70 },
    { x: 28, y: 74 },
    { x: 50, y: 66 },
    { x: 72, y: 74 },
    { x: 92, y: 70 },
    { x: 34, y: 49 },
    { x: 66, y: 49 },
    { x: 16, y: 23 },
    { x: 50, y: 15 },
    { x: 84, y: 23 },
  ],
  '5-3-2': [
    { x: 50, y: 88 },
    { x: 8, y: 70 },
    { x: 28, y: 74 },
    { x: 50, y: 66 },
    { x: 72, y: 74 },
    { x: 92, y: 70 },
    { x: 25, y: 49 },
    { x: 50, y: 54 },
    { x: 75, y: 49 },
    { x: 36, y: 17 },
    { x: 64, y: 17 },
  ],
  '5-4-1': [
    { x: 50, y: 88 },
    { x: 8, y: 70 },
    { x: 28, y: 74 },
    { x: 50, y: 66 },
    { x: 72, y: 74 },
    { x: 92, y: 70 },
    { x: 12, y: 46 },
    { x: 38, y: 50 },
    { x: 62, y: 50 },
    { x: 88, y: 46 },
    { x: 50, y: 15 },
  ],
}

const goalkeeperPoint: PitchPoint = { x: 50, y: 88 }
const lineXCoordinates: Record<number, number[]> = {
  1: [50],
  2: [35, 65],
  3: [22, 50, 78],
  4: [12, 36, 64, 88],
  5: [8, 29, 50, 71, 92],
  6: [7, 24, 40, 60, 76, 93],
  7: [6, 20, 35, 50, 65, 80, 94],
}
const lineYCoordinates: Record<number, number[]> = {
  2: [72, 22],
  3: [72, 50, 18],
  4: [73, 56, 38, 16],
  5: [74, 59, 44, 29, 14],
  6: [75, 62, 49, 36, 23, 12],
  7: [76, 65, 54, 43, 32, 22, 12],
  8: [77, 67, 57, 47, 37, 28, 20, 12],
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

function roundCoordinate(value: number) {
  return Math.round(value * 10) / 10
}

function normalizeFormationShape(value: string) {
  return value.trim().replace(/[‐‑‒–—]/g, '-')
}

function parseSupportedFormation(value: string): number[] | null {
  const parts = normalizeFormationShape(value)
    .split('-')
    .map((part) => Number.parseInt(part, 10))

  if (
    parts.length < 2
    || parts.some((part) => !Number.isSafeInteger(part) || part <= 0)
    || parts.reduce((total, part) => total + part, 0) !== 10
    || parts[0] < 3
    || parts[0] > 6
    || parts.some((part) => part > 7)
  ) {
    return null
  }

  return parts
}

function composePositiveParts(total: number): number[][] {
  if (total <= 0) return [[]]

  const result: number[][] = []
  for (let value = 1; value <= total; value += 1) {
    composePositiveParts(total - value).forEach((tail) => {
      result.push([value, ...tail])
    })
  }
  return result
}

function linePoints(count: number, y: number, lineIndex: number, lineCount: number): PitchPoint[] {
  const xs = lineXCoordinates[count] ?? lineXCoordinates[1]
  const isDefense = lineIndex === 0
  const isAttack = lineIndex === lineCount - 1
  const centerIndex = (xs.length - 1) / 2

  return xs.map((x, index) => {
    const centerDistance = xs.length <= 1 ? 0 : Math.abs(index - centerIndex) / centerIndex
    let yOffset = 0

    if (xs.length === 1) {
      yOffset = isAttack ? -2 : 1
    } else if (isDefense) {
      yOffset = (1 - centerDistance) * 1.4 - centerDistance * 2
    } else if (isAttack) {
      yOffset = centerDistance * 2.6 - (1 - centerDistance) * 2
    } else {
      yOffset = (1 - centerDistance) * 1.2 - centerDistance * 1.2
    }

    return {
      x: roundCoordinate(x),
      y: roundCoordinate(clamp(y + yOffset, 10, 90)),
    }
  })
}

function buildFormationLayout(parts: number[]): FormationLayout {
  const lineYs = lineYCoordinates[parts.length]
  if (!lineYs) {
    return manualFormationLayouts['4-3-3']
  }

  return [
    goalkeeperPoint,
    ...parts.flatMap((count, lineIndex) => linePoints(count, lineYs[lineIndex], lineIndex, parts.length)),
  ]
}

function buildFormationLayouts() {
  const layouts: Record<string, FormationLayout> = {}
  for (let backLine = 3; backLine <= 6; backLine += 1) {
    composePositiveParts(10 - backLine).forEach((rest) => {
      const parts = [backLine, ...rest]
      layouts[parts.join('-')] = buildFormationLayout(parts)
    })
  }

  return {
    ...layouts,
    ...manualFormationLayouts,
  }
}

const formationLayouts = buildFormationLayouts()

const themes: Record<LeagueSlug, Theme> = {
  'premier-league': {
    slug: 'premier-league',
    label: '프리미어리그',
    panel: '#32105A',
    panelAlt: '#E90052',
    pitch: '#3158A8',
    pitchAlt: '#284B93',
    border: '#04B8D9',
    text: '#FFFFFF',
    muted: '#F2D7FF',
    accent: '#E90052',
    accentAlt: '#04B8D9',
    dark: '#12051F',
  },
  'champions-league': {
    slug: 'champions-league',
    label: 'UEFA 챔피언스리그',
    panel: '#071542',
    panelAlt: '#315DFF',
    pitch: '#203B88',
    pitchAlt: '#182E6F',
    border: '#F1F4FF',
    text: '#FFFFFF',
    muted: '#CAD7FF',
    accent: '#315DFF',
    accentAlt: '#F1F4FF',
    dark: '#02081F',
  },
  'europa-league': {
    slug: 'europa-league',
    label: 'UEFA 유로파리그',
    panel: '#23160A',
    panelAlt: '#FF6A00',
    pitch: '#704018',
    pitchAlt: '#5A3212',
    border: '#FFB000',
    text: '#FFFFFF',
    muted: '#FFE3BD',
    accent: '#FF6A00',
    accentAlt: '#FFB000',
    dark: '#120904',
  },
  'carabao-cup': {
    slug: 'carabao-cup',
    label: '카라바오컵',
    panel: '#141A32',
    panelAlt: '#DA1E28',
    pitch: '#42506F',
    pitchAlt: '#35425F',
    border: '#FFF2E6',
    text: '#FFFFFF',
    muted: '#FFD7D9',
    accent: '#DA1E28',
    accentAlt: '#FFF2E6',
    dark: '#070B17',
  },
  'fa-cup': {
    slug: 'fa-cup',
    label: 'FA컵',
    panel: '#132D5E',
    panelAlt: '#DB1F35',
    pitch: '#2E4E86',
    pitchAlt: '#253F70',
    border: '#F7F1E3',
    text: '#FFFFFF',
    muted: '#DDE7FF',
    accent: '#DB1F35',
    accentAlt: '#F7F1E3',
    dark: '#071733',
  },
  'world-cup-2026': {
    slug: 'world-cup-2026',
    label: 'FIFA 월드컵 2026',
    panel: '#111111',
    panelAlt: '#C9972B',
    pitch: '#263A78',
    pitchAlt: '#1E3067',
    border: '#F5F1E8',
    text: '#FFFFFF',
    muted: '#F6E1A8',
    accent: '#C8102E',
    accentAlt: '#003478',
    dark: '#050505',
  },
}

function hasStatusIcons(player: PlayerNode) {
  return player.yellowCard || player.redCard || player.substitution !== 'none'
}

function ratingChipStyle(rating: string) {
  const value = Number.parseFloat(rating)
  if (!Number.isFinite(value)) return undefined

  const clamped = Math.min(8.5, Math.max(5.5, value))
  const ratio = (clamped - 5.5) / 3
  const hue = Math.round(356 - ratio * 150)
  const saturation = Math.round(74 + ratio * 10)
  const topLightness = Math.round(18 + ratio * 6)
  const bottomLightness = Math.max(11, topLightness - 7)
  const borderLightness = Math.round(42 + ratio * 13)

  return {
    '--rating-bg-top': `hsl(${hue} ${saturation}% ${topLightness}%)`,
    '--rating-bg-bottom': `hsl(${hue} ${saturation}% ${bottomLightness}%)`,
    '--rating-border': `hsl(${hue} 88% ${borderLightness}%)`,
    '--rating-glow': `hsl(${hue} 86% 34% / 0.55)`,
  }
}

const searchParams = new URLSearchParams(
  typeof window === 'undefined' ? '' : window.location.search,
)
const requestedFixtureId = readBroadcastFixtureId(searchParams)
const teamColorMode = readBroadcastTeamColorMode(searchParams)
const requestedLeague = searchParams.get('league') as LeagueSlug | null
const selectedLeague =
  requestedLeague && Object.hasOwn(themes, requestedLeague)
    ? requestedLeague
    : 'premier-league'
const materialRevision =
  searchParams.get('revision') === 'material' || searchParams.get('material') === 'on'

const theme = computed(() => themes[selectedLeague])
const activeMatch = ref<BroadcastMatch | null>(null)
const activeApiFootballSnapshot = ref<ApiFootballBroadcastSnapshot | null>(null)
const match = computed(() => activeMatch.value)
const liveStatus = ref<LiveStatus>('loading')
const liveError = ref<string | null>(null)
const hasEventBaseline = ref(false)
const baselineFixtureId = ref<number | null>(null)
const previousEvents = ref<BroadcastEvent[]>([])
const eventNotificationQueue = ref<BroadcastEvent[]>([])
const activeNotificationEvent = ref<BroadcastEvent | null>(null)
const manualClockFixtureId = ref<number | null>(null)
const manualClockSeconds = ref(0)
const manualAddedSeconds = ref(0)
const isManualClockRunning = ref(false)
let eventTimer: number | undefined
let livePollingTimer: number | undefined
let manualClockTimer: number | undefined
let lastLineupsRefreshAt = 0
let hiddenMomentumSyncInFlight = false
const themeVars = computed<Record<string, string>>(() => ({
  '--panel': theme.value.panel,
  '--panel-alt': theme.value.panelAlt,
  '--pitch': theme.value.pitch,
  '--pitch-alt': theme.value.pitchAlt,
  '--border': theme.value.border,
  '--text': theme.value.text,
  '--muted': theme.value.muted,
  '--accent': theme.value.accent,
  '--accent-alt': theme.value.accentAlt,
  '--dark': theme.value.dark,
}))
const liveStateLabel = computed(() => {
  if (liveStatus.value === 'loading') return 'API-Football 라이브 데이터 로딩 중'
  if (liveStatus.value === 'error') return liveError.value ?? 'API-Football 라이브 데이터 사용 불가'
  return 'API-Football 라이브 데이터'
})
const currentEvent = computed<BroadcastEvent | null>(() => activeNotificationEvent.value)
const homeBroadcastCode = computed(() => {
  if (!match.value) return ''
  return theme.value.slug === 'premier-league' ? match.value.homeEnglishCode : match.value.homeCode
})
const awayBroadcastCode = computed(() => {
  if (!match.value) return ''
  return theme.value.slug === 'premier-league' ? match.value.awayEnglishCode : match.value.awayCode
})
const homeScoreboardName = computed(() => match.value ? shortTeamLabel(match.value.homeCode, match.value.home) : '')
const awayScoreboardName = computed(() => match.value ? shortTeamLabel(match.value.awayCode, match.value.away) : '')
const displayClock = computed(() => formatClock(manualClockSeconds.value))
const displayAddedTime = computed(() => formatClock(manualAddedSeconds.value))
const shouldShowEventLiveState = computed(() => liveStatus.value !== 'ready')
const isAdminAllowed = ref(
  typeof localStorage !== 'undefined' && localStorage.getItem('mockRole') === 'ADMIN',
)

onMounted(() => {
  if (!isAdminAllowed.value) return

  void refreshApiFootballLive()
  if (shouldUseApiFootballLive()) {
    livePollingTimer = window.setInterval(() => {
      void refreshApiFootballLive()
    }, API_FOOTBALL_LIVE_POLL_MS)
  }

  eventTimer = window.setInterval(() => {
    showNextQueuedEvent()
  }, 8400)

  manualClockTimer = window.setInterval(() => {
    if (isManualClockRunning.value) {
      manualClockSeconds.value += 1
    }
  }, 1000)
})

onBeforeUnmount(() => {
  if (eventTimer !== undefined) {
    window.clearInterval(eventTimer)
  }
  if (livePollingTimer !== undefined) {
    window.clearInterval(livePollingTimer)
  }
  if (manualClockTimer !== undefined) {
    window.clearInterval(manualClockTimer)
  }
})

async function refreshApiFootballLive() {
  if (!shouldUseApiFootballLive()) {
    liveStatus.value = 'error'
    liveError.value = 'API-Football 라이브 모드가 설정되지 않았습니다'
    return
  }

  try {
    liveStatus.value = activeMatch.value ? 'ready' : 'loading'
    liveError.value = null
    const hadSnapshot = activeApiFootballSnapshot.value !== null
    let snapshot = await fetchNextApiFootballSnapshot()
    const now = Date.now()
    if (!hadSnapshot) {
      lastLineupsRefreshAt = now
    } else if (now - lastLineupsRefreshAt >= API_FOOTBALL_LINEUPS_REFRESH_MS) {
      try {
        snapshot = await fetchApiFootballBroadcastLineupsSnapshot(snapshot.fixtureId, snapshot)
      } catch (lineupsError) {
        console.error('Failed to refresh API-Football broadcast lineups', lineupsError)
      } finally {
        lastLineupsRefreshAt = now
      }
    }
    activeApiFootballSnapshot.value = snapshot
    syncManualTimeFromSnapshot(snapshot)
    const nextMatch = createBroadcastMatchFromSnapshot(snapshot)
    activeMatch.value = nextMatch
    syncEventNotificationQueue(snapshot.fixtureId, nextMatch.events)
    liveStatus.value = 'ready'
    void syncHiddenMomentum(snapshot.fixtureId)
  } catch (error) {
    liveStatus.value = 'error'
    liveError.value = (error as Error).message
    console.error('Failed to refresh API-Football broadcast overlay data', error)
  }
}

async function syncHiddenMomentum(fixtureId: number) {
  if (hiddenMomentumSyncInFlight) return

  hiddenMomentumSyncInFlight = true
  try {
    const colorSnapshot = await fetchApiFootballBroadcastSnapshot(fixtureId)
    const currentSnapshot = activeApiFootballSnapshot.value
    if (currentSnapshot?.fixtureId === fixtureId && Array.isArray(colorSnapshot.lineups)) {
      const teamColors = new Map<
        number,
        { primaryColor?: string; secondaryColor?: string; accentColor?: string }
      >()
      colorSnapshot.lineups.forEach((lineup) => {
        if (lineup.teamId !== undefined) {
          const primaryColor = isValidHexColor(lineup.primaryColor)
            ? lineup.primaryColor
            : undefined
          const secondaryColor = isValidHexColor(lineup.secondaryColor)
            ? lineup.secondaryColor
            : undefined
          const accentColor = isValidHexColor(lineup.accentColor)
            ? lineup.accentColor
            : undefined
          if (primaryColor || secondaryColor || accentColor) {
            teamColors.set(lineup.teamId, { primaryColor, secondaryColor, accentColor })
          }
        }
      })

      const lineups = currentSnapshot.lineups.map((lineup) => {
        const teamColor = lineup.teamId !== undefined
          ? teamColors.get(lineup.teamId)
          : undefined
        return {
          ...lineup,
          primaryColor: teamColor?.primaryColor ?? lineup.primaryColor,
          secondaryColor: teamColor?.secondaryColor ?? lineup.secondaryColor,
          accentColor: teamColor?.accentColor ?? lineup.accentColor,
        }
      })
      const enrichedSnapshot = { ...currentSnapshot, lineups }
      activeApiFootballSnapshot.value = enrichedSnapshot
      activeMatch.value = createBroadcastMatchFromSnapshot(enrichedSnapshot)
    }
  } catch (error) {
    console.error('Failed to collect hidden broadcast momentum', error)
  } finally {
    hiddenMomentumSyncInFlight = false
  }
}

async function fetchNextApiFootballSnapshot() {
  const previousSnapshot = activeApiFootballSnapshot.value
  if (requestedFixtureId !== null) {
    return previousSnapshot
      ? fetchApiFootballBroadcastTickSnapshot(requestedFixtureId, previousSnapshot)
      : fetchApiFootballBroadcastInitialSnapshot(requestedFixtureId)
  }

  if (previousSnapshot) {
    return fetchApiFootballBroadcastTickSnapshot(previousSnapshot.fixtureId, previousSnapshot)
  }

  return fetchApiFootballFirstLiveFixture()
}

function syncEventNotificationQueue(fixtureId: number, nextEvents: BroadcastEvent[]) {
  if (!hasEventBaseline.value || baselineFixtureId.value !== fixtureId) {
    hasEventBaseline.value = true
    baselineFixtureId.value = fixtureId
    previousEvents.value = nextEvents
    eventNotificationQueue.value = []
    activeNotificationEvent.value = null
    return
  }

  const previousLength = previousEvents.value.length
  if (nextEvents.length > previousLength) {
    eventNotificationQueue.value.push(...nextEvents.slice(previousLength))
  }

  previousEvents.value = nextEvents
}

function showNextQueuedEvent() {
  const nextEvent = eventNotificationQueue.value.shift()
  if (!nextEvent) {
    return
  }

  activeNotificationEvent.value = nextEvent
}

function createBroadcastMatchFromSnapshot(snapshot: ApiFootballBroadcastSnapshot): BroadcastMatch {
  return {
    fixtureId: snapshot.fixtureId,
    home: snapshot.home,
    away: snapshot.away,
    leagueName: snapshot.leagueName,
    leagueShortName: snapshot.leagueShortName,
    homeCode: snapshot.homeCode,
    awayCode: snapshot.awayCode,
    homeEnglishCode: snapshot.homeEnglishCode,
    awayEnglishCode: snapshot.awayEnglishCode,
    homeLogoUrl: snapshot.homeLogoUrl,
    awayLogoUrl: snapshot.awayLogoUrl,
    score: snapshot.score,
    clock: snapshot.clock,
    addedTime: snapshot.addedTime,
    status: snapshot.status,
    venue: snapshot.venue,
    lineups: buildBroadcastLineups(snapshot),
    stats: snapshot.stats,
    events: snapshot.events.map((event) => toBroadcastEvent(event, snapshot)),
  }
}

function syncManualTimeFromSnapshot(snapshot: ApiFootballBroadcastSnapshot) {
  if (manualClockFixtureId.value === snapshot.fixtureId) {
    return
  }

  manualClockFixtureId.value = snapshot.fixtureId
  manualClockSeconds.value = 0
  manualAddedSeconds.value = 0
  isManualClockRunning.value = false
}

function shortTeamLabel(shortName: string, fallback: string) {
  return shortName.trim() || fallback
}

function formatClock(totalSeconds: number) {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds))
  const minutes = Math.floor(safeSeconds / 60)
  const seconds = safeSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

function parseClockText(value: string) {
  const trimmed = value.trim()
  if (!trimmed) return null

  if (!trimmed.includes(':')) {
    const minutes = Number.parseInt(trimmed, 10)
    return Number.isSafeInteger(minutes) && minutes >= 0 ? minutes * 60 : null
  }

  const [minutesText, secondsText] = trimmed.split(':')
  const minutes = Number.parseInt(minutesText, 10)
  const seconds = Number.parseInt(secondsText, 10)
  if (
    !Number.isSafeInteger(minutes)
    || !Number.isSafeInteger(seconds)
    || minutes < 0
    || seconds < 0
    || seconds > 59
  ) {
    return null
  }

  return minutes * 60 + seconds
}

function parseAddedTimeText(value: string) {
  const trimmed = value.trim()
  if (!trimmed) return null
  const withoutPlus = trimmed.replace(/^\+/, '')
  if (withoutPlus.includes(':')) {
    return parseClockText(withoutPlus)
  }

  const minutes = Number.parseInt(withoutPlus, 10)
  return Number.isSafeInteger(minutes) && minutes >= 0 ? minutes * 60 : null
}

function pauseManualClock() {
  isManualClockRunning.value = false
}

function playManualClock() {
  isManualClockRunning.value = true
}

function handleHomeTeamClockControl() {
  if (theme.value.slug === 'premier-league') return
  pauseManualClock()
}

function handleAwayTeamClockControl() {
  if (theme.value.slug !== 'premier-league') {
    playManualClock()
    return
  }
  isManualClockRunning.value = !isManualClockRunning.value
}

function requestTimeInput(kind: TimeEditorKind) {
  const label = kind === 'clock' ? '경기시간 입력' : '추가시간 입력'
  const currentValue = kind === 'clock' ? displayClock.value : displayAddedTime.value
  const value = window.prompt(label, currentValue)
  if (value === null) return

  if (kind === 'clock') {
    const parsed = parseClockText(value)
    if (parsed === null) {
      window.alert('경기시간은 64:30 또는 64 형식으로 입력하세요')
      return
    }
    manualClockSeconds.value = parsed
    return
  }

  const parsed = parseAddedTimeText(value)
  if (parsed === null) {
    window.alert('추가시간은 03:00, +3 또는 3 형식으로 입력하세요')
    return
  }
  manualAddedSeconds.value = parsed
}

function buildBroadcastLineups(snapshot: ApiFootballBroadcastSnapshot): LineupSide[] {
  const homeLineup = pickLineup(snapshot.lineups, snapshot.homeId, snapshot.homeCode) ?? snapshot.lineups[0]
  const awayLineup = pickLineup(snapshot.lineups, snapshot.awayId, snapshot.awayCode)
    ?? snapshot.lineups.find((lineup) => lineup !== homeLineup)

  return [homeLineup, awayLineup]
    .filter((lineup): lineup is ApiFootballBroadcastLineup => Boolean(lineup))
    .map((lineup) => toLineupSide(lineup, snapshot.events, snapshot.playerRatings))
}

function pickLineup(
  lineups: ApiFootballBroadcastLineup[],
  teamId: number | undefined,
  code: string,
) {
  return lineups.find((lineup) => lineup.teamId === teamId || lineup.code === code)
}

function toLineupSide(
  lineup: ApiFootballBroadcastLineup,
  events: ApiFootballBroadcastEvent[],
  playerRatings: ApiFootballBroadcastSnapshot['playerRatings'],
): LineupSide {
  const activePlayers = applyLineupSubstitutions(
    lineup.players.slice(0, 11),
    lineup.substituteNumbers,
    events,
    lineup.teamId,
    playerRatings,
  )

  return {
    name: lineup.name,
    code: lineup.code,
    primaryColor: lineup.primaryColor,
    secondaryColor: lineup.secondaryColor,
    accentColor: lineup.accentColor,
    shape: lineup.shape,
    players: activePlayers.map((player) => ({
      id: player.id,
      no: player.no,
      name: player.name,
      pos: player.pos,
      grid: player.grid,
      rating: player.rating,
      x: 0,
      y: 0,
      goals: events.filter((event) => event.kind === 'goal' && eventMatchesPlayer(event, player)).length,
      yellowCard: events.some((event) => event.kind === 'yellow-card' && eventMatchesPlayer(event, player)),
      redCard: events.some((event) => event.kind === 'red-card' && eventMatchesPlayer(event, player)),
      substitution: substitutionState(player, events),
    })),
  }
}

function applyLineupSubstitutions(
  starters: ApiFootballBroadcastLineup['players'],
  substituteNumbers: ApiFootballBroadcastLineup['substituteNumbers'],
  events: ApiFootballBroadcastEvent[],
  teamId: number | undefined,
  playerRatings: ApiFootballBroadcastSnapshot['playerRatings'],
) {
  return events.reduce<ActiveLineupPlayer[]>((players, event) => {
    if (teamId !== undefined && event.teamId !== undefined && event.teamId !== teamId) {
      return players
    }
    if (event.kind !== 'substitution' || (!event.inPlayer && event.assistId === undefined)) {
      return players
    }

    const outIndex = players.findIndex((player) => eventMatchesPlayer(event, player))
    if (outIndex < 0) {
      return players
    }

    const outgoing = players[outIndex]
    const incomingId = event.assistId
    const incoming: ActiveLineupPlayer = {
      id: incomingId,
      no: incomingId !== undefined ? substituteNumbers[String(incomingId)] ?? '?' : '?',
      name: event.inPlayerShortName ?? event.assistShortName ?? event.inPlayer ?? event.assist ?? outgoing.name,
      grid: outgoing.grid,
      rating: incomingId !== undefined ? playerRatings[String(incomingId)] : undefined,
    }
    const nextPlayers = [...players]
    nextPlayers[outIndex] = incoming
    return nextPlayers
  }, starters)
}

function normalizePlayerName(value: string | undefined) {
  return value?.trim().toLowerCase() ?? ''
}

function replacementMatchesEvent(
  event: ApiFootballBroadcastEvent,
  player: ActiveLineupPlayer,
) {
  if (event.assistId !== undefined && player.id === event.assistId) {
    return true
  }

  if (event.assistId !== undefined) {
    return false
  }

  return (
    normalizePlayerName(player.name) === normalizePlayerName(event.inPlayerShortName)
    || normalizePlayerName(player.name) === normalizePlayerName(event.inPlayer)
  )
}

function eventMatchesPlayer(
  event: ApiFootballBroadcastEvent,
  player: ActiveLineupPlayer,
) {
  if (event.playerId !== undefined && player.id === event.playerId) {
    return true
  }

  if (event.playerId !== undefined) {
    return false
  }

  return (
    normalizePlayerName(player.name) === normalizePlayerName(event.playerShortName)
    || normalizePlayerName(player.name) === normalizePlayerName(event.player)
  )
}

function substitutionState(
  player: ActiveLineupPlayer,
  events: ApiFootballBroadcastEvent[],
): PlayerNode['substitution'] {
  if (events.some((event) => event.kind === 'substitution' && replacementMatchesEvent(event, player))) {
    return 'in'
  }
  if (events.some((event) => event.kind === 'substitution' && eventMatchesPlayer(event, player))) {
    return 'out'
  }

  return 'none'
}

function toBroadcastEvent(
  event: ApiFootballBroadcastEvent,
  snapshot: ApiFootballBroadcastSnapshot,
): BroadcastEvent {
  return {
    id: event.id,
    kind: toBroadcastEventKind(event),
    teamCode: event.teamCode,
    opponentCode: event.opponentCode,
    minute: event.minute,
    title: event.title,
    detail: event.detail,
    player: event.player,
    playerShortName: event.playerShortName,
    assist: event.assist,
    assistShortName: event.assistShortName,
    score: event.score ?? snapshot.score,
    inPlayer: event.inPlayer,
    inPlayerShortName: event.inPlayerShortName,
    outPlayer: event.outPlayer,
    outPlayerShortName: event.outPlayerShortName,
    statLabel: event.title,
    statValue: event.minute,
  }
}

function toBroadcastEventKind(event: ApiFootballBroadcastEvent): BroadcastEventKind {
  if (event.kind === 'goal' || event.kind === 'own-goal') return 'goal'
  if (event.kind === 'substitution') return 'substitution'
  if (event.kind === 'yellow-card' || event.kind === 'red-card' || event.kind === 'card') {
    return 'yellow-card'
  }
  if (event.kind === 'var' || event.kind === 'goal-cancelled' || event.kind === 'penalty-missed') return 'var'
  return 'stat'
}

function formationLabel(lineup: LineupSide): string {
  return lineup.shape || 'N/A'
}

function isValidHexColor(color: string | null | undefined): color is string {
  return typeof color === 'string' && /^#[0-9A-Fa-f]{6}$/.test(color)
}

function mixHexColor(base: string, target: '#000000' | '#FFFFFF', weight: number): string {
  const targetChannel = target === '#FFFFFF' ? 255 : 0
  const channels = [1, 3, 5].map((offset) => Number.parseInt(base.slice(offset, offset + 2), 16))
  return `#${channels
    .map((channel) => Math.round(channel * (1 - weight) + targetChannel * weight)
      .toString(16)
      .padStart(2, '0'))
    .join('')}`.toUpperCase()
}

function hexLuminance(color: string): number {
  const red = Number.parseInt(color.slice(1, 3), 16)
  const green = Number.parseInt(color.slice(3, 5), 16)
  const blue = Number.parseInt(color.slice(5, 7), 16)
  return red * 0.2126 + green * 0.7152 + blue * 0.0722
}

function contrastColor(color: string): '#111111' | '#FFFFFF' {
  return hexLuminance(color) >= 150 ? '#111111' : '#FFFFFF'
}

function formationPitchStyle(lineup: LineupSide): Record<string, string> {
  if (teamColorMode === 'marker-primary') {
    if (!isValidHexColor(lineup.primaryColor)) return {}

    const markerColor = lineup.primaryColor.toUpperCase()
    const markerContrast = contrastColor(markerColor)
    return {
      '--team-player': markerColor,
      '--team-player-text': markerContrast,
      '--team-player-border': markerContrast,
    }
  }

  const style: Record<string, string> = {}
  let secondaryColor: string | undefined

  if (isValidHexColor(lineup.secondaryColor)) {
    secondaryColor = lineup.secondaryColor.toUpperCase()
    const secondaryContrast = contrastColor(secondaryColor)
    style['--team-secondary'] = secondaryColor
    style['--team-secondary-text'] = secondaryContrast
    style['--team-player'] = secondaryColor
    style['--team-player-text'] = secondaryContrast
    style['--team-player-border'] = secondaryContrast
  }

  if (isValidHexColor(lineup.accentColor)) {
    const accentColor = lineup.accentColor.toUpperCase()
    style['--team-accent'] = accentColor
    style['--team-accent-text'] = contrastColor(accentColor)
  }

  if (!isValidHexColor(lineup.primaryColor)) return style

  const primaryColor = lineup.primaryColor.toUpperCase()
  const primaryContrast = contrastColor(primaryColor)
  const pitchColor = primaryColor
  const pitchContrast = contrastColor(pitchColor)
  const pitchLuminance = hexLuminance(pitchColor)
  const stripeColor = pitchLuminance < 72
    ? mixHexColor(pitchColor, '#FFFFFF', 0.14)
    : mixHexColor(pitchColor, '#000000', 0.16)

  const teamStyle: Record<string, string> = {
    ...style,
    '--team-primary': primaryColor,
    '--team-primary-text': primaryContrast,
    '--team-pitch': pitchColor,
    '--team-pitch-alt': stripeColor,
    '--team-field-line': pitchContrast,
    '--team-frame': style['--team-accent'] ?? style['--team-player'] ?? primaryContrast,
    '--team-frame-text': style['--team-accent-text'] ?? style['--team-player-text'] ?? primaryContrast,
  }

  return teamStyle
}

function formationLayout(shape: string): FormationLayout {
  const normalized = normalizeFormationShape(shape)
  const parts = parseSupportedFormation(normalized)
  if (parts) {
    return formationLayouts[parts.join('-')] ?? formationLayouts['4-3-3']
  }

  return formationLayouts['4-3-3']
}

type ParsedPlayerGrid = {
  row: number
  column: number
}

function parsePlayerGrid(grid: string | undefined): ParsedPlayerGrid | null {
  if (!grid) return null

  const [rowText, columnText] = grid.split(':')
  const row = Number.parseInt(rowText, 10)
  const column = Number.parseInt(columnText, 10)
  if (
    !Number.isSafeInteger(row)
    || !Number.isSafeInteger(column)
    || row <= 0
    || column <= 0
  ) {
    return null
  }

  return { row, column }
}

function gridRowCounts(players: PlayerNode[]) {
  const rowCounts = new Map<number, number>()
  players.forEach((player) => {
    const parsed = parsePlayerGrid(player.grid)
    if (!parsed) return
    rowCounts.set(parsed.row, Math.max(rowCounts.get(parsed.row) ?? 0, parsed.column))
  })
  return rowCounts
}

function fallbackGridLineY(lineIndex: number, lineCount: number) {
  if (lineCount <= 1) return 16

  return roundCoordinate(76 - (lineIndex / (lineCount - 1)) * 64)
}

function pointFromGrid(
  grid: string | undefined,
  rowCounts: Map<number, number>,
  maxRow: number,
) {
  const parsed = parsePlayerGrid(grid)
  if (!parsed) return null

  if (parsed.row === 1) {
    return parsed.column === 1 ? goalkeeperPoint : null
  }

  const lineIndex = parsed.row - 2
  const lineCount = Math.max(1, maxRow - 1)
  const count = rowCounts.get(parsed.row) ?? parsed.column
  const y = lineYCoordinates[lineCount]?.[lineIndex] ?? fallbackGridLineY(lineIndex, lineCount)

  if (lineIndex < 0 || lineIndex >= lineCount || parsed.column > count) {
    return null
  }

  return linePoints(count, y, lineIndex, lineCount)[parsed.column - 1] ?? null
}

function playersForLineup(lineup: LineupSide): PlayerNode[] {
  const layout = formationLayout(lineup.shape)
  const rowCounts = gridRowCounts(lineup.players)
  const maxGridRow = Math.max(0, ...rowCounts.keys())

  return lineup.players.map((player, index) => {
    const point = pointFromGrid(player.grid, rowCounts, maxGridRow) ?? layout[index]

    return {
      ...player,
      x: point?.x ?? player.x,
      y: point?.y ?? player.y,
    }
  })
}

</script>

<template>
  <main
    v-if="isAdminAllowed"
    class="broadcast-stage"
    :data-league="theme.slug"
    :data-revision="materialRevision ? 'material' : 'base'"
    :data-team-color-mode="teamColorMode"
    :style="themeVars"
    data-testid="broadcast-stage"
  >
    <section class="top-row" aria-label="경기 스코어보드">
      <div class="top-left-slot"></div>
      <section class="scoreboard" data-testid="broadcast-scoreboard">
        <template v-if="match">
          <div class="worldcup-score-strip" data-testid="worldcup-score-strip" aria-hidden="true">
            <span></span><span></span><span></span><span></span><span></span>
          </div>
          <component
            :is="theme.slug === 'premier-league' ? 'div' : 'button'"
            :type="theme.slug === 'premier-league' ? undefined : 'button'"
            class="score-team score-team-home"
            data-testid="score-team-home"
            :aria-label="theme.slug === 'premier-league' ? undefined : '경기시간 일시정지'"
            :aria-pressed="theme.slug === 'premier-league' ? undefined : !isManualClockRunning"
            @click="handleHomeTeamClockControl"
          >
            <span class="team-code-slot">
              <span class="team-mark country-badge" data-testid="country-badge" :aria-label="homeBroadcastCode">
                <img
                  v-if="match.homeLogoUrl"
                  class="country-flag"
                  :src="match.homeLogoUrl"
                  alt=""
                  aria-hidden="true"
                />
                <b v-else>{{ homeBroadcastCode }}</b>
              </span>
            </span>
            <strong>{{ homeScoreboardName }}</strong>
          </component>
          <div class="score-core">
            <span class="score-status">{{ match.status }}</span>
            <strong class="score-number">{{ match.score }}</strong>
            <button
              type="button"
              class="score-clock"
              data-testid="manual-clock-button"
              @click="requestTimeInput('clock')"
            >
              {{ displayClock }}
            </button>
          </div>
          <button
            type="button"
            class="score-team score-team-away"
            data-testid="score-team-away"
            :aria-label="
              theme.slug === 'premier-league'
                ? isManualClockRunning
                  ? '경기시간 일시정지'
                  : '경기시간 시작'
                : '경기시간 재생'
            "
            :aria-pressed="isManualClockRunning"
            @click="handleAwayTeamClockControl"
          >
            <strong>{{ awayScoreboardName }}</strong>
            <span class="team-code-slot">
              <span class="team-mark country-badge" data-testid="country-badge" :aria-label="awayBroadcastCode">
                <img
                  v-if="match.awayLogoUrl"
                  class="country-flag"
                  :src="match.awayLogoUrl"
                  alt=""
                  aria-hidden="true"
                />
                <b v-else>{{ awayBroadcastCode }}</b>
              </span>
            </span>
          </button>
          <button
            type="button"
            class="score-added-time"
            data-testid="manual-added-time-button"
            @click="requestTimeInput('added')"
          >
            <span>추가시간</span>
            <strong>{{ displayAddedTime }}</strong>
          </button>
        </template>
        <div v-else class="live-state live-state--score" data-testid="broadcast-live-state">
          <span>라이브 데이터</span>
          <strong>{{ liveStateLabel }}</strong>
        </div>
      </section>
      <div
        class="chat-reserve"
        data-testid="chat-reserve"
        aria-label="외부 방송 채팅 표시 영역"
      ></div>
    </section>

    <section class="body-row">
      <aside class="left-column" data-testid="broadcast-left-column" aria-label="양 팀 라인업">
        <div
          v-if="!match || match.lineups.length === 0"
          class="live-state live-state--panel"
          data-testid="formation-live-empty"
        >
          <span>포메이션</span>
          <strong>{{ liveStateLabel }}</strong>
        </div>
        <article
          v-for="lineup in match?.lineups ?? []"
          :key="lineup.code"
          class="formation-card"
          :data-team-color="isValidHexColor(lineup.primaryColor) ? 'true' : undefined"
          :data-accent-color="isValidHexColor(lineup.accentColor) ? lineup.accentColor : undefined"
          :style="formationPitchStyle(lineup)"
          data-testid="formation-card"
        >
          <div class="formation-side-rail formation-side-rail-left">
            {{ lineup.code }}
          </div>
          <div class="formation-side-rail formation-side-rail-right">
            {{ match?.leagueShortName ?? match?.leagueName ?? theme.label }}
          </div>
          <div class="worldcup-formation-band" data-testid="worldcup-formation-band" aria-hidden="true">
            <b class="formation-ribbon-label">{{ match?.leagueName ?? theme.label }}</b>
            <i v-if="theme.slug !== 'premier-league'" class="formation-ribbon-code">{{ lineup.code }}</i>
            <span></span><span></span><span></span><span></span><span></span>
          </div>
          <header class="formation-header">
            <div>
              <span v-if="theme.slug !== 'premier-league'" class="eyebrow">{{ lineup.code }}</span>
              <strong>{{ lineup.name }}</strong>
            </div>
            <span
              class="shape-pill"
              data-testid="formation-trigger"
            >
              {{ formationLabel(lineup) }}
            </span>
          </header>
          <div
            class="pitch"
            :aria-label="`${lineup.name} ${formationLabel(lineup)}`"
            :data-primary-color="lineup.primaryColor || undefined"
            :data-secondary-color="lineup.secondaryColor || undefined"
            :data-accent-color="lineup.accentColor || undefined"
            :style="formationPitchStyle(lineup)"
          >
            <div class="pitch-stripes" aria-hidden="true">
              <span></span>
              <span></span>
              <span></span>
              <span></span>
              <span></span>
              <span></span>
            </div>
            <div class="field-markings" data-testid="field-markings" aria-hidden="true">
              <span class="halfway-line"></span>
              <span class="center-circle" data-testid="center-circle"></span>
              <span class="center-spot"></span>
              <span class="penalty-box penalty-box-top"></span>
              <span class="penalty-box penalty-box-bottom"></span>
              <span class="goal-area goal-area-top"></span>
              <span class="goal-area goal-area-bottom"></span>
              <span class="penalty-spot penalty-spot-top"></span>
              <span class="penalty-spot penalty-spot-bottom"></span>
              <span class="corner-arc corner-arc-top-left"></span>
              <span class="corner-arc corner-arc-top-right"></span>
              <span class="corner-arc corner-arc-bottom-left"></span>
              <span class="corner-arc corner-arc-bottom-right"></span>
            </div>
            <span
              v-for="player in playersForLineup(lineup)"
              :key="`${lineup.code}-${player.id ?? player.name}-${player.no}`"
              class="player-node"
              :style="{ left: `${player.x}%`, top: `${player.y}%` }"
            >
              <span class="player-marker" data-testid="player-marker">
                <span
                  v-if="player.goals > 0"
                  class="goal-history"
                  data-testid="goal-history-icons"
                >
                  <img
                    class="marker-icon goal-icon"
                    :src="goalIconUrl"
                    alt=""
                    aria-hidden="true"
                  />
                  <span v-if="player.goals > 1" class="goal-count" data-testid="goal-count">
                    {{ player.goals }}
                  </span>
                </span>
                <span
                  v-if="player.rating"
                  class="rating-chip"
                  :style="ratingChipStyle(player.rating)"
                >
                  {{ player.rating }}
                </span>
                <span class="shirt">{{ player.no }}</span>
                <span
                  v-if="hasStatusIcons(player)"
                  class="player-status-icons"
                  data-testid="player-status-icons"
                >
                  <span v-if="player.yellowCard" class="status-slot status-slot-yellow">
                    <img
                      class="marker-icon status-icon"
                      :src="yellowCardIconUrl"
                      alt=""
                      aria-hidden="true"
                    />
                  </span>
                  <span v-if="player.redCard" class="status-slot status-slot-red">
                    <img
                      class="marker-icon status-icon"
                      :src="redCardIconUrl"
                      alt=""
                      aria-hidden="true"
                    />
                  </span>
                  <span v-if="player.substitution !== 'none'" class="status-slot status-slot-sub">
                    <img
                      class="marker-icon status-icon"
                      :src="substitutionIconUrl"
                      alt=""
                      aria-hidden="true"
                    />
                  </span>
                </span>
              </span>
              <span class="player-name">{{ player.name }}</span>
            </span>
          </div>
        </article>
      </aside>

      <section
        class="character-safe-zone"
        data-testid="character-safe-zone"
        aria-label="중앙 캐릭터 표시 영역"
      >
        <div class="event-dock" aria-live="polite">
          <article
            v-if="currentEvent"
            :key="currentEvent.id"
            :class="['event-toast', `event-toast--${currentEvent.kind}`]"
            data-testid="event-toast"
          >
            <template v-if="currentEvent.kind === 'substitution'">
              <div class="sub-out">
                <span>교체아웃</span>
                <strong>{{ currentEvent.outPlayer }}</strong>
              </div>
              <div class="sub-core">
                <img :src="substitutionIconUrl" alt="" aria-hidden="true" />
                <span>{{ currentEvent.minute }}</span>
                <strong>{{ currentEvent.title }}</strong>
              </div>
              <div class="sub-in">
                <span>교체투입</span>
                <strong>{{ currentEvent.inPlayer }}</strong>
              </div>
            </template>

            <template v-else-if="currentEvent.kind === 'yellow-card'">
              <div class="card-plate-icon">
                <img :src="yellowCardIconUrl" alt="" aria-hidden="true" />
              </div>
              <div class="card-plate-copy">
                <span>{{ currentEvent.minute }} · {{ currentEvent.teamCode }}</span>
                <strong>{{ currentEvent.title }} · {{ currentEvent.player }}</strong>
                <i>{{ currentEvent.detail }}</i>
              </div>
            </template>

            <template v-else-if="currentEvent.kind === 'var'">
              <span class="var-label">VAR 판독</span>
              <strong class="var-main">{{ currentEvent.title }}</strong>
              <i class="var-detail">{{ currentEvent.detail }}</i>
              <b class="var-live">라이브</b>
            </template>

            <template v-else-if="currentEvent.kind === 'stat'">
              <b class="stat-team">{{ currentEvent.teamCode }}</b>
              <div class="stat-copy">
                <span>{{ currentEvent.statLabel }}</span>
                <strong>{{ currentEvent.statValue }}</strong>
                <i>{{ currentEvent.detail }}</i>
              </div>
              <b class="stat-team">{{ currentEvent.opponentCode }}</b>
            </template>

            <template v-else>
              <div class="event-logo-circle" data-testid="event-logo-circle">
                <span>{{ currentEvent.teamCode }}</span>
              </div>
              <div class="event-card">
                <div class="event-title-box" data-testid="event-title">
                  <span>{{ currentEvent.minute }}</span>
                  <strong>{{ currentEvent.title }}</strong>
                  <i>{{ currentEvent.score }}</i>
                </div>
                <div class="event-detail-box" data-testid="event-detail">
                  {{ currentEvent.player }} · {{ currentEvent.detail }}
                </div>
              </div>
            </template>
          </article>
          <div v-else-if="shouldShowEventLiveState" class="live-state live-state--event" data-testid="event-live-empty">
            <span>이벤트</span>
            <strong>{{ liveStateLabel }}</strong>
          </div>
        </div>
      </section>

      <aside class="right-column" data-testid="broadcast-right-column">
        <div class="right-chat-slot"></div>
        <BroadcastStatsBoard
          v-if="match"
          :league="theme.slug"
          :theme-label="match.leagueName"
          :home="match.home"
          :away="match.away"
          :home-code="homeBroadcastCode"
          :away-code="awayBroadcastCode"
          :home-logo-url="match.homeLogoUrl"
          :away-logo-url="match.awayLogoUrl"
          :score="match.score"
          :clock="displayClock"
          :status="match.status"
          :stats="match.stats"
          :fixture-id="match.fixtureId"
          :material-revision="materialRevision"
        />
        <div v-else class="live-state live-state--panel" data-testid="stats-live-empty">
          <span>스탯</span>
          <strong>{{ liveStateLabel }}</strong>
        </div>
      </aside>
    </section>

  </main>
  <main v-else class="broadcast-stage broadcast-stage--locked" data-testid="broadcast-locked">
    <section class="broadcast-locked-panel">
      <strong>권한이 필요합니다</strong>
      <span>방송용 페이지는 ADMIN 전용입니다.</span>
    </section>
  </main>
</template>

<style scoped>
*,
*::before,
*::after {
  box-sizing: border-box;
}

.broadcast-stage {
  position: relative;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: #00B140;
  color: var(--text);
  font-family:
    'Avenir Next Condensed',
    'DIN Condensed',
    'Pretendard',
    system-ui,
    sans-serif;
  letter-spacing: 0;
}

.broadcast-stage--locked {
  align-items: center;
  justify-content: center;
  background: #101318;
  color: #f8fafc;
}

.broadcast-locked-panel {
  display: grid;
  gap: 0.5rem;
  min-width: 18rem;
  padding: 1.4rem 1.6rem;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 0.5rem;
  background: rgba(12, 16, 22, 0.92);
  text-align: center;
}

.broadcast-locked-panel strong {
  font-size: 1.25rem;
}

.broadcast-locked-panel span {
  color: rgba(248, 250, 252, 0.72);
}

.top-row {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  z-index: 20;
  height: 14%;
  display: flex;
  align-items: center;
  width: 100%;
}

.top-left-slot,
.chat-reserve {
  flex: 0 0 22%;
  height: 100%;
  display: flex;
  align-items: center;
  padding: 0 1%;
}

.top-left-slot {
  justify-content: flex-start;
}

.chat-reserve {
  justify-content: flex-end;
}

.score-clock:focus-visible,
.score-added-time:focus-visible,
.score-team:focus-visible {
  outline: 0.2rem solid var(--accent-alt);
  outline-offset: 0.12rem;
}

.scoreboard {
  position: relative;
  flex: 0 0 56%;
  min-height: 52%;
  display: flex;
  align-items: stretch;
  overflow: hidden;
  background: var(--panel);
  border: 0.18rem solid var(--border);
  border-radius: 1rem;
  box-shadow: 0.45rem 0.45rem 0 #000000;
}

.worldcup-score-strip,
.score-added-time,
.worldcup-formation-band {
  display: none;
}

.formation-ribbon-label,
.formation-ribbon-code,
.formation-side-rail {
  display: none;
}

.score-team,
.score-core {
  display: flex;
  align-items: center;
  justify-content: center;
}

.score-team {
  flex: 1 1 34%;
  gap: 5%;
  padding: 0 3%;
  font-size: 1.7rem;
  background: var(--panel);
  border: 0;
  color: var(--text);
  cursor: pointer;
  font: inherit;
  font-size: 1.7rem;
  font-weight: 950;
  letter-spacing: 0;
}

.score-team-away {
  text-align: right;
}

.score-team strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.team-mark {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 3.5rem;
  aspect-ratio: 1;
  border-radius: 50%;
  background: var(--dark);
  border: 0.16rem solid var(--accent-alt);
  color: var(--text);
  font-size: 1rem;
  font-weight: 900;
}

.team-code-slot {
  display: contents;
}

.team-mark b {
  position: relative;
  z-index: 2;
}

.country-flag {
  display: block;
  width: 78%;
  height: 78%;
  object-fit: contain;
}

.score-core {
  flex: 0 0 32%;
  flex-direction: column;
  background: var(--panel-alt);
  color: var(--text);
  border-left: 0.16rem solid var(--border);
  border-right: 0.16rem solid var(--border);
}

.score-number {
  font-size: 3.5rem;
  line-height: 1;
}

.score-status,
.score-clock,
.eyebrow {
  color: var(--muted);
  font-size: 0.95rem;
  font-weight: 800;
}

.score-clock,
.score-added-time {
  border: 0;
  cursor: pointer;
  font: inherit;
  letter-spacing: 0;
}

.score-clock {
  background: transparent;
  font-size: 1.08rem;
  font-weight: 950;
}

.body-row {
  flex: 1 1 100%;
  display: flex;
  width: 100%;
  height: 100%;
  min-height: 0;
}

.left-column,
.right-column {
  flex: 0 0 22%;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.left-column {
  gap: 1.25%;
  padding: 0.75% 0.85% 0.62% 1%;
}

.live-state {
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  border: 0.16rem solid var(--border);
  border-radius: 0.7rem;
  background: var(--panel);
  color: var(--text);
  text-align: center;
  box-shadow: 0.38rem 0.38rem 0 #000000;
}

.live-state span {
  color: var(--muted);
  font-size: 0.78rem;
  font-weight: 900;
  letter-spacing: 0;
}

.live-state strong {
  max-width: 82%;
  color: var(--text);
  font-size: 1rem;
  line-height: 1.25;
}

.live-state--score {
  grid-column: 1 / -1;
  grid-row: 1 / -1;
  min-height: 100%;
}

.live-state--panel {
  flex: 1 1 100%;
}

.live-state--event {
  width: 100%;
  height: 100%;
}

.formation-card {
  background: var(--panel);
  border: 0.16rem solid var(--border);
  color: var(--text);
  box-shadow: 0.38rem 0.38rem 0 #000000;
}

.formation-card {
  position: relative;
  flex: 1 1 49%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-radius: 0.7rem;
}

.formation-header {
  flex: 0 0 14%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4%;
  padding: 0 5%;
  background: var(--dark);
  border-bottom: 0.14rem solid var(--border);
}

.formation-header strong {
  display: block;
  font-size: 1.25rem;
  line-height: 1.1;
}

.shape-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 4.2rem;
  height: 2rem;
  border-radius: 999rem;
  background: var(--accent);
  border: 0.12rem solid var(--accent-alt);
  color: var(--text);
  font: inherit;
  font-weight: 900;
  letter-spacing: 0;
}

.formation-debug-menu {
  position: absolute;
  top: 13%;
  right: 4%;
  width: 66%;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.24rem;
  padding: 0.35rem;
  background: var(--dark);
  border: 0.14rem solid var(--border);
  border-radius: 0.55rem;
  box-shadow: 0.25rem 0.25rem 0 #000000;
  z-index: 8;
}

.formation-option {
  min-height: 1.65rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0.08rem solid var(--border);
  border-radius: 0.32rem;
  background: var(--panel);
  color: var(--text);
  cursor: pointer;
  font: inherit;
  font-size: 0.72rem;
  font-weight: 900;
  letter-spacing: 0;
}

.formation-option[aria-pressed='true'] {
  background: var(--accent);
  border-color: var(--accent-alt);
}

.pitch {
  position: relative;
  flex: 1 1 auto;
  margin: 3%;
  background: var(--team-pitch, var(--pitch));
  border: 0.14rem solid var(--muted);
  overflow: hidden;
}

.pitch-stripes,
.field-markings {
  position: absolute;
  inset: 0;
}

.pitch-stripes {
  display: flex;
  flex-direction: column;
  z-index: 0;
}

.pitch-stripes span {
  flex: 1 1 16.666%;
  background: var(--team-pitch, var(--pitch));
}

.pitch-stripes span:nth-child(even) {
  background: var(--team-pitch-alt, var(--pitch-alt));
}

.field-markings {
  z-index: 1;
}

.halfway-line,
.center-circle,
.center-spot,
.penalty-box,
.goal-area,
.penalty-spot,
.corner-arc {
  position: absolute;
  display: block;
}

.halfway-line {
  left: 0;
  right: 0;
  top: 50%;
  border-top: 0.12rem solid var(--muted);
}

.center-circle {
  left: 50%;
  top: 50%;
  width: 27%;
  aspect-ratio: 1;
  border: 0.12rem solid var(--muted);
  border-radius: 50%;
  transform: translate(-50%, -50%);
}

.center-spot,
.penalty-spot {
  width: 0.38rem;
  aspect-ratio: 1;
  border-radius: 50%;
  background: var(--muted);
  transform: translate(-50%, -50%);
}

.center-spot {
  left: 50%;
  top: 50%;
}

.penalty-box {
  left: 17%;
  width: 66%;
  height: 23%;
  border: 0.12rem solid var(--muted);
}

.penalty-box-top {
  top: -0.12rem;
}

.penalty-box-bottom {
  bottom: -0.12rem;
}

.goal-area {
  left: 34%;
  width: 32%;
  height: 10%;
  border: 0.12rem solid var(--muted);
}

.goal-area-top {
  top: -0.12rem;
}

.goal-area-bottom {
  bottom: -0.12rem;
}

.penalty-spot {
  left: 50%;
}

.penalty-spot-top {
  top: 16%;
}

.penalty-spot-bottom {
  top: 84%;
}

.corner-arc {
  width: 1rem;
  aspect-ratio: 1;
  border: 0.12rem solid var(--muted);
  border-radius: 50%;
}

.corner-arc-top-left {
  left: -0.5rem;
  top: -0.5rem;
}

.corner-arc-top-right {
  right: -0.5rem;
  top: -0.5rem;
}

.corner-arc-bottom-left {
  left: -0.5rem;
  bottom: -0.5rem;
}

.corner-arc-bottom-right {
  right: -0.5rem;
  bottom: -0.5rem;
}

.player-node {
  position: absolute;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.1rem;
  transform: translate(-50%, -50%);
  z-index: 2;
}

.player-marker {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 3.8rem;
  height: 3rem;
}

.rating-chip {
  position: absolute;
  left: 0.28rem;
  bottom: 0.1rem;
  min-width: 1.8rem;
  height: 1.05rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 0.36rem;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.1), rgba(255, 255, 255, 0) 38%),
    linear-gradient(
      135deg,
      var(--rating-bg-top, var(--dark)),
      var(--rating-bg-bottom, var(--dark))
    );
  border: 0.08rem solid var(--rating-border, var(--accent-alt));
  color: #FFFFFF;
  font-size: 0.62rem;
  font-weight: 900;
  line-height: 1;
  text-shadow: 0 0.06rem 0.08rem rgba(0, 0, 0, 0.85);
  box-shadow:
    inset 0 0.08rem 0 rgba(255, 255, 255, 0.14),
    0 0 0 0.04rem var(--accent-alt),
    0.1rem 0.1rem 0 #000000,
    0 0 0.42rem var(--rating-glow, rgba(0, 0, 0, 0.28));
  z-index: 3;
}

.shirt {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.62rem;
  aspect-ratio: 1;
  border-radius: 50%;
  background: var(--team-player, var(--accent));
  border: 0.13rem solid var(--team-player-border, var(--accent-alt));
  color: var(--team-player-text, var(--text));
  font-size: 1.1rem;
  font-weight: 900;
  box-shadow: 0.16rem 0.16rem 0 #000000;
}

.goal-history {
  position: absolute;
  left: 0.28rem;
  top: 0.02rem;
  width: 1.46rem;
  height: 1.46rem;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 3;
}

.marker-icon {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.goal-icon {
  width: 1.22rem;
  height: 1.22rem;
}

.goal-count {
  position: absolute;
  right: -0.1rem;
  top: -0.24rem;
  color: #FFFFFF;
  font-size: 0.82rem;
  font-weight: 950;
  line-height: 1;
  text-shadow:
    -0.06rem -0.06rem 0 #000000,
    0.06rem -0.06rem 0 #000000,
    -0.06rem 0.06rem 0 #000000,
    0.06rem 0.06rem 0 #000000;
}

.player-status-icons {
  position: absolute;
  right: 0.2rem;
  top: 0.12rem;
  width: 1.34rem;
  height: 3.05rem;
  z-index: 3;
}

.status-slot {
  position: absolute;
  right: 0;
  width: 1.34rem;
  height: 1.34rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.status-slot-yellow {
  top: 0;
}

.status-slot-red {
  top: 50%;
  transform: translateY(-50%);
}

.status-slot-sub {
  bottom: 0;
}

.status-icon {
  width: 1.22rem;
  height: 1.22rem;
  filter: drop-shadow(0.09rem 0.09rem 0 #000000);
}

.player-name {
  min-width: 3.05rem;
  padding: 0.12rem 0.34rem;
  border-radius: 0.35rem;
  background: #000000;
  color: #FFFFFF;
  font-size: 0.72rem;
  font-weight: 800;
  text-align: center;
  line-height: 1;
}

.character-safe-zone {
  position: relative;
  flex: 0 0 56%;
  min-width: 0;
  min-height: 0;
}

.event-dock {
  position: absolute;
  left: 18%;
  right: 18%;
  bottom: 5%;
  height: 13%;
  pointer-events: none;
}

.event-toast {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: stretch;
  animation: event-rise 8.4s ease-in-out both;
}

.event-logo-circle {
  flex: 0 0 18%;
  display: flex;
  align-items: center;
  justify-content: center;
  aspect-ratio: 1;
  align-self: center;
  border-radius: 50%;
  background: var(--dark);
  border: 0.25rem solid var(--accent-alt);
  box-shadow: 0.35rem 0.35rem 0 #000000;
  z-index: 2;
}

.event-logo-circle span {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 76%;
  aspect-ratio: 1;
  border-radius: 50%;
  background: var(--panel-alt);
  color: var(--text);
  font-size: 1.4rem;
  font-weight: 900;
}

.event-card {
  flex: 1 1 auto;
  margin-left: -4%;
  display: flex;
  flex-direction: column;
  border-radius: 0 1.1rem 1.1rem 0;
  overflow: hidden;
  border: 0.2rem solid var(--border);
  background: var(--panel);
  box-shadow: 0.35rem 0.35rem 0 #000000;
}

.event-title-box,
.event-detail-box {
  display: flex;
  align-items: center;
  padding-left: 9%;
  padding-right: 5%;
}

.event-title-box {
  flex: 0 0 45%;
  gap: 5%;
  background: var(--panel-alt);
  border-bottom: 0.16rem solid var(--border);
}

.event-title-box span {
  font-size: 1.15rem;
  font-weight: 900;
}

.event-title-box strong {
  font-size: 1.7rem;
}

.event-title-box i {
  margin-left: auto;
  color: var(--accent-alt);
  font-style: normal;
  font-size: 1.22rem;
  font-weight: 950;
}

.event-detail-box {
  flex: 1 1 auto;
  background: var(--panel);
  color: var(--text);
  font-size: 1.08rem;
  font-weight: 800;
}

.event-toast--substitution,
.event-toast--yellow-card,
.event-toast--var,
.event-toast--stat {
  justify-content: center;
  gap: 0.42rem;
}

.sub-out,
.sub-in,
.sub-core {
  min-height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0.28rem 0.28rem 0 #000000;
}

.sub-out,
.sub-in {
  flex: 1 1 31%;
  flex-direction: column;
  gap: 0.12rem;
  color: #FFFFFF;
}

.sub-out {
  background: #D71920;
  border-radius: 0.85rem 0 0 0.85rem;
}

.sub-in {
  background: var(--accent-alt);
  color: var(--dark);
  border-radius: 0 0.85rem 0.85rem 0;
}

.sub-out span,
.sub-in span,
.sub-core span {
  font-size: 0.8rem;
  font-weight: 950;
}

.sub-out strong,
.sub-in strong {
  font-size: 1.45rem;
}

.sub-core {
  flex: 0 0 28%;
  flex-direction: column;
  gap: 0.12rem;
  background: var(--border);
  border: 0.12rem solid var(--dark);
  color: var(--dark);
}

.sub-core img {
  width: 1.25rem;
  height: 1.25rem;
}

.sub-core strong {
  font-size: 1.24rem;
}

.card-plate-icon {
  flex: 0 0 16%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-alt);
  border: 0.16rem solid var(--dark);
  border-radius: 0.65rem 0 0 0.65rem;
  box-shadow: 0.28rem 0.28rem 0 #000000;
}

.card-plate-icon img {
  width: 3.4rem;
  height: 3.4rem;
  object-fit: contain;
}

.card-plate-copy {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0 1.2rem;
  background: var(--dark);
  border: 0.16rem solid var(--accent-alt);
  border-left: 0;
  border-radius: 0 0.65rem 0.65rem 0;
  box-shadow: 0.28rem 0.28rem 0 #000000;
}

.card-plate-copy span,
.card-plate-copy i {
  color: var(--accent-alt);
  font-size: 0.82rem;
  font-style: normal;
}

.card-plate-copy strong {
  font-size: 1.65rem;
}

.var-label,
.var-main,
.var-detail,
.var-live {
  min-height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 1rem;
  box-shadow: 0.25rem 0.25rem 0 #000000;
  font-style: normal;
}

.var-label {
  flex: 0 0 20%;
  background: var(--accent-alt);
  color: var(--dark);
  border-radius: 0.6rem 0 0 0.6rem;
}

.var-main {
  flex: 0 0 24%;
  background: var(--dark);
  border: 0.12rem solid var(--accent-alt);
}

.var-detail {
  flex: 1;
  background: var(--panel);
  color: var(--muted);
}

.var-live {
  flex: 0 0 12%;
  background: var(--accent);
  border-radius: 0 0.6rem 0.6rem 0;
}

.stat-team {
  flex: 0 0 16%;
  display: flex;
  align-items: center;
  justify-content: center;
  aspect-ratio: 1;
  align-self: center;
  border-radius: 50%;
  background: var(--border);
  border: 0.16rem solid var(--accent-alt);
  color: var(--dark);
  box-shadow: 0.25rem 0.25rem 0 #000000;
  font-size: 1.3rem;
}

.stat-copy {
  flex: 1;
  min-height: 92%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0 1.2rem;
  background: var(--panel);
  border: 0.14rem solid var(--accent-alt);
  border-radius: 999rem;
  box-shadow: 0.25rem 0.25rem 0 #000000;
  text-align: center;
}

.stat-copy span,
.stat-copy i {
  color: var(--muted);
  font-size: 0.82rem;
  font-style: normal;
}

.stat-copy strong {
  color: var(--accent-alt);
  font-size: 1.85rem;
}

.right-column {
  padding: 0 1% 1% 1%;
}

.right-chat-slot {
  flex: 0 0 50%;
}

.broadcast-stage[data-league='champions-league'] .scoreboard {
  min-height: 62%;
  background: #010056;
  border-color: var(--border);
  border-radius: 0.75rem;
}

.broadcast-stage[data-league='champions-league'] .score-team {
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0)),
    var(--panel);
}

.broadcast-stage[data-league='champions-league'] .score-core {
  background: var(--accent);
  border-color: var(--border);
}

.broadcast-stage[data-league='premier-league'] .scoreboard {
  min-height: 60%;
  padding: 0.22rem;
  overflow: visible;
  display: grid;
  grid-template-columns:
    minmax(5.5rem, 0.9fr)
    5rem
    minmax(0, 1.25fr)
    minmax(6rem, 1.25fr)
    minmax(0, 1.25fr)
    5rem
    minmax(5.5rem, 0.9fr);
  grid-template-rows: 1fr;
  align-items: center;
  background: var(--dark);
  border-color: var(--accent-alt);
  border-radius: 999rem;
}

.broadcast-stage[data-league='premier-league'] .score-team {
  grid-row: 1;
  display: grid;
  min-width: 0;
  height: 100%;
  gap: 0;
  padding: 0;
  background: var(--panel);
  border-radius: 0;
}

.broadcast-stage[data-league='premier-league'] .score-team-home {
  grid-column: 2 / 4;
  grid-template-columns: 5rem minmax(0, 1fr);
  cursor: default;
}

.broadcast-stage[data-league='premier-league'] .score-team-away {
  grid-column: 5 / 7;
  grid-template-columns: minmax(0, 1fr) 5rem;
}

.broadcast-stage[data-league='premier-league'] .score-team strong {
  padding: 0 0.5rem;
  text-align: center;
}

.broadcast-stage[data-league='premier-league'] .team-code-slot {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  padding-inline: 0.4rem;
}

.broadcast-stage[data-league='premier-league'] .score-core {
  display: contents;
}

.broadcast-stage[data-league='premier-league'] .score-status {
  display: none;
}

.broadcast-stage[data-league='premier-league'] .score-clock {
  grid-column: 1;
  grid-row: 1;
  width: 100%;
  height: 100%;
  padding: 0.22rem 0.56rem;
  background: transparent;
  border-radius: 999rem;
  color: var(--muted);
  font-size: 2rem;
  text-align: center;
}

.broadcast-stage[data-league='premier-league'] .score-added-time {
  grid-column: 7;
  grid-row: 1;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.08rem;
  background: transparent;
  color: var(--muted);
  font-weight: 950;
  text-align: center;
}

.broadcast-stage[data-league='premier-league'] .score-added-time span {
  font-size: 0.74rem;
  line-height: 1;
}

.broadcast-stage[data-league='premier-league'] .score-added-time strong {
  font-size: 2rem;
  line-height: 1;
}

.broadcast-stage[data-league='premier-league'] .score-number {
  grid-column: 4;
  grid-row: 1;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent);
  color: var(--text);
  font-size: 2.8rem;
}

.broadcast-stage[data-league='premier-league'] .score-team .team-mark {
  width: 4.2rem;
  height: 4.2rem;
  overflow: hidden;
  border-radius: 999rem;
  background: var(--text);
  border-color: var(--accent-alt);
  color: var(--panel);
}

.broadcast-stage[data-league='premier-league'] .score-team .country-flag {
  flex: 0 0 auto;
  width: 110%;
  height: 110%;
  max-width: none;
}

.broadcast-stage[data-league='europa-league'] .scoreboard {
  min-height: 62%;
  overflow: visible;
  border-radius: 0.4rem;
  border-color: var(--accent-alt);
  background: var(--dark);
}

.broadcast-stage[data-league='europa-league'] .score-core {
  background: var(--accent);
}

.broadcast-stage[data-league='europa-league'] .score-added-time {
  position: absolute;
  left: 50%;
  top: calc(100% + 0.28rem);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.46rem;
  min-width: 9.2rem;
  height: 2.15rem;
  padding: 0 0.8rem;
  background: var(--accent-alt);
  border: 0.12rem solid var(--dark);
  border-radius: 0.25rem;
  color: var(--dark);
  font-weight: 950;
  transform: translateX(-50%) skewX(5deg);
  box-shadow: 0.22rem 0.22rem 0 #000000;
}

.broadcast-stage[data-league='europa-league'] .score-added-time span,
.broadcast-stage[data-league='europa-league'] .score-added-time strong {
  transform: skewX(-5deg);
}

.broadcast-stage[data-league='europa-league'] .scoreboard {
  transform: skewX(-5deg);
}

.broadcast-stage[data-league='europa-league'] .scoreboard > * {
  transform: skewX(5deg);
}

.broadcast-stage[data-league='europa-league'] .scoreboard > .score-added-time {
  transform: translateX(-50%) skewX(5deg);
}

.broadcast-stage[data-league='carabao-cup'] .formation-card {
  border-radius: 0.25rem;
}

.broadcast-stage[data-league='premier-league'] .worldcup-formation-band {
  flex: 0 0 4.7%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0.62rem;
  background: var(--panel);
  border-bottom: 0.1rem solid var(--accent-alt);
  color: var(--text);
  font-size: 0.72rem;
}

.broadcast-stage[data-league='premier-league'] .worldcup-formation-band span {
  display: none;
}

.broadcast-stage[data-league='premier-league'] .formation-ribbon-label,
.broadcast-stage[data-league='premier-league'] .formation-ribbon-code {
  display: inline-flex;
  align-items: center;
  font-style: normal;
  font-weight: 950;
}

.broadcast-stage[data-league='premier-league'] .formation-ribbon-code {
  color: var(--accent-alt);
}

.broadcast-stage[data-league='premier-league'] .formation-card {
  border-color: var(--accent-alt);
}

.broadcast-stage[data-league='premier-league'] .formation-header {
  background: var(--dark);
  border-bottom-color: var(--accent-alt);
}

.broadcast-stage[data-league='premier-league'] .pitch {
  background: var(--team-pitch, var(--pitch));
  border-color: var(--accent-alt);
}

.broadcast-stage[data-league='premier-league'] .pitch-stripes {
  flex-direction: row;
}

.broadcast-stage[data-league='premier-league'] .pitch-stripes span {
  background: var(--team-pitch, var(--pitch));
}

.broadcast-stage[data-league='premier-league'] .pitch-stripes span:nth-child(2),
.broadcast-stage[data-league='premier-league'] .pitch-stripes span:nth-child(5) {
  background: var(--team-pitch-alt, var(--pitch-alt));
}

.broadcast-stage[data-league='premier-league'] .pitch-stripes span:nth-child(3),
.broadcast-stage[data-league='premier-league'] .pitch-stripes span:nth-child(4) {
  background: var(--team-pitch, var(--pitch));
}

.broadcast-stage[data-league='premier-league'] .halfway-line,
.broadcast-stage[data-league='premier-league'] .center-circle,
.broadcast-stage[data-league='premier-league'] .penalty-box,
.broadcast-stage[data-league='premier-league'] .goal-area,
.broadcast-stage[data-league='premier-league'] .corner-arc {
  border-color: var(--accent-alt);
}

.broadcast-stage[data-league='premier-league'] .center-spot,
.broadcast-stage[data-league='premier-league'] .penalty-spot {
  background: var(--accent-alt);
}

.broadcast-stage[data-league='champions-league'] .formation-card,
.broadcast-stage[data-league='europa-league'] .formation-card {
  border-color: var(--accent-alt);
}

.broadcast-stage[data-league='champions-league'] .formation-side-rail,
.broadcast-stage[data-league='europa-league'] .formation-side-rail {
  position: absolute;
  top: 15%;
  bottom: 0.9rem;
  z-index: 7;
  width: 0.9rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent);
  border: 0.08rem solid var(--border);
  color: var(--text);
  font-size: 0.54rem;
  font-weight: 950;
  letter-spacing: 0;
  writing-mode: vertical-rl;
  pointer-events: none;
}

.broadcast-stage[data-league='champions-league'] .formation-side-rail-left,
.broadcast-stage[data-league='europa-league'] .formation-side-rail-left {
  left: 0.42rem;
}

.broadcast-stage[data-league='champions-league'] .formation-side-rail-right,
.broadcast-stage[data-league='europa-league'] .formation-side-rail-right {
  right: 0.42rem;
  background: var(--accent-alt);
  color: var(--dark);
}

.broadcast-stage[data-league='champions-league'] .pitch,
.broadcast-stage[data-league='europa-league'] .pitch {
  background: var(--team-pitch, var(--pitch));
  border-color: var(--accent-alt);
}

.broadcast-stage[data-league='champions-league'] .pitch-stripes,
.broadcast-stage[data-league='europa-league'] .pitch-stripes {
  display: flex;
  flex-direction: column;
}

.broadcast-stage[data-league='champions-league'] .pitch-stripes span,
.broadcast-stage[data-league='europa-league'] .pitch-stripes span {
  background: var(--team-pitch, var(--pitch));
}

.broadcast-stage[data-league='champions-league'] .pitch-stripes span:nth-child(even),
.broadcast-stage[data-league='europa-league'] .pitch-stripes span:nth-child(even) {
  background: var(--team-pitch-alt, var(--pitch-alt));
}

.broadcast-stage[data-league='champions-league'] .pitch-stripes span:nth-child(3),
.broadcast-stage[data-league='europa-league'] .pitch-stripes span:nth-child(3) {
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0)),
    var(--team-pitch, var(--pitch));
}

.broadcast-stage[data-league='champions-league'] .field-markings::before,
.broadcast-stage[data-league='europa-league'] .field-markings::before {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background:
    linear-gradient(0deg, transparent 0 33%, rgba(255, 255, 255, 0.16) 33% calc(33% + 0.06rem), transparent calc(33% + 0.06rem) 66%, rgba(255, 255, 255, 0.16) 66% calc(66% + 0.06rem), transparent calc(66% + 0.06rem));
  opacity: 0.7;
  content: '';
}

.broadcast-stage[data-league='champions-league'] .halfway-line,
.broadcast-stage[data-league='champions-league'] .center-circle,
.broadcast-stage[data-league='champions-league'] .penalty-box,
.broadcast-stage[data-league='champions-league'] .goal-area,
.broadcast-stage[data-league='champions-league'] .corner-arc,
.broadcast-stage[data-league='europa-league'] .halfway-line,
.broadcast-stage[data-league='europa-league'] .center-circle,
.broadcast-stage[data-league='europa-league'] .penalty-box,
.broadcast-stage[data-league='europa-league'] .goal-area,
.broadcast-stage[data-league='europa-league'] .corner-arc {
  border-color: var(--muted);
}

.broadcast-stage[data-league='champions-league'] .center-spot,
.broadcast-stage[data-league='champions-league'] .penalty-spot,
.broadcast-stage[data-league='europa-league'] .center-spot,
.broadcast-stage[data-league='europa-league'] .penalty-spot {
  background: var(--muted);
}

.broadcast-stage[data-league='fa-cup'] .formation-card,
.broadcast-stage[data-league='fa-cup'] .scoreboard {
  border-width: 0.24rem;
}

.broadcast-stage[data-league='world-cup-2026'] .score-core,
.broadcast-stage[data-league='world-cup-2026'] .event-title-box {
  background: var(--accent);
}

.broadcast-stage[data-league='world-cup-2026'] .scoreboard {
  min-height: 82%;
  display: grid;
  grid-template-columns: 34% 32% 34%;
  grid-template-rows: 16% 58% 26%;
  align-items: stretch;
  background: #071866;
  border-color: #F5F1E8;
  border-radius: 0.42rem;
}

.broadcast-stage[data-league='world-cup-2026'] .worldcup-score-strip {
  grid-column: 1 / -1;
  grid-row: 1;
  display: flex;
  height: 100%;
  border-bottom: 0.12rem solid #F5F1E8;
}

.broadcast-stage[data-league='world-cup-2026'] .worldcup-score-strip span,
.broadcast-stage[data-league='world-cup-2026'] .worldcup-formation-band span {
  flex: 1 1 0;
}

.broadcast-stage[data-league='world-cup-2026'] .worldcup-score-strip span:nth-child(1),
.broadcast-stage[data-league='world-cup-2026'] .worldcup-formation-band span:nth-child(1) {
  background: #C8102E;
}

.broadcast-stage[data-league='world-cup-2026'] .worldcup-score-strip span:nth-child(2),
.broadcast-stage[data-league='world-cup-2026'] .worldcup-formation-band span:nth-child(2) {
  background: #D4AF37;
}

.broadcast-stage[data-league='world-cup-2026'] .worldcup-score-strip span:nth-child(3),
.broadcast-stage[data-league='world-cup-2026'] .worldcup-formation-band span:nth-child(3) {
  background: #000000;
}

.broadcast-stage[data-league='world-cup-2026'] .worldcup-score-strip span:nth-child(4),
.broadcast-stage[data-league='world-cup-2026'] .worldcup-formation-band span:nth-child(4) {
  background: #F5F1E8;
}

.broadcast-stage[data-league='world-cup-2026'] .worldcup-score-strip span:nth-child(5),
.broadcast-stage[data-league='world-cup-2026'] .worldcup-formation-band span:nth-child(5) {
  background: #003478;
}

.broadcast-stage[data-league='world-cup-2026'] .score-team {
  grid-row: 2 / 4;
  flex-direction: column;
  gap: 0.58rem;
  padding: 0.58rem 0.9rem 0.72rem;
  background: #0B2D92;
  border: 0;
  font-size: 1.5rem;
  text-align: center;
}

.broadcast-stage[data-league='world-cup-2026'] .score-team-home {
  grid-column: 1;
}

.broadcast-stage[data-league='world-cup-2026'] .score-team-away {
  grid-column: 3;
}

.broadcast-stage[data-league='world-cup-2026'] .country-badge {
  position: relative;
  width: 7.05rem;
  border-radius: 50%;
  overflow: hidden;
  background: #F5F1E8;
  border: 0.24rem solid #F5F1E8;
  box-shadow:
    inset 0 0 0 0.18rem #D4AF37,
    0.24rem 0.24rem 0 #000000;
  font-size: 1.12rem;
}

.broadcast-stage[data-league='world-cup-2026'] .country-flag {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.broadcast-stage[data-league='world-cup-2026'] .country-badge::after {
  position: absolute;
  left: 15%;
  top: 10%;
  width: 44%;
  height: 16%;
  display: block;
  background: rgba(255, 255, 255, 0.42);
  border-radius: 999rem;
  content: '';
  transform: rotate(-18deg);
}

.broadcast-stage[data-league='world-cup-2026'] .score-team-away .team-mark {
  order: 1;
}

.broadcast-stage[data-league='world-cup-2026'] .score-team-away strong {
  order: 2;
}

.broadcast-stage[data-league='world-cup-2026'] .score-core {
  grid-column: 2;
  grid-row: 2;
  background: #F5F1E8;
  border: 0;
  color: #000000;
}

.broadcast-stage[data-league='world-cup-2026'] .score-status,
.broadcast-stage[data-league='world-cup-2026'] .score-clock {
  color: #C8102E;
}

.broadcast-stage[data-league='world-cup-2026'] .score-number {
  color: #000000;
}

.broadcast-stage[data-league='world-cup-2026'] .score-added-time {
  grid-column: 2;
  grid-row: 3;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.55rem;
  background: #D4AF37;
  border-top: 0.12rem solid #000000;
  color: #000000;
  font-weight: 900;
}

.broadcast-stage[data-league='world-cup-2026'] .score-added-time span {
  font-size: 0.86rem;
}

.broadcast-stage[data-league='world-cup-2026'] .score-added-time strong {
  font-size: 1.7rem;
}

.broadcast-stage[data-league='world-cup-2026'] .worldcup-formation-band {
  flex: 0 0 5.2%;
  display: flex;
  border-bottom: 0.1rem solid #F5F1E8;
}

.broadcast-stage[data-league='world-cup-2026'] .formation-card {
  background: #050505;
  border-color: #D4AF37;
  box-shadow: 0.44rem 0.44rem 0 #000000;
}

.broadcast-stage[data-league='world-cup-2026'] .formation-header {
  flex-basis: 12.5%;
  background: #071866;
  border-bottom-color: #D4AF37;
}

.broadcast-stage[data-league='world-cup-2026'] .pitch {
  margin: 2.25%;
  background: repeating-radial-gradient(circle at 50% 50%, #111111 0 14%, #202020 14% 28%);
  border-color: #D4AF37;
}

.broadcast-stage[data-league='world-cup-2026'] .pitch-stripes {
  display: none;
}

.broadcast-stage[data-league='world-cup-2026'] .field-markings {
  z-index: 1;
}

.broadcast-stage[data-league='world-cup-2026'] .halfway-line,
.broadcast-stage[data-league='world-cup-2026'] .center-circle,
.broadcast-stage[data-league='world-cup-2026'] .penalty-box,
.broadcast-stage[data-league='world-cup-2026'] .goal-area,
.broadcast-stage[data-league='world-cup-2026'] .corner-arc {
  border-color: #D4AF37;
}

.broadcast-stage[data-league='world-cup-2026'] .center-spot,
.broadcast-stage[data-league='world-cup-2026'] .penalty-spot {
  background: #F5F1E8;
}

.broadcast-stage[data-league='world-cup-2026'] .formation-card:nth-child(2) .shirt {
  background: var(--team-player, var(--accent-alt));
  border-color: var(--team-player-border, #F5F1E8);
}

.broadcast-stage[data-revision='material'] .scoreboard,
.broadcast-stage[data-revision='material'] .formation-card,
.broadcast-stage[data-revision='material'] .event-card,
.broadcast-stage[data-revision='material'] .event-logo-circle {
  box-shadow:
    0.45rem 0.45rem 0 #000000,
    0 0 0.7rem rgba(255, 255, 255, 0.12);
}

.broadcast-stage[data-revision='material'] .scoreboard {
  position: relative;
  isolation: isolate;
}

.broadcast-stage[data-revision='material'] .scoreboard > * {
  position: relative;
  z-index: 1;
}

.broadcast-stage[data-revision='material'][data-league='europa-league'] .scoreboard > .score-added-time {
  position: absolute;
  z-index: 3;
}

.broadcast-stage[data-revision='material'] .scoreboard::before {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
  content: '';
  background:
    linear-gradient(105deg, rgba(255, 255, 255, 0) 0 28%, rgba(255, 255, 255, 0.1) 38%, rgba(255, 255, 255, 0) 48%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.09), rgba(255, 255, 255, 0) 40%);
  mix-blend-mode: screen;
}

.broadcast-stage[data-revision='material'] .scoreboard::after {
  position: absolute;
  inset: 0.28rem;
  z-index: 2;
  pointer-events: none;
  border: 0.08rem solid rgba(255, 255, 255, 0.18);
  border-radius: inherit;
  content: '';
}

.broadcast-stage[data-revision='material'] .score-team {
  background-image: linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0) 42%);
}

.broadcast-stage[data-revision='material'] .score-core {
  box-shadow:
    inset 0 0.12rem 0 rgba(255, 255, 255, 0.22),
    inset 0 -0.12rem 0 rgba(0, 0, 0, 0.12);
}

.broadcast-stage[data-revision='material'] .country-badge {
  filter: saturate(1.06) contrast(1.04);
  box-shadow:
    inset 0 0 0 0.18rem rgba(212, 175, 55, 0.9),
    inset 0 0.7rem 1rem rgba(255, 255, 255, 0.12),
    inset 0 -0.7rem 1rem rgba(0, 0, 0, 0.14),
    0.24rem 0.24rem 0 #000000,
    0 0 0.55rem rgba(255, 255, 255, 0.12);
}

.broadcast-stage[data-revision='material'] .country-badge::before {
  position: absolute;
  inset: 0.22rem;
  z-index: 2;
  display: block;
  pointer-events: none;
  border-radius: 50%;
  content: '';
  background: radial-gradient(circle at 31% 22%, rgba(255, 255, 255, 0.22), rgba(255, 255, 255, 0) 42%);
}

.broadcast-stage[data-revision='material'] .country-badge::after {
  z-index: 3;
  background: rgba(255, 255, 255, 0.16);
}

.broadcast-stage[data-revision='material'] .country-flag {
  z-index: 1;
}

.broadcast-stage[data-revision='material'] .formation-card {
  isolation: isolate;
}

.broadcast-stage[data-revision='material'] .formation-card::after {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  content: '';
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.07), rgba(255, 255, 255, 0) 18%),
    radial-gradient(circle at 14% 12%, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0) 30%);
}

.broadcast-stage[data-revision='material'] .formation-card > *:not(.formation-side-rail) {
  position: relative;
  z-index: 2;
}

.broadcast-stage[data-revision='material'] .pitch {
  position: relative;
  box-shadow:
    inset 0 0 0 0.08rem rgba(255, 255, 255, 0.1),
    inset 0 0 1.2rem rgba(255, 255, 255, 0.06);
}

.broadcast-stage[data-revision='material'] .pitch::before {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  content: '';
  background:
    linear-gradient(90deg, rgba(255, 255, 255, 0.07) 0 1px, transparent 1px 12.5%),
    linear-gradient(0deg, rgba(255, 255, 255, 0.05) 0 1px, transparent 1px 12.5%),
    radial-gradient(circle at 50% 50%, rgba(212, 175, 55, 0.08), rgba(212, 175, 55, 0) 42%);
}

.broadcast-stage[data-revision='material'] .event-card,
.broadcast-stage[data-revision='material'] .event-logo-circle {
  position: relative;
  isolation: isolate;
}

.broadcast-stage[data-revision='material'] .event-card::before {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
  content: '';
  background:
    linear-gradient(105deg, rgba(255, 255, 255, 0) 0 25%, rgba(255, 255, 255, 0.12) 36%, rgba(255, 255, 255, 0) 48%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0) 48%);
  mix-blend-mode: screen;
}

.broadcast-stage[data-revision='material'] .event-title-box,
.broadcast-stage[data-revision='material'] .event-detail-box,
.broadcast-stage[data-revision='material'] .event-logo-circle span {
  position: relative;
  z-index: 1;
}

.broadcast-stage[data-revision='material'] .event-logo-circle::after {
  position: absolute;
  left: 18%;
  top: 14%;
  z-index: 2;
  width: 42%;
  height: 16%;
  pointer-events: none;
  border-radius: 999rem;
  background: rgba(255, 255, 255, 0.18);
  content: '';
  transform: rotate(-18deg);
}

/* Team palette only: preserve each competition's formation-card structure. */
.broadcast-stage[data-team-color-mode='full'] .formation-card[data-team-color='true'] {
  background: var(--team-secondary, var(--team-primary));
  border-color: var(--team-frame);
}

.broadcast-stage[data-team-color-mode='full'] .formation-card[data-team-color='true'] .formation-header {
  background: var(--team-secondary, var(--team-primary));
  border-bottom-color: var(--team-frame);
  color: var(--team-secondary-text, var(--team-primary-text));
}

.broadcast-stage[data-team-color-mode='full'] .formation-card[data-team-color='true'] .formation-header strong {
  color: inherit;
}

.broadcast-stage[data-team-color-mode='full'] .formation-card[data-accent-color] .shape-pill {
  background: var(--team-accent);
  color: var(--team-accent-text);
}

.broadcast-stage[data-team-color-mode='full'] .formation-card[data-team-color='true'] .pitch {
  border-color: var(--team-frame);
}

.broadcast-stage[data-team-color-mode='full'] .formation-card[data-team-color='true'] .halfway-line,
.broadcast-stage[data-team-color-mode='full'] .formation-card[data-team-color='true'] .center-circle,
.broadcast-stage[data-team-color-mode='full'] .formation-card[data-team-color='true'] .penalty-box,
.broadcast-stage[data-team-color-mode='full'] .formation-card[data-team-color='true'] .goal-area,
.broadcast-stage[data-team-color-mode='full'] .formation-card[data-team-color='true'] .corner-arc {
  border-color: var(--team-field-line);
}

.broadcast-stage[data-team-color-mode='full'] .formation-card[data-team-color='true'] .center-spot,
.broadcast-stage[data-team-color-mode='full'] .formation-card[data-team-color='true'] .penalty-spot {
  background: var(--team-field-line);
}

@keyframes event-rise {
  0% {
    transform: translateY(145%);
  }
  8% {
    transform: translateY(0);
  }
  92% {
    transform: translateY(0);
  }
  100% {
    transform: translateY(145%);
  }
}
</style>
