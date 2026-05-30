<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Clock3,
  LayoutGrid,
  RotateCw,
} from 'lucide-vue-next'
import { generalApi } from '@/lib/api/general'
import {
  HOME_LEAGUE_TABS,
  LEAGUE_SHORT_KO,
  leagueLogoUrl,
  leagueVar,
  slugFromId,
} from '@/lib/league-colors'
import { shiftKstYmd, todayKstYmd } from '@/stores/home'
import type { FixtureSummary, FixtureStatus, LeagueRef, LeagueSlug, Period, TeamRef } from '@/types/home'

type StatusFilter = 'all' | 'upcoming' | 'live' | 'finished'
type ViewMode = 'competition' | 'time'

interface FixtureGroup {
  id: string
  label: string
  caption: string
  logoUrl: string | null
  slug: LeagueSlug | null
  fixtures: FixtureSummary[]
}

const router = useRouter()
const fixtures = ref<FixtureSummary[]>([])
const selectedLeagueId = ref<number | null>(null)
const period = ref<Period>('week')
const baseDate = ref(todayKstYmd())
const statusFilter = ref<StatusFilter>('all')
const viewMode = ref<ViewMode>('competition')
const status = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const error = ref<string | null>(null)

const periodOptions: { value: Period; label: string; hint: string }[] = [
  { value: 'day', label: '오늘', hint: '1일' },
  { value: 'week', label: '주간', hint: '월-일' },
  { value: 'month', label: '월간', hint: '1일-말일' },
]

const statusOptions: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: '전체' },
  { value: 'upcoming', label: '예정' },
  { value: 'live', label: '진행중' },
  { value: 'finished', label: '종료' },
]

const activeLeague = computed(() => HOME_LEAGUE_TABS.find((league) => league.id === selectedLeagueId.value))
const requestDate = computed(() => periodStartYmd(baseDate.value, period.value))
const pickerType = computed(() => {
  if (period.value === 'week') return 'week'
  if (period.value === 'month') return 'month'
  return 'date'
})
const pickerLabel = computed(() => {
  if (period.value === 'week') return '기준 주'
  if (period.value === 'month') return '기준 월'
  return '기준일'
})
const pickerValue = computed({
  get() {
    if (period.value === 'week') return ymdToIsoWeek(requestDate.value)
    if (period.value === 'month') return requestDate.value.slice(0, 7)
    return requestDate.value
  },
  set(value: string) {
    if (!value) return
    if (period.value === 'week') {
      baseDate.value = isoWeekToMondayYmd(value)
      return
    }
    if (period.value === 'month') {
      baseDate.value = `${value}-01`
      return
    }
    baseDate.value = value
  },
})
const rangeLabel = computed(() => {
  const start = requestDate.value
  if (period.value === 'day') return formatYmdKo(start)
  const endExclusive = period.value === 'week' ? shiftKstYmd(start, 7) : shiftKstMonthYmd(start, 1)
  return `${formatYmdKo(start)} - ${formatYmdKo(shiftKstYmd(endExclusive, -1))}`
})
const filteredFixtures = computed(() => fixtures.value.filter((fixture) => statusMatches(fixture.status_short)))
const summary = computed(() => ({
  total: fixtures.value.length,
  visible: filteredFixtures.value.length,
  upcoming: fixtures.value.filter((fixture) => fixtureKind(fixture.status_short) === 'upcoming').length,
  live: fixtures.value.filter((fixture) => fixtureKind(fixture.status_short) === 'live').length,
  finished: fixtures.value.filter((fixture) => fixtureKind(fixture.status_short) === 'finished').length,
}))

const nextFixture = computed(() => {
  const upcoming = filteredFixtures.value
    .filter((fixture) => fixtureKind(fixture.status_short) === 'upcoming')
    .sort((a, b) => new Date(a.kickoff_at).getTime() - new Date(b.kickoff_at).getTime())
  return upcoming[0] ?? filteredFixtures.value[0] ?? null
})

const groupedFixtures = computed(() => (
  viewMode.value === 'time' ? groupByTime(filteredFixtures.value) : groupByCompetition(filteredFixtures.value)
))

async function loadFixtures() {
  status.value = 'loading'
  error.value = null
  try {
    fixtures.value = (
      await generalApi.fixtures({
        leagueId: selectedLeagueId.value,
        period: period.value,
        date: requestDate.value,
        limit: 200,
      })
    ).items
    status.value = 'ok'
  } catch (err) {
    fixtures.value = []
    error.value = (err as Error).message
    status.value = 'error'
  }
}

