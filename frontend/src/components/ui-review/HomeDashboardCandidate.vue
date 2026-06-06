<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight,
  CalendarDays,
  Table2,
  TrendingUp,
  UsersRound,
} from 'lucide-vue-next'
import { hasHomeStandings, useHomeStore } from '@/stores/home'
import LeagueMark from '@/components/common/LeagueMark.vue'
import { kstTime } from '@/lib/format/datetime'
import {
  HOME_COMPETITION_OPTIONS,
  HOME_LEAGUE_TABS,
  LEAGUE_SHORT_KO,
  leagueLogoUrl,
} from '@/lib/league-colors'
import type { FixtureSummary, LeagueRef, MetricKey, Period, StandingRow, TeamRef } from '@/types/home'

const home = useHomeStore()
const router = useRouter()
const PHASE_STANDINGS_LEAGUE_IDS = new Set([1, 2, 3])

const periodOptions: { value: Period; label: string }[] = [
  { value: 'day', label: '일간' },
  { value: 'week', label: '주간' },
  { value: 'month', label: '월간' },
]

const metricLabels: Record<MetricKey, string> = {
  goals: '득점',
  assists: '도움',
  yellow_cards: '경고',
  red_cards: '퇴장',
}
const metricOptions = (Object.keys(metricLabels) as MetricKey[]).map((value) => ({
  value,
  label: metricLabels[value],
}))
const standingsLeagueOptions = HOME_COMPETITION_OPTIONS.filter((league) => hasHomeStandings(league.id))
const topPlayerLeagueOptions = HOME_COMPETITION_OPTIONS

const fixtureRows = computed(() => home.fixtures.data.value ?? [])
const featuredFixtures = computed(() => fixtureRows.value.slice(0, 4))
const scheduleRows = computed(() => fixtureRows.value)
const standingsRowsAll = computed(() => home.standings.data.value ?? [])
const standingsRows = computed(() => standingsRowsAll.value.slice(0, 6))
const topPlayerRows = computed(() => home.topPlayers.data.value ?? [])
const hotRows = computed(() => home.hot.value ?? [])
const isPhaseStandings = computed(() => PHASE_STANDINGS_LEAGUE_IDS.has(home.standings.league_id))
const phaseGroups = computed(() => groupStandingRows(standingsRowsAll.value))
const singlePhaseGroup = computed(() => (phaseGroups.value.length === 1 ? phaseGroups.value[0] : null))
const isSinglePhaseTable = computed(() => (singlePhaseGroup.value?.rows.length ?? 0) > 8)

const standingsLeagueLabel = computed(() => {
  const selected = standingsLeagueOptions.find((league) => league.id === home.standings.league_id)
  return selected?.label ?? '순위'
})

const standingsSeasonLabel = computed(() => {
  const season = home.standings.season
  const leagueLabel = home.standings.league ? leagueShort(home.standings.league) : standingsLeagueLabel.value
  return season ? `${leagueLabel} ${season} 시즌` : leagueLabel
})

const standingsMetaLabel = computed(() => (isPhaseStandings.value ? '조별리그' : '상위 6팀'))

function teamName(team: TeamRef): string {
  return team.short_name_ko ?? team.name_ko ?? team.name
}

function leagueShort(league: LeagueRef): string {
  return league.short_name_ko ?? LEAGUE_SHORT_KO[league.slug] ?? league.name
}

function logoFor(league: LeagueRef): string | null {
  return league.logo_url ?? leagueLogoUrl(league.external_id)
}

function fixtureCenter(fixture: FixtureSummary): string {
  if (fixture.goals_home != null && fixture.goals_away != null) {
    return `${fixture.goals_home} - ${fixture.goals_away}`
  }
  return kstTime(fixture.kickoff_at)
}

function fixtureStatus(fixture: FixtureSummary): string {
  if (fixture.status_short === 'NS') return '예정'
  if (fixture.status_short === 'FT' || fixture.status_short === 'AET') return '종료'
  if (fixture.status_short === 'PST') return '연기'
  return fixture.status_short
}

function goalDiff(row: { goals_for: number; goals_against: number; goal_diff?: number | null }): number {
  return row.goal_diff ?? row.goals_for - row.goals_against
}

