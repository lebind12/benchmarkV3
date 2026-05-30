<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Activity, CalendarDays, MapPin, MonitorPlay, Shield, Swords, Trophy, UsersRound, X } from 'lucide-vue-next'
import {
  getLeagueStandings,
  getLineups,
  getMatch,
  getMatchupInsights,
  getStatistics,
  getTeamRecentMatches,
} from '@/lib/api/fixtureDetail'
import { leagueName, playerName, teamName } from '@/lib/displayNames'
import { kstTime } from '@/lib/format/datetime'
import type { FixtureSummary, PlayerRef } from '@/types/home'
import type {
  LeagueStandingsPayload,
  LineupPlayer,
  MatchDetail,
  MatchupInsightMetric,
  MatchupInsightsPayload,
  TeamLineup,
  TeamStat,
} from '@/types/fixtureDetail'
import { resolveFormation } from '@/lib/formations'

const route = useRoute()
const router = useRouter()

const match = ref<MatchDetail | null>(null)
const lineups = ref<{ home: TeamLineup; away: TeamLineup } | null>(null)
const homeTeamFixtures = ref<FixtureSummary[]>([])
const awayTeamFixtures = ref<FixtureSummary[]>([])
const matchupInsights = ref<MatchupInsightsPayload | null>(null)
const statistics = ref<{ home: TeamStat; away: TeamStat } | null>(null)
const standings = ref<LeagueStandingsPayload | null>(null)
const status = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const error = ref<string | null>(null)
const isBroadcastPickerOpen = ref(false)

const externalId = computed(() => Number(route.params.externalId))
const highlightedRows = computed(() => {
  if (!standings.value || !match.value) return []
  const ids = new Set([match.value.home.external_id, match.value.away.external_id])
  return standings.value.rows.filter((row) => ids.has(row.team.external_id))
})
const homeRecent = computed(() =>
  match.value ? recentFixturesFor(match.value.home.external_id, homeTeamFixtures.value) : [],
)
const awayRecent = computed(() =>
  match.value ? recentFixturesFor(match.value.away.external_id, awayTeamFixtures.value) : [],
)
const hasConfirmedLineups = computed(() =>
  Boolean(lineups.value?.home.start_xi.length || lineups.value?.away.start_xi.length),
)
const fixtureHasStarted = computed(() =>
  match.value
    ? !['NS', 'PST', 'CANC', 'SUSP'].includes(match.value.status_short)
    : false,
)
const lineupAvailabilityLabel = computed(() => {
  if (hasConfirmedLineups.value) {
    if (match.value && ['FT', 'AET', 'PEN'].includes(match.value.status_short)) return '최종 라인업'
    return fixtureHasStarted.value ? '실시간 라인업' : '라인업 선공개'
  }
  if (fixtureHasStarted.value) return '라인업 데이터 없음'
  return '킥오프 전 미공개'
})

type LineupSide = 'home' | 'away'

interface PitchPlayer {
  row: LineupPlayer
  side: LineupSide
  x: number
  y: number
}

const lineupPanelTitle = computed(() => {
  if (!hasConfirmedLineups.value) return '라인업'
  return fixtureHasStarted.value ? '라인업' : '예상 라인업'
})

const lineupSections = computed<Array<{ side: LineupSide; lineup: TeamLineup }>>(() => {
  if (!lineups.value) return []
  return [
    { side: 'home', lineup: lineups.value.home },
    { side: 'away', lineup: lineups.value.away },
  ]
})

const combinedPitchPlayers = computed(() =>
  lineupSections.value.flatMap(({ side, lineup }) => pitchPlayers(lineup, side)),
)

const hasScore = computed(() =>
  Boolean(match.value && (match.value.goals_home != null || match.value.goals_away != null)),
)
const broadcastQuery = computed(() => {
  if (!match.value) return ''
  const query = new URLSearchParams({
    fixtureId: String(match.value.external_id),
    league: match.value.league.slug,
  })
  return query.toString()
})
const watchTogetherHref = computed(() => `/broadcast.html?${broadcastQuery.value}`)
const programHref = computed(() => `/broadcast-program.html?${broadcastQuery.value}`)

function kstDate(iso: string): string {
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: 'long',
    day: 'numeric',
    weekday: 'short',
  }).format(new Date(iso))
}

function displayScore(value: number | null): string {
  return value == null ? '-' : String(value)
}

function statPair(key: keyof TeamStat): { home: number | null; away: number | null } {
  return {
    home: statistics.value?.home[key] ?? null,
    away: statistics.value?.away[key] ?? null,
  }
}

function isCompleted(status: string): boolean {
  return ['FT', 'AET', 'PEN'].includes(status)
}

function recentFixturesFor(teamExternalId: number, fixtures: FixtureSummary[]): FixtureSummary[] {
  const kickoff = match.value ? new Date(match.value.kickoff_at).getTime() : Number.POSITIVE_INFINITY
  return fixtures
    .filter((fixture) => fixture.external_id !== match.value?.external_id)
    .filter((fixture) => isCompleted(fixture.status_short))
    .filter((fixture) => new Date(fixture.kickoff_at).getTime() <= kickoff)
    .filter((fixture) =>
      fixture.home.external_id === teamExternalId || fixture.away.external_id === teamExternalId,
    )
    .sort((a, b) => new Date(b.kickoff_at).getTime() - new Date(a.kickoff_at).getTime())
    .slice(0, 10)
}