function setLeague(id: number | null) {
  selectedLeagueId.value = id
}

function setPeriod(value: Period) {
  period.value = value
  baseDate.value = periodStartYmd(baseDate.value, value)
}

function shiftDate(delta: number) {
  if (period.value === 'week') {
    baseDate.value = shiftKstYmd(requestDate.value, delta * 7)
  } else if (period.value === 'month') {
    baseDate.value = shiftKstMonthYmd(requestDate.value, delta)
  } else {
    baseDate.value = shiftKstYmd(requestDate.value, delta)
  }
  void loadFixtures()
}

function openFixture(id: number) {
  void router.push({ name: 'fixture-detail', params: { externalId: id } })
}

function teamName(team: TeamRef): string {
  return team.short_name_ko ?? team.name_ko ?? team.name
}

function leagueName(league: LeagueRef): string {
  return league.short_name_ko ?? LEAGUE_SHORT_KO[league.slug] ?? league.name_ko ?? league.name
}

function statusLabel(statusShort: FixtureStatus): string {
  if (statusShort === 'NS') return '예정'
  if (statusShort === 'PST') return '연기'
  if (statusShort === 'FT' || statusShort === 'AET' || statusShort === 'PEN') return '종료'
  if (statusShort === 'CANC') return '취소'
  return '진행중'
}

function fixtureKind(statusShort: FixtureStatus): Exclude<StatusFilter, 'all'> {
  if (statusShort === 'FT' || statusShort === 'AET' || statusShort === 'PEN') return 'finished'
  if (statusShort === 'NS' || statusShort === 'PST' || statusShort === 'CANC') return 'upcoming'
  return 'live'
}

function statusMatches(statusShort: FixtureStatus): boolean {
  return statusFilter.value === 'all' || fixtureKind(statusShort) === statusFilter.value
}

function scoreText(fixture: FixtureSummary): string {
  if (fixture.goals_home != null && fixture.goals_away != null) {
    return `${fixture.goals_home} - ${fixture.goals_away}`
  }
  return 'vs'
}

function dayLabel(value: string): string {
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: 'long',
    day: 'numeric',
    weekday: 'short',
  }).format(new Date(value))
}

function timeLabel(value: string): string {
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

function periodStartYmd(ymd: string, value: Period): string {
  if (value === 'week') return startOfWeekYmd(ymd)
  if (value === 'month') return `${ymd.slice(0, 8)}01`
  return ymd
}

function startOfWeekYmd(ymd: string): string {
  const dt = ymdToUtcDate(ymd)
  const weekday = dt.getUTCDay() || 7
  dt.setUTCDate(dt.getUTCDate() - weekday + 1)
  return utcDateToYmd(dt)
}

function shiftKstMonthYmd(ymd: string, deltaMonths: number): string {
  const dt = ymdToUtcDate(periodStartYmd(ymd, 'month'))
  dt.setUTCMonth(dt.getUTCMonth() + deltaMonths)
  return utcDateToYmd(dt)
}

function ymdToIsoWeek(ymd: string): string {
  const dt = ymdToUtcDate(ymd)
  const weekday = dt.getUTCDay() || 7
  dt.setUTCDate(dt.getUTCDate() + 4 - weekday)
  const weekYear = dt.getUTCFullYear()
  const yearStart = new Date(Date.UTC(weekYear, 0, 1))
  const week = Math.ceil((((dt.getTime() - yearStart.getTime()) / 86400000) + 1) / 7)
  return `${weekYear}-W${String(week).padStart(2, '0')}`
}

function isoWeekToMondayYmd(value: string): string {
  const match = /^(?<year>\d{4})-W(?<week>\d{2})$/.exec(value)
  if (!match?.groups) return startOfWeekYmd(baseDate.value)
  const year = Number(match.groups.year)
  const week = Number(match.groups.week)
  const jan4 = new Date(Date.UTC(year, 0, 4))
  const jan4Weekday = jan4.getUTCDay() || 7
  const monday = new Date(jan4)
  monday.setUTCDate(jan4.getUTCDate() - jan4Weekday + 1 + ((week - 1) * 7))
  return utcDateToYmd(monday)
}

function formatYmdKo(ymd: string): string {
  const dt = ymdToUtcDate(ymd)
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: 'long',
    day: 'numeric',
    weekday: 'short',
  }).format(dt)
}

