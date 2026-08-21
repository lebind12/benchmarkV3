<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  fetchApiFootballAiReview,
  type ApiFootballAiReviewResponse,
} from '@/lib/api/apiFootballLive'

type LeagueSlug =
  | 'premier-league'
  | 'champions-league'
  | 'europa-league'
  | 'carabao-cup'
  | 'fa-cup'
  | 'world-cup-2026'

type StatItem = {
  label: string
  home: string
  away: string
  homePct: number
  awayPct: number
}

type BoardVariant = 'ribbon' | 'dial' | 'matrix' | 'timeline' | 'ticket' | 'lower' | 'tower'
type DialTabId = 'attack' | 'chance' | 'control' | 'discipline' | 'ai'
type DialStatTabId = Exclude<DialTabId, 'ai'>
type DialMetricScaleKind = 'percentage' | 'continuous' | 'count'

type DialMetricScale = {
  kind: DialMetricScaleKind
  max: number
}

type DialTabDefinition = {
  id: DialTabId
  label: string
}

type DialStatGroup = {
  id: DialStatTabId
  metrics: StatItem[]
}

const dialTabs: DialTabDefinition[] = [
  { id: 'attack', label: '공격' },
  { id: 'chance', label: '찬스' },
  { id: 'control', label: '운영' },
  { id: 'discipline', label: '징계' },
  { id: 'ai', label: 'AI 요약' },
]

const dialStatLabels: Record<DialStatTabId, string[]> = {
  attack: ['xG', '유효슈팅', '슈팅정확도'],
  chance: ['전체슈팅', '박스안슈팅', '코너킥'],
  control: ['점유율', '패스성공률', '오프사이드'],
  discipline: ['파울', '옐로카드', '레드카드'],
}

const percentageDialStats = new Set(['슈팅정확도', '점유율', '패스성공률'])

const props = defineProps<{
  league: LeagueSlug
  themeLabel: string
  home: string
  away: string
  homeCode: string
  awayCode: string
  homeLogoUrl?: string
  awayLogoUrl?: string
  score: string
  clock: string
  status: string
  stats: StatItem[]
  fixtureId?: number
  materialRevision?: boolean
}>()

const boardVariant = computed<BoardVariant>(() => {
  switch (props.league) {
    case 'world-cup-2026':
      return 'ribbon'
    case 'premier-league':
      return 'dial'
    case 'champions-league':
      return 'matrix'
    case 'europa-league':
      return 'timeline'
    case 'carabao-cup':
      return 'ticket'
    case 'fa-cup':
      return 'tower'
    default:
      return 'tower'
  }
})

const possession = computed(() => props.stats.find((stat) => stat.label === '점유율') ?? props.stats[0])
const secondaryStats = computed(() => props.stats.filter((stat) => stat !== possession.value))
const compactStats = computed(() => secondaryStats.value.slice(0, 3))
const matrixStats = computed(() => props.stats.slice(0, 4))
const activeDialTab = ref<DialTabId>('attack')
const dialTransitionDirection = ref<'next' | 'prev'>('next')
const aiReviewStatus = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const aiReviewResult = ref<ApiFootballAiReviewResponse | null>(null)
const aiReviewError = ref('')
let dialSwipeStartX: number | null = null

const dialStatGroups = computed<DialStatGroup[]>(() =>
  (Object.keys(dialStatLabels) as DialStatTabId[]).map((id) => ({
    id,
    metrics: dialStatLabels[id].map((label) => statMetricForLabel(label)),
  })),
)

const activeDialStatGroup = computed(() =>
  dialStatGroups.value.find((group) => group.id === activeDialTab.value) ?? null,
)

const aiReviewBasisLabel = computed(() => {
  const basis = aiReviewResult.value?.reviewBasis
  if (!basis) return ''
  const matchClock = basis.matchClockLabel
    || (basis.clock
      ? `경기시각 ${basis.clock} 기준`
      : typeof basis.minute === 'number'
        ? `${basis.minute}분 기준`
        : '')
  const phase = basis.phaseLabel || basis.status || ''
  return [matchClock, phase, aiReviewResult.value?.cached ? '캐시' : '생성']
    .filter(Boolean)
    .join(' · ')
})

watch(
  () => props.fixtureId,
  () => {
    aiReviewStatus.value = 'idle'
    aiReviewResult.value = null
    aiReviewError.value = ''
  },
)

function findStat(label: string) {
  return props.stats.find((stat) => stat.label === label)
}

function statMetricForLabel(label: string): StatItem {
  if (label === '슈팅정확도') {
    return shootingAccuracyMetric()
  }
  return findStat(label) ?? {
    label,
    home: '-',
    away: '-',
    homePct: 0,
    awayPct: 0,
  }
}

function shootingAccuracyMetric(): StatItem {
  const totalShots = findStat('전체슈팅')
  const shotsOnTarget = findStat('유효슈팅')
  if (!totalShots || !shotsOnTarget) {
    return { label: '슈팅정확도', home: '-', away: '-', homePct: 0, awayPct: 0 }
  }

  const homeTotal = numericStat(totalShots.home)
  const awayTotal = numericStat(totalShots.away)
  const homeAccuracy = homeTotal > 0 ? numericStat(shotsOnTarget.home) / homeTotal * 100 : 0
  const awayAccuracy = awayTotal > 0 ? numericStat(shotsOnTarget.away) / awayTotal * 100 : 0
  const pct = pairedPercent(homeAccuracy, awayAccuracy)
  return {
    label: '슈팅정확도',
    home: `${Math.round(homeAccuracy)}%`,
    away: `${Math.round(awayAccuracy)}%`,
    homePct: pct.home,
    awayPct: pct.away,
  }
}

