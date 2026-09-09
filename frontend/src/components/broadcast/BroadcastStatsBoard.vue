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

const fallbackPossession: StatItem = {
  label: '점유율',
  home: '50%',
  away: '50%',
  homePct: 50,
  awayPct: 50,
}
const possession = computed(() => {
  const received = props.stats.find((stat) => stat.label === '점유율')
  if (!received) return fallbackPossession
  if (numericStat(received.home) + numericStat(received.away) <= 0) return fallbackPossession
  return received
})
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

  const largestValue = Math.max(numericStat(metric.home), numericStat(metric.away))
  const dynamicMax = Math.max(1, Math.ceil(largestValue * 1.2))
  if (metric.label === 'xG') {
    return { kind: 'continuous', max: dynamicMax }
  }

  return {
    kind: 'count',
    max: dynamicMax,
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

function possessionRingStyle(metric: StatItem) {
  const awayPercent = Math.max(0, Math.min(100, metric.awayPct))
  return {
    '--dial-possession-away-angle': `${awayPercent * 3.6}deg`,
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

</script>

<template>
  <article
    class="stats-card stats-card--dial"
    :class="{ 'stats-card--material': materialRevision }"
    data-variant="dial"
    :data-league="league"
    data-testid="stats-card"
  >
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
      <div
        class="dial-ring"
        :style="possessionRingStyle(possession)"
        data-testid="stats-possession-ring"
      >
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

.stats-card--dial {
  --stats-type-scale: 1.3;
  --stats-label-scale: 1.6;
  --stats-label-color: var(--accent-alt);
  flex-direction: column;
  border-radius: 2.2rem 2.2rem 0.8rem 0.8rem;
  background: var(--dark);
  border-color: var(--border);
}

.stats-card--dial[data-league='world-cup-2026'] {
  --stats-label-color: var(--muted);
}

.dial-header {
  gap: 0.4rem;
  padding-inline: 0.6rem;
  flex: 0 0 15%;
  display: flex;
  align-items: center;
  justify-content: space-around;
  background: var(--panel);
  color: #FFFFFF;
}

.dial-header b {
  min-width: 3rem;
  padding: 0.28rem 0.4rem;
  text-align: center;
  background: var(--text);
  color: var(--panel);
  border-radius: 999rem;
  font-size: calc(1rem * var(--stats-type-scale));
}

.dial-header span {
  min-width: 0;
  text-align: center;
  color: var(--stats-label-color);
  font-size: calc(0.78rem * var(--stats-label-scale, var(--stats-type-scale)));
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
  width: 5.25rem;
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
    inset 0 0 0 0.08rem color-mix(in srgb, var(--dark) 12%, transparent);
}

.dial-team-crest--home {
  left: 1.05rem;
}

.dial-team-crest--away {
  right: 1.05rem;
}

.dial-possession-value {
  position: absolute;
  bottom: 6.07rem;
  z-index: 2;
  width: 5.25rem;
  color: var(--text);
  font-size: calc(1.4rem * var(--stats-type-scale));
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
  flex: 0 0 auto;
  width: 110%;
  height: 110%;
  max-width: none;
  object-fit: contain;
}

.dial-team-crest b {
  color: var(--panel);
  font-size: calc(0.72rem * var(--stats-type-scale));
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
  background: conic-gradient(
    var(--accent) 0deg var(--dial-possession-away-angle),
    var(--accent-alt) var(--dial-possession-away-angle) 360deg
  );
  border: 0.38rem solid var(--text);
  box-shadow: 0.2rem 0.2rem 0 #000000;
}

.dial-ring span {
  padding: 0.12rem 0.5rem;
  background: var(--dark);
  border-radius: 999rem;
  font-size: calc(0.72rem * var(--stats-type-scale));
}

.dial-tabbed-stats {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-rows: 2.05rem minmax(0, 1fr);
  overflow: hidden;
  background: var(--dark);
  border-top: 0.08rem solid color-mix(in srgb, var(--accent-alt) 38%, transparent);
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
  border-right: 0.05rem solid color-mix(in srgb, var(--muted) 12%, transparent);
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font: inherit;
  font-size: calc(0.62rem * var(--stats-label-scale, var(--stats-type-scale)));
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
  background: linear-gradient(180deg, color-mix(in srgb, var(--accent) 34%, transparent), color-mix(in srgb, var(--panel) 12%, transparent));
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
    linear-gradient(145deg, color-mix(in srgb, var(--muted) 11%, transparent), color-mix(in srgb, var(--dark) 14%, transparent)),
    var(--panel);
  border: 0.07rem solid color-mix(in srgb, var(--accent-alt) 62%, transparent);
  border-radius: 0.42rem;
  box-shadow: inset 0 -0.08rem 0 rgba(0, 0, 0, 0.18);
}

.dial-stat-metric > span {
  min-width: 0;
  overflow: hidden;
  color: var(--muted);
  font-size: calc(0.64rem * var(--stats-label-scale, var(--stats-type-scale)));
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
  background: color-mix(in srgb, var(--muted) 10%, transparent);
  box-shadow: inset 0 0 0 0.04rem color-mix(in srgb, var(--muted) 16%, transparent);
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
  font-size: calc(0.84rem * var(--stats-type-scale));
  font-weight: 950;
  line-height: 1;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dial-stat-score b:first-child {
  color: var(--stats-label-color);
}

.dial-stat-score b:last-child {
  color: #FFFFFF;
  text-shadow: 0 0 0.32rem color-mix(in srgb, var(--accent) 76%, transparent);
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
  color: var(--stats-label-color);
  font-size: calc(0.62rem * var(--stats-type-scale));
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
  font-size: calc(0.58rem * var(--stats-type-scale));
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
    linear-gradient(135deg, color-mix(in srgb, var(--accent) 12%, transparent), color-mix(in srgb, var(--accent-alt) 8%, transparent)),
    var(--panel);
  border: 0.07rem solid color-mix(in srgb, var(--accent-alt) 52%, transparent);
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
  font-size: calc(0.68rem * var(--stats-type-scale));
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
  color: var(--stats-label-color);
  font-size: calc(0.72rem * var(--stats-type-scale));
  line-height: 1.15;
}

.dial-ai-review-body b {
  margin-top: 0.26rem;
  color: var(--text);
  font-size: calc(0.72rem * var(--stats-type-scale));
  line-height: 1.28;
}

.dial-ai-review-body p {
  margin: 0.34rem 0 0;
  color: var(--muted);
  font-size: calc(0.64rem * var(--stats-type-scale));
  font-weight: 800;
  line-height: 1.42;
}

.dial-ai-review-body small {
  margin-top: 0.34rem;
  color: color-mix(in srgb, var(--muted) 64%, transparent);
  font-size: calc(0.56rem * var(--stats-type-scale));
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

</style>
