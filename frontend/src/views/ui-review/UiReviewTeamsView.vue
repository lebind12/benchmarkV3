<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight,
  Building2,
  CalendarDays,
  ListFilter,
  RefreshCw,
  Search,
  Shield,
  Star,
  Trophy,
  UsersRound,
} from 'lucide-vue-next'
import LeagueMark from '@/components/common/LeagueMark.vue'
import {
  generalApi,
  type TeamDetailPayload,
  type TeamListItem,
} from '@/lib/api/general'
import { leagueName, playerName, teamName } from '@/lib/displayNames'
import {
  HOME_LEAGUE_TABS,
  LEAGUE_SHORT_KO,
  leagueLogoUrl,
  leagueVar,
  slugFromId,
} from '@/lib/league-colors'
import { kstTime } from '@/lib/format/datetime'
import type { FixtureSummary, LeagueRef, LeagueSlug } from '@/types/home'

type DetailTab = 'overview' | 'matches' | 'squad'

const router = useRouter()
const teams = ref<TeamListItem[]>([])
const selectedLeagueId = ref<number | null>(39)
const query = ref('')
const selectedSlug = ref<string | null>(null)
const selectedDetail = ref<TeamDetailPayload | null>(null)
const detailTab = ref<DetailTab>('overview')
const listStatus = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const detailStatus = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const listError = ref<string | null>(null)
const detailError = ref<string | null>(null)
const teamListRef = ref<HTMLElement | null>(null)
const teamScrollbarRef = ref<HTMLElement | null>(null)
const teamListScrollTop = ref(0)
const teamListClientHeight = ref(0)
const teamListScrollHeight = ref(0)
let teamListResizeObserver: ResizeObserver | null = null
let teamScrollbarDragOffset = 0

const selectedLeague = computed(() => HOME_LEAGUE_TABS.find((league) => league.id === selectedLeagueId.value))
const selectedLeagueSlug = computed(() => slugFromId(selectedLeagueId.value))
const selectedLeagueName = computed(() => selectedLeague.value?.label ?? '전체 대회')
const orderedTeams = computed(() => [...teams.value].sort((a, b) => {
  const rankA = a.rank ?? 9999
  const rankB = b.rank ?? 9999
  if (rankA !== rankB) return rankA - rankB
  return teamName(a.team).localeCompare(teamName(b.team), 'ko')
}))
const selectedRow = computed(() => orderedTeams.value.find((item) => item.team.slug === selectedSlug.value) ?? null)
const visibleCount = computed(() => orderedTeams.value.length)
const rankedCount = computed(() => orderedTeams.value.filter((item) => item.rank != null).length)
const averagePoints = computed(() => {
  const rows = orderedTeams.value.filter((item) => item.points != null)
  if (!rows.length) return null
  return Math.round(rows.reduce((sum, row) => sum + (row.points ?? 0), 0) / rows.length)
})
const topTeams = computed(() => orderedTeams.value.slice(0, 8))
const completedFixtures = computed(() => {
  if (selectedDetail.value?.recent_results) return selectedDetail.value.recent_results
  return (selectedDetail.value?.fixtures ?? [])
    .filter((fixture) => ['FT', 'AET', 'PEN'].includes(fixture.status_short))
    .slice(0, 8)
})
const upcomingFixtures = computed(() => {
  if (selectedDetail.value?.upcoming_fixtures) return selectedDetail.value.upcoming_fixtures
  return (selectedDetail.value?.fixtures ?? [])
    .filter((fixture) => !['FT', 'AET', 'PEN'].includes(fixture.status_short))
    .slice(0, 5)
})
const squadRows = computed(() => selectedDetail.value?.squad ?? [])
const keyPlayers = computed(() =>
  [...squadRows.value]
    .sort((a, b) => {
      const scoreA = (a.goals ?? 0) * 3 + (a.assists ?? 0) * 2 + (a.appearances ?? 0) * 0.2
      const scoreB = (b.goals ?? 0) * 3 + (b.assists ?? 0) * 2 + (b.appearances ?? 0) * 0.2
      return scoreB - scoreA
    })
    .slice(0, 5),
)
const teamListScrollable = computed(() => teamListScrollHeight.value > teamListClientHeight.value + 1)
const teamListThumbHeight = computed(() => {
  if (!teamListScrollable.value) return 0
  return Math.max(42, Math.round((teamListClientHeight.value / teamListScrollHeight.value) * teamListClientHeight.value))
})
const teamListThumbTop = computed(() => {
  const maxScroll = teamListScrollHeight.value - teamListClientHeight.value
  const maxTop = teamListClientHeight.value - teamListThumbHeight.value
  if (maxScroll <= 0 || maxTop <= 0) return 0
  return Math.round((teamListScrollTop.value / maxScroll) * maxTop)
})
const teamListThumbStyle = computed(() => ({
  height: `${teamListThumbHeight.value}px`,
  transform: `translateY(${teamListThumbTop.value}px)`,
}))