function numericStat(value: string) {
  const parsed = Number.parseFloat(value.replace('%', ''))
  return Number.isFinite(parsed) ? parsed : 0
}

function pairedPercent(home: number, away: number) {
  const total = home + away
  if (total <= 0) return { home: 0, away: 0 }
  const homePct = Math.round(home / total * 100)
  return { home: homePct, away: 100 - homePct }
}

function dialMetricScale(metric: StatItem): DialMetricScale {
  if (percentageDialStats.has(metric.label)) {
    return { kind: 'percentage', max: 100 }
  }
  if (metric.label === 'xG') {
    return { kind: 'continuous', max: 3 }
  }

  const largestValue = Math.max(numericStat(metric.home), numericStat(metric.away))
  return {
    kind: 'count',
    max: Math.max(1, Math.ceil(largestValue * 1.2)),
  }
}

function dialMetricStyle(metric: StatItem) {
  const scale = dialMetricScale(metric)
  const fillPercent = (value: string) => Math.max(
    0,
    Math.min(100, numericStat(value) / scale.max * 100),
  )
  return {
    '--dial-home-pct': `${fillPercent(metric.home)}%`,
    '--dial-away-pct': `${fillPercent(metric.away)}%`,
  }
}

function selectDialTab(nextTab: DialTabId) {
  if (nextTab === activeDialTab.value) return
  const currentIndex = dialTabs.findIndex((tab) => tab.id === activeDialTab.value)
  const nextIndex = dialTabs.findIndex((tab) => tab.id === nextTab)
  dialTransitionDirection.value = nextIndex >= currentIndex ? 'next' : 'prev'
  activeDialTab.value = nextTab
}

function moveDialTab(offset: -1 | 1) {
  const currentIndex = dialTabs.findIndex((tab) => tab.id === activeDialTab.value)
  const nextIndex = Math.max(0, Math.min(dialTabs.length - 1, currentIndex + offset))
  if (nextIndex !== currentIndex) {
    selectDialTab(dialTabs[nextIndex].id)
  }
}

function handleDialPointerDown(event: PointerEvent) {
  if (event.pointerType === 'mouse' && event.button !== 0) return
  dialSwipeStartX = event.clientX
}

function handleDialPointerUp(event: PointerEvent) {
  if (dialSwipeStartX === null) return
  const delta = event.clientX - dialSwipeStartX
  dialSwipeStartX = null
  if (Math.abs(delta) < 36) return
  moveDialTab(delta < 0 ? 1 : -1)
}

function handleDialPointerCancel() {
  dialSwipeStartX = null
}

async function requestAiReview(forceRefresh = false) {
  if (!props.fixtureId || aiReviewStatus.value === 'loading') return
  aiReviewStatus.value = 'loading'
  aiReviewError.value = ''
  try {
    const result = await fetchApiFootballAiReview(props.fixtureId, { forceRefresh })
    aiReviewResult.value = result
    aiReviewStatus.value = result.available ? 'ready' : 'error'
    aiReviewError.value = result.available
      ? ''
      : result.message ?? 'AI 경기요약을 아직 생성할 수 없습니다.'
  } catch (error) {
    aiReviewStatus.value = 'error'
    aiReviewError.value = (error as Error).message
  }
}

function widthStyle(value: number) {
  return { width: `${value}%` }
}

function awayOffsetStyle(value: number) {
  return { marginLeft: `${100 - value}%`, width: `${value}%` }
}

</script>