function fixtureOutcome(fixture: FixtureSummary, teamExternalId: number): 'W' | 'D' | 'L' | null {
  if (fixture.goals_home == null || fixture.goals_away == null) return null
  if (fixture.goals_home === fixture.goals_away) return 'D'
  const isHome = fixture.home.external_id === teamExternalId
  const won = isHome ? fixture.goals_home > fixture.goals_away : fixture.goals_away > fixture.goals_home
  return won ? 'W' : 'L'
}

function opponentName(fixture: FixtureSummary, teamExternalId: number): string {
  return teamName(fixture.home.external_id === teamExternalId ? fixture.away : fixture.home)
}

function shortMatchDate(iso: string): string {
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(iso))
}

function homeAwayLabel(fixture: FixtureSummary, teamExternalId: number): string {
  return fixture.home.external_id === teamExternalId ? '홈' : '원정'
}

function scoreLine(fixture: FixtureSummary): string {
  return `${teamName(fixture.home)} ${displayScore(fixture.goals_home)}-${displayScore(fixture.goals_away)} ${teamName(fixture.away)}`
}

function insightValue(value: number | null, metric: MatchupInsightMetric): string {
  if (value == null) return '-'
  const formatted = metric.precision > 0 ? value.toFixed(metric.precision) : String(Math.round(value))
  return metric.unit ? `${formatted}${metric.unit}` : formatted
}

function insightMax(metric: MatchupInsightMetric): number {
  return Math.max(metric.home ?? 0, metric.away ?? 0, 1)
}

function insightWidth(value: number | null, metric: MatchupInsightMetric): string {
  if (value == null) return '0%'
  return `${Math.max(4, Math.min(100, (value / insightMax(metric)) * 100))}%`
}

function sampleLabel(size: number): string {
  return size === 1 ? '실제 기록' : `${size}경기 평균`
}

function playerShortName(player: PlayerRef): string {
  if (player.short_name_ko) return player.short_name_ko
  const translated = player.name_ko
  if (translated?.includes(' ')) return translated.split(/\s+/).at(-1) ?? translated
  if (translated) return translated
  if (player.name.includes(' ')) return player.name.split(/\s+/).at(-1) ?? player.name
  return player.name
}

function parsedGrid(grid: string | null): { line: number; slot: number } | null {
  const match = grid?.match(/^(\d+):(\d+)$/)
  if (!match) return null
  return {
    line: Number(match[1]),
    slot: Number(match[2]),
  }
}

function pct(slot: number, count: number): number {
  return (slot / (count + 1)) * 100
}

function yForLine(line: number, lineCount: number, side: LineupSide): number {
  if (lineCount <= 1) return side === 'home' ? 76 : 24
  const progress = (line - 1) / (lineCount - 1)
  return side === 'home' ? 92 - progress * 40 : 8 + progress * 40
}

function pitchPlayers(lineup: TeamLineup, side: LineupSide): PitchPlayer[] {
  const withGrid = lineup.start_xi
    .map((row) => ({ row, grid: parsedGrid(row.grid) }))
    .filter((item): item is { row: LineupPlayer; grid: { line: number; slot: number } } => item.grid !== null)

  if (withGrid.length === lineup.start_xi.length && withGrid.length > 0) {
    const lineCount = Math.max(...withGrid.map((item) => item.grid.line))
    const slotsByLine = withGrid.reduce<Record<number, number>>((acc, item) => {
      acc[item.grid.line] = Math.max(acc[item.grid.line] ?? 0, item.grid.slot)
      return acc
    }, {})

    return withGrid.map((item) => ({
      row: item.row,
      side,
      x: pct(item.grid.slot, slotsByLine[item.grid.line] ?? 1),
      y: yForLine(item.grid.line, lineCount, side),
    }))
  }

  const counts = resolveFormation(lineup.formation)
  const nodes: PitchPlayer[] = []
  let cursor = 0

  counts.forEach((count, lineIndex) => {
    lineup.start_xi.slice(cursor, cursor + count).forEach((row, slotIndex) => {
      nodes.push({
        row,
        side,
        x: pct(slotIndex + 1, count),
        y: yForLine(lineIndex + 1, counts.length, side),
      })
    })
    cursor += count
  })

  return nodes
}

function subbedInPlayers(lineup: TeamLineup): LineupPlayer[] {
  if (!fixtureHasStarted.value) return []
  return lineup.bench.filter((row) => row.minutes != null && row.minutes > 0)
}

function starterSubLabel(row: LineupPlayer): string | null {
  if (!fixtureHasStarted.value || row.minutes == null || row.minutes >= 90) return null
  return `${row.minutes}'`
}

function benchSubLabel(row: LineupPlayer): string | null {
  if (!fixtureHasStarted.value || row.minutes == null || row.minutes <= 0) return null
  return `${row.minutes}'`
}

function teamSubbedInPlayers(side: LineupSide): LineupPlayer[] {
  const lineup = side === 'home' ? lineups.value?.home : lineups.value?.away
  return lineup ? subbedInPlayers(lineup) : []
}

function ratingClass(rating: number | null): string {
  if (rating == null) return ''
  if (rating >= 8) return 'rating-chip--great'
  if (rating >= 7) return 'rating-chip--good'
  if (rating < 6.5) return 'rating-chip--low'
  return 'rating-chip--ok'
}