function updateTeamListScrollMetrics() {
  const list = teamListRef.value
  if (!list) return
  teamListScrollTop.value = list.scrollTop
  teamListClientHeight.value = list.clientHeight
  teamListScrollHeight.value = list.scrollHeight
}

async function refreshTeamListScrollMetrics() {
  await nextTick()
  updateTeamListScrollMetrics()
  if (!teamListRef.value) return
  teamListResizeObserver?.disconnect()
  teamListResizeObserver = new ResizeObserver(updateTeamListScrollMetrics)
  teamListResizeObserver.observe(teamListRef.value)
}

function scrollTeamListThumbTo(clientY: number) {
  const list = teamListRef.value
  const rail = teamScrollbarRef.value
  if (!list || !rail) return
  const maxScroll = teamListScrollHeight.value - teamListClientHeight.value
  const maxThumbTop = rail.clientHeight - teamListThumbHeight.value
  if (maxScroll <= 0 || maxThumbTop <= 0) return
  const railTop = rail.getBoundingClientRect().top
  const nextTop = Math.min(Math.max(clientY - railTop - teamScrollbarDragOffset, 0), maxThumbTop)
  list.scrollTop = (nextTop / maxThumbTop) * maxScroll
  updateTeamListScrollMetrics()
}

function stopTeamScrollbarDrag() {
  window.removeEventListener('pointermove', onTeamScrollbarPointerMove)
  window.removeEventListener('pointerup', stopTeamScrollbarDrag)
}

function onTeamScrollbarPointerMove(event: PointerEvent) {
  event.preventDefault()
  scrollTeamListThumbTo(event.clientY)
}

function onTeamScrollbarPointerDown(event: PointerEvent) {
  if (!teamListScrollable.value) return
  event.preventDefault()
  const target = event.target as HTMLElement
  const thumb = target.closest('.custom-scrollbar__thumb') as HTMLElement | null
  teamScrollbarDragOffset = thumb
    ? event.clientY - thumb.getBoundingClientRect().top
    : teamListThumbHeight.value / 2
  scrollTeamListThumbTo(event.clientY)
  window.addEventListener('pointermove', onTeamScrollbarPointerMove)
  window.addEventListener('pointerup', stopTeamScrollbarDrag, { once: true })
}

async function loadTeams() {
  listStatus.value = 'loading'
  listError.value = null
  try {
    teams.value = (
      await generalApi.teams({
        leagueId: selectedLeagueId.value,
        query: query.value.trim() || null,
        limit: 240,
      })
    ).items
    listStatus.value = 'ok'
    if (!teams.value.some((item) => item.team.slug === selectedSlug.value)) {
      selectedSlug.value = orderedTeams.value[0]?.team.slug ?? null
    }
  } catch (err) {
    teams.value = []
    selectedSlug.value = null
    selectedDetail.value = null
    listError.value = (err as Error).message
    listStatus.value = 'error'
  }
}

async function loadSelectedTeam(slug: string | null) {
  if (!slug) {
    selectedDetail.value = null
    detailStatus.value = 'idle'
    return
  }
  detailStatus.value = 'loading'
  detailError.value = null
  try {
    selectedDetail.value = await generalApi.team(slug)
    detailStatus.value = 'ok'
  } catch (err) {
    selectedDetail.value = null
    detailError.value = (err as Error).message
    detailStatus.value = 'error'
  }
}

function setLeague(id: number | null) {
  selectedLeagueId.value = id
}

function selectTeam(slug: string) {
  selectedSlug.value = slug
}

function teamRankLabel(row: TeamListItem | null): string {
  if (!row?.rank) return '순위 없음'
  return `${row.rank}위`
}

function leagueShort(league: LeagueRef): string {
  return league.short_name_ko ?? LEAGUE_SHORT_KO[league.slug] ?? league.name_ko ?? league.name
}

function logoFor(league: LeagueRef): string | null {
  return league.logo_url ?? leagueLogoUrl(league.external_id)
}

function detailLeagueLabel(): string {
  if (selectedRow.value) return leagueName(selectedRow.value.league)
  const league = selectedDetail.value?.leagues[0]?.league
  return league ? leagueName(league) : selectedLeagueName.value
}

function fixtureOpponent(fixture: FixtureSummary): string {
  const id = selectedDetail.value?.team.external_id
  if (!id) return `${teamName(fixture.home)} vs ${teamName(fixture.away)}`
  return teamName(fixture.home.external_id === id ? fixture.away : fixture.home)
}

function homeAwayLabel(fixture: FixtureSummary): string {
  return fixture.home.external_id === selectedDetail.value?.team.external_id ? '홈' : '원정'
}

function scoreLine(fixture: FixtureSummary): string {
  if (fixture.goals_home == null || fixture.goals_away == null) return kstTime(fixture.kickoff_at)
  return `${fixture.goals_home} - ${fixture.goals_away}`
}