function ymdToUtcDate(ymd: string): Date {
  const [year, month, day] = ymd.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day))
}

function utcDateToYmd(dt: Date): string {
  const year = dt.getUTCFullYear()
  const month = String(dt.getUTCMonth() + 1).padStart(2, '0')
  const day = String(dt.getUTCDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function groupByCompetition(rows: FixtureSummary[]): FixtureGroup[] {
  const order = new Map(HOME_LEAGUE_TABS.map((league, index) => [league.id, index]))
  const grouped = new Map<number, FixtureGroup>()
  for (const fixture of rows) {
    const key = fixture.league.external_id
    const existing = grouped.get(key)
    if (existing) {
      existing.fixtures.push(fixture)
      continue
    }
    grouped.set(key, {
      id: String(key),
      label: leagueName(fixture.league),
      caption: `${fixture.league.name} · ${rows.filter((item) => item.league.external_id === key).length}경기`,
      logoUrl: fixture.league.logo_url ?? leagueLogoUrl(key),
      slug: fixture.league.slug,
      fixtures: [fixture],
    })
  }
  return [...grouped.values()]
    .map((group) => ({ ...group, fixtures: sortFixtures(group.fixtures) }))
    .sort((a, b) => (order.get(Number(a.id)) ?? 99) - (order.get(Number(b.id)) ?? 99))
}

function groupByTime(rows: FixtureSummary[]): FixtureGroup[] {
  const grouped = new Map<string, FixtureGroup>()
  for (const fixture of sortFixtures(rows)) {
    const key = dayLabel(fixture.kickoff_at)
    const existing = grouped.get(key)
    if (existing) {
      existing.fixtures.push(fixture)
      continue
    }
    grouped.set(key, {
      id: key,
      label: key,
      caption: '시간순 일정',
      logoUrl: null,
      slug: null,
      fixtures: [fixture],
    })
  }
  return [...grouped.values()]
}

function sortFixtures(rows: FixtureSummary[]): FixtureSummary[] {
  return [...rows].sort((a, b) => new Date(a.kickoff_at).getTime() - new Date(b.kickoff_at).getTime())
}

function themeStyle(slug: LeagueSlug | null): Record<string, string> {
  return {
    '--fixture-primary': leagueVar(slug, 'primary'),
    '--fixture-secondary': leagueVar(slug, 'secondary'),
    '--fixture-accent': leagueVar(slug, 'accent'),
    '--fixture-on-primary': leagueVar(slug, 'on-primary'),
  }
}

function leagueTabStyle(id: number | null): Record<string, string> {
  return themeStyle(slugFromId(id))
}

onMounted(() => {
  void loadFixtures()
})

watch([selectedLeagueId, period], () => {
  void loadFixtures()
})
</script>

<template>
  <main class="fixtures-page app-container" data-testid="ui-review-fixtures-page">
    <section class="fixtures-shell">
      <header class="fixtures-hero" :style="leagueTabStyle(selectedLeagueId)">
        <div class="fixtures-hero__copy">
          <span class="eyebrow">Fixtures Board</span>
          <h1>경기 일정</h1>
          <p>
            {{ activeLeague?.label ?? '전체 대회' }} · {{ rangeLabel }} ·
            {{ periodOptions.find((option) => option.value === period)?.label }}
          </p>
        </div>
        <div class="fixtures-hero__stats" aria-label="일정 요약">
          <span><strong>{{ summary.visible }}</strong>표시</span>
          <span><strong>{{ summary.upcoming }}</strong>예정</span>
          <span><strong>{{ summary.finished }}</strong>종료</span>
        </div>
      </header>

      <section class="control-band" aria-label="일정 필터">
        <div class="date-control">
          <button type="button" class="icon-button" aria-label="이전 기간" @click="shiftDate(-1)">
            <ChevronLeft :size="17" />
          </button>
          <label>
            <CalendarDays :size="15" aria-hidden="true" />
            <span>{{ pickerLabel }}</span>
            <input :key="period" v-model="pickerValue" :type="pickerType" @change="loadFixtures" />
          </label>
          <button type="button" class="icon-button" aria-label="다음 기간" @click="shiftDate(1)">
            <ChevronRight :size="17" />
          </button>
        </div>

        <div class="segmented" aria-label="기간 선택">
          <button
            v-for="option in periodOptions"
            :key="option.value"
            type="button"
            :class="{ active: period === option.value }"
            @click="setPeriod(option.value)"
          >
            <strong>{{ option.label }}</strong>
            <span>{{ option.hint }}</span>
          </button>
        </div>

        <div class="segmented segmented--status" aria-label="상태 선택">
          <button
            v-for="option in statusOptions"
            :key="option.value"
            type="button"
            :class="{ active: statusFilter === option.value }"
            @click="statusFilter = option.value"
          >
            {{ option.label }}
          </button>
        </div>

        <div class="view-switch" aria-label="보기 방식">
          <button
            type="button"
            :class="{ active: viewMode === 'competition' }"
            @click="viewMode = 'competition'"
          >
            <LayoutGrid :size="14" />
            대회별
          </button>
          <button type="button" :class="{ active: viewMode === 'time' }" @click="viewMode = 'time'">
            <Clock3 :size="14" />
            시간순
          </button>
        </div>

        <button type="button" class="refresh-button" @click="loadFixtures">
          <RotateCw :size="15" />
          새로고침
        </button>
      </section>

      <section class="league-filter" aria-label="리그 필터">
        <button
          v-for="league in HOME_LEAGUE_TABS"
          :key="league.id ?? 'all'"
          type="button"
          :class="['league-card', { 'league-card--active': selectedLeagueId === league.id }]"
          :style="leagueTabStyle(league.id)"
          @click="setLeague(league.id)"
        >
          <span class="league-card__mark">
            <img v-if="league.logoUrl" :src="league.logoUrl" alt="" />
            <b v-else>ALL</b>
          </span>
          <span>{{ league.label }}</span>
        </button>
      </section>

      <section v-if="nextFixture" class="next-strip" :style="themeStyle(nextFixture.league.slug)">
        <div>
          <span class="next-strip__label">다음 표시 경기</span>
          <strong>{{ teamName(nextFixture.home) }} vs {{ teamName(nextFixture.away) }}</strong>
        </div>
        <span>{{ dayLabel(nextFixture.kickoff_at) }} · {{ timeLabel(nextFixture.kickoff_at) }}</span>
      </section>

      <section class="fixtures-content" aria-live="polite">
        <div v-if="status === 'loading'" class="state">경기 데이터를 불러오는 중입니다.</div>
        <div v-else-if="status === 'error'" class="state state--error">{{ error }}</div>
        <div v-else-if="groupedFixtures.length === 0" class="state">조건에 맞는 경기가 없습니다.</div>
        <div v-else class="fixture-groups">
          <article
            v-for="group in groupedFixtures"
            :key="group.id"
            class="fixture-group"
            :style="themeStyle(group.slug)"
          >
            <header class="fixture-group__head">
              <span class="fixture-group__logo">
                <img v-if="group.logoUrl" :src="group.logoUrl" alt="" />
                <Clock3 v-else :size="22" aria-hidden="true" />
              </span>
              <div>
                <strong>{{ group.label }}</strong>
                <em>{{ group.caption }}</em>
              </div>
              <b>{{ group.fixtures.length }} 경기</b>
            </header>

            <div class="fixture-list">
              <article
                v-for="fixture in group.fixtures"
                :key="fixture.external_id"
                class="fixture-row"
                :style="themeStyle(fixture.league.slug)"
              >
                <button type="button" class="fixture-row__main" @click="openFixture(fixture.external_id)">
                  <span class="fixture-row__time">
                    <strong>{{ timeLabel(fixture.kickoff_at) }}</strong>
                    <em>{{ statusLabel(fixture.status_short) }}</em>
                  </span>

                  <span class="team-block team-block--home">
                    <span class="team-logo">
                      <img v-if="fixture.home.logo_url" :src="fixture.home.logo_url" alt="" />
                      <b v-else>{{ teamName(fixture.home).slice(0, 1) }}</b>
                    </span>
                    <strong>{{ teamName(fixture.home) }}</strong>
                  </span>

                  <span class="score-chip" :data-kind="fixtureKind(fixture.status_short)">
                    {{ scoreText(fixture) }}
                  </span>

                  <span class="team-block">
                    <span class="team-logo">
                      <img v-if="fixture.away.logo_url" :src="fixture.away.logo_url" alt="" />
                      <b v-else>{{ teamName(fixture.away).slice(0, 1) }}</b>
                    </span>
                    <strong>{{ teamName(fixture.away) }}</strong>
                  </span>
                </button>

                <aside class="fixture-row__side">
                  <span class="league-badge">
                    <img
                      v-if="fixture.league.logo_url ?? leagueLogoUrl(fixture.league.external_id)"
                      :src="fixture.league.logo_url ?? leagueLogoUrl(fixture.league.external_id) ?? undefined"
                      alt=""
                    />
                    {{ leagueName(fixture.league) }}
                  </span>
                  <button type="button" @click="openFixture(fixture.external_id)">
                    상세
                    <ArrowRight :size="13" />
                  </button>
                </aside>
              </article>
            </div>
          </article>
        </div>
      </section>
    </section>
  </main>
</template>

<style scoped>
.fixtures-page {
  height: calc(100vh - var(--header-height));
  overflow: hidden;
  padding-block: 14px 18px;
}

.fixtures-shell {
  display: grid;
  grid-template-rows: auto auto auto auto minmax(0, 1fr);
  gap: 10px;
  height: 100%;
  min-height: 0;
}

.fixtures-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 18px;
  min-height: 96px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 16px 18px;
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--fixture-primary) 15%, transparent), transparent 58%),
    var(--color-card);
  box-shadow: inset 4px 0 0 var(--fixture-primary);
}