function playerTitle(row: LineupPlayer): string {
  const parts = [`${playerName(row.player)} #${row.number}`, row.position]
  if (row.rating != null) parts.push(`평점 ${row.rating.toFixed(1)}`)
  if (row.minutes != null) parts.push(`${row.minutes}분 출전`)
  return parts.join(' · ')
}

function goPlayer(slug: string) {
  void router.push(`/players/${slug}`)
}

function openBroadcastPicker() {
  isBroadcastPickerOpen.value = true
}

function closeBroadcastPicker() {
  isBroadcastPickerOpen.value = false
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') closeBroadcastPicker()
}

async function loadFixture() {
  status.value = 'loading'
  error.value = null
  match.value = null
  lineups.value = null
  homeTeamFixtures.value = []
  awayTeamFixtures.value = []
  matchupInsights.value = null
  statistics.value = null
  standings.value = null

  try {
    match.value = await getMatch(externalId.value)
    const [lineupResult, recentResult, statResult, standingResult, insightResult] = await Promise.allSettled([
      getLineups(externalId.value),
      getTeamRecentMatches(externalId.value),
      getStatistics(externalId.value),
      getLeagueStandings(externalId.value),
      getMatchupInsights(externalId.value),
    ])

    if (lineupResult.status === 'fulfilled') lineups.value = lineupResult.value
    if (recentResult.status === 'fulfilled') {
      homeTeamFixtures.value = recentResult.value.home.fixtures
      awayTeamFixtures.value = recentResult.value.away.fixtures
    }
    if (statResult.status === 'fulfilled') statistics.value = statResult.value
    if (standingResult.status === 'fulfilled') standings.value = standingResult.value
    if (insightResult.status === 'fulfilled') matchupInsights.value = insightResult.value
    status.value = 'ok'
  } catch (err) {
    error.value = (err as Error).message
    status.value = 'error'
  }
}

onMounted(() => {
  void loadFixture()
})

watch(isBroadcastPickerOpen, (isOpen) => {
  if (typeof window === 'undefined') return
  if (isOpen) {
    window.addEventListener('keydown', onKeydown)
    return
  }
  window.removeEventListener('keydown', onKeydown)
})

watch(
  () => route.params.externalId,
  () => {
    void loadFixture()
  },
)

