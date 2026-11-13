<script setup lang="ts">
/**
 * 독자용 경기 프리뷰 (MP-09).
 *
 * 이 화면이 보여주는 것은 **독자가 실제로 읽는 것**이다. 관리자 진단은 접힌 영역에서
 * 같은 실행의 별도 경로(`/preview/diagnostics`)로 연다. 그래서 이 화면은 진단 필드를
 * DOM에 렌더하지 않고, 카드를 만들어놓고 CSS로 숨기지도 않는다.
 *
 * 지키는 것:
 *
 * - 없는 보조 항목은 카드 자체를 만들지 않는다(빈 카드·누락 배너 금지).
 * - AI 예측에는 "AI 예측"이라는 표시와 판단 이유를 붙인다.
 * - 제공자 알고리즘 예측과 외부 매체 전망을 같은 종류로 그리지 않는다.
 * - 모의·재생 결과는 관리자 화면에서 실행 방식으로 표시한다. 본문 문장에는 넣지 않는다.
 * - 내부 ID·토큰·워크플로우 이름을 본문에 넣지 않는다(서버가 이미 지운 값을 다시 그리지 않음).
 */
import { computed, onMounted, ref, watch } from 'vue'
import { previewRunsApi } from '@/features/match-preview/api'
import GroundingSources from '@/features/match-preview/GroundingSources.vue'
import InlineEmphasis from './InlineEmphasis.vue'
import type {
  ReaderPreview,
  ReaderPreviewDiagnostics,
  ReaderPreviewOdds,
  ReaderPreviewOutlook,
} from '@/features/match-preview/types'

const props = defineProps<{
  /** 조회할 실행 ID. 없으면 저장된 결과를 열지 않는다. */
  runId: string
}>()

const loading = ref(true)
const errorMessage = ref<string | null>(null)
const preview = ref<ReaderPreview | null>(null)
const diagnostics = ref<ReaderPreviewDiagnostics | null>(null)
const diagnosticsOpen = ref(false)
const diagnosticsError = ref<string | null>(null)

const paragraphs = computed<string[]>(() => {
  const body = preview.value?.body ?? ''
  return body
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0)
})

/**
 * 구성본에서 온 섹션 본문(표시 순서). 있으면 본문 영역을 이 목록으로 그린다.
 * 옛 S1 응답에는 이 값이 없으므로 그때는 기존 단일 본문 표시를 그대로 쓴다.
 */
const sections = computed(() => preview.value?.sections ?? [])

/** 섹션 본문을 문단으로 나눈다(저장된 본문을 그대로 나눈다). */
function bodyParagraphs(body: string): string[] {
  return body
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0)
}

const watchPoints = computed(() => preview.value?.watch_points ?? [])
const players = computed(() => preview.value?.players_to_watch ?? [])
const outlookRows = computed<ReaderPreviewOutlook[]>(() => preview.value?.external_outlook ?? [])
const prediction = computed(() => preview.value?.ai_prediction ?? null)
const sources = computed(() => preview.value?.sources ?? [])
/**
 * 배당은 **선택 섹션**이다. 서버가 값을 내려줄 때만 표시하고, 없으면 카드 자체를
 * 만들지 않는다. 값이 빈 칸은 비워 두며 추정해 채우지 않는다.
 */
const oddsRows = computed<ReaderPreviewOdds[]>(() =>
  (preview.value?.odds ?? []).filter(
    (row) => Boolean(row.bookmaker) && Boolean(row.home || row.draw || row.away),
  ),
)

const leanLabel = computed<string | null>(() => {
  const lean = prediction.value?.lean
  if (lean === 'home') return '홈팀 우세'
  if (lean === 'draw') return '무승부'
  if (lean === 'away') return '원정팀 우세'
  return null
})

function isAlgorithmic(row: ReaderPreviewOutlook): boolean {
  return row.source_kind === 'api_prediction'
}

async function load(runId: string) {
  loading.value = true
  errorMessage.value = null
  diagnostics.value = null
  diagnosticsOpen.value = false
  if (!runId) {
    preview.value = null
    loading.value = false
    return
  }
  const result = await previewRunsApi.readerPreview(runId)
  loading.value = false
  if (!result.ok) {
    preview.value = null
    errorMessage.value = result.message
    return
  }
  preview.value = result.data
}

