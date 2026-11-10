<script setup lang="ts">
/**
 * 운영 지표 화면 — MP-08.
 *
 * 관리자가 저장된 실행 기록만으로 완료율·모듈 성공률·자료 확보율·API 보완·429·재시도·
 * 처리 시간·사용량을 확인하고, 이상한 지표에서 해당 실행의 시도 기록으로 내려간다.
 *
 * 이 화면이 지키는 것:
 * - 기간·분모 범위·표본 수·환경·실행 방식을 항상 함께 보여준다.
 * - 기본 조회는 운영(prod)·실호출(live)이다. 개발·모의·재생은 필터를 켰을 때만 보이고,
 *   걸러낸 건수를 숨기지 않는다. 모의 기록을 운영 성공률로 읽을 수 없게 한다.
 * - 표본이 없으면 0%가 아니라 "표본 없음"이다. 제공자가 주지 않은 사용량·비용은
 *   0이 아니라 "미확인"으로 표시한다.
 * - 조회만 한다. 실행 생성·취소나 외부 호출을 하지 않는다.
 *
 * 실행 열기는 이 화면의 소유가 아니다. `select-run` 이벤트로 실행 ID를 넘기고,
 * 실제 라우팅은 공유 라우터 소유자(MP-04)가 연결한다.
 */
import { computed, onMounted, ref } from 'vue'
import {
  barPercent,
  formatCount,
  formatFraction,
  formatMs,
  formatRatio,
  previewMetricsApi,
  scopeLabel,
  type MetricRowPayload,
  type MetricsEnvironment,
  type MetricsMode,
  type MetricsResponse,
} from './metrics'

const emit = defineEmits<{ (event: 'select-run', runId: string): void }>()

const data = ref<MetricsResponse | null>(null)
const loading = ref(true)
const errorMessage = ref<string | null>(null)
const selectedRunId = ref<string | null>(null)
const drilldownFilter = ref<string | null>(null)

// 필터 상태. 기본값은 비어 있고, 서버가 운영·실호출 기본 조회를 적용한다.
const fromAt = ref('')
const toAt = ref('')
const environments = ref<MetricsEnvironment[]>([])
const modes = ref<MetricsMode[]>([])
const moduleIds = ref('')
const models = ref('')
const contractVersions = ref('')

const ENVIRONMENT_OPTIONS: { value: MetricsEnvironment; label: string }[] = [
  { value: 'prod', label: '운영 (prod)' },
  { value: 'dev', label: '개발 (dev)' },
  { value: 'test', label: '테스트 (test)' },
]

const MODE_OPTIONS: { value: MetricsMode; label: string }[] = [
  { value: 'live', label: '실호출 (live)' },
  { value: 'replay', label: '저장 응답 재생 (replay)' },
  { value: 'mock', label: '모의 (mock)' },
]

function toggle<T extends string>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((entry) => entry !== value) : [...list, value]
}

function toIso(local: string): string | undefined {
  if (!local) return undefined
  const parsed = new Date(local)
  return Number.isNaN(parsed.getTime()) ? undefined : parsed.toISOString()
}

async function load() {
  loading.value = true
  errorMessage.value = null
  const result = await previewMetricsApi.query({
    fromAt: toIso(fromAt.value),
    toAt: toIso(toAt.value),
    environments: environments.value,
    modes: modes.value,
    moduleIds: splitList(moduleIds.value),
    models: splitList(models.value),
    contractVersions: splitList(contractVersions.value),
  })
  loading.value = false
  if (!result.ok) {
    errorMessage.value = result.message
    return
  }
  data.value = result.data
  selectedRunId.value = null
  drilldownFilter.value = null
}

function splitList(raw: string): string[] {
  return raw
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean)
}

function resetFilters() {
  fromAt.value = ''
  toAt.value = ''
  environments.value = []
  modes.value = []
  moduleIds.value = ''
  models.value = ''
  contractVersions.value = ''
  void load()
}

onMounted(load)

const rows = computed<MetricRowPayload[]>(() => data.value?.rows ?? [])

/** 차트는 비율 지표만 그린다. 표본이 없는 행은 막대를 만들지 않는다(0%로 그리지 않는다). */
const chartRows = computed(() =>
  rows.value.filter((row) => row.denominator !== null && row.available && row.ratio !== null),
)

const drilldownRuns = computed(() => {
  if (!data.value) return []
  const allowed = drilldownFilter.value
    ? new Set(rows.value.find((row) => row.metric === drilldownFilter.value)?.detail_run_ids ?? [])
    : null
  const list = allowed
    ? data.value.runs.filter((run) => allowed.has(run.run_id))
    : data.value.runs
  return list.slice(0, 20)
})