function fixtureOutcome(fixture: FixtureSummary): 'W' | 'D' | 'L' | null {
  const id = selectedDetail.value?.team.external_id
  if (!id || fixture.goals_home == null || fixture.goals_away == null) return null
  if (fixture.goals_home === fixture.goals_away) return 'D'
  const isHome = fixture.home.external_id === id
  const won = isHome ? fixture.goals_home > fixture.goals_away : fixture.goals_away > fixture.goals_home
  return won ? 'W' : 'L'
}

function shortFixtureDate(value: string): string {
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(value))
}

function openTeamDetail() {
  if (!selectedDetail.value) return
  void router.push({ name: 'team-detail', params: { slug: selectedDetail.value.team.slug } })
}

function openFixture(id: number) {
  void router.push({ name: 'fixture-detail', params: { externalId: id } })
}

function openPlayer(slug: string) {
  void router.push({ name: 'player-detail', params: { slug } })
}

function themeStyle(slug: LeagueSlug | null): Record<string, string> {
  return {
    '--team-primary': leagueVar(slug, 'primary'),
    '--team-secondary': leagueVar(slug, 'secondary'),
    '--team-accent': leagueVar(slug, 'accent'),
    '--team-on-primary': leagueVar(slug, 'on-primary'),
  }
}

onMounted(async () => {
  await loadTeams()
  await refreshTeamListScrollMetrics()
})

onBeforeUnmount(() => {
  teamListResizeObserver?.disconnect()
  stopTeamScrollbarDrag()
})

watch(selectedLeagueId, () => {
  void loadTeams()
})

watch(selectedSlug, (slug) => {
  void loadSelectedTeam(slug)
})

watch(orderedTeams, () => {
  void refreshTeamListScrollMetrics()
})
</script>