function groupStandingRows(rows: StandingRow[]): { group_name: string; rows: StandingRow[] }[] {
  const grouped = new Map<string, StandingRow[]>()
  for (const row of rows) {
    const key = row.group_name ?? standingsLeagueLabel.value
    grouped.set(key, [...(grouped.get(key) ?? []), row])
  }
  return [...grouped.entries()].map(([group_name, groupRows]) => ({ group_name, rows: groupRows }))
}

function setLeague(id: number | null) {
  home.setLeagueFilter(id)
}

function setPeriod(period: Period) {
  home.setPeriod(period)
}

function setStandingsLeague(id: number) {
  if (home.standings.league_id === id) return
  home.setStandingsLeague(id)
}

function setTopPlayersLeague(id: number) {
  if (home.topPlayers.league_id === id) return
  home.setTopPlayersLeague(id)
}

function setTopPlayersMetric(metric: MetricKey) {
  if (home.topPlayers.metric === metric) return
  home.setTopPlayersMetric(metric)
}

function openFixture(id: number) {
  router.push(`/fixtures/${id}`)
}

function openFixtures() {
  router.push('/fixtures')
}

function openStats() {
  router.push('/stats')
}

function openTournament(leagueId: number) {
  router.push({ name: 'standings', query: { league_id: String(leagueId), tab: 'tournament' } })
}
</script>