const selectedRun = computed(
  () => data.value?.runs.find((run) => run.run_id === selectedRunId.value) ?? null,
)

function drilldown(metric: string) {
  drilldownFilter.value = metric
  selectedRunId.value = null
}

/**
 * 실행 열기는 이 화면이 라우팅하지 않는다. 선택 상태만 여기서 관리하고, 실제 화면
 * 이동은 `select-run` 이벤트를 받은 공유 라우터 소유자가 연결한다.
 */
function openRun(runId: string) {
  selectedRunId.value = runId
  emit('select-run', runId)
}

function formatTime(value: string | null): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toISOString().replace('T', ' ').replace('.000Z', 'Z')
}
</script>

<template>
  <div class="metrics">
    <header class="metrics__head">
      <h2 class="metrics__title">운영 지표</h2>
      <p class="metrics__hint">
        저장된 실행·모듈 실행·시도 기록만 읽어 집계합니다. 이 화면은 외부 모델·API를 호출하지
        않습니다.
      </p>
    </header>

    <form class="filters" data-testid="metrics-filters" @submit.prevent="load">
      <div class="filters__grid">
        <label class="field">
          <span class="label">시작 시각</span>
          <input v-model="fromAt" class="input measured" type="datetime-local" data-testid="from-at" />
        </label>
        <label class="field">
          <span class="label">종료 시각 (미포함)</span>
          <input v-model="toAt" class="input measured" type="datetime-local" data-testid="to-at" />
        </label>
        <label class="field">
          <span class="label">모듈 ID (쉼표 구분)</span>
          <input v-model="moduleIds" class="input measured" placeholder="예: R1,R2" data-testid="module-ids" />
        </label>
        <label class="field">
          <span class="label">모델 (쉼표 구분)</span>
          <input v-model="models" class="input measured" placeholder="예: gemini-3.8-flash" data-testid="models" />
        </label>
        <label class="field">
          <span class="label">계약 버전 (쉼표 구분)</span>
          <input
            v-model="contractVersions"
            class="input measured"
            placeholder="예: mp02-1"
            data-testid="contract-versions"
          />
        </label>
      </div>

      <div class="filters__row">
        <fieldset class="toggles">
          <legend class="label">환경</legend>
          <button
            v-for="option in ENVIRONMENT_OPTIONS"
            :key="option.value"
            class="toggle"
            :class="{ 'toggle--on': environments.includes(option.value) }"
            :aria-pressed="environments.includes(option.value)"
            type="button"
            :data-testid="`env-${option.value}`"
            @click="environments = toggle(environments, option.value)"
          >
            {{ option.label }}
          </button>
        </fieldset>
        <fieldset class="toggles">
          <legend class="label">실행 방식</legend>
          <button
            v-for="option in MODE_OPTIONS"
            :key="option.value"
            class="toggle"
            :class="{ 'toggle--on': modes.includes(option.value) }"
            :aria-pressed="modes.includes(option.value)"
            type="button"
            :data-testid="`mode-${option.value}`"
            @click="modes = toggle(modes, option.value)"
          >
            {{ option.label }}
          </button>
        </fieldset>
      </div>

      <div class="filters__actions">
        <button class="button" type="submit" :disabled="loading" data-testid="apply-filters">
          {{ loading ? '집계 중…' : '지표 조회' }}
        </button>
        <button class="button button--quiet" type="button" :disabled="loading" @click="resetFilters">
          기본 조회로 되돌리기
        </button>
        <p class="filters__note">필터를 비우면 운영(prod)·실호출(live) 기록만 집계합니다.</p>
      </div>
    </form>

    <p v-if="errorMessage" class="notice notice--error" role="alert" data-testid="metrics-error">
      {{ errorMessage }}
      <button class="button button--quiet" type="button" @click="load">다시 시도</button>
    </p>

    <div v-else-if="loading" class="skeleton" aria-busy="true" aria-live="polite" data-testid="metrics-loading">
      <span class="visually-hidden">지표를 집계하는 중입니다.</span>
      <div class="skeleton__row" />
      <div class="skeleton__row" />
      <div class="skeleton__row" />
    </div>

    <template v-else-if="data">
      <p class="period" data-testid="metrics-window">
        집계 기간 <span class="measured">{{ formatTime(data.window.from_at) }}</span> ~
        <span class="measured">{{ formatTime(data.window.to_at) }}</span>
        <span class="period__badge">
          {{ data.window.source === 'default' ? '기본 기간' : '지정 기간' }} /
          {{ data.window.days }}일
        </span>
      </p>

      <p class="filters-summary" data-testid="metrics-filter-summary">
        환경 <span class="measured">{{ data.filters.environments.join(', ') || '지정 없음' }}</span>
        · 실행 방식
        <span class="measured">{{ data.filters.modes.join(', ') || '지정 없음' }}</span>
        <span v-if="data.filters.defaulted_environments" class="filters-summary__badge">
          기본값(운영·실호출) 적용
        </span>
      </p>

      <p class="notice notice--info" data-testid="metrics-excluded">
        {{ data.filters.note }}
        기간 안에서 환경 기준으로 {{ data.excluded.by_environment }}건, 실행 방식 기준으로
        {{ data.excluded.by_mode }}건을 이 조회에서 제외했습니다. 경기 목록 수집
        {{ data.excluded.fixture_catalog_runs }}건은 프리뷰 완료율에 넣지 않았습니다.
        <span v-if="data.excluded.duplicate_events_dropped > 0">
          중복 수신 {{ data.excluded.duplicate_events_dropped }}건은 한 번만 셌습니다.
        </span>
      </p>

      <div v-if="data.empty" class="empty" data-testid="metrics-empty">
        <p class="empty__title">이 기간에 집계할 실행 기록이 없습니다.</p>
        <p class="empty__body">
          0%가 아니라 표본이 없다는 뜻입니다. 기간을 넓히거나, 개발·모의 기록을 보려면 환경·실행
          방식 필터를 직접 켜세요. 모의 기록을 운영 성공률로 표시하지 않습니다.
        </p>
      </div>

      <template v-else>
        <table class="table metrics-table" data-testid="metrics-table">
          <caption>
            지표 {{ rows.length }}개 · 분자/분모와 표본 수를 함께 표시합니다. 행을 누르면 해당 실행으로
            내려갑니다.
          </caption>
          <thead>
            <tr>
              <th scope="col">지표</th>
              <th scope="col">값</th>
              <th scope="col">분자 / 분모</th>
              <th scope="col">표본</th>
              <th scope="col">분모 범위</th>
              <th scope="col"><span class="visually-hidden">내려가기</span></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in rows"
              :key="row.metric"
              :data-testid="`metric-${row.metric}`"
              :class="{ 'row--muted': !row.available }"
            >
              <td>
                <span class="metric-label">{{ row.label }}</span>
                <span class="metric-id measured">{{ row.metric }}</span>
              </td>
              <td class="measured metric-value">{{ formatRatio(row) }}</td>
              <td class="measured">{{ formatFraction(row) }}</td>
              <td class="measured">{{ row.available ? row.sample_size : 0 }}</td>
              <td class="metric-scope">{{ scopeLabel(row.scope) }}</td>
              <td>
                <button
                  v-if="row.detail_run_ids.length > 0"
                  class="button button--quiet"
                  type="button"
                  :data-testid="`drilldown-${row.metric}`"
                  @click="drilldown(row.metric)"
                >
                  실행 {{ row.detail_run_ids.length }}건
                </button>
                <span v-else class="metric-scope">내려갈 실행 없음</span>
              </td>
            </tr>
          </tbody>
        </table>

        <section class="chart" aria-labelledby="chart-title" data-testid="metrics-chart">
          <h3 id="chart-title" class="chart__title">비율 비교</h3>
          <p class="chart__hint">
            막대는 분자/분모 비율입니다. 표본이 없는 지표는 막대를 그리지 않습니다(0%가 아님).
          </p>
          <ul class="bars">
            <li v-for="row in chartRows" :key="row.metric" class="bars__row">
              <span class="bars__label">{{ row.label }}</span>
              <span class="bars__track" aria-hidden="true">
                <span
                  v-if="barPercent(row) !== null"
                  class="bars__fill"
                  :class="{ 'bars__fill--bad': row.metric.includes('429') || row.metric.includes('retry') }"
                  :style="{ width: `${barPercent(row)}%` }"
                />
              </span>
              <span class="bars__value measured">
                {{ formatRatio(row) }}
                <span class="bars__sample">({{ formatFraction(row) }})</span>
              </span>
            </li>
          </ul>
        </section>

        <section class="panel metrics-side" aria-labelledby="timing-title">
          <h3 id="timing-title" class="chart__title">처리 시간</h3>
          <table class="table">
            <caption>표본 수와 함께 표시합니다. 표본이 적으면 일반 성능으로 단정하지 않습니다.</caption>
            <tbody>
              <tr>
                <th scope="row">{{ data.timings.run_wall_clock.label }}</th>
                <td class="measured">중앙값 {{ formatMs(data.timings.run_wall_clock.median_ms) }}</td>
                <td class="measured">95백분위 {{ formatMs(data.timings.run_wall_clock.p95_ms) }}</td>
                <td class="measured">표본 {{ data.timings.run_wall_clock.sample_size }}</td>
              </tr>
              <tr>
                <th scope="row">{{ data.timings.attempt_duration.label }}</th>
                <td class="measured">중앙값 {{ formatMs(data.timings.attempt_duration.median_ms) }}</td>
                <td class="measured">95백분위 {{ formatMs(data.timings.attempt_duration.p95_ms) }}</td>
                <td class="measured">표본 {{ data.timings.attempt_duration.sample_size }}</td>
              </tr>
              <tr>
                <th scope="row">재시도 대기 합계</th>
                <td class="measured">{{ formatMs(data.timings.wait_total_ms) }}</td>
                <td colspan="2" class="measured">표본 {{ data.timings.wait_samples }} · {{ data.timings.wait_note }}</td>
              </tr>
            </tbody>
          </table>

          <h3 class="chart__title">사용량</h3>
          <dl class="usage" data-testid="metrics-usage">
            <div class="usage__item">
              <dt>입력 토큰</dt>
              <dd class="measured">{{ formatCount(data.usage.input_tokens) }}</dd>
            </div>
            <div class="usage__item">
              <dt>출력 토큰</dt>
              <dd class="measured">{{ formatCount(data.usage.output_tokens) }}</dd>
            </div>
            <div class="usage__item">
              <dt>검색 사용량</dt>
              <dd class="measured">{{ formatCount(data.usage.search_queries) }}</dd>
            </div>
            <div class="usage__item">
              <dt>비용</dt>
              <dd class="measured">{{ formatCount(data.usage.cost) }}</dd>
            </div>
          </dl>
          <p class="chart__hint" data-testid="metrics-usage-note">
            사용량이 보고된 시도 {{ data.usage.attempts_with_usage }} /
            {{ data.usage.attempts_total }} (누락 {{ data.usage.attempts_missing_usage }}건).
            {{ data.usage.note }} {{ data.usage.cost_note }}
          </p>
        </section>

        <section class="panel drilldown" aria-labelledby="drilldown-title" data-testid="metrics-drilldown">
          <header class="drilldown__head">
            <h3 id="drilldown-title" class="chart__title">
              내려갈 실행
              <span class="measured">{{ drilldownRuns.length }}건</span>
            </h3>
            <button
              v-if="drilldownFilter"
              class="button button--quiet"
              type="button"
              data-testid="clear-drilldown"
              @click="drilldownFilter = null"
            >
              지표 필터 해제
            </button>
          </header>
          <p class="chart__hint">
            조회 필터를 그대로 적용한 목록입니다. 실행을 열면 모듈별 요청·원문 응답·시도 기록을
            확인할 수 있습니다.
          </p>

          <ul v-if="drilldownRuns.length > 0" class="runs">
            <li v-for="run in drilldownRuns" :key="run.run_id" class="run">
              <button
                class="run__button"
                type="button"
                :data-testid="`open-run-${run.run_id}`"
                @click="openRun(run.run_id)"
              >
                <span class="measured run__id">{{ run.run_id.slice(0, 8) }}</span>
                <span class="chip" :class="{ 'chip--mock': run.mode !== 'live' }">
                  {{ run.mode === 'live' ? '실호출' : run.mode }}
                </span>
                <span class="measured">{{ run.environment }}</span>
                <span class="measured">{{ run.status }} / {{ run.quality }}</span>
                <span class="measured run__time">{{ formatTime(run.requested_at) }}</span>
              </button>
              <span class="run__attempts measured">시도 {{ run.modules.reduce((n, m) => n + m.attempts.length, 0) }}건</span>
            </li>
          </ul>
          <p v-else class="chart__hint">내려갈 실행이 없습니다.</p>

          <div v-if="selectedRun" class="run-detail" data-testid="metrics-run-detail">
            <h4 class="chart__title">선택한 실행 {{ selectedRun.run_id.slice(0, 8) }}</h4>
            <table class="table">
              <caption>모듈 실행과 실제 시도. 실패한 시도도 지우지 않고 그대로 보여줍니다.</caption>
              <thead>
                <tr>
                  <th scope="col">모듈</th>
                  <th scope="col">상태</th>
                  <th scope="col">시도</th>
                  <th scope="col">HTTP</th>
                  <th scope="col">사용량</th>
                </tr>
              </thead>
              <tbody>
                <template v-for="module in selectedRun.modules" :key="module.module_execution_id">
                  <tr v-for="attempt in module.attempts" :key="attempt.attempt_id">
                    <td class="measured">{{ module.module_id }}</td>
                    <td class="measured">{{ attempt.outcome }}</td>
                    <td class="measured">{{ attempt.attempt_ordinal + 1 }}</td>
                    <td class="measured">{{ attempt.http_status ?? '—' }}</td>
                    <td class="measured">{{ attempt.usage_reported ? '보고됨' : '미확인' }}</td>
                  </tr>
                  <tr v-if="module.attempts.length === 0">
                    <td class="measured">{{ module.module_id }}</td>
                    <td class="measured">{{ module.status }}</td>
                    <td colspan="3" class="measured">저장된 시도가 없습니다.</td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </section>
      </template>

      <ul class="notes" data-testid="metrics-notes">
        <li v-for="note in data.notes" :key="note">{{ note }}</li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.metrics {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.metrics__head {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.metrics__title {
  font-size: var(--text-title);
}

.metrics__hint,
.filters__note,
.chart__hint {
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.filters {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-4);
  border: var(--rule-hair) solid var(--color-rule);
  border-radius: var(--radius-panel);
  background: var(--color-paper-2);
}

.filters__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: var(--space-3);
}

.filters__row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-5);
}