<template>
  <article
    class="stats-card"
    :class="[`stats-card--${boardVariant}`, { 'stats-card--material': materialRevision }]"
    :data-variant="boardVariant"
    data-testid="stats-card"
  >
    <div v-if="stats.length === 0" class="stats-empty" data-testid="stats-empty">
      <span>경기 스탯</span>
      <strong>라이브 스탯 수신 대기</strong>
      <p>{{ homeCode }} / {{ awayCode }}</p>
    </div>

    <template v-else-if="boardVariant === 'ribbon'">
      <div class="ribbon-strips" aria-hidden="true">
        <span></span><span></span><span></span><span></span><span></span>
      </div>
      <header class="ribbon-crest-row">
        <span class="ribbon-country-badge" data-testid="stats-country-badge" :aria-label="homeCode">
          <img v-if="homeLogoUrl" :src="homeLogoUrl" alt="" aria-hidden="true" />
          <b v-else>{{ homeCode }}</b>
        </span>
        <span>경기 스탯</span>
        <span class="ribbon-country-badge" data-testid="stats-country-badge" :aria-label="awayCode">
          <img v-if="awayLogoUrl" :src="awayLogoUrl" alt="" aria-hidden="true" />
          <b v-else>{{ awayCode }}</b>
        </span>
      </header>
      <div class="ribbon-team-row">
        <strong>{{ home }}</strong>
        <i>{{ themeLabel }}</i>
        <strong>{{ away }}</strong>
      </div>
      <div v-if="possession" class="ribbon-possession">
        <strong>{{ possession.home }}</strong>
        <div class="split-meter">
          <span class="home-meter" :style="widthStyle(possession.homePct)"></span>
          <span class="away-meter" :style="widthStyle(possession.awayPct)"></span>
        </div>
        <strong>{{ possession.away }}</strong>
      </div>
      <div class="ribbon-stat-list">
        <p v-for="stat in secondaryStats" :key="stat.label">
          <b>{{ stat.home }}</b>
          <span>{{ stat.label }}</span>
          <b>{{ stat.away }}</b>
        </p>
      </div>
    </template>

    <template v-else-if="boardVariant === 'dial'">
      <header class="dial-header">
        <b>{{ homeCode }}</b>
        <span>{{ themeLabel }}</span>
        <b>{{ awayCode }}</b>
      </header>
      <div v-if="possession" class="dial-core">
        <strong
          class="dial-possession-value dial-possession-value--home"
          data-testid="stats-possession-home-value"
        >
          {{ possession.home }}
        </strong>
        <span
          class="dial-team-crest dial-team-crest--home"
          data-testid="stats-possession-home-logo"
          :aria-label="home"
        >
          <img v-if="homeLogoUrl" :src="homeLogoUrl" alt="" aria-hidden="true" />
          <b v-else>{{ homeCode }}</b>
        </span>
        <div class="dial-ring">
          <span>점유율</span>
        </div>
        <strong
          class="dial-possession-value dial-possession-value--away"
          data-testid="stats-possession-away-value"
        >
          {{ possession.away }}
        </strong>
        <span
          class="dial-team-crest dial-team-crest--away"
          data-testid="stats-possession-away-logo"
          :aria-label="away"
        >
          <img v-if="awayLogoUrl" :src="awayLogoUrl" alt="" aria-hidden="true" />
          <b v-else>{{ awayCode }}</b>
        </span>
      </div>
      <div class="dial-tabbed-stats" data-testid="dial-tabbed-stats">
        <div class="dial-stat-tabs" role="tablist" aria-label="경기 스탯 구분">
          <button
            v-for="tab in dialTabs"
            :id="`dial-tab-${tab.id}`"
            :key="tab.id"
            type="button"
            role="tab"
            :aria-controls="`dial-panel-${tab.id}`"
            :aria-selected="activeDialTab === tab.id"
            :class="{ active: activeDialTab === tab.id }"
            :data-testid="`dial-stat-tab-${tab.id}`"
            @click="selectDialTab(tab.id)"
          >
            {{ tab.label }}
          </button>
        </div>
        <div
          class="dial-stat-viewport"
          :data-transition-direction="dialTransitionDirection"
          data-testid="dial-stat-viewport"
          @pointerdown="handleDialPointerDown"
          @pointerup="handleDialPointerUp"
          @pointercancel="handleDialPointerCancel"
        >
          <Transition name="dial-stat-slide" mode="out-in">
            <section
              v-if="activeDialTab !== 'ai'"
              :id="`dial-panel-${activeDialTab}`"
              :key="activeDialTab"
              class="dial-stat-grid"
              role="tabpanel"
              :aria-labelledby="`dial-tab-${activeDialTab}`"
              :data-testid="`dial-stat-panel-${activeDialTab}`"
            >
              <article
                v-for="metric in activeDialStatGroup?.metrics ?? []"
                :key="metric.label"
                class="dial-stat-metric"
                :class="`dial-stat-metric--${dialMetricScale(metric).kind}`"
                :style="dialMetricStyle(metric)"
                :data-scale-kind="dialMetricScale(metric).kind"
                :data-scale-max="dialMetricScale(metric).max"
                data-testid="dial-stat-metric"
              >
                <span>{{ metric.label }}</span>
                <div class="dial-stat-bars" aria-hidden="true">
                  <i class="dial-stat-bar dial-stat-bar--home"></i>
                  <i class="dial-stat-bar dial-stat-bar--away"></i>
                </div>
                <div class="dial-stat-score">
                  <b>{{ metric.home }}</b>
                  <b>{{ metric.away }}</b>
                </div>
              </article>
            </section>
            <section
              v-else
              id="dial-panel-ai"
              key="ai"
              class="dial-ai-review"
              role="tabpanel"
              aria-labelledby="dial-tab-ai"
              data-testid="dial-ai-review"
            >
              <header>
                <span>AI MATCH REVIEW</span>
                <button
                  v-if="aiReviewStatus === 'ready'"
                  type="button"
                  :disabled="!fixtureId"
                  aria-label="AI 경기요약 새로고침"
                  data-testid="dial-ai-refresh"
                  @click="requestAiReview(true)"
                >
                  새로고침
                </button>
              </header>
              <div class="dial-ai-review-body">
                <div v-if="aiReviewStatus === 'idle'" class="dial-ai-review-action">
                  <button
                    type="button"
                    :disabled="!fixtureId"
                    data-testid="dial-ai-generate"
                    @click="requestAiReview()"
                  >
                    AI 경기요약 생성
                  </button>
                  <small v-if="!fixtureId">경기 정보 수신 대기</small>
                </div>
                <div v-else-if="aiReviewStatus === 'loading'" class="dial-ai-review-action">
                  <p class="dial-ai-review-muted">경기 데이터와 흐름을 요약하고 있습니다.</p>
                </div>
                <template v-else-if="aiReviewStatus === 'ready' && aiReviewResult?.commentary">
                  <strong>{{ aiReviewResult.commentary.headline || 'AI 경기요약' }}</strong>
                  <b>{{ aiReviewResult.commentary.oneLineSummary }}</b>
                  <p>{{ aiReviewResult.commentary.mainCommentary }}</p>
                  <small v-if="aiReviewBasisLabel">{{ aiReviewBasisLabel }}</small>
                </template>
                <div v-else class="dial-ai-review-action">
                  <p class="dial-ai-review-muted">{{ aiReviewError || 'AI 경기요약을 생성할 수 없습니다.' }}</p>
                  <button
                    type="button"
                    :disabled="!fixtureId"
                    data-testid="dial-ai-retry"
                    @click="requestAiReview()"
                  >
                    다시 시도
                  </button>
                </div>
              </div>
            </section>
          </Transition>
        </div>
      </div>
    </template>

    <template v-else-if="boardVariant === 'matrix'">
      <header class="matrix-header">
        <b>{{ homeCode }}</b>
        <strong>경기 흐름</strong>
        <b>{{ awayCode }}</b>
      </header>
      <div class="matrix-grid">
        <div v-for="stat in matrixStats" :key="stat.label" class="matrix-cell">
          <span>{{ stat.label }}</span>
          <p>
            <b>{{ stat.home }}</b>
            <i></i>
            <b>{{ stat.away }}</b>
          </p>
        </div>
      </div>
      <footer class="matrix-footer">{{ themeLabel }}</footer>
    </template>

    <template v-else-if="boardVariant === 'timeline'">
      <header class="timeline-header">
        <strong>{{ themeLabel }}</strong>
        <span>{{ homeCode }} / {{ awayCode }}</span>
      </header>
      <div class="timeline-lanes">
        <div v-for="stat in stats" :key="stat.label" class="timeline-row">
          <b>{{ stat.home }}</b>
          <div>
            <span class="timeline-label">{{ stat.label }}</span>
            <i class="timeline-home" :style="widthStyle(stat.homePct)"></i>
            <i class="timeline-away" :style="awayOffsetStyle(stat.awayPct)"></i>
          </div>
          <b>{{ stat.away }}</b>
        </div>
      </div>
    </template>

    <template v-else-if="boardVariant === 'lower'">
      <header class="lower-score">
        <b>{{ homeCode }}</b>
        <strong>경기 스탯</strong>
        <b>{{ awayCode }}</b>
        <span>{{ themeLabel }}</span>
      </header>
      <div class="lower-stack">
        <div v-for="stat in compactStats" :key="stat.label" class="lower-band">
          <strong>{{ stat.home }}</strong>
          <span>{{ stat.label }}</span>
          <strong>{{ stat.away }}</strong>
        </div>
      </div>
      <footer v-if="possession" class="lower-possession">
        <span>{{ possession.home }}</span>
        <div class="split-meter">
          <span class="home-meter" :style="widthStyle(possession.homePct)"></span>
          <span class="away-meter" :style="widthStyle(possession.awayPct)"></span>
        </div>
        <span>{{ possession.away }}</span>
      </footer>
    </template>

    <template v-else-if="boardVariant === 'ticket'">
      <aside class="ticket-stub">
        <span>경기</span>
        <b>스탯</b>
      </aside>
      <section class="ticket-main">
        <header>
          <b>{{ homeCode }}</b>
          <strong>경기 스탯</strong>
          <b>{{ awayCode }}</b>
        </header>
        <div class="ticket-teams">
          <span>{{ home }}</span>
          <span>{{ away }}</span>
        </div>
        <div class="ticket-stats">
          <p v-for="stat in stats" :key="stat.label">
            <b>{{ stat.home }}</b>
            <span>{{ stat.label }}</span>
            <b>{{ stat.away }}</b>
          </p>
        </div>
      </section>
    </template>

    <template v-else>
      <header class="tower-header">
        <div>
          <b>{{ homeCode }}</b>
          <span>{{ home }}</span>
        </div>
        <strong>{{ themeLabel }}</strong>
        <div>
          <b>{{ awayCode }}</b>
          <span>{{ away }}</span>
        </div>
      </header>
      <div class="tower-body">
        <div v-if="possession" class="tower-feature">
          <span>점유율</span>
          <strong>{{ possession.home }} - {{ possession.away }}</strong>
        </div>
        <p v-for="stat in secondaryStats" :key="stat.label">
          <b>{{ stat.home }}</b>
          <span>{{ stat.label }}</span>
          <b>{{ stat.away }}</b>
        </p>
      </div>
    </template>
  </article>