onBeforeUnmount(() => {
  if (typeof window === 'undefined') return
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <main class="fixture-page app-container" data-testid="ui-review-fixture-preview-page">
    <div v-if="status === 'loading'" class="state">경기 정보를 불러오는 중입니다.</div>
    <div v-else-if="status === 'error'" class="state state--error">{{ error }}</div>

    <template v-else-if="match">
      <header class="match-hero">
        <button
          type="button"
          class="streaming-button"
          :aria-expanded="isBroadcastPickerOpen"
          aria-controls="ui-review-broadcast-picker"
          @click="openBroadcastPicker"
        >
          <MonitorPlay :size="16" aria-hidden="true" />
          <span>스트리밍</span>
        </button>
        <div class="team-block">
          <img v-if="match.home.logo_url" :src="match.home.logo_url" :alt="teamName(match.home)" />
          <strong>{{ teamName(match.home) }}</strong>
        </div>
        <div class="match-center">
          <h1 v-if="hasScore" class="match-score" aria-label="경기 스코어">
            <b>{{ displayScore(match.goals_home) }}</b>
            <i>-</i>
            <b>{{ displayScore(match.goals_away) }}</b>
          </h1>
          <h1 v-else>{{ kstDate(match.kickoff_at) }} {{ kstTime(match.kickoff_at) }}</h1>
          <div class="match-meta">
            <span>{{ leagueName(match.league) }} · {{ match.round }}</span>
            <p v-if="hasScore">{{ match.status_long }} · {{ kstDate(match.kickoff_at) }} {{ kstTime(match.kickoff_at) }}</p>
            <p v-else>{{ match.status_long }}</p>
          </div>
        </div>
        <div class="team-block team-block--away">
          <img v-if="match.away.logo_url" :src="match.away.logo_url" :alt="teamName(match.away)" />
          <strong>{{ teamName(match.away) }}</strong>
        </div>
      </header>

      <div
        v-if="isBroadcastPickerOpen"
        class="broadcast-picker"
        role="presentation"
        @click.self="closeBroadcastPicker"
      >
        <section
          id="ui-review-broadcast-picker"
          class="broadcast-picker__panel"
          role="dialog"
          aria-modal="true"
          aria-labelledby="ui-review-broadcast-picker-title"
        >
          <div class="broadcast-picker__header">
            <div>
              <p>STREAMING</p>
              <h2 id="ui-review-broadcast-picker-title">방송 화면 선택</h2>
            </div>
            <button type="button" aria-label="닫기" @click="closeBroadcastPicker">
              <X :size="18" aria-hidden="true" />
            </button>
          </div>
          <div class="broadcast-picker__options">
            <a
              class="broadcast-picker__option broadcast-picker__option--program"
              :href="programHref"
              target="_blank"
              rel="noopener noreferrer"
              @click="closeBroadcastPicker"
            >
              <span class="broadcast-picker__icon" aria-hidden="true">
                <MonitorPlay :size="22" />
              </span>
              <span class="broadcast-picker__copy">
                <strong>TV 중계 화면</strong>
                <em>경기 화면 + 하단 배너</em>
              </span>
            </a>
            <a
              class="broadcast-picker__option"
              :href="watchTogetherHref"
              target="_blank"
              rel="noopener noreferrer"
              @click="closeBroadcastPicker"
            >
              <span class="broadcast-picker__icon" aria-hidden="true">
                <UsersRound :size="22" />
              </span>
              <span class="broadcast-picker__copy">
                <strong>같이보기 화면</strong>
                <em>캐릭터 중심 방송 레이아웃</em>
              </span>
            </a>
          </div>
        </section>
      </div>

      <section class="preview-grid" aria-label="경기 프리매치 후보">
        <article class="panel info-panel">
          <header class="panel__head">
            <span><CalendarDays :size="16" aria-hidden="true" /> 경기 정보</span>
          </header>
          <dl class="info-list">
            <div>
              <dt><MapPin :size="14" aria-hidden="true" /> 경기장</dt>
              <dd>{{ match.venue?.name ?? '경기장 미정' }}<span v-if="match.venue?.city"> · {{ match.venue.city }}</span></dd>
            </div>
            <div>
              <dt><Shield :size="14" aria-hidden="true" /> 심판</dt>
              <dd>{{ match.referee ?? '배정 전' }}</dd>
            </div>
            <div>
              <dt><Trophy :size="14" aria-hidden="true" /> 대회</dt>
              <dd>{{ leagueName(match.league) }}</dd>
            </div>
          </dl>
        </article>

        <article class="panel standings-panel">
          <header class="panel__head">
            <span><Trophy :size="16" aria-hidden="true" /> 현재 순위</span>
          </header>
          <div class="standings-pair">
            <div v-for="row in highlightedRows" :key="row.team.external_id">
              <span>{{ row.rank }}위</span>
              <strong>{{ teamName(row.team) }}</strong>
              <em>{{ row.points }}점 · {{ row.win }}승 {{ row.draw }}무 {{ row.loss }}패</em>
            </div>
            <div v-if="highlightedRows.length === 0" class="state state--inline">순위 데이터가 없습니다.</div>
          </div>
        </article>

        <article class="panel recent-panel">
          <header class="panel__head">
            <span><Swords :size="16" aria-hidden="true" /> 팀별 최근 10경기</span>
            <strong>완료 경기 기준</strong>
          </header>
          <div class="recent-match-grid">
            <section
              v-for="{ team, fixtures } in [
                { team: match.home, fixtures: homeRecent },
                { team: match.away, fixtures: awayRecent },
              ]"
              :key="team.external_id"
              class="recent-team-card"
            >
              <header class="recent-team-card__head">
                <span class="team-logo">
                  <img v-if="team.logo_url" :src="team.logo_url" :alt="teamName(team)" />
                </span>
                <strong>{{ teamName(team) }}</strong>
                <em>{{ fixtures.length }}경기</em>
              </header>
              <div class="recent-match-list">
                <div v-for="fixture in fixtures" :key="fixture.external_id" class="recent-match-row">
                  <span :class="`form-chip form-chip--${fixtureOutcome(fixture, team.external_id) ?? 'N'}`">
                    {{ fixtureOutcome(fixture, team.external_id) ?? '-' }}
                  </span>
                  <div>
                    <strong>{{ opponentName(fixture, team.external_id) }}</strong>
                    <small>{{ homeAwayLabel(fixture, team.external_id) }} · {{ scoreLine(fixture) }}</small>
                  </div>
                  <span class="recent-league-mark" :title="leagueName(fixture.league)">
                    <img v-if="fixture.league.logo_url" :src="fixture.league.logo_url" :alt="leagueName(fixture.league)" />
                    <b v-else>{{ fixture.league.short_name_ko ?? fixture.league.name }}</b>
                    <em>{{ shortMatchDate(fixture.kickoff_at) }}</em>
                  </span>
                </div>
                <div v-if="fixtures.length === 0" class="state state--inline">최근 완료 경기 데이터가 없습니다.</div>
              </div>
            </section>
          </div>
        </article>

        <article class="panel insight-panel">
          <header class="panel__head">
            <span><Activity :size="16" aria-hidden="true" /> {{ matchupInsights?.title ?? '매치업 인사이트' }}</span>
            <strong>{{ matchupInsights?.subtitle ?? '기록 기준' }}</strong>
          </header>
          <div v-if="matchupInsights" class="insight-grid">
            <div class="insight-teams">
              <div>
                <strong>{{ teamName(matchupInsights.home.team) }}</strong>
                <span>{{ sampleLabel(matchupInsights.home.sample_size) }}</span>
              </div>
              <div>
                <strong>{{ teamName(matchupInsights.away.team) }}</strong>
                <span>{{ sampleLabel(matchupInsights.away.sample_size) }}</span>
              </div>
            </div>
            <div v-for="metric in matchupInsights.metrics" :key="metric.key" class="insight-row">
              <span>{{ insightValue(metric.home, metric) }}</span>
              <strong>{{ metric.label }}</strong>
              <span>{{ insightValue(metric.away, metric) }}</span>
              <div class="insight-bars" aria-hidden="true">
                <i class="insight-bars__home" :style="{ width: insightWidth(metric.home, metric) }"></i>
                <i class="insight-bars__away" :style="{ width: insightWidth(metric.away, metric) }"></i>
              </div>
            </div>
          </div>
          <div v-else class="state state--inline">
            인사이트 데이터를 불러오지 못했습니다.
          </div>
        </article>

        <article class="panel lineup-panel">
          <header class="panel__head">
            <span><UsersRound :size="16" aria-hidden="true" /> {{ lineupPanelTitle }}</span>
            <strong>{{ lineupAvailabilityLabel }}</strong>
          </header>
          <div v-if="hasConfirmedLineups && lineups" class="lineup-grid">
            <section class="formation-card">
              <div class="formation-card__head">
                <div
                  v-for="{ side, lineup } in lineupSections"
                  :key="side"
                  class="formation-team"
                  :data-side="side"
                >
                  <span>{{ side === 'home' ? '홈' : '원정' }}</span>
                  <strong>{{ teamName(lineup.team) }}</strong>
                  <em>{{ lineup.formation ?? '포메이션 미정' }}</em>
                </div>
              </div>

              <div class="mini-pitch" aria-label="양 팀 포메이션">
                <button
                  v-for="node in combinedPitchPlayers"
                  :key="`${node.side}-${node.row.player.external_id}`"
                  type="button"
                  class="player-badge"
                  :data-side="node.side"
                  :style="{ left: `${node.x}%`, top: `${node.y}%` }"
                  :title="playerTitle(node.row)"
                  @click="goPlayer(node.row.player.slug)"
                >
                  <span class="player-badge__avatar">
                    <img
                      v-if="node.row.player.photo_url"
                      :src="node.row.player.photo_url"
                      :alt="playerName(node.row.player)"
                    />
                    <b v-else>{{ node.row.number }}</b>
                  </span>
                  <span class="player-badge__name">{{ playerShortName(node.row.player) }}</span>
                  <span
                    v-if="node.row.rating != null"
                    class="player-badge__rating"
                    :class="ratingClass(node.row.rating)"
                  >
                    {{ node.row.rating.toFixed(1) }}
                  </span>
                  <span
                    v-if="starterSubLabel(node.row)"
                    class="player-badge__sub player-badge__sub--out"
                    aria-label="교체 아웃"
                  >
                    ↓ {{ starterSubLabel(node.row) }}
                  </span>
                </button>
              </div>

              <div
                v-if="teamSubbedInPlayers('home').length || teamSubbedInPlayers('away').length"
                class="bench-grid"
              >
                <div
                  v-for="{ side, lineup } in lineupSections"
                  :key="`bench-${side}`"
                  class="bench-strip"
                >
                  <span class="bench-strip__label">{{ teamName(lineup.team) }} 교체 투입</span>
                  <button
                    v-for="row in teamSubbedInPlayers(side)"
                    :key="row.player.external_id"
                    type="button"
                    class="bench-chip"
                    :data-side="side"
                    :title="playerTitle(row)"
                    @click="goPlayer(row.player.slug)"
                  >
                    <span>↑ {{ benchSubLabel(row) }}</span>
                    <strong>{{ playerShortName(row.player) }}</strong>
                    <em v-if="row.rating != null" :class="ratingClass(row.rating)">
                      {{ row.rating.toFixed(1) }}
                    </em>
                  </button>
                </div>
              </div>
            </section>
          </div>
          <div v-else class="lineup-placeholder">
            공식 라인업이 들어오면 경기 상태와 무관하게 이 영역에 포메이션과 선발 요약을 채웁니다.
          </div>
        </article>

        <article class="panel stats-panel">
          <header class="panel__head">
            <span>기본 지표</span>
          </header>
          <div class="stat-list">
            <div v-for="item in [
              { label: '점유율', key: 'possession' as const },
              { label: '슈팅', key: 'shots_total' as const },
              { label: '유효슈팅', key: 'shots_on_target' as const },
              { label: '코너킥', key: 'corners' as const },
            ]" :key="item.key">
              <span>{{ statPair(item.key).home ?? '-' }}</span>
              <strong>{{ item.label }}</strong>
              <span>{{ statPair(item.key).away ?? '-' }}</span>
            </div>
          </div>
        </article>
      </section>
    </template>
  </main>