<template>
  <main class="teams-page app-container" data-testid="ui-review-teams-page">
    <section class="teams-shell">
      <section class="team-search-row" aria-label="팀 검색">
        <form class="search-box" @submit.prevent="loadTeams">
          <Search :size="16" aria-hidden="true" />
          <input v-model="query" type="search" placeholder="팀명 검색" />
          <button type="submit">검색</button>
        </form>
      </section>

      <section class="league-strip" aria-label="리그 필터">
        <button
          v-for="league in HOME_LEAGUE_TABS"
          :key="league.id ?? 'all'"
          type="button"
          :class="['league-card', { 'league-card--active': selectedLeagueId === league.id }]"
          :style="themeStyle(league.slug)"
          @click="setLeague(league.id)"
        >
          <span class="league-card__mark">
            <img v-if="league.logoUrl" :src="league.logoUrl" alt="" />
            <b v-else>ALL</b>
          </span>
          <span>{{ league.label }}</span>
        </button>
      </section>

      <section class="teams-layout">
        <aside class="team-index panel">
          <header class="panel__head">
            <span><ListFilter :size="16" aria-hidden="true" /> 팀 목록</span>
            <button type="button" @click="loadTeams">
              <RefreshCw :size="14" aria-hidden="true" />
              새로고침
            </button>
          </header>

          <div class="summary-rail">
            <div>
              <strong>{{ visibleCount }}</strong>
              <span>표시</span>
            </div>
            <div>
              <strong>{{ rankedCount }}</strong>
              <span>순위 포함</span>
            </div>
            <div>
              <strong>{{ averagePoints ?? '-' }}</strong>
              <span>평균 승점</span>
            </div>
          </div>

          <div v-if="listStatus === 'loading'" class="state">팀 데이터를 불러오는 중입니다.</div>
          <div v-else-if="listStatus === 'error'" class="state state--error">{{ listError }}</div>
          <div v-else-if="orderedTeams.length === 0" class="state">조건에 맞는 팀이 없습니다.</div>
          <div v-else class="team-list-shell">
            <div
              ref="teamListRef"
              class="team-list scroll-region team-list--custom-scroll"
              @scroll="updateTeamListScrollMetrics"
            >
              <button
                v-for="item in orderedTeams"
                :key="`${item.team.external_id}-${item.league.external_id}`"
                type="button"
                :class="['team-row', { 'team-row--active': selectedSlug === item.team.slug }]"
                @click="selectTeam(item.team.slug)"
              >
                <span class="team-row__logo">
                  <img v-if="item.team.logo_url" :src="item.team.logo_url" alt="" />
                  <Shield v-else :size="19" aria-hidden="true" />
                </span>
                <span class="team-row__copy">
                  <strong>{{ teamName(item.team) }}</strong>
                  <em>{{ leagueName(item.league) }} · {{ item.country ?? '국가 미상' }}</em>
                </span>
                <span class="rank-pill">{{ teamRankLabel(item) }}</span>
              </button>
            </div>
            <div
              v-if="teamListScrollable"
              ref="teamScrollbarRef"
              class="custom-scrollbar team-list-scrollbar"
              aria-hidden="true"
              @pointerdown="onTeamScrollbarPointerDown"
            >
              <span class="custom-scrollbar__thumb" :style="teamListThumbStyle" />
            </div>
          </div>
        </aside>

        <section class="spotlight" :style="themeStyle(selectedLeagueSlug)">
          <div v-if="detailStatus === 'loading'" class="state state--wide">팀 상세를 불러오는 중입니다.</div>
          <div v-else-if="detailStatus === 'error'" class="state state--error state--wide">{{ detailError }}</div>
          <div v-else-if="!selectedDetail" class="state state--wide">팀을 선택해주세요.</div>

          <template v-else>
            <article class="club-hero">
              <div class="club-hero__identity">
                <span class="club-logo">
                  <img v-if="selectedDetail.team.logo_url" :src="selectedDetail.team.logo_url" alt="" />
                  <Shield v-else :size="38" aria-hidden="true" />
                </span>
                <div>
                  <span class="eyebrow">{{ detailLeagueLabel() }}</span>
                  <h2>{{ teamName(selectedDetail.team) }}</h2>
                  <p>{{ selectedDetail.country ?? '국가 미상' }} · 창단 {{ selectedDetail.founded ?? '-' }}</p>
                </div>
              </div>
              <div class="club-hero__rank">
                <span>{{ teamRankLabel(selectedRow) }}</span>
                <strong>{{ selectedRow?.points ?? '-' }}</strong>
                <em>승점</em>
              </div>
              <button type="button" class="detail-link" @click="openTeamDetail">
                원본 상세
                <ArrowRight :size="14" aria-hidden="true" />
              </button>
            </article>

            <div class="detail-tabs" role="tablist" aria-label="팀 상세 보기">
              <button
                v-for="tab in [
                  { key: 'overview', label: '개요' },
                  { key: 'matches', label: '경기' },
                  { key: 'squad', label: '스쿼드' },
                ]"
                :key="tab.key"
                type="button"
                role="tab"
                :aria-selected="detailTab === tab.key"
                :class="{ active: detailTab === tab.key }"
                @click="detailTab = tab.key as DetailTab"
              >
                {{ tab.label }}
              </button>
            </div>

            <section v-if="detailTab === 'overview'" class="overview-grid">
              <article class="info-card">
                <span><Building2 :size="16" aria-hidden="true" /> 홈구장</span>
                <strong>{{ selectedDetail.venue?.name ?? '경기장 미정' }}</strong>
                <em>{{ selectedDetail.venue?.city ?? '' }}</em>
              </article>
              <article class="info-card">
                <span><UsersRound :size="16" aria-hidden="true" /> 감독</span>
                <strong>{{ selectedDetail.coach ? playerName(selectedDetail.coach.coach) : '-' }}</strong>
                <em>{{ selectedDetail.coach?.league ? leagueName(selectedDetail.coach.league) : '최근 확인 데이터' }}</em>
              </article>
              <article class="info-card">
                <span><Trophy :size="16" aria-hidden="true" /> 참가 대회</span>
                <strong>{{ selectedDetail.leagues.length }}</strong>
                <em>{{ selectedDetail.leagues.map((item) => leagueName(item.league)).join(', ') || '-' }}</em>
              </article>
              <article class="form-card">
                <header>
                  <span><Star :size="16" aria-hidden="true" /> 최근 결과</span>
                  <strong>{{ completedFixtures.length }}경기</strong>
                </header>
                <div class="form-dots">
                  <span
                    v-for="fixture in completedFixtures"
                    :key="fixture.external_id"
                    :class="`form-dot form-dot--${fixtureOutcome(fixture) ?? 'N'}`"
                  >
                    {{ fixtureOutcome(fixture) ?? '-' }}
                  </span>
                </div>
                <p v-if="completedFixtures.length === 0">이번 달 완료 경기 데이터가 없습니다.</p>
              </article>
              <article class="key-player-card">
                <header>
                  <span><UsersRound :size="16" aria-hidden="true" /> 핵심 선수</span>
                  <strong>{{ squadRows.length }}명</strong>
                </header>
                <button
                  v-for="row in keyPlayers"
                  :key="row.player.external_id"
                  type="button"
                  class="key-player"
                  @click="openPlayer(row.player.slug)"
                >
                  <img v-if="row.player.photo_url" :src="row.player.photo_url" alt="" />
                  <span v-else>{{ playerName(row.player).slice(0, 1) }}</span>
                  <strong>{{ playerName(row.player) }}</strong>
                  <em>{{ row.goals ?? 0 }}G · {{ row.assists ?? 0 }}A</em>
                </button>
              </article>
            </section>

            <section v-else-if="detailTab === 'matches'" class="matches-grid">
              <article class="match-panel">
                <header>
                  <span><CalendarDays :size="16" aria-hidden="true" /> 최근 결과</span>
                  <strong>{{ completedFixtures.length }}</strong>
                </header>
                <div class="match-list">
                  <button
                    v-for="fixture in completedFixtures"
                    :key="fixture.external_id"
                    type="button"
                    class="match-row"
                    @click="openFixture(fixture.external_id)"
                  >
                    <span :class="`form-dot form-dot--${fixtureOutcome(fixture) ?? 'N'}`">
                      {{ fixtureOutcome(fixture) ?? '-' }}
                    </span>
                    <div>
                      <strong>{{ fixtureOpponent(fixture) }}</strong>
                      <em>{{ homeAwayLabel(fixture) }} · {{ shortFixtureDate(fixture.kickoff_at) }}</em>
                    </div>
                    <b>{{ scoreLine(fixture) }}</b>
                    <LeagueMark
                      :external-id="fixture.league.external_id"
                      :slug="fixture.league.slug"
                      :logo-url="logoFor(fixture.league)"
                      :label="leagueShort(fixture.league)"
                      size="xs"
                    />
                  </button>
                  <div v-if="completedFixtures.length === 0" class="state state--inline">완료 경기 데이터가 없습니다.</div>
                </div>
              </article>
              <article class="match-panel">
                <header>
                  <span><CalendarDays :size="16" aria-hidden="true" /> 예정 경기</span>
                  <strong>{{ upcomingFixtures.length }}</strong>
                </header>
                <div class="match-list">
                  <button
                    v-for="fixture in upcomingFixtures"
                    :key="fixture.external_id"
                    type="button"
                    class="match-row"
                    @click="openFixture(fixture.external_id)"
                  >
                    <span class="time-chip">{{ kstTime(fixture.kickoff_at) }}</span>
                    <div>
                      <strong>{{ fixtureOpponent(fixture) }}</strong>
                      <em>{{ homeAwayLabel(fixture) }} · {{ shortFixtureDate(fixture.kickoff_at) }}</em>
                    </div>
                    <b>vs</b>
                    <LeagueMark
                      :external-id="fixture.league.external_id"
                      :slug="fixture.league.slug"
                      :logo-url="logoFor(fixture.league)"
                      :label="leagueShort(fixture.league)"
                      size="xs"
                    />
                  </button>
                  <div v-if="upcomingFixtures.length === 0" class="state state--inline">예정 경기 데이터가 없습니다.</div>
                </div>
              </article>
            </section>

            <section v-else class="squad-panel">
              <header>
                <span><UsersRound :size="16" aria-hidden="true" /> 선수단</span>
                <strong>{{ squadRows.length }}명</strong>
              </header>
              <div class="squad-table">
                <table>
                  <thead>
                    <tr>
                      <th>선수</th>
                      <th>포지션</th>
                      <th>출전</th>
                      <th>G</th>
                      <th>A</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in squadRows" :key="row.player.external_id">
                      <td>
                        <button type="button" @click="openPlayer(row.player.slug)">
                          <img v-if="row.player.photo_url" :src="row.player.photo_url" alt="" />
                          <span v-else>{{ playerName(row.player).slice(0, 1) }}</span>
                          <strong>{{ playerName(row.player) }}</strong>
                        </button>
                      </td>
                      <td>{{ row.position ?? '-' }}</td>
                      <td>{{ row.appearances ?? '-' }}</td>
                      <td>{{ row.goals ?? 0 }}</td>
                      <td>{{ row.assists ?? 0 }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>
          </template>
        </section>

        <aside class="league-snapshot panel">
          <header class="panel__head">
            <span><Trophy :size="16" aria-hidden="true" /> 상위 팀</span>
            <strong>{{ selectedLeagueName }}</strong>
          </header>
          <ol class="top-list">
            <li v-for="item in topTeams" :key="item.team.external_id">
              <span>{{ item.rank ?? '-' }}</span>
              <img v-if="item.team.logo_url" :src="item.team.logo_url" alt="" />
              <strong>{{ teamName(item.team) }}</strong>
              <em>{{ item.points ?? '-' }}점</em>
            </li>
          </ol>
          <div v-if="topTeams.length === 0" class="state state--inline">상위 팀 데이터가 없습니다.</div>
        </aside>
      </section>
    </section>
  </main>
</template>

<style scoped>
.teams-page {
  height: calc(100vh - var(--header-height));
  overflow: hidden;
  padding-block: 14px 18px;
}

.teams-shell {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: 10px;
  height: 100%;
  min-height: 0;
}

.team-search-row,
.panel,
.club-hero,
.detail-tabs,
.info-card,
.form-card,
.key-player-card,
.match-panel,
.squad-panel {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
}

.team-search-row {
  padding: 10px 12px;
}

.eyebrow {
  display: block;
  margin-bottom: 4px;
  color: var(--team-primary);
  font-size: 11px;
  font-weight: 900;
  text-transform: uppercase;
}

h1,
h2 {
  margin: 0;
  color: var(--color-fg);
  line-height: 1.1;
}

h1 {
  font-size: 28px;
}

h2 {
  font-size: 26px;
}

.club-hero p {
  margin: 8px 0 0;
  color: var(--color-muted);
  font-size: 13px;
}

.search-box {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  height: 40px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 0 5px 0 12px;
  color: var(--color-muted);
  background: var(--color-bg);
}

.search-box input {
  min-width: 0;
  border: 0;
  color: var(--color-fg);
  background: transparent;
  font: inherit;
}

.search-box button,
.panel__head button,
.detail-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  height: 30px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 0 10px;
  color: var(--color-fg);
  background: var(--color-card);
  cursor: pointer;
  font-size: 11px;
  font-weight: 900;
}