</template>

<style scoped>
*,
*::before,
*::after {
  box-sizing: border-box;
}

.stats-card {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  overflow: hidden;
  color: var(--text);
  background: var(--panel);
  border: 0.16rem solid var(--border);
  box-shadow: 0.38rem 0.38rem 0 #000000;
  font-weight: 900;
}

.stats-empty {
  width: 100%;
  min-height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  padding: 1rem;
  text-align: center;
}

.stats-empty span {
  color: var(--muted);
  font-size: 0.78rem;
}

.stats-empty strong {
  color: var(--text);
  font-size: 1.1rem;
}

.stats-empty p {
  margin: 0;
  color: var(--accent-alt);
  font-size: 0.8rem;
}

.split-meter {
  display: flex;
  height: 0.72rem;
  overflow: hidden;
  background: var(--dark);
  border: 0.08rem solid var(--border);
  border-radius: 999rem;
}

.home-meter,
.away-meter {
  display: block;
  height: 100%;
}

.home-meter {
  background: var(--accent);
}

.away-meter {
  background: var(--accent-alt);
}

.stats-card--ribbon {
  flex-direction: column;
  border-radius: 1rem 1rem 0.5rem 0.5rem;
  background: #1239A7;
  border-color: #F5F1E8;
}

.stats-card--material {
  position: relative;
  isolation: isolate;
  box-shadow:
    0.42rem 0.42rem 0 #000000,
    0 0 0.75rem rgba(255, 255, 255, 0.1);
}

.stats-card--material::before,
.stats-card--material::after {
  position: absolute;
  inset: 0;
  pointer-events: none;
  content: '';
}

.stats-card--material::before {
  z-index: 2;
  background:
    linear-gradient(108deg, rgba(255, 255, 255, 0) 0 27%, rgba(255, 255, 255, 0.08) 37%, rgba(255, 255, 255, 0) 48%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.07), rgba(255, 255, 255, 0) 46%);
  mix-blend-mode: screen;
}