</template>

<style scoped>
.fixture-page {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 12px;
  height: calc(100vh - var(--header-height));
  min-height: 0;
  overflow: hidden;
  padding-block: 16px;
}

.match-hero,
.panel {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
}

.match-hero {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(360px, 0.8fr) minmax(0, 1fr);
  align-items: center;
  gap: 16px;
  padding: 18px 16px;
}

.streaming-button {
  position: absolute;
  top: 12px;
  right: 12px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 34px;
  border: 1px solid color-mix(in srgb, var(--color-primary) 38%, var(--color-border));
  border-radius: 999px;
  padding: 0 13px;
  color: #fff;
  background: color-mix(in srgb, var(--color-primary) 88%, #111827);
  cursor: pointer;
  font-family: inherit;
  font-size: 12px;
  font-weight: 900;
  line-height: 1;
  box-shadow: 0 10px 24px color-mix(in srgb, var(--color-primary) 24%, transparent);
}

.streaming-button:hover,
.streaming-button:focus-visible {
  border-color: var(--color-primary);
  outline: none;
  transform: translateY(-1px);
}

.team-block {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.team-block--away {
  justify-content: flex-end;
  text-align: right;
}

.team-block img {
  width: 54px;
  height: 54px;
  border-radius: 999px;
  padding: 7px;
  background: #fff;
  object-fit: contain;
}

.team-block strong {
  overflow: hidden;
  color: var(--color-fg);
  font-size: 21px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.match-center {
  display: grid;
  justify-items: center;
  min-width: 0;
  text-align: center;
}

.match-meta {
  display: grid;
  justify-items: center;
  gap: 4px;
  margin-top: 8px;
  min-width: 0;
}

.match-meta span,
.match-meta p {
  margin: 0;
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 800;
}

.match-center h1 {
  margin: 0;
  color: var(--color-fg);
  font-size: 24px;
}

.match-score {
  display: grid;
  grid-template-columns: 52px auto 52px;
  align-items: center;
  gap: 12px;
  min-width: 152px;
  padding: 6px 12px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-bg);
  box-shadow: inset 0 1px 0 color-mix(in srgb, #fff 68%, transparent);
}

.broadcast-picker {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: grid;
  place-items: center;
  padding: 16px;
  background: color-mix(in srgb, var(--color-bg) 78%, #020617 22%);
}

.broadcast-picker__panel {
  width: min(520px, 100%);
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--color-primary) 24%, var(--color-border));
  border-radius: 8px;
  color: var(--color-fg);
  background: var(--color-card);
  box-shadow: 0 28px 84px rgba(15, 23, 42, 0.38);
}

.broadcast-picker__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 16px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg);
}