.league-strip {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 7px;
  min-width: 0;
}

.league-card {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  height: 48px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 6px 9px;
  color: var(--color-muted);
  background: var(--color-card);
  cursor: pointer;
  font-size: 12px;
  font-weight: 900;
  text-align: left;
}

.league-card__mark,
.team-row__logo,
.club-logo,
.top-list img {
  display: grid;
  place-items: center;
  border: 1px solid rgb(17 24 39 / 0.14);
  border-radius: 999px;
  background: #fff;
  overflow: hidden;
}

.league-card__mark {
  width: 34px;
  height: 34px;
}

.league-card__mark img {
  width: 78%;
  height: 78%;
  object-fit: contain;
}

.league-card__mark b {
  color: #111827;
  font-size: 9px;
}

.league-card > span:last-child {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.league-card--active {
  border-color: color-mix(in srgb, var(--team-primary) 62%, var(--color-border));
  color: var(--color-fg);
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--team-primary) 16%, transparent), transparent),
    var(--color-card);
  box-shadow: inset 0 -3px 0 var(--team-primary);
}

.teams-layout {
  display: grid;
  grid-template-columns: minmax(300px, 0.8fr) minmax(480px, 1.45fr) minmax(230px, 0.6fr);
  gap: 10px;
  min-height: 0;
}