.stats-card--material::after {
  inset: 0.28rem;
  z-index: 2;
  border: 0.08rem solid rgba(255, 255, 255, 0.16);
  border-radius: inherit;
}

.stats-card--material > * {
  position: relative;
  z-index: 1;
}

.ribbon-strips {
  flex: 0 0 10%;
  display: flex;
  background: #F5F1E8;
}

.ribbon-strips span {
  flex: 1;
}

.ribbon-strips span:nth-child(1) {
  background: #C8102E;
}

.ribbon-strips span:nth-child(2) {
  background: #D4AF37;
}

.ribbon-strips span:nth-child(3) {
  background: #000000;
}

.ribbon-strips span:nth-child(4) {
  background: #F5F1E8;
}

.ribbon-strips span:nth-child(5) {
  background: #003478;
}

.ribbon-crest-row {
  flex: 0 0 24%;
  display: flex;
  align-items: center;
  justify-content: space-around;
  padding: 0 8%;
  background: #0B2D92;
}

.stats-card--material .ribbon-crest-row {
  background:
    radial-gradient(circle at 50% -18%, rgba(255, 255, 255, 0.12), rgba(255, 255, 255, 0) 44%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.07), rgba(255, 255, 255, 0) 58%),
    #0B2D92;
}

.ribbon-country-badge {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 4.65rem;
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: 50%;
  background: #F5F1E8;
  border: 0.2rem solid #F5F1E8;
  box-shadow:
    inset 0 0 0 0.16rem #D4AF37,
    0.16rem 0.16rem 0 #000000;
}

.ribbon-country-badge img {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.ribbon-country-badge b {
  position: relative;
  z-index: 1;
  color: #071866;
  font-size: 1rem;
}

.stats-card--material .ribbon-country-badge {
  box-shadow:
    inset 0 0 0 0.16rem rgba(212, 175, 55, 0.95),
    inset 0 0.7rem 1rem rgba(255, 255, 255, 0.12),
    inset 0 -0.7rem 1rem rgba(0, 0, 0, 0.14),
    0.16rem 0.16rem 0 #000000,
    0 0 0.55rem rgba(255, 255, 255, 0.1);
}

.stats-card--material .ribbon-country-badge::before {
  position: absolute;
  inset: 0.18rem;
  z-index: 2;
  display: block;
  pointer-events: none;
  border-radius: 50%;
  background: radial-gradient(circle at 32% 20%, rgba(255, 255, 255, 0.22), rgba(255, 255, 255, 0) 42%);
  content: '';
}

.ribbon-country-badge::after {
  position: absolute;
  left: 15%;
  top: 12%;
  width: 48%;
  height: 15%;
  display: block;
  background: rgba(255, 255, 255, 0.42);
  border-radius: 999rem;
  content: '';
  transform: rotate(-18deg);
}

.stats-card--material .ribbon-country-badge::after {
  z-index: 3;
  background: rgba(255, 255, 255, 0.16);
}

.stats-card--material .ribbon-country-badge img {
  z-index: 1;
}

.ribbon-crest-row span {
  font-size: 1rem;
}

.ribbon-team-row,
.ribbon-possession,
.ribbon-stat-list p {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.ribbon-team-row {
  flex: 0 0 14%;
  padding: 0 7%;
  background: #071866;
  border-top: 0.08rem solid #F5F1E8;
  border-bottom: 0.08rem solid #F5F1E8;
  font-size: 0.86rem;
}

.ribbon-team-row i {
  font-style: normal;
  color: #D4AF37;
  font-size: 0.76rem;
}

.ribbon-possession {
  flex: 0 0 17%;
  gap: 0.65rem;
  padding: 0 8%;
  background: #1239A7;
}

.ribbon-possession .split-meter {
  flex: 1;
}

.stats-card--material .ribbon-possession .split-meter {
  position: relative;
  box-shadow:
    inset 0 0.08rem 0 rgba(255, 255, 255, 0.18),
    inset 0 -0.08rem 0 rgba(0, 0, 0, 0.16);
}

.stats-card--material .ribbon-possession .split-meter::after {
  position: absolute;
  left: 0.18rem;
  right: 0.18rem;
  top: 0.14rem;
  height: 28%;
  pointer-events: none;
  border-radius: 999rem;
  background: rgba(255, 255, 255, 0.14);
  content: '';
}

.ribbon-stat-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  padding: 0.32rem 9% 0.52rem;
  background: #102E8D;
}

.ribbon-stat-list p {
  margin: 0;
  font-size: 0.9rem;
}

.stats-card--material .ribbon-stat-list p {
  min-height: 1.9rem;
  padding: 0 0.7rem;
  border: 0.06rem solid rgba(255, 255, 255, 0.12);
  border-radius: 0.5rem;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0) 48%),
    rgba(7, 24, 102, 0.24);
  box-shadow: inset 0 -0.06rem 0 rgba(0, 0, 0, 0.12);
}

.ribbon-stat-list span {
  color: #DCE6FF;
}

.stats-card--dial {
  flex-direction: column;
  border-radius: 2.2rem 2.2rem 0.8rem 0.8rem;
  background: var(--dark);
  border-color: var(--accent-alt);
}

.dial-header {
  flex: 0 0 15%;
  display: flex;
  align-items: center;
  justify-content: space-around;
  background: var(--panel);
  color: #FFFFFF;
}

.dial-header b {
  width: 3rem;
  padding: 0.28rem 0;
  text-align: center;
  background: var(--text);
  color: var(--panel);
  border-radius: 999rem;
}