<template>
  <div class="candidate-home" data-testid="ui-review-home-candidate">
    <section class="home-toolbar" aria-label="홈 필터">
      <div class="periods" role="tablist" aria-label="기간 필터">
        <button
          v-for="option in periodOptions"
          :key="option.value"
          type="button"
          :class="['period', { 'period--active': home.fixtures.filter.period === option.value }]"
          :aria-selected="home.fixtures.filter.period === option.value"
          role="tab"
          @click="setPeriod(option.value)"
        >
          {{ option.label }}
        </button>
      </div>
    </section>

    <section class="league-strip" aria-label="리그 필터">
      <button
        v-for="league in HOME_LEAGUE_TABS"
        :key="league.id ?? 'all'"
        type="button"
        :class="['league-chip', { 'league-chip--active': home.fixtures.filter.league_id === league.id }]"
        @click="setLeague(league.id)"
      >
        <LeagueMark
          v-if="league.id !== null"
          :external-id="league.id"
          :slug="league.slug"
          :logo-url="league.logoUrl"
          :label="league.label"
          size="xs"
        />
        <span>{{ league.label }}</span>
      </button>
    </section>

    <section class="featured" aria-label="주요 경기">
      <button
        v-for="fixture in featuredFixtures"
        :key="fixture.external_id"
        type="button"
        class="featured__item"
        @click="openFixture(fixture.external_id)"
      >
        <span class="featured__league">
          <LeagueMark
            :external-id="fixture.league.external_id"
            :slug="fixture.league.slug"
            :logo-url="logoFor(fixture.league)"
            :label="leagueShort(fixture.league)"
            size="xs"
          />
          {{ leagueShort(fixture.league) }}
        </span>
        <span class="featured__teams">{{ teamName(fixture.home) }} vs {{ teamName(fixture.away) }}</span>
        <strong>{{ fixtureCenter(fixture) }}</strong>
      </button>
      <div v-if="home.fixtures.data.status === 'loading'" class="featured__placeholder">
        경기 목록을 불러오는 중
      </div>
      <div v-else-if="featuredFixtures.length === 0" class="featured__placeholder">
        선택한 조건에 예정된 경기가 없습니다
      </div>
    </section>

    <section class="dashboard" aria-label="홈 대시보드">
      <article class="panel panel--schedule">
        <header class="panel__head">
          <div>
            <span class="panel__icon"><CalendarDays :size="15" aria-hidden="true" /></span>
            <strong>일정 타임라인</strong>
          </div>
          <button type="button" class="panel__link" @click="openFixtures">
            전체 일정
            <ArrowRight :size="14" aria-hidden="true" />
          </button>
        </header>
        <div class="schedule">
          <button
            v-for="fixture in scheduleRows"
            :key="fixture.external_id"
            type="button"
            class="match-row"
            @click="openFixture(fixture.external_id)"
          >
            <span class="match-row__time">{{ fixtureCenter(fixture) }}</span>
            <span class="match-row__body">
              <span class="match-row__teams">{{ teamName(fixture.home) }} <b>vs</b> {{ teamName(fixture.away) }}</span>
              <span class="match-row__meta">
                {{ fixtureStatus(fixture) }}
              </span>
            </span>
            <span class="match-row__league" :title="leagueShort(fixture.league)">
              <LeagueMark
                :external-id="fixture.league.external_id"
                :slug="fixture.league.slug"
                :logo-url="logoFor(fixture.league)"
                :label="leagueShort(fixture.league)"
                size="md"
              />
            </span>
          </button>
          <div v-if="home.fixtures.data.status === 'loading'" class="state-row">일정 로딩 중</div>
          <div v-else-if="scheduleRows.length === 0" class="state-row">표시할 일정이 없습니다</div>
        </div>
      </article>

      <aside :class="['side-stack', { 'side-stack--phase': isPhaseStandings }]">
        <article class="panel panel--compact panel--stacked">
          <header class="panel__head">
            <div>
              <span class="panel__icon"><Table2 :size="15" aria-hidden="true" /></span>
              <strong>순위 요약</strong>
            </div>
            <span class="panel__meta">{{ standingsMetaLabel }}</span>
          </header>
          <div class="selector-strip" aria-label="순위 리그 선택">
            <button
              v-for="league in standingsLeagueOptions"
              :key="league.id"
              type="button"
              :class="['selector-pill', { 'selector-pill--active': home.standings.league_id === league.id }]"
              @click="setStandingsLeague(league.id)"
            >
              <LeagueMark
                :external-id="league.id"
                :slug="league.slug"
                :logo-url="league.logoUrl"
                :label="league.label"
                size="xs"
              />
              <span>{{ league.label }}</span>
            </button>
          </div>
          <div v-if="isPhaseStandings" class="phase-panel">
            <div class="phase-panel__topline">
              <span>{{ standingsSeasonLabel }}</span>
              <button type="button" class="phase-panel__button" @click="openTournament(home.standings.league_id)">
                토너먼트 트리
                <ArrowRight :size="13" aria-hidden="true" />
              </button>
            </div>
            <div v-if="home.standings.data.status === 'loading'" class="state-row">조별 순위 로딩 중</div>
            <div v-else-if="home.standings.data.status === 'error'" class="state-row">
              {{ home.standings.data.error }}
            </div>
            <div v-else-if="phaseGroups.length === 0" class="state-row">조별 순위 데이터 없음</div>
            <article v-else-if="isSinglePhaseTable && singlePhaseGroup" class="phase-table-card">
              <header>
                <strong>{{ singlePhaseGroup.group_name }}</strong>
                <span>전체 순위</span>
              </header>
              <ol>
                <li v-for="row in singlePhaseGroup.rows" :key="row.team.external_id">
                  <span>{{ row.rank }}</span>
                  <strong>{{ teamName(row.team) }}</strong>
                  <small>{{ row.played }}경기</small>
                  <em>{{ goalDiff(row) >= 0 ? '+' : '' }}{{ goalDiff(row) }}</em>
                  <b>{{ row.points }}</b>
                </li>
              </ol>
            </article>
            <div v-else class="group-grid">
              <article v-for="group in phaseGroups" :key="group.group_name" class="group-card">
                <header>{{ group.group_name }}</header>
                <ol>
                  <li v-for="row in group.rows.slice(0, 4)" :key="row.team.external_id">
                    <span>{{ row.rank }}</span>
                    <strong>{{ teamName(row.team) }}</strong>
                    <em>{{ goalDiff(row) >= 0 ? '+' : '' }}{{ goalDiff(row) }}</em>
                    <b>{{ row.points }}</b>
                  </li>
                </ol>
              </article>
            </div>
          </div>
          <ol v-else class="rank-list">
            <li class="rank-list__season">
              <span></span>
              <strong>{{ standingsSeasonLabel }}</strong>
              <em>승점</em>
            </li>
            <li v-for="row in standingsRows" :key="row.team.external_id">
              <span class="rank-list__rank">{{ row.rank }}</span>
              <span class="rank-list__team">{{ teamName(row.team) }}</span>
              <strong>{{ row.points }}</strong>
            </li>
          </ol>
          <div v-if="!isPhaseStandings && home.standings.data.status === 'loading'" class="state-row">
            순위 로딩 중
          </div>
          <div v-else-if="!isPhaseStandings && standingsRows.length === 0" class="state-row">
            순위 데이터 없음
          </div>
        </article>

        <article class="panel panel--compact panel--stacked">
          <header class="panel__head">
            <div>
              <span class="panel__icon"><TrendingUp :size="15" aria-hidden="true" /></span>
              <strong>주요 스탯</strong>
            </div>
            <button type="button" class="panel__link" @click="openStats">
              {{ metricLabels[home.topPlayers.metric] }}
              <ArrowRight :size="14" aria-hidden="true" />
            </button>
          </header>
          <div class="stat-control">
            <div class="selector-strip selector-strip--dense" aria-label="스탯 리그 선택">
              <button
                v-for="league in topPlayerLeagueOptions"
                :key="league.id"
                type="button"
                :class="['selector-pill', { 'selector-pill--active': home.topPlayers.league_id === league.id }]"
                @click="setTopPlayersLeague(league.id)"
              >
                <LeagueMark
                  :external-id="league.id"
                  :slug="league.slug"
                  :logo-url="league.logoUrl"
                  :label="league.label"
                  size="xs"
                />
                <span>{{ league.label }}</span>
              </button>
            </div>
            <div class="metric-tabs" aria-label="스탯 종류 선택">
              <button
                v-for="option in metricOptions"
                :key="option.value"
                type="button"
                :class="['metric-tab', { 'metric-tab--active': home.topPlayers.metric === option.value }]"
                @click="setTopPlayersMetric(option.value)"
              >
                {{ option.label }}
              </button>
            </div>
          </div>
          <ol class="player-list">
            <li v-for="row in topPlayerRows" :key="row.player.external_id">
              <span>{{ row.rank }}</span>
              <strong>{{ row.player.name_ko ?? row.player.name }}</strong>
              <em>{{ row.metric_value }}</em>
            </li>
          </ol>
          <div v-if="home.topPlayers.data.status === 'loading'" class="state-row">스탯 로딩 중</div>
          <div v-else-if="topPlayerRows.length === 0" class="state-row">스탯 데이터 없음</div>
        </article>
      </aside>

      <article class="panel panel--hot">
        <header class="panel__head">
          <div>
            <span class="panel__icon"><UsersRound :size="15" aria-hidden="true" /></span>
            <strong>핫 플레이어</strong>
          </div>
          <span class="panel__meta">최근 폼</span>
        </header>
        <div class="hot-list">
          <div v-for="item in hotRows" :key="item.player.external_id" class="hot-card">
            <img
              v-if="item.player.photo_url"
              :src="item.player.photo_url"
              :alt="item.player.name_ko ?? item.player.name"
            />
            <div v-else class="hot-card__fallback">{{ (item.player.name_ko ?? item.player.name).slice(0, 1) }}</div>
            <span>
              <strong>{{ item.player.name_ko ?? item.player.name }}</strong>
              <em>{{ item.goals }}G · {{ item.assists }}A</em>
            </span>
          </div>
          <div v-if="home.hot.status === 'loading'" class="state-row">선수 로딩 중</div>
          <div v-else-if="hotRows.length === 0" class="state-row">선수 데이터 없음</div>
        </div>
      </article>
    </section>
  </div>