.panel,
.spotlight {
  min-height: 0;
}

.spotlight {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  overflow: hidden;
}

.team-index,
.league-snapshot {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  overflow: hidden;
}

.panel__head,
.match-panel header,
.squad-panel > header,
.form-card header,
.key-player-card header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 44px;
  border-bottom: 1px solid var(--color-border);
  padding: 10px 12px;
}

.panel__head span,
.match-panel header span,
.squad-panel > header span,
.form-card header span,
.key-player-card header span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--color-fg);
  font-size: 13px;
  font-weight: 900;
}

.panel__head strong,
.match-panel header strong,
.squad-panel > header strong {
  color: var(--color-muted);
  font-size: 11px;
}

.summary-rail {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  padding: 8px;
}

.summary-rail div {
  display: grid;
  place-items: center;
  min-height: 52px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg);
}

.summary-rail strong {
  color: var(--color-fg);
  font-size: 18px;
}

.summary-rail span {
  color: var(--color-muted);
  font-size: 10px;
  font-weight: 800;
}

.team-list-shell {
  position: relative;
  min-height: 0;
  overflow: hidden;
}

.team-list {
  display: grid;
  align-content: start;
  gap: 7px;
  min-height: 0;
  block-size: 100%;
  padding: 10px 24px 10px 10px;
}

.scroll-region,
.overview-grid,
.match-list,
.squad-table,
.top-list {
  --ui-scrollbar-track: color-mix(in srgb, var(--color-bg) 88%, var(--color-border));
  --ui-scrollbar-thumb: color-mix(in srgb, var(--team-primary) 62%, var(--color-muted));
  --ui-scrollbar-thumb-hover: color-mix(in srgb, var(--team-primary) 82%, var(--color-fg));

  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-color: var(--ui-scrollbar-thumb) var(--ui-scrollbar-track);
  scrollbar-gutter: stable;
  scrollbar-width: thin;
}