.broadcast-picker__header p {
  margin: 0 0 4px;
  color: var(--color-primary);
  font-size: 11px;
  font-weight: 950;
  letter-spacing: 0.12em;
}

.broadcast-picker__header h2 {
  margin: 0;
  font-size: 18px;
  line-height: 1.25;
}

.broadcast-picker__header button {
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  width: 34px;
  height: 34px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  color: var(--color-fg);
  background: var(--color-card);
  cursor: pointer;
}

.broadcast-picker__header button:hover,
.broadcast-picker__header button:focus-visible {
  border-color: var(--color-primary);
  outline: none;
}

.broadcast-picker__options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 16px;
}

.broadcast-picker__option {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  min-height: 92px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 14px;
  color: var(--color-fg);
  background: color-mix(in srgb, var(--color-primary) 5%, var(--color-bg));
  text-decoration: none;
}

.broadcast-picker__option--program {
  background: color-mix(in srgb, #0ea5e9 8%, var(--color-bg));
}

.broadcast-picker__option:hover,
.broadcast-picker__option:focus-visible {
  border-color: var(--color-primary);
  outline: none;
  transform: translateY(-1px);
}

.broadcast-picker__icon {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 8px;
  color: #fff;
  background: color-mix(in srgb, var(--color-primary) 88%, #111827);
}

.broadcast-picker__copy {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.broadcast-picker__copy strong {
  overflow: hidden;
  font-size: 14px;
  font-weight: 950;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.broadcast-picker__copy em {
  overflow: hidden;
  color: var(--color-muted);
  font-size: 12px;
  font-style: normal;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.match-score b {
  font-size: 31px;
  font-weight: 950;
  line-height: 1;
}

.match-score i {
  color: var(--color-muted);
  font-size: 22px;
  font-style: normal;
  font-weight: 900;
}

.preview-grid {
  display: grid;
  grid-template-columns: minmax(270px, 0.75fr) minmax(480px, 1.35fr) minmax(300px, 0.95fr);
  grid-template-rows: minmax(0, 0.72fr) minmax(0, 0.9fr) minmax(0, 0.9fr);
  gap: 12px;
  min-height: 0;
  overflow: hidden;
}

.panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.info-panel {
  grid-row: 1 / 2;
  grid-column: 1 / 2;
}

.standings-panel {
  grid-row: 1 / 2;
  grid-column: 3 / 4;
}

.recent-panel {
  grid-row: 2 / 4;
  grid-column: 3 / 4;
}

.insight-panel {
  grid-row: 2 / 3;
  grid-column: 1 / 2;
}

.lineup-panel {
  grid-row: 1 / 4;
  grid-column: 2 / 3;
}

.stats-panel {
  grid-row: 3 / 4;
  grid-column: 1 / 2;
}

.panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 42px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg);
}

.panel__head span {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--color-fg);
  font-size: 13px;
  font-weight: 900;
}

.panel__head strong {
  color: var(--color-muted);
  font-size: 12px;
}

.info-list {
  display: grid;
  align-content: start;
  gap: 10px;
  min-height: 0;
  margin: 0;
  padding: 12px;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: none;
}

.info-list::-webkit-scrollbar,
.standings-pair::-webkit-scrollbar,
.insight-grid::-webkit-scrollbar,
.lineup-grid::-webkit-scrollbar,
.stat-list::-webkit-scrollbar,
.recent-match-grid::-webkit-scrollbar,
.recent-match-list::-webkit-scrollbar {
  display: none;
}

.info-list div {
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 9px;
}

.info-list dt {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--color-muted);
  font-size: 11px;
  font-weight: 900;
}

.info-list dd {
  margin: 5px 0 0;
  color: var(--color-fg);
  font-size: 13px;
  font-weight: 800;
}

.standings-pair,
.insight-grid,
.lineup-grid,
.stat-list {
  display: grid;
  align-content: start;
  gap: 8px;
  min-height: 0;
  padding: 12px;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: none;
}

.standings-pair {
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: none;
}

.standings-pair div,
.lineup-grid > .formation-card,
.stat-list div {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 10px;
  background: var(--color-bg);
}

.standings-pair span {
  color: var(--color-muted);
  font-size: 11px;
  font-style: normal;
  font-weight: 800;
}

.standings-pair strong {
  display: block;
  margin: 4px 0;
  color: var(--color-fg);
}

.form-chip {
  display: inline-grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  color: #fff;
  font-size: 11px;
  font-style: normal;
  font-weight: 950;
}

.form-chip--W {
  background: #16a34a;
}

.form-chip--D {
  background: #64748b;
}

.form-chip--L {
  background: #dc2626;
}

.form-chip--N {
  background: var(--color-muted);
}

.standings-pair em {
  color: var(--color-muted);
  font-size: 12px;
  font-style: normal;
}

.insight-grid {
  gap: 7px;
}

.insight-teams {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
  min-width: 0;
}

.insight-teams div,
.insight-row {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg);
}