</template>

<style scoped>
.candidate-home {
  display: grid;
  grid-template-rows: auto auto auto minmax(0, 1fr);
  gap: 8px;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  padding: 10px;
  background: var(--color-bg);
}

.home-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
}

.periods {
  display: inline-flex;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 2px;
  background: var(--color-bg);
}

.period {
  border: 0;
  border-radius: 999px;
  padding: 5px 9px;
  color: var(--color-muted);
  background: transparent;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
}

.period--active {
  color: var(--color-bg);
  background: var(--color-fg);
}

.league-strip {
  display: flex;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
}

.league-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 5px 8px;
  color: var(--color-muted);
  background: var(--color-card);
  font-size: 11px;
  font-weight: 800;
  cursor: pointer;
}

.league-chip span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.league-chip--active {
  color: var(--color-fg);
  background: var(--color-bg);
  box-shadow: inset 0 0 0 1px var(--color-fg);
}

.featured {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 7px;
  min-height: 72px;
}

.featured__item,
.featured__placeholder {
  display: grid;
  align-content: center;
  gap: 4px;
  min-width: 0;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 8px;
  color: var(--color-fg);
  background: var(--color-card);
  text-align: left;
}

.featured__item {
  cursor: pointer;
}

.featured__item:hover,
.match-row:hover {
  background: var(--color-card-hover);
}

.featured__league {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  color: var(--color-muted);
  font-size: 10px;
  font-weight: 800;
}