:global(html.dark) .scroll-region,
:global(html.dark) .overview-grid,
:global(html.dark) .match-list,
:global(html.dark) .squad-table,
:global(html.dark) .top-list {
  --ui-scrollbar-track: color-mix(in srgb, var(--color-bg) 76%, #020617);
  --ui-scrollbar-thumb: color-mix(in srgb, var(--team-primary) 54%, #64748b);
  --ui-scrollbar-thumb-hover: color-mix(in srgb, var(--team-primary) 78%, #cbd5e1);
}

.scroll-region::-webkit-scrollbar,
.overview-grid::-webkit-scrollbar,
.match-list::-webkit-scrollbar,
.squad-table::-webkit-scrollbar,
.top-list::-webkit-scrollbar {
  width: 10px;
  height: 10px;
  background-color: var(--ui-scrollbar-track);
}

.scroll-region::-webkit-scrollbar-track,
.overview-grid::-webkit-scrollbar-track,
.match-list::-webkit-scrollbar-track,
.squad-table::-webkit-scrollbar-track,
.top-list::-webkit-scrollbar-track {
  border-radius: 999px;
  background-color: var(--ui-scrollbar-track);
}

.scroll-region::-webkit-scrollbar-thumb,
.overview-grid::-webkit-scrollbar-thumb,
.match-list::-webkit-scrollbar-thumb,
.squad-table::-webkit-scrollbar-thumb,
.top-list::-webkit-scrollbar-thumb {
  border: 2px solid var(--ui-scrollbar-track);
  border-radius: 999px;
  background-color: var(--ui-scrollbar-thumb);
}

.scroll-region::-webkit-scrollbar-thumb:hover,
.overview-grid::-webkit-scrollbar-thumb:hover,
.match-list::-webkit-scrollbar-thumb:hover,
.squad-table::-webkit-scrollbar-thumb:hover,
.top-list::-webkit-scrollbar-thumb:hover {
  background-color: var(--ui-scrollbar-thumb-hover);
}

.scroll-region::-webkit-scrollbar-corner,
.overview-grid::-webkit-scrollbar-corner,
.match-list::-webkit-scrollbar-corner,
.squad-table::-webkit-scrollbar-corner,
.top-list::-webkit-scrollbar-corner {
  background-color: var(--ui-scrollbar-track);
}

.team-list--custom-scroll {
  scrollbar-width: none;
}

.team-list--custom-scroll::-webkit-scrollbar {
  width: 0;
  height: 0;
  background-color: transparent;
}

.team-list-scrollbar {
  --custom-scrollbar-track: color-mix(in srgb, var(--color-bg) 82%, var(--color-border));
  --custom-scrollbar-thumb: color-mix(in srgb, var(--team-primary) 68%, var(--color-muted));
  --custom-scrollbar-thumb-hover: color-mix(in srgb, var(--team-primary) 86%, var(--color-fg));

  position: absolute;
  top: 10px;
  right: 8px;
  bottom: 10px;
  width: 10px;
  border: 1px solid color-mix(in srgb, var(--custom-scrollbar-thumb) 16%, transparent);
  border-radius: 999px;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--custom-scrollbar-track) 68%, transparent), var(--custom-scrollbar-track)),
    var(--color-bg);
  cursor: pointer;
}