.eyebrow {
  display: block;
  margin-bottom: 4px;
  color: var(--fixture-primary);
  font-size: 11px;
  font-weight: 900;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  color: var(--color-fg);
  font-size: 28px;
  line-height: 1.1;
}

.fixtures-hero p {
  margin: 8px 0 0;
  color: var(--color-muted);
  font-size: 13px;
}

.fixtures-hero__stats {
  display: grid;
  grid-template-columns: repeat(3, 76px);
  gap: 7px;
}

.fixtures-hero__stats span {
  display: grid;
  place-items: center;
  gap: 2px;
  height: 58px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-muted);
  background: var(--color-bg);
  font-size: 11px;
  font-weight: 800;
}

.fixtures-hero__stats strong {
  color: var(--color-fg);
  font-size: 20px;
}

.control-band {
  display: grid;
  grid-template-columns: auto auto auto auto minmax(118px, 1fr);
  align-items: center;
  gap: 8px;
  min-width: 0;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 8px;
  background: var(--color-card);
}

.date-control,
.segmented,
.view-switch {
  display: inline-flex;
  align-items: center;
  min-width: 0;
}

.date-control {
  gap: 5px;
}

.date-control label {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 34px;
  border: 1px solid var(--color-border);
  border-radius: 7px;
  padding: 0 9px;
  color: var(--color-muted);
  background: var(--color-bg);
}