.featured__teams {
  overflow: hidden;
  font-size: 12px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.featured strong {
  font-size: 14px;
}

.featured__placeholder {
  grid-column: 1 / -1;
  justify-content: center;
  color: var(--color-muted);
  font-size: 12px;
}

.dashboard {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(230px, 0.85fr);
  grid-template-rows: minmax(0, 1fr) minmax(118px, 0.36fr);
  gap: 8px;
  min-height: 0;
  overflow: hidden;
}

.panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
}

.panel--schedule {
  grid-column: 1;
  grid-row: 1;
}

.panel--stacked {
  grid-template-rows: auto auto minmax(0, 1fr);
}

.side-stack {
  display: grid;
  grid-column: 2;
  grid-row: 1 / 3;
  grid-template-rows: minmax(0, 1fr) minmax(0, 1fr);
  gap: 8px;
  min-height: 0;
  overflow: hidden;
}

.side-stack--phase {
  grid-template-rows: minmax(0, 1.2fr) minmax(0, 0.8fr);
}

.panel--hot {
  grid-column: 1;
  grid-row: 2;
}

.panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 38px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg);
}

.panel__head div,
.panel__link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.panel__head strong {
  color: var(--color-fg);
  font-size: 13px;
}

.panel__icon {
  display: inline-flex;
  color: var(--color-muted);
}

.panel__link {
  border: 0;
  padding: 0;
  color: var(--color-muted);
  background: transparent;
  font-size: 11px;
  font-weight: 800;
  cursor: pointer;
}

.panel__meta {
  color: var(--color-muted);
  font-size: 11px;
}

.selector-strip {
  display: flex;
  gap: 4px;
  min-width: 0;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 6px 8px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-card);
  scrollbar-width: none;
}

.selector-strip::-webkit-scrollbar,
.phase-panel::-webkit-scrollbar,
.phase-table-card ol::-webkit-scrollbar {
  display: none;
}

.selector-strip--dense {
  padding: 0;
  border-bottom: 0;
  background: transparent;
}

.selector-pill {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 4px;
  height: 25px;
  min-width: 0;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 3px 7px;
  color: var(--color-muted);
  background: var(--color-bg);
  font-size: 10px;
  font-weight: 900;
  cursor: pointer;
}

.selector-pill span {
  max-width: 58px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.selector-pill--active {
  color: var(--color-fg);
  border-color: color-mix(in srgb, var(--color-fg) 45%, var(--color-border));
  background: var(--color-card-hover);
}

.stat-control {
  display: grid;
  gap: 5px;
  min-width: 0;
  padding: 6px 8px;
  border-bottom: 1px solid var(--color-border);
}

.metric-tabs {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 4px;
}

.metric-tab {
  min-width: 0;
  height: 25px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-muted);
  background: var(--color-bg);
  font-size: 10px;
  font-weight: 900;
  cursor: pointer;
}

.metric-tab--active {
  color: var(--color-bg);
  border-color: var(--color-fg);
  background: var(--color-fg);
}

.schedule,
.hot-list {
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 8px;
  scrollbar-width: none;
}

.schedule::-webkit-scrollbar,
.hot-list::-webkit-scrollbar,
.rank-list::-webkit-scrollbar,
.player-list::-webkit-scrollbar {
  display: none;
}

.match-row {
  display: grid;
  grid-template-columns: 54px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  width: 100%;
  margin-bottom: 6px;
  border: 1px solid var(--color-border);
  border-radius: 7px;
  padding: 8px;
  color: inherit;
  background: var(--color-bg);
  text-align: left;
  cursor: pointer;
}

.match-row__time {
  color: var(--color-fg);
  font-size: 13px;
  font-weight: 900;
  text-align: center;
}

.match-row__body {
  display: grid;
  min-width: 0;
  gap: 2px;
}

.match-row__teams {
  overflow: hidden;
  font-size: 12px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.match-row__teams b {
  color: var(--color-muted);
  font-size: 10px;
}

.match-row__meta {
  color: var(--color-muted);
  font-size: 10px;
}

.match-row__league {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
}

.rank-list,
.player-list {
  display: grid;
  align-content: start;
  gap: 4px;
  min-height: 0;
  margin: 0;
  padding: 8px;
  list-style: none;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: none;
}

.rank-list__season {
  color: var(--color-muted);
  background: color-mix(in srgb, var(--color-card-hover) 58%, transparent);
}

.rank-list__season strong,
.rank-list__season em {
  color: var(--color-muted);
  font-size: 10px;
  font-style: normal;
  font-weight: 900;
}

.phase-panel {
  display: grid;
  align-content: start;
  gap: 5px;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 6px;
  scrollbar-width: none;
}

.phase-panel__topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
  color: var(--color-muted);
  font-size: 10px;
  font-weight: 900;
}