:global(html.dark) .team-list-scrollbar {
  --custom-scrollbar-track: color-mix(in srgb, var(--color-bg) 86%, #020617);
  --custom-scrollbar-thumb: color-mix(in srgb, var(--team-primary) 60%, #94a3b8);
  --custom-scrollbar-thumb-hover: color-mix(in srgb, var(--team-primary) 82%, #e2e8f0);
}

.custom-scrollbar__thumb {
  position: absolute;
  top: 0;
  right: 1px;
  left: 1px;
  min-height: 42px;
  border-radius: 999px;
  background:
    linear-gradient(180deg, color-mix(in srgb, #fff 22%, transparent), transparent),
    var(--custom-scrollbar-thumb);
  box-shadow:
    inset 0 0 0 1px color-mix(in srgb, #fff 22%, transparent),
    0 6px 16px color-mix(in srgb, var(--custom-scrollbar-thumb) 28%, transparent);
}

.team-list-scrollbar:hover .custom-scrollbar__thumb {
  background:
    linear-gradient(180deg, color-mix(in srgb, #fff 26%, transparent), transparent),
    var(--custom-scrollbar-thumb-hover);
}

.team-row {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px;
  min-height: 58px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 7px 8px;
  color: inherit;
  background: var(--color-bg);
  cursor: pointer;
  text-align: left;
}

.team-row--active {
  border-color: color-mix(in srgb, var(--team-primary) 52%, var(--color-border));
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--team-primary) 12%, transparent), transparent),
    var(--color-bg);
  box-shadow: inset 3px 0 0 var(--team-primary);
}

.team-row__logo {
  width: 38px;
  height: 38px;
}

.team-row__logo img,
.top-list img {
  width: 78%;
  height: 78%;
  object-fit: contain;
}

.team-row__copy {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.team-row__copy strong,
.top-list strong {
  overflow: hidden;
  color: var(--color-fg);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.team-row__copy em {
  overflow: hidden;
  color: var(--color-muted);
  font-size: 10px;
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rank-pill {
  border-radius: 999px;
  padding: 3px 7px;
  color: var(--team-primary);
  background: color-mix(in srgb, var(--team-primary) 12%, transparent);
  font-size: 10px;
  font-weight: 900;
}

.club-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 92px auto;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
  padding: 14px;
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--team-primary) 16%, transparent), transparent 52%),
    var(--color-card);
}

.club-hero__identity {
  display: grid;
  grid-template-columns: 78px minmax(0, 1fr);
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.club-logo {
  width: 78px;
  height: 78px;
}

.club-logo img {
  width: 78%;
  height: 78%;
  object-fit: contain;
}

.club-logo svg,
.team-row__logo svg {
  color: #111827;
}

.club-hero__rank {
  display: grid;
  place-items: center;
  min-height: 76px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg);
}

.club-hero__rank span,
.club-hero__rank em {
  color: var(--color-muted);
  font-size: 10px;
  font-style: normal;
  font-weight: 800;
}

.club-hero__rank strong {
  color: var(--color-fg);
  font-size: 24px;
}

.detail-tabs {
  display: inline-flex;
  gap: 4px;
  margin-bottom: 10px;
  padding: 4px;
  background: var(--color-bg);
}

.detail-tabs button {
  min-width: 74px;
  height: 30px;
  border: 0;
  border-radius: 6px;
  color: var(--color-muted);
  background: transparent;
  cursor: pointer;
  font-size: 11px;
  font-weight: 900;
}

.detail-tabs button.active {
  color: var(--team-on-primary);
  background: var(--team-primary);
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.info-card,
.form-card,
.key-player-card,
.match-panel,
.squad-panel {
  min-width: 0;
  overflow: hidden;
}

.info-card {
  display: grid;
  gap: 5px;
  min-height: 104px;
  padding: 12px;
}

.info-card span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--color-muted);
  font-size: 11px;
  font-weight: 900;
}

.info-card strong {
  overflow: hidden;
  color: var(--color-fg);
  font-size: 16px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.info-card em {
  overflow: hidden;
  color: var(--color-muted);
  font-size: 11px;
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.form-card {
  grid-column: span 1;
}

.form-dots {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  padding: 12px;
}

.form-card p {
  margin: 0;
  padding: 0 12px 12px;
  color: var(--color-muted);
  font-size: 12px;
}

.form-dot,
.time-chip {
  display: inline-grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 999px;
  color: #fff;
  background: #64748b;
  font-size: 11px;
  font-weight: 1000;
}

.form-dot--W {
  background: #16a34a;
}

.form-dot--D {
  background: #f59e0b;
}

.form-dot--L {
  background: #dc2626;
}

.time-chip {
  width: 42px;
  color: var(--color-fg);
  background: var(--color-bg);
}

.key-player-card {
  grid-column: span 2;
}

.key-player {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  width: calc(100% - 24px);
  min-height: 42px;
  margin: 6px 12px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: inherit;
  background: var(--color-bg);
  cursor: pointer;
  text-align: left;
}

.key-player img,
.key-player span,
.squad-table img,
.squad-table td button > span {
  width: 30px;
  height: 30px;
  border-radius: 999px;
  object-fit: cover;
  background: var(--color-card);
}

.key-player span,
.squad-table td button > span {
  display: grid;
  place-items: center;
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 900;
}

.key-player strong,
.key-player em {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.key-player strong {
  color: var(--color-fg);
  font-size: 12px;
}

.key-player em {
  color: var(--color-muted);
  font-size: 11px;
  font-style: normal;
}

.matches-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  min-height: 0;
}

.match-panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-height: 0;
}

.match-list {
  display: grid;
  align-content: start;
  gap: 7px;
  padding: 10px;
}

.match-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto 34px;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 52px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: inherit;
  background: var(--color-bg);
  cursor: pointer;
  text-align: left;
}

.match-row div {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.match-row strong,
.match-row em {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.match-row strong {
  color: var(--color-fg);
  font-size: 12px;
}

.match-row em {
  color: var(--color-muted);
  font-size: 10px;
  font-style: normal;
}

.match-row b {
  color: var(--color-fg);
  font-size: 12px;
}

.squad-table {
  max-height: none;
}

.squad-panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-height: 0;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

th,
td {
  border-bottom: 1px solid var(--color-border);
  padding: 8px 10px;
  text-align: center;
}

th {
  color: var(--color-muted);
  background: var(--color-card);
  font-size: 10px;
  font-weight: 900;
  position: sticky;
  top: 0;
  z-index: 1;
}

th:first-child,
td:first-child {
  text-align: left;
}

.squad-table td button {
  display: inline-grid;
  grid-template-columns: 30px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  max-width: 100%;
  border: 0;
  color: var(--color-fg);
  background: transparent;
  cursor: pointer;
  font: inherit;
  font-weight: 800;
  text-align: left;
}

.squad-table td button strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.top-list {
  display: grid;
  align-content: start;
  gap: 7px;
  margin: 0;
  padding: 10px;
  list-style: none;
}

.top-list li {
  display: grid;
  grid-template-columns: 22px 32px minmax(0, 1fr) auto;
  align-items: center;
  gap: 7px;
  min-height: 42px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 5px 7px;
  background: var(--color-bg);
}

.top-list span {
  color: var(--color-muted);
  font-size: 11px;
  font-weight: 900;
  text-align: center;
}

.top-list img {
  width: 32px;
  height: 32px;
}

.top-list em {
  color: var(--color-muted);
  font-size: 11px;
  font-style: normal;
  font-weight: 800;
}

.state {
  display: grid;
  place-items: center;
  min-height: 160px;
  margin: 8px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-muted);
  background: var(--color-bg);
  font-size: 13px;
}

.state--wide {
  min-height: 360px;
}

.state--inline {
  min-height: 80px;
}

.state--error {
  color: #b91c1c;
}

@media (max-width: 1180px) {
  .teams-layout {
    grid-template-columns: minmax(280px, 0.85fr) minmax(480px, 1.4fr);
  }

  .league-snapshot {
    display: none;
  }
}
</style>