.date-control label > span {
  color: var(--color-muted);
  font-size: 10px;
  font-weight: 900;
  white-space: nowrap;
}

.date-control input {
  width: 132px;
  border: 0;
  color: var(--color-fg);
  background: transparent;
  font: inherit;
  font-size: 12px;
}

.icon-button,
.refresh-button,
.view-switch button,
.segmented button {
  border: 1px solid var(--color-border);
  color: var(--color-muted);
  background: var(--color-bg);
  cursor: pointer;
}

.icon-button {
  display: inline-grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 7px;
}

.segmented {
  gap: 4px;
}

.segmented button {
  display: grid;
  gap: 1px;
  min-width: 58px;
  height: 34px;
  border-radius: 7px;
  padding: 3px 9px;
  font-size: 10px;
  font-weight: 900;
}

.segmented button span {
  font-size: 9px;
  font-weight: 800;
  opacity: 0.72;
}

.segmented--status button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.view-switch {
  gap: 4px;
}

.view-switch button,
.refresh-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  height: 34px;
  border-radius: 7px;
  padding: 0 10px;
  font-size: 11px;
  font-weight: 900;
}

.segmented button.active,
.view-switch button.active {
  border-color: var(--fixture-primary, var(--color-fg));
  color: var(--fixture-on-primary, var(--color-bg));
  background: var(--fixture-primary, var(--color-fg));
}

.refresh-button {
  color: var(--color-fg);
  justify-self: end;
  min-width: 118px;
}

.league-filter {
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
  min-width: 0;
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

.league-card__mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: 1px solid rgb(17 24 39 / 0.14);
  border-radius: 999px;
  background: #fff;
  overflow: hidden;
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

.league-card span:last-child {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.league-card--active {
  border-color: color-mix(in srgb, var(--fixture-primary) 62%, var(--color-border));
  color: var(--color-fg);
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--fixture-primary) 16%, transparent), transparent),
    var(--color-card);
  box-shadow: inset 0 -3px 0 var(--fixture-primary);
}