.dial-header span {
  color: var(--accent-alt);
  font-size: 0.78rem;
}

.dial-core {
  position: relative;
  flex: 0 0 42%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--dark);
}

.dial-team-crest {
  position: absolute;
  bottom: 0.52rem;
  z-index: 2;
  width: 3.5rem;
  aspect-ratio: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 0.16rem solid var(--border);
  border-radius: 50%;
  background: #FFFFFF;
  box-shadow:
    0.14rem 0.14rem 0 #000000,
    inset 0 0 0 0.08rem rgba(18, 5, 31, 0.12);
}

.dial-team-crest--home {
  left: 1.05rem;
}

.dial-team-crest--away {
  right: 1.05rem;
}

.dial-possession-value {
  position: absolute;
  bottom: 4.32rem;
  z-index: 2;
  width: 3.5rem;
  color: var(--text);
  font-size: 1.4rem;
  line-height: 1;
  text-align: center;
}

.dial-possession-value--home {
  left: 1.05rem;
}

.dial-possession-value--away {
  right: 1.05rem;
}

.dial-team-crest img {
  display: block;
  width: 76%;
  height: 76%;
  object-fit: contain;
}

.dial-team-crest b {
  color: var(--panel);
  font-size: 0.72rem;
  line-height: 1;
}

.dial-ring {
  width: 8.2rem;
  aspect-ratio: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: conic-gradient(var(--accent) 0deg 220deg, var(--accent-alt) 220deg 360deg);
  border: 0.38rem solid var(--text);
  box-shadow: 0.2rem 0.2rem 0 #000000;
}

.dial-ring span {
  padding: 0.12rem 0.5rem;
  background: var(--dark);
  border-radius: 999rem;
  font-size: 0.72rem;
}

.dial-tabbed-stats {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-rows: 2.05rem minmax(0, 1fr);
  overflow: hidden;
  background: var(--dark);
  border-top: 0.08rem solid rgba(4, 184, 217, 0.38);
}

.dial-stat-tabs {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  background: var(--panel);
  border-bottom: 0.08rem solid var(--accent-alt);
}

.dial-stat-tabs button {
  position: relative;
  min-width: 0;
  padding: 0.28rem 0.1rem;
  border: 0;
  border-right: 0.05rem solid rgba(242, 215, 255, 0.12);
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font: inherit;
  font-size: 0.62rem;
  font-weight: 950;
  letter-spacing: 0;
  white-space: nowrap;
}

.dial-stat-tabs button:last-child {
  border-right: 0;
}

.dial-stat-tabs button::after {
  position: absolute;
  left: 18%;
  right: 18%;
  bottom: 0;
  height: 0.16rem;
  background: var(--accent-alt);
  content: '';
  opacity: 0;
  transform: scaleX(0.4);
  transition: opacity 160ms ease, transform 160ms ease;
}

.dial-stat-tabs button.active {
  background: linear-gradient(180deg, rgba(233, 0, 82, 0.34), rgba(50, 16, 90, 0.12));
  color: var(--text);
}

.dial-stat-tabs button.active::after {
  opacity: 1;
  transform: scaleX(1);
}

.dial-stat-tabs button:focus-visible {
  z-index: 2;
  outline: 0.12rem solid var(--accent-alt);
  outline-offset: -0.12rem;
}

.dial-stat-viewport {
  position: relative;
  min-height: 0;
  overflow: hidden;
  touch-action: pan-y;
  user-select: none;
}

.dial-stat-grid {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.38rem;
  padding: 0.48rem;
}

.dial-stat-metric {
  position: relative;
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(2.8rem, 1fr) auto;
  gap: 0.24rem;
  padding: 0.38rem 0.32rem;
  overflow: hidden;
  background:
    linear-gradient(145deg, rgba(242, 215, 255, 0.11), rgba(18, 5, 31, 0.14)),
    var(--panel);
  border: 0.07rem solid rgba(4, 184, 217, 0.62);
  border-radius: 0.42rem;
  box-shadow: inset 0 -0.08rem 0 rgba(0, 0, 0, 0.18);
}