.filters__actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.toggles {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  border: 0;
  padding: 0;
  margin: 0;
}

.toggles legend {
  padding: 0;
  margin-bottom: 0;
  margin-right: var(--space-2);
}

.toggle {
  min-height: 32px;
  padding: var(--space-1) var(--space-3);
  border: var(--rule-hair) solid var(--color-rule-2);
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--color-ink-2);
  font-family: var(--font-body);
  font-size: var(--text-sm);
  cursor: pointer;
}

.toggle--on {
  border-color: var(--color-accent);
  color: var(--color-accent);
  background: var(--color-accent-soft);
}

.period,
.filters-summary {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.period__badge,
.filters-summary__badge {
  padding: 0 var(--space-2);
  border: var(--rule-hair) solid var(--color-rule-2);
  border-radius: var(--radius-control);
  color: var(--color-ink-2);
}

.metrics-table .row--muted {
  color: var(--color-muted);
}

.metric-label {
  display: block;
  color: var(--color-ink);
}

.metric-id,
.metric-scope {
  display: block;
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.metric-value {
  color: var(--color-ink);
}

.chart {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-4);
  border: var(--rule-hair) solid var(--color-rule);
  border-radius: var(--radius-panel);
  background: var(--color-paper-2);
}

.chart__title {
  font-size: var(--text-lg);
}

.bars {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.bars__row {
  display: grid;
  grid-template-columns: minmax(10rem, 16rem) 1fr auto;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--text-sm);
}

.bars__label {
  color: var(--color-ink-2);
}

.bars__track {
  height: 10px;
  border-radius: 999px;
  background: var(--color-paper-3);
  border: var(--rule-hair) solid var(--color-rule);
  overflow: hidden;
}

.bars__fill {
  display: block;
  height: 100%;
  background: var(--color-accent);
}

.bars__fill--bad {
  background: var(--color-cool);
}

.bars__value {
  color: var(--color-ink);
  white-space: nowrap;
}

.bars__sample {
  color: var(--color-muted);
}

.metrics-side {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.usage {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
  gap: var(--space-3);
  margin: 0;
}

.usage__item dt {
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.usage__item dd {
  margin: 0;
  font-size: var(--text-lg);
  color: var(--color-ink);
}

.drilldown {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.drilldown__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.runs {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.run {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  border-bottom: var(--rule-hair) solid var(--color-rule);
}

.run__button {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex: 1;
  min-height: 34px;
  padding: var(--space-1) 0;
  border: 0;
  background: transparent;
  color: var(--color-ink-2);
  font-family: var(--font-body);
  font-size: var(--text-sm);
  text-align: left;
  cursor: pointer;
}

.run__button:hover {
  color: var(--color-ink);
}

.run__id {
  color: var(--color-accent);
}

.run__time,
.run__attempts {
  color: var(--color-muted);
  white-space: nowrap;
}

.chip {
  font-size: var(--text-sm);
  padding: 0 var(--space-2);
  border-radius: var(--radius-control);
  border: var(--rule-hair) solid var(--color-rule-2);
  color: var(--color-ink-2);
  white-space: nowrap;
}

.chip--mock {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.run-detail {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-top: var(--space-3);
}

.notes {
  margin: 0;
  padding-left: var(--space-4);
  font-size: var(--text-sm);
  color: var(--color-muted);
}

@media (max-width: 40rem) {
  .bars__row {
    grid-template-columns: 1fr;
  }
}
</style>