.insight-teams div {
  min-width: 0;
  padding: 8px 9px;
}

.insight-teams strong {
  display: block;
  overflow: hidden;
  color: var(--color-fg);
  font-size: 12px;
  font-weight: 950;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.insight-teams span {
  display: block;
  margin-top: 3px;
  color: var(--color-muted);
  font-size: 10px;
  font-weight: 900;
}

.insight-row {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr) 56px;
  align-items: center;
  gap: 6px;
  min-width: 0;
  padding: 7px 9px;
}

.insight-row > span {
  color: var(--color-fg);
  font-size: 15px;
  font-weight: 950;
  line-height: 1;
}

.insight-row > span:last-of-type {
  text-align: right;
}

.insight-row > strong {
  overflow: hidden;
  color: var(--color-muted);
  font-size: 11px;
  font-weight: 900;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.insight-bars {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 6px;
  height: 4px;
}

.insight-bars i {
  display: block;
  height: 4px;
  border-radius: 999px;
}

.insight-bars__home {
  justify-self: end;
  background: #2563eb;
}

.insight-bars__away {
  justify-self: start;
  background: #dc2626;
}

.recent-match-grid {
  display: grid;
  grid-template-rows: repeat(2, minmax(0, 1fr));
  align-content: start;
  gap: 10px;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 12px;
  scrollbar-width: none;
}

.recent-team-card {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg);
}

.recent-team-card__head {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border-bottom: 1px solid var(--color-border);
}

.team-logo {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  overflow: hidden;
  border-radius: 999px;
  background: #fff;
}

.team-logo img {
  width: 21px;
  height: 21px;
  object-fit: contain;
}

.recent-team-card__head strong {
  overflow: hidden;
  color: var(--color-fg);
  font-size: 13px;
  font-weight: 950;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-team-card__head em {
  color: var(--color-muted);
  font-size: 11px;
  font-style: normal;
  font-weight: 900;
}

.recent-match-list {
  display: grid;
  align-content: start;
  gap: 7px;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 9px;
  scrollbar-width: none;
}

.recent-match-row {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) 50px;
  align-items: center;
  gap: 8px;
  min-width: 0;
  border: 1px solid var(--color-border);
  border-radius: 7px;
  padding: 7px 8px;
  background: var(--color-card);
}

.recent-match-row div {
  min-width: 0;
}