.dial-stat-metric > span {
  min-width: 0;
  overflow: hidden;
  color: var(--muted);
  font-size: 0.64rem;
  font-weight: 950;
  line-height: 1;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dial-stat-bars {
  min-height: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: end;
  gap: 0.34rem;
  padding: 0.08rem 0.12rem 0;
}

.dial-stat-bar {
  position: relative;
  height: 100%;
  min-height: 2.8rem;
  display: block;
  overflow: hidden;
  background: rgba(242, 215, 255, 0.1);
  box-shadow: inset 0 0 0 0.04rem rgba(242, 215, 255, 0.16);
}

.dial-stat-bar::before {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  transform-origin: bottom;
  animation: dial-stat-bar-fill 480ms cubic-bezier(0.16, 1, 0.3, 1) both;
  content: '';
}

.dial-stat-metric:nth-child(2) .dial-stat-bar::before {
  animation-delay: 55ms;
}

.dial-stat-metric:nth-child(3) .dial-stat-bar::before {
  animation-delay: 110ms;
}

@keyframes dial-stat-bar-fill {
  from {
    transform: scaleY(0);
  }

  to {
    transform: scaleY(1);
  }
}

.dial-stat-bar--home::before {
  height: var(--dial-home-pct);
  background: var(--accent-alt);
}

.dial-stat-bar--away::before {
  height: var(--dial-away-pct);
  background: var(--accent);
}

.dial-stat-score {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.24rem;
}

.dial-stat-score b {
  min-width: 0;
  overflow: hidden;
  color: var(--text);
  font-size: 0.84rem;
  font-weight: 950;
  line-height: 1;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dial-stat-score b:first-child {
  color: var(--accent-alt);
}

.dial-stat-score b:last-child {
  color: #FFFFFF;
  text-shadow: 0 0 0.32rem rgba(233, 0, 82, 0.76);
}

.dial-ai-review {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 0.34rem;
  padding: 0.46rem;
  background: var(--dark);
}

.dial-ai-review header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.4rem;
}

.dial-ai-review header span {
  color: var(--accent-alt);
  font-size: 0.62rem;
  font-weight: 950;
  letter-spacing: 0.08em;
}

.dial-ai-review header button {
  padding: 0.22rem 0.4rem;
  border: 0.06rem solid var(--accent-alt);
  background: var(--panel);
  color: var(--muted);
  cursor: pointer;
  font: inherit;
  font-size: 0.58rem;
  font-weight: 950;
  letter-spacing: 0;
}

.dial-ai-review header button:disabled {
  cursor: not-allowed;
  opacity: 0.46;
}

.dial-ai-review-body {
  min-height: 0;
  padding: 0.42rem 0.5rem;
  overflow-y: auto;
  background:
    linear-gradient(135deg, rgba(233, 0, 82, 0.12), rgba(4, 184, 217, 0.08)),
    var(--panel);
  border: 0.07rem solid rgba(4, 184, 217, 0.52);
  border-radius: 0.42rem;
}

.dial-ai-review-action {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.42rem;
  text-align: center;
}

.dial-ai-review-action button {
  min-width: 8.2rem;
  padding: 0.5rem 0.68rem;
  border: 0.08rem solid var(--accent-alt);
  border-radius: 0.34rem;
  background: var(--panel);
  box-shadow: inset 0 -0.1rem 0 rgba(0, 0, 0, 0.2);
  color: var(--text);
  cursor: pointer;
  font: inherit;
  font-size: 0.68rem;
  font-weight: 950;
}

.dial-ai-review-action button:hover,
.dial-ai-review-action button:focus-visible {
  background: var(--accent-alt);
  color: var(--dark);
  outline: none;
}

.dial-ai-review-action button:disabled {
  cursor: not-allowed;
  opacity: 0.46;
}

.dial-ai-review-body strong,
.dial-ai-review-body b,
.dial-ai-review-body p,
.dial-ai-review-body small {
  display: block;
}

.dial-ai-review-body strong {
  color: var(--accent-alt);
  font-size: 0.72rem;
  line-height: 1.15;
}

.dial-ai-review-body b {
  margin-top: 0.26rem;
  color: var(--text);
  font-size: 0.72rem;
  line-height: 1.28;
}

.dial-ai-review-body p {
  margin: 0.34rem 0 0;
  color: var(--muted);
  font-size: 0.64rem;
  font-weight: 800;
  line-height: 1.42;
}

.dial-ai-review-body small {
  margin-top: 0.34rem;
  color: rgba(242, 215, 255, 0.64);
  font-size: 0.56rem;
  line-height: 1.3;
}

.dial-ai-review-body .dial-ai-review-muted {
  margin: 0;
  color: var(--muted);
}

.dial-stat-slide-enter-active,
.dial-stat-slide-leave-active {
  transition: opacity 170ms ease, transform 190ms cubic-bezier(0.16, 1, 0.3, 1);
}

.dial-stat-slide-enter-from {
  opacity: 0;
  transform: translateX(1.1rem);
}

.dial-stat-slide-leave-to {
  opacity: 0;
  transform: translateX(-1.1rem);
}

.dial-stat-viewport[data-transition-direction='prev'] .dial-stat-slide-enter-from {
  transform: translateX(-1.1rem);
}

.dial-stat-viewport[data-transition-direction='prev'] .dial-stat-slide-leave-to {
  transform: translateX(1.1rem);
}

@media (prefers-reduced-motion: reduce) {
  .dial-stat-bar::before {
    animation: none;
  }

  .dial-stat-tabs button::after,
  .dial-stat-slide-enter-active,
  .dial-stat-slide-leave-active {
    transition: none;
  }
}

.stats-card--matrix {
  flex-direction: column;
  padding: 0.65rem;
  background: #E9EEFF;
  color: #010056;
  border-color: #F1F4FF;
  border-radius: 0.6rem;
}

.matrix-header {
  flex: 0 0 18%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0.65rem;
  background: #010056;
  color: #FFFFFF;
  border-radius: 0.45rem 0.45rem 0 0;
}

.matrix-header strong {
  color: #8CB2FF;
}

.matrix-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.5rem;
  padding-top: 0.55rem;
}

.matrix-cell {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0.62rem;
  background: #FFFFFF;
  border: 0.12rem solid #010056;
  border-radius: 0.45rem;
  box-shadow: 0.16rem 0.16rem 0 #315DFF;
}

.matrix-cell span {
  color: #315DFF;
  font-size: 0.78rem;
}