async function toggleDiagnostics() {
  if (!props.runId) return
  diagnosticsOpen.value = !diagnosticsOpen.value
  if (!diagnosticsOpen.value || diagnostics.value) return
  const result = await previewRunsApi.readerPreviewDiagnostics(props.runId)
  if (!result.ok) {
    diagnosticsError.value = result.message
    return
  }
  diagnostics.value = result.data
}

onMounted(() => load(props.runId))
watch(() => props.runId, (value) => load(value))
</script>

<template>
  <article class="preview" data-testid="match-preview">
    <p v-if="loading" class="preview__state" data-testid="preview-loading">프리뷰를 여는 중…</p>

    <div v-else-if="errorMessage" class="preview__notice" role="alert" data-testid="preview-error">
      <p class="preview__notice-title">프리뷰를 열 수 없습니다</p>
      <p>{{ errorMessage }}</p>
    </div>

    <template v-else-if="preview">
      <header class="preview__head">
        <p class="preview__fixture" data-testid="preview-fixture">
          {{ preview.fixture.label }}<template v-if="preview.fixture.league"> · {{ preview.fixture.league }}</template>
        </p>
        <h1 class="preview__headline" data-testid="preview-headline">{{ preview.headline }}</h1>
        <p class="preview__meta measured" data-testid="preview-meta">
          <span>생성 {{ preview.generated_at.slice(0, 16).replace('T', ' ') }}</span>
          <template v-if="preview.data_as_of">
            <span>자료 기준 {{ preview.data_as_of.slice(0, 16).replace('T', ' ') }}</span>
          </template>
        </p>
      </header>

      <!--
        새 정보 원문 묶음 경로의 **완성 본문**을 먼저 보여준다. 저장된 섹션 본문을 표시
        순서대로 그대로 낸다. 진단·수집 실패 사유는 여기 넣지 않는다(관리자 화면 몫).
      -->
      <div v-if="sections.length" class="preview__sections" data-testid="preview-sections">
        <section
          v-for="section in sections"
          :key="section.section_id"
          class="preview__section"
          data-testid="preview-section"
        >
          <h2 class="preview__title">{{ section.title }}</h2>
          <div class="preview__body">
            <p v-for="(paragraph, index) in bodyParagraphs(section.body)" :key="index">
              <InlineEmphasis :text="paragraph" />
            </p>
          </div>
          <ul v-if="section.sources?.length" class="preview__sources">
            <li v-for="(source, index) in section.sources" :key="index">
              <a v-if="source.url" :href="source.url" rel="noreferrer noopener" target="_blank">
                {{ source.label || source.url }}
              </a>
              <span v-else>{{ source.label }}</span>
            </li>
          </ul>
        </section>
      </div>

      <div v-else class="preview__body" data-testid="preview-body">
        <p v-for="(paragraph, index) in paragraphs" :key="index"><InlineEmphasis :text="paragraph" /></p>
      </div>

      <section v-if="!sections.length && watchPoints.length" class="preview__section" data-testid="preview-watch-points">
        <h2 class="preview__title">관전 포인트</h2>
        <ul class="preview__list">
          <li v-for="(point, index) in watchPoints" :key="index">{{ point }}</li>
        </ul>
      </section>

      <section v-if="!sections.length && players.length" class="preview__section" data-testid="preview-players">
        <h2 class="preview__title">주목할 선수</h2>
        <dl class="preview__players">
          <div v-for="(player, index) in players" :key="index" class="preview__player">
            <dt>
              {{ player.player }}
              <span v-if="player.team" class="preview__team">{{ player.team }}</span>
            </dt>
            <dd>{{ player.reason }}</dd>
          </div>
        </dl>
      </section>

      <section
        v-if="!sections.length && preview.absences_impact"
        class="preview__section"
        data-testid="preview-absences"
      >
        <h2 class="preview__title">결장과 전력 영향</h2>
        <p>{{ preview.absences_impact }}</p>
      </section>

      <section v-if="!sections.length && outlookRows.length" class="preview__section" data-testid="preview-outlook">
        <h2 class="preview__title">외부 전망</h2>
        <ul class="preview__outlook">
          <li v-for="(row, index) in outlookRows" :key="index" class="preview__outlook-row">
            <p class="preview__publisher">
              {{ row.publisher }}
              <span v-if="isAlgorithmic(row)" class="preview__kind">알고리즘 예측</span>
              <span v-if="row.published_at" class="measured preview__stamp">{{ row.published_at }}</span>
            </p>
            <p class="preview__statement">{{ row.statement }}</p>
          </li>
        </ul>
      </section>

      <section v-if="!sections.length && oddsRows.length" class="preview__section" data-testid="preview-odds">
        <h2 class="preview__title">배당 (정규시간 1X2)</h2>
        <table class="preview__odds">
          <caption class="visually-hidden">사이트별 정규시간 홈승·무승부·원정승 배당</caption>
          <thead>
            <tr>
              <th scope="col">사이트</th>
              <th scope="col">홈</th>
              <th scope="col">무</th>
              <th scope="col">원정</th>
              <th scope="col">수집</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in oddsRows" :key="`${row.bookmaker}-${index}`" data-testid="preview-odds-row">
              <th scope="row">{{ row.bookmaker }}</th>
              <td class="measured">{{ row.home ?? '—' }}</td>
              <td class="measured">{{ row.draw ?? '—' }}</td>
              <td class="measured">{{ row.away ?? '—' }}</td>
              <td class="measured preview__stamp">{{ row.observed_at ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section v-if="!sections.length && prediction" class="preview__section preview__forecast" data-testid="preview-forecast">
        <h2 class="preview__title">{{ preview.attribution.ai_forecast_label }}</h2>
        <p class="preview__forecast-lead">
          <span v-if="leanLabel">{{ leanLabel }}</span>
          <span v-if="prediction.score" class="measured preview__score">
            예상 스코어 {{ prediction.score }}
          </span>
        </p>
        <p class="preview__note">{{ preview.attribution.ai_forecast_note }}</p>
        <ul v-if="prediction.reasoning?.length" class="preview__list" data-testid="preview-reasoning">
          <li v-for="(reason, index) in prediction.reasoning" :key="index"><InlineEmphasis :text="reason" /></li>
        </ul>
        <p v-if="prediction.note" class="preview__note">{{ prediction.note }}</p>
      </section>

      <GroundingSources :sources="sources" />

      <details class="preview__diagnostics" data-testid="preview-diagnostics">
        <summary class="preview__summary" data-testid="preview-diagnostics-toggle" @click.prevent="toggleDiagnostics">
          관리자 진단 보기
        </summary>
        <div v-if="diagnosticsOpen" class="preview__diagnostics-body">
          <p class="preview__note">
            아래는 관리자용 진단이며 독자용 본문에 포함되지 않습니다.
          </p>
          <p v-if="diagnosticsError" class="preview__notice" role="alert" data-testid="preview-diagnostics-error">
            {{ diagnosticsError }}
          </p>
          <template v-else-if="diagnostics">
            <dl class="preview__facts measured">
              <dt>실행 방식</dt>
              <dd data-testid="preview-diagnostics-mode">{{ diagnostics.mode.label }}</dd>
              <dt>실행 상태 / 품질</dt>
              <dd>{{ diagnostics.quality.run }} / {{ diagnostics.quality.section ?? '—' }}</dd>
              <dt>종합 버전</dt>
              <dd>
                <span>{{ diagnostics.synthesis_versions.implementation }}</span>
                <span class="preview__inline-sep">{{ diagnostics.synthesis_versions.prompt }}</span>
              </dd>
            </dl>

            <h3 class="preview__subtitle">선택한 입력 버전</h3>
            <ul class="preview__list measured" data-testid="preview-diagnostics-inputs">
              <li v-for="row in diagnostics.selected_inputs" :key="row.result_id" class="preview__input-row">
                <span class="preview__input-module">{{ row.module_id }}</span>
                <span>v{{ row.version }}</span>
                <span>{{ row.implementation_version }}</span>
                <span class="preview__input-counts">
                  채택 {{ row.adopted_claim_count }}건, 제외 {{ row.excluded_claim_count }}건
                </span>
              </li>
            </ul>

            <template v-if="diagnostics.gaps.length">
              <h3 class="preview__subtitle">자료 공백</h3>
              <ul class="preview__list measured" data-testid="preview-diagnostics-gaps">
                <li v-for="(gap, index) in diagnostics.gaps" :key="index" class="preview__input-row">
                  <span class="preview__input-module">{{ gap.module_id }}</span>
                  <span>{{ gap.reason }}</span>
                </li>
              </ul>
            </template>

            <template v-if="diagnostics.diagnostics.length">
              <h3 class="preview__subtitle">검증·조정 기록</h3>
              <ul class="preview__list measured">
                <li v-for="(note, index) in diagnostics.diagnostics" :key="index">{{ note }}</li>
              </ul>
            </template>
          </template>
          <p v-else class="preview__note">진단을 불러오는 중…</p>
        </div>
      </details>
    </template>
  </article>
</template>

<style scoped>
.preview {
  max-width: var(--measure);
  margin: 0 auto;
  padding: var(--space-6) var(--space-4) var(--space-7);
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  color: var(--color-ink-2);
}

.preview__head {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.preview__fixture {
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.preview__headline {
  font-size: var(--text-display);
  letter-spacing: -0.03em;
  min-width: 0;
  overflow-wrap: break-word;
  max-width: 28ch;
}

.preview__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.preview__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  font-size: var(--text-lg);
  line-height: 1.65;
}

.preview__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  border-top: var(--rule-hair) solid var(--color-rule);
  padding-top: var(--space-4);
}

.preview__title {
  font-size: var(--text-title);
  min-width: 0;
  overflow-wrap: break-word;
}

.preview__subtitle {
  font-size: var(--text-sm);
  color: var(--color-muted);
  margin-top: var(--space-3);
}

.preview__list {
  margin: 0;
  padding-left: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.preview__players {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.preview__player dt {
  color: var(--color-ink);
  font-weight: 500;
}

.preview__player dd {
  margin: var(--space-1) 0 0;
}

.preview__team {
  color: var(--color-muted);
  font-weight: 400;
  font-size: var(--text-sm);
  margin-left: var(--space-2);
}

.preview__outlook {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.preview__outlook-row {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.preview__publisher {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-2);
  color: var(--color-ink);
  font-weight: 500;
}

.preview__odds {
  width: 100%;
  border-collapse: collapse;
}

.preview__odds th,
.preview__odds td {
  text-align: left;
  padding: var(--space-1) var(--space-2);
  border-bottom: var(--rule-hair) solid var(--color-rule);
  font-weight: 400;
}

.preview__odds thead th {
  color: var(--color-muted);
  font-size: var(--text-sm);
}

.preview__kind {
  font-size: var(--text-sm);
  font-weight: 400;
  color: var(--color-cool);
}

.preview__stamp {
  color: var(--color-muted);
  font-weight: 400;
}

.preview__statement {
  color: var(--color-ink-2);
}

.preview__forecast {
  background: var(--color-paper-2);
  border: var(--rule-hair) solid var(--color-rule);
  border-radius: var(--radius-panel);
  padding: var(--space-4);
}

.preview__forecast-lead {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-3);
  font-size: var(--text-lg);
  color: var(--color-ink);
}

.preview__score {
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.preview__note {
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.preview__diagnostics {
  border-top: var(--rule-hair) solid var(--color-rule);
  padding-top: var(--space-3);
}

.preview__summary {
  cursor: pointer;
  color: var(--color-muted);
  font-size: var(--text-sm);
  list-style: none;
}

.preview__summary:hover {
  color: var(--color-ink);
}

.preview__summary:focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
  border-radius: 2px;
  color: var(--color-ink);
}

.preview__summary:active {
  color: var(--color-ink-2);
}

.preview__diagnostics-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-top: var(--space-3);
  font-size: var(--text-sm);
}

.preview__facts {
  display: grid;
  grid-template-columns: minmax(0, max-content) minmax(0, 1fr);
  gap: var(--space-1) var(--space-3);
  margin: 0;
}

.preview__facts dt {
  color: var(--color-muted);
}

.preview__facts dd {
  margin: 0;
  color: var(--color-ink-2);
}

.preview__input-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-2);
  border-bottom: var(--rule-hair) solid var(--color-rule);
  padding: var(--space-1) 0;
}

.preview__input-row:last-child {
  border-bottom: 0;
}

.preview__input-module {
  color: var(--color-ink);
  font-weight: 500;
}

.preview__input-counts {
  color: var(--color-muted);
}

.preview__inline-sep {
  margin-left: var(--space-2);
  color: var(--color-muted);
}

.preview__state {
  color: var(--color-muted);
  font-size: var(--text-sm);
}

.preview__notice {
  border: var(--rule-hair) solid var(--color-rule);
  border-left: 2px solid var(--color-bad);
  background: var(--color-bad-soft);
  border-radius: var(--radius-control);
  padding: var(--space-3);
  font-size: var(--text-sm);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.preview__notice-title {
  color: var(--color-ink);
  font-weight: 500;
}

@media (prefers-reduced-motion: reduce) {
  .preview * {
    transition: none !important;
    animation: none !important;
  }
}
</style>