.next-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 46px;
  border: 1px solid color-mix(in srgb, var(--fixture-primary) 35%, var(--color-border));
  border-radius: 8px;
  padding: 8px 12px;
  background: color-mix(in srgb, var(--fixture-primary) 10%, var(--color-card));
}

.next-strip div {
  display: grid;
  gap: 2px;
}

.next-strip__label,
.next-strip > span {
  color: var(--color-muted);
  font-size: 11px;
  font-weight: 800;
}

.next-strip strong {
  color: var(--color-fg);
  font-size: 13px;
}

.fixtures-content {
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: none;
}

.fixtures-content::-webkit-scrollbar {
  display: none;
}

.fixture-groups {
  display: grid;
  gap: 10px;
  padding-bottom: 12px;
}

.fixture-group {
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
}

.fixture-group__head {
  display: grid;
  grid-template-columns: 46px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  min-height: 62px;
  border-bottom: 1px solid var(--color-border);
  padding: 9px 12px;
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--fixture-primary) 14%, transparent), transparent),
    var(--color-bg);
}

.fixture-group__logo {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  border: 1px solid rgb(17 24 39 / 0.14);
  border-radius: 999px;
  color: var(--fixture-primary);
  background: #fff;
}

.fixture-group__logo img {
  width: 78%;
  height: 78%;
  object-fit: contain;
}

.fixture-group__head div {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.fixture-group__head strong {
  overflow: hidden;
  color: var(--color-fg);
  font-size: 15px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fixture-group__head em {
  overflow: hidden;
  color: var(--color-muted);
  font-size: 11px;
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fixture-group__head > b {
  color: var(--fixture-primary);
  font-size: 12px;
}

.fixture-list {
  display: grid;
  gap: 0;
}

.fixture-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 154px;
  min-width: 0;
  border-bottom: 1px solid var(--color-border);
  box-shadow: inset 4px 0 0 var(--fixture-primary);
}

.fixture-row:last-child {
  border-bottom: 0;
}

.fixture-row__main {
  display: grid;
  grid-template-columns: 78px minmax(0, 1fr) 72px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  min-width: 0;
  border: 0;
  padding: 12px 14px 12px 16px;
  color: inherit;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.fixture-row__main:hover {
  background: color-mix(in srgb, var(--fixture-primary) 8%, transparent);
}

.fixture-row__time {
  display: grid;
  gap: 4px;
}

.fixture-row__time strong {
  color: var(--color-fg);
  font-size: 15px;
}

.fixture-row__time em {
  width: fit-content;
  border-radius: 999px;
  padding: 2px 7px;
  color: var(--fixture-primary);
  background: color-mix(in srgb, var(--fixture-primary) 13%, transparent);
  font-size: 10px;
  font-style: normal;
  font-weight: 900;
}

.team-block {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  align-items: center;
  gap: 9px;
  min-width: 0;
}

.team-block--home {
  justify-content: end;
  text-align: right;
}

.team-block strong {
  overflow: hidden;
  color: var(--color-fg);
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.team-logo {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border: 1px solid rgb(17 24 39 / 0.12);
  border-radius: 999px;
  background: #fff;
  overflow: hidden;
}

.team-logo img {
  width: 78%;
  height: 78%;
  object-fit: contain;
}

.team-logo b {
  color: #111827;
}

.score-chip {
  display: grid;
  place-items: center;
  justify-self: center;
  width: 62px;
  height: 38px;
  border: 1px solid color-mix(in srgb, var(--fixture-primary) 45%, var(--color-border));
  border-radius: 999px;
  color: var(--color-fg);
  background: var(--color-bg);
  font-size: 16px;
  font-weight: 1000;
}

.score-chip[data-kind='live'] {
  color: #fff;
  background: #dc2626;
  border-color: #dc2626;
}

.fixture-row__side {
  display: grid;
  align-content: center;
  gap: 7px;
  border-left: 1px solid var(--color-border);
  padding: 10px 12px;
}

.league-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  color: var(--color-muted);
  font-size: 10px;
  font-weight: 900;
}

.league-badge img {
  width: 22px;
  height: 22px;
  border-radius: 999px;
  object-fit: contain;
  background: #fff;
}

.fixture-row__side button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  height: 28px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  color: var(--color-fg);
  background: var(--color-bg);
  cursor: pointer;
  font-size: 11px;
  font-weight: 900;
}

.state {
  display: grid;
  place-items: center;
  min-height: 240px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-muted);
  background: var(--color-card);
}

.state--error {
  color: #b91c1c;
}
</style>