.matrix-cell p {
  margin: 0.35rem 0 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.matrix-cell b {
  font-size: 1.45rem;
}

.matrix-cell i {
  display: block;
  width: 0.28rem;
  height: 2.2rem;
  background: #9A00FF;
  border-radius: 999rem;
}

.matrix-footer {
  flex: 0 0 10%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #315DFF;
  font-size: 0.72rem;
}

.stats-card--timeline {
  flex-direction: column;
  padding: 0.7rem;
  background: #1A1A1A;
  border-color: #FFB000;
  border-radius: 0.2rem;
}

.timeline-header {
  flex: 0 0 16%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #FFFFFF;
  border-bottom: 0.12rem solid #FF6A00;
}

.timeline-header strong {
  color: #FFB000;
  font-size: 1.5rem;
}

.timeline-header span {
  color: #FFFFFF;
}

.timeline-lanes {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
}

.timeline-row {
  display: grid;
  grid-template-columns: 2.4rem 1fr 2.4rem;
  align-items: center;
  gap: 0.45rem;
}

.timeline-row b {
  font-size: 1rem;
  text-align: center;
}

.timeline-row div {
  position: relative;
  height: 2.05rem;
  background: #3C2A20;
  border: 0.08rem solid #FFB000;
  border-radius: 999rem;
  overflow: hidden;
}

.timeline-label {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 3;
  color: #FFFFFF;
  font-size: 0.72rem;
}

.timeline-home,
.timeline-away {
  position: absolute;
  top: 0;
  height: 50%;
  display: block;
}

.timeline-home {
  left: 0;
  background: #FF6A00;
}

.timeline-away {
  top: auto;
  bottom: 0;
  background: #FFB000;
}

.stats-card--ticket {
  border-radius: 0.75rem;
  background: var(--muted);
  border-color: var(--dark);
  color: var(--dark);
}

.ticket-stub {
  flex: 0 0 24%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1.3rem;
  background: var(--accent);
  border-right: 0.16rem dashed var(--dark);
  writing-mode: vertical-rl;
}

.ticket-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 0.7rem;
}

.ticket-main header,
.ticket-teams,
.ticket-stats p {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.ticket-main header {
  flex: 0 0 20%;
  color: #FFFFFF;
}

.ticket-main header b,
.ticket-main header strong {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 3rem;
  height: 2.2rem;
  background: var(--dark);
  border-radius: 0.4rem;
}

.ticket-main header strong {
  min-width: 5.4rem;
  background: var(--accent);
  font-size: 0.78rem;
}

.ticket-teams {
  flex: 0 0 12%;
  font-size: 0.72rem;
  border-bottom: 0.12rem solid var(--dark);
}

.ticket-stats {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
}

.ticket-stats p {
  margin: 0;
  font-size: 0.86rem;
}

.ticket-stats span {
  color: var(--panel);
}

.stats-card--lower {
  flex-direction: column;
  border-radius: 0.75rem;
  background: var(--dark);
  border-color: var(--accent-alt);
}

.lower-score {
  flex: 0 0 23%;
  display: grid;
  grid-template-columns: 1fr 1.2fr 1fr 0.9fr;
  align-items: center;
  min-height: 0;
  background: var(--accent);
  color: var(--text);
}

.lower-score b,
.lower-score strong,
.lower-score span {
  min-height: 100%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.lower-score strong {
  background: var(--panel);
  border-left: 0.08rem solid var(--border);
  border-right: 0.08rem solid var(--border);
  font-size: 1.35rem;
}

.lower-score span {
  background: var(--accent-alt);
  color: var(--dark);
  font-size: 0.82rem;
}

.lower-stack {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.45rem;
  padding: 0.72rem;
  background:
    linear-gradient(110deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0) 42%),
    var(--panel);
}

.lower-band {
  min-height: 2.55rem;
  display: grid;
  grid-template-columns: 1fr 1.7fr 1fr;
  align-items: center;
  padding: 0 0.7rem;
  border: 0.08rem solid var(--border);
  border-radius: 0.42rem;
  background: var(--dark);
}

.lower-band strong:last-child {
  text-align: right;
}

.lower-band span {
  color: var(--muted);
  text-align: center;
  font-size: 0.82rem;
}

.lower-possession {
  flex: 0 0 18%;
  display: grid;
  grid-template-columns: 3rem 1fr 3rem;
  align-items: center;
  gap: 0.55rem;
  padding: 0 0.75rem;
  background: var(--dark);
}

.lower-possession span {
  font-size: 0.86rem;
  text-align: center;
}

.stats-card--tower {
  flex-direction: column;
  border-radius: 1.05rem;
  background: var(--panel);
  border-color: var(--border);
}

.tower-header {
  flex: 0 0 34%;
  display: grid;
  grid-template-columns: 1fr 0.9fr 1fr;
  align-items: center;
  gap: 0.35rem;
  padding: 0.65rem;
  background: var(--dark);
  border-bottom: 0.16rem solid var(--accent-alt);
}

.tower-header div {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.35rem;
}

.tower-header b {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 3.2rem;
  aspect-ratio: 1;
  border-radius: 50%;
  background: var(--border);
  color: var(--dark);
}

.tower-header span {
  font-size: 0.72rem;
  text-align: center;
}

.tower-header strong {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 2.8rem;
  padding: 0 0.35rem;
  background: var(--panel);
  border: 0.12rem solid var(--accent-alt);
  border-radius: 0.35rem;
  color: var(--text);
  font-size: 0.68rem;
  text-align: center;
}

.tower-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  padding: 0.62rem 0.82rem;
  background: var(--panel);
}

.tower-feature {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.2rem;
  padding: 0.46rem;
  background: var(--dark);
  border: 0.1rem solid var(--border);
  border-radius: 0.42rem;
}

.tower-feature span {
  color: var(--accent-alt);
  font-size: 0.72rem;
}

.tower-feature strong {
  font-size: 1.22rem;
}

.tower-body p {
  margin: 0;
  display: grid;
  grid-template-columns: 1fr 1.5fr 1fr;
  align-items: center;
  font-size: 0.84rem;
}

.tower-body p span {
  color: var(--muted);
  text-align: center;
}

.tower-body p b:last-child {
  text-align: right;
}
</style>