.phase-panel__topline span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.phase-panel__button {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 4px;
  height: 22px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 0 7px;
  color: var(--color-fg);
  background: var(--color-bg);
  font-size: 10px;
  font-weight: 900;
  cursor: pointer;
}

.phase-table-card {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: 7px;
  background: var(--color-bg);
}

.phase-table-card header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 5px 7px;
  border-bottom: 1px solid var(--color-border);
}

.phase-table-card header strong {
  overflow: hidden;
  color: var(--color-fg);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.phase-table-card header span {
  flex: 0 0 auto;
  color: var(--color-muted);
  font-size: 9px;
  font-weight: 900;
}

.phase-table-card ol {
  display: grid;
  align-content: start;
  gap: 1px;
  min-height: 0;
  margin: 0;
  padding: 4px 6px 6px;
  list-style: none;
  overflow-y: auto;
  scrollbar-width: none;
}

.phase-table-card li {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) 34px 28px 22px;
  align-items: center;
  gap: 4px;
  min-width: 0;
  border-bottom: 1px solid color-mix(in srgb, var(--color-border) 70%, transparent);
  padding: 4px 0;
  color: var(--color-muted);
  font-size: 10px;
}

.phase-table-card li:last-child {
  border-bottom: 0;
}

.phase-table-card li strong {
  overflow: hidden;
  color: var(--color-fg);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.phase-table-card small,
.phase-table-card em,
.phase-table-card b {
  font-size: 9px;
  font-style: normal;
  font-weight: 900;
  text-align: right;
}

.group-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 5px;
}

.group-card {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: 7px;
  background: var(--color-bg);
}

.group-card header {
  padding: 4px 6px;
  border-bottom: 1px solid var(--color-border);
  color: var(--color-fg);
  font-size: 9px;
  font-weight: 900;
}

.group-card ol {
  display: grid;
  gap: 1px;
  margin: 0;
  padding: 3px 5px 5px;
  list-style: none;
}

.group-card li {
  display: grid;
  grid-template-columns: 13px minmax(0, 1fr) 20px 17px;
  align-items: center;
  gap: 3px;
  min-width: 0;
  color: var(--color-muted);
  font-size: 9px;
}

.group-card strong {
  overflow: hidden;
  color: var(--color-fg);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-card em,
.group-card b {
  font-style: normal;
  font-weight: 900;
  text-align: right;
}

.rank-list li,
.player-list li {
  display: grid;
  align-items: center;
  gap: 6px;
  min-width: 0;
  border-bottom: 1px solid var(--color-border);
  padding: 5px 0;
  font-size: 11px;
}

.rank-list li {
  grid-template-columns: 22px minmax(0, 1fr) 32px;
}

.player-list li {
  grid-template-columns: 22px minmax(0, 1fr) 34px;
}

.rank-list__rank,
.player-list span {
  color: var(--color-muted);
  font-weight: 900;
}

.rank-list__team,
.player-list strong {
  overflow: hidden;
  color: var(--color-fg);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rank-list strong,
.player-list em {
  color: var(--color-fg);
  font-style: normal;
  font-weight: 900;
  text-align: right;
}

li.rank-list__season strong,
li.rank-list__season em {
  color: var(--color-muted);
  font-size: 10px;
}

.hot-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}

.hot-card {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  align-items: center;
  gap: 6px;
  min-width: 0;
  border: 1px solid var(--color-border);
  border-radius: 7px;
  padding: 6px;
  background: var(--color-bg);
}

.hot-card img,
.hot-card__fallback {
  width: 32px;
  height: 32px;
  border-radius: 999px;
  object-fit: cover;
  background: var(--color-card);
}

.hot-card__fallback {
  display: grid;
  place-items: center;
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 900;
}

.hot-card span {
  display: grid;
  min-width: 0;
  gap: 2px;
}

.hot-card strong {
  overflow: hidden;
  color: var(--color-fg);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hot-card em {
  color: var(--color-muted);
  font-size: 10px;
  font-style: normal;
}

.state-row {
  display: grid;
  place-items: center;
  min-height: 48px;
  color: var(--color-muted);
  font-size: 12px;
}
</style>