.recent-match-row strong {
  display: block;
  overflow: hidden;
  color: var(--color-fg);
  font-size: 12px;
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-match-row small {
  display: block;
  overflow: hidden;
  color: var(--color-muted);
  font-size: 10px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-league-mark {
  display: grid;
  justify-items: center;
  gap: 3px;
  min-width: 0;
}

.recent-league-mark img,
.recent-league-mark b {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 999px;
  background: #fff;
}

.recent-league-mark img {
  padding: 4px;
  object-fit: contain;
}

.recent-league-mark b {
  overflow: hidden;
  padding: 3px;
  color: #111827;
  font-size: 8px;
  font-weight: 950;
  line-height: 1;
  text-align: center;
}

.recent-league-mark em {
  color: var(--color-muted);
  font-size: 10px;
  font-style: normal;
  font-weight: 900;
}

.lineup-grid {
  grid-template-columns: minmax(0, 1fr);
  align-content: stretch;
}

.formation-card {
  display: grid;
  grid-template-rows: auto minmax(520px, 1fr) auto;
  gap: 10px;
  height: 100%;
  min-height: 0;
}

.formation-card__head {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  min-width: 0;
}

.formation-team {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 7px;
  min-width: 0;
  border: 1px solid color-mix(in srgb, var(--side-color) 32%, var(--color-border));
  border-radius: 7px;
  padding: 7px 9px;
  background: color-mix(in srgb, var(--side-color) 8%, var(--color-bg));
}

.formation-team[data-side='home'],
.player-badge[data-side='home'],
.bench-chip[data-side='home'] {
  --side-color: #2563eb;
}

.formation-team[data-side='away'],
.player-badge[data-side='away'],
.bench-chip[data-side='away'] {
  --side-color: #dc2626;
}

.formation-team span {
  color: var(--side-color);
  font-size: 10px;
  font-weight: 950;
}

.formation-team strong {
  overflow: hidden;
  color: var(--color-fg);
  font-size: 12px;
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.formation-team em {
  flex: 0 0 auto;
  color: var(--color-muted);
  font-size: 11px;
  font-style: normal;
  font-weight: 900;
}

.mini-pitch {
  position: relative;
  min-height: 520px;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, #ffffff 32%, transparent);
  border-radius: 8px;
  background:
    linear-gradient(0deg, transparent 49.5%, color-mix(in srgb, #ffffff 42%, transparent) 49.5% 50.5%, transparent 50.5%),
    radial-gradient(circle at 50% 50%, transparent 0 18%, color-mix(in srgb, #ffffff 34%, transparent) 18.4% 19%, transparent 19.4%),
    repeating-linear-gradient(
      90deg,
      color-mix(in srgb, #15803d 86%, #ffffff 14%) 0 12.5%,
      color-mix(in srgb, #166534 82%, #ffffff 18%) 12.5% 25%
    );
}

.mini-pitch::before,
.mini-pitch::after {
  position: absolute;
  left: 50%;
  width: 54%;
  height: 18%;
  border: 1px solid color-mix(in srgb, #ffffff 45%, transparent);
  content: '';
  transform: translateX(-50%);
}

.mini-pitch::before {
  top: -1px;
  border-top: 0;
}

.mini-pitch::after {
  bottom: -1px;
  border-bottom: 0;
}

.player-badge {
  position: absolute;
  display: grid;
  justify-items: center;
  width: 76px;
  min-height: 54px;
  border: 0;
  background: transparent;
  cursor: pointer;
  transform: translate(-50%, -50%);
}

.player-badge__avatar {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  overflow: hidden;
  border: 2px solid #fff;
  border-radius: 999px;
  color: #fff;
  background:
    linear-gradient(145deg, var(--side-color), color-mix(in srgb, var(--side-color) 55%, #111827 45%));
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.38);
}

.player-badge__avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.player-badge__avatar b {
  font-size: 13px;
  font-weight: 950;
  line-height: 1;
}

.player-badge__name {
  max-width: 74px;
  margin-top: 3px;
  overflow: hidden;
  color: #fff;
  font-size: 10px;
  font-weight: 900;
  line-height: 1.05;
  text-align: center;
  text-overflow: ellipsis;
  text-shadow: 0 1px 4px rgba(15, 23, 42, 0.82);
  white-space: nowrap;
}

.player-badge__rating,
.bench-chip em {
  min-width: 24px;
  border-radius: 999px;
  font-size: 10px;
  font-style: normal;
  font-weight: 950;
  line-height: 1;
  text-align: center;
}

.player-badge__rating {
  position: absolute;
  top: 23px;
  left: 45px;
  padding: 4px 5px;
  border: 1px solid color-mix(in srgb, #fff 55%, transparent);
}

.rating-chip--great {
  color: #073b20;
  background: #22c55e;
}

.rating-chip--good {
  color: #09244f;
  background: #60a5fa;
}

.rating-chip--ok {
  color: #3b2d08;
  background: #facc15;
}

.rating-chip--low {
  color: #4a1010;
  background: #fb7185;
}

.player-badge__sub {
  position: absolute;
  top: -3px;
  left: 41px;
  padding: 3px 5px;
  border-radius: 999px;
  color: #fff;
  font-size: 9px;
  font-weight: 950;
  line-height: 1;
  white-space: nowrap;
  box-shadow: 0 5px 12px rgba(15, 23, 42, 0.28);
}

.player-badge__sub--out {
  background: #ef4444;
}

.bench-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  min-height: 0;
}

.bench-strip {
  display: grid;
  align-content: start;
  gap: 6px;
  min-width: 0;
}

.bench-strip__label {
  color: var(--color-muted);
  font-size: 10px;
  font-weight: 900;
}

.bench-chip {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 6px;
  width: 100%;
  min-width: 0;
  border: 1px solid color-mix(in srgb, var(--side-color) 24%, var(--color-border));
  border-radius: 7px;
  padding: 6px 7px;
  color: var(--color-fg);
  background: color-mix(in srgb, var(--side-color) 7%, var(--color-bg));
  cursor: pointer;
  text-align: left;
}

.bench-chip span {
  color: var(--side-color);
  font-size: 10px;
  font-weight: 950;
}

.bench-chip strong {
  overflow: hidden;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bench-chip em {
  padding: 4px 5px;
}

.player-badge:focus-visible,
.bench-chip:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.player-badge:hover .player-badge__avatar,
.bench-chip:hover {
  transform: translateY(-1px);
}

.player-badge:hover .player-badge__avatar {
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.48);
}

.bench-chip:hover {
  border-color: color-mix(in srgb, var(--side-color) 45%, var(--color-border));
}

.lineup-placeholder {
  color: var(--color-muted);
  font-size: 12px;
  line-height: 1.45;
}

.lineup-placeholder {
  display: grid;
  place-items: center;
  padding: 16px;
  text-align: center;
}

.stat-list div {
  display: grid;
  grid-template-columns: 54px minmax(0, 1fr) 54px;
  align-items: center;
  text-align: center;
}

.stat-list span {
  color: var(--color-fg);
  font-size: 18px;
  font-weight: 900;
}

.stat-list strong {
  color: var(--color-muted);
  font-size: 12px;
}

.state {
  display: grid;
  place-items: center;
  min-height: 120px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-muted);
  background: var(--color-card);
}

.state--inline {
  min-height: 70px;
}

.state--error {
  color: #b91c1c;
}
</style>
