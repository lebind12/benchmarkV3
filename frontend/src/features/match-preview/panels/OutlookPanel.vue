<script lang="ts">
/**
 * R3 배당·외부 전망 결과 화면의 자료형 (MP-07).
 *
 * 서버 `OutlookResearch.to_dict()`와 같은 이름을 쓴다. 공통 `types.ts`는 MP-05
 * 소유이므로 이 모양은 여기서만 정의하고, 필요한 등록은 통합 담당자에게 요청한다.
 */
export type OutlookMode = 'live' | 'replay' | 'mock'

export interface OutlookOddsView {
  claim_id: string
  bookmaker: string | null
  market: string | null
  observed_at: string | null
  home: string | null
  draw: string | null
  away: string | null
  fixture_id: number | null
  adopted: boolean
  rejection_reason: string | null
}

export interface OutlookMediaView {
  claim_id: string
  publisher: string | null
  url: string
  published_at: string | null
  statement: string
  predicted_score: string | null
  source_confirmed: boolean
  adopted: boolean
  rejection_reason: string | null
}

export interface OutlookApiPredictionView {
  claim_id: string
  provider: string
  winner_name: string | null
  advice: string | null
  under_over: string | null
  percent_home: string | null
  percent_draw: string | null
  percent_away: string | null
}

export interface OutlookGroundingView {
  present: boolean
  web_search_queries: string[]
  chunk_uris: string[]
  chunk_titles: string[]
  search_suggestions_html: string | null
  absence_reason: string | null
  missing_queries_note: string | null
}

export interface OutlookSourceView {
  label: string
  kind: 'bookmaker' | 'media' | 'api_prediction' | string
  url: string | null
  publisher: string | null
  published_at: string | null
  note: string | null
}

export interface OutlookCoverageView {
  topic: string
  state: string
  detail: string | null
}

export interface OutlookResultView {
  module_id: string
  implementation_version: string
  prompt_version: string
  mode: OutlookMode
  fixture: { fixture_id: number; league_id: number; season: number } | null
  odds: OutlookOddsView[]
  rejected_odds: OutlookOddsView[]
  media: OutlookMediaView[]
  rejected_media: OutlookMediaView[]
  api_prediction: OutlookApiPredictionView | null
  grounding: OutlookGroundingView
  coverage: OutlookCoverageView[]
  diagnostics: string[]
  quality: string
  model_name: string | null
  external_calls: number
  reader_body: string
  reader_sources: OutlookSourceView[]
}
</script>

<script setup lang="ts">
/**
 * R3 배당·외부 전망 패널 (MP-07).
 *
 * 이 화면은 **진단용 구성 요소**이며 승인 단위가 아니다. 승인 단위는 이 모듈을
 * 포함한 섹션 워크플로우의 결과 본문이다.
 *
 * 표시 원칙:
 *
 * - 독자용 본문을 먼저 보여준다. 누락·오류·재시도 안내는 그 본문에 넣지 않고
 *   아래 관리자 영역에만 둔다.
 * - 세 자료를 섞지 않는다. 경기 전 승무패 배당(업체·시장·기준 시각), 외부 매체
 *   전망(매체·URL·게시 시각), 제공자 알고리즘 예측(매체 의견 아님)을 각각 그린다.
 * - 검색 grounding 메타데이터와 그 부재 사유는 관리자 영역에 그대로 남긴다.
 * - 검증에서 제외된 자료는 채택 목록에 넣지 않고, 사유와 함께 접이식으로 보여준다.
 */
import { computed } from 'vue'

const props = defineProps<{
  result: OutlookResultView | null
  loading?: boolean
  errorMessage?: string | null
}>()

const readerBody = computed(() => (props.result?.reader_body ?? '').trim())
const odds = computed(() => props.result?.odds ?? [])
const media = computed(() => props.result?.media ?? [])
const apiPrediction = computed(() => props.result?.api_prediction ?? null)
const rejectedOdds = computed(() => props.result?.rejected_odds ?? [])
const rejectedMedia = computed(() => props.result?.rejected_media ?? [])
const coverage = computed(() => props.result?.coverage ?? [])
const diagnostics = computed(() => props.result?.diagnostics ?? [])
const grounding = computed(() => props.result?.grounding ?? null)
const sources = computed(() => props.result?.reader_sources ?? [])

const mediaSources = computed(() => sources.value.filter((item) => item.kind === 'media'))
const bookmakerSources = computed(() =>
  sources.value.filter((item) => item.kind === 'bookmaker'),
)
const apiSources = computed(() =>
  sources.value.filter((item) => item.kind === 'api_prediction'),
)

const groundingState = computed(() => {
  const current = grounding.value
  if (!current) return '기록 없음'
  if (!current.present) return '메타데이터 없음'
  if (current.chunk_uris.length === 0) return '출처 목록 비어 있음'
  return `출처 ${current.chunk_uris.length}건 · 검색 질의 ${current.web_search_queries.length}건`
})

const modeLabel = computed(() => {
  const mode = props.result?.mode
  if (!mode) return '실행 방식 미상'
  if (mode === 'live') return '실호출 (live)'
  if (mode === 'replay') return '저장 응답 재생 (replay, 외부 호출 없음)'
  return '모의 실행 (mock, 외부 호출 없음)'
})

const coverageLabelMap: Record<string, string> = {
  available: '확보',
  search_not_found: '검색 미발견',
  api_not_provided: '제공자 미제공',
  not_run: '실행 안 함',
  call_error: '호출 오류',
  validation_rejected: '검증 탈락',
  source_conflict: '출처 충돌',
  unknown: '알 수 없음',
}

function coverageLabel(state: string): string {
  return coverageLabelMap[state] ?? state
}

function sourceLabel(source: OutlookSourceView): string {
  if (source.kind === 'api_prediction') return '제공자 알고리즘 예측'
  if (source.kind === 'media') return '외부 매체'
  return '배당 업체'
}
</script>

<template>
  <section class="outlook-panel" data-testid="outlook-panel">
    <header class="outlook-panel__head">
      <h3>R3 배당·외부 전망</h3>
      <p class="hint">
        경기 전 승무패 배당, 외부 매체 전망, 제공자 알고리즘 예측을 구분해 보여줍니다.
        이 화면은 진단용이며 승인 단위는 섹션 워크플로우 결과입니다.
      </p>
    </header>

    <p v-if="loading" class="state">R3 결과를 읽는 중입니다.</p>
    <p v-else-if="errorMessage" class="state error" data-test="outlook-error">
      {{ errorMessage }}
    </p>
    <p v-else-if="!result" class="state" data-test="outlook-empty">
      아직 R3를 실행하지 않았습니다.
    </p>

    <template v-else>
      <dl class="summary">
        <div>
          <dt>실행 방식</dt>
          <dd data-test="outlook-mode">{{ modeLabel }}</dd>
        </div>
        <div>
          <dt>모델 호출</dt>
          <dd data-test="outlook-external-calls">{{ result.external_calls }}회</dd>
        </div>
        <div>
          <dt>품질</dt>
          <dd data-test="outlook-quality">{{ result.quality }}</dd>
        </div>
        <div>
          <dt>모델</dt>
          <dd>{{ result.model_name ?? '기록 없음' }}</dd>
        </div>
      </dl>

      <h4>독자용 본문</h4>
      <div v-if="readerBody" class="reader" data-test="outlook-reader-body">
        <pre>{{ readerBody }}</pre>
      </div>
      <p v-else class="state" data-test="outlook-no-reader-body">
        독자용 본문이 없습니다. 아래 자료 확보 상태와 내부 진단에서 사유를 확인하세요.
      </p>

      <h4>경기 전 승무패 배당 ({{ odds.length }}건)</h4>
      <table v-if="odds.length > 0" class="table" data-test="outlook-odds">
        <thead>
          <tr>
            <th>업체</th>
            <th>시장</th>
            <th>기준 시각</th>
            <th>홈</th>
            <th>무</th>
            <th>원정</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in odds" :key="row.claim_id">
            <td>{{ row.bookmaker ?? '업체 미상' }}</td>
            <td>{{ row.market ?? '시장 미상' }}</td>
            <td>{{ row.observed_at ?? '시각 미확인' }}</td>
            <td>{{ row.home ?? '미제공' }}</td>
            <td>{{ row.draw ?? '미제공' }}</td>
            <td>{{ row.away ?? '미제공' }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="state">채택한 승무패 배당이 없습니다.</p>

      <h4>외부 매체 전망 ({{ media.length }}건)</h4>
      <ul v-if="media.length > 0" class="media" data-test="outlook-media">
        <li v-for="row in media" :key="row.claim_id">
          <strong>{{ row.publisher ?? '매체 미상' }}</strong>
          <span class="muted"> · 게시 {{ row.published_at ?? '시각 미확인' }}</span>
          <div>{{ row.statement }}</div>
          <div v-if="row.predicted_score" class="muted">
            인용된 예상 스코어 {{ row.predicted_score }}
          </div>
          <a v-if="row.url" :href="row.url" target="_blank" rel="noopener noreferrer">
            {{ row.url }}
          </a>
        </li>
      </ul>
      <p v-else class="state">채택한 매체 전망이 없습니다.</p>

      <h4>제공자 알고리즘 예측</h4>
      <dl v-if="apiPrediction" class="api" data-test="outlook-api-prediction">
        <div>
          <dt>제공자</dt>
          <dd>{{ apiPrediction.provider }} (매체 의견 아님)</dd>
        </div>
        <div v-if="apiPrediction.winner_name">
          <dt>우세 팀</dt>
          <dd>{{ apiPrediction.winner_name }}</dd>
        </div>
        <div v-if="apiPrediction.percent_home">
          <dt>확률</dt>
          <dd>
            홈 {{ apiPrediction.percent_home }} · 무
            {{ apiPrediction.percent_draw ?? '미제공' }} · 원정
            {{ apiPrediction.percent_away ?? '미제공' }}
          </dd>
        </div>
        <div v-if="apiPrediction.advice">
          <dt>제공자 조언</dt>
          <dd>{{ apiPrediction.advice }}</dd>
        </div>
        <div v-if="apiPrediction.under_over">
          <dt>언더오버 기준</dt>
          <dd>{{ apiPrediction.under_over }}</dd>
        </div>
      </dl>
      <p v-else class="state">제공자 알고리즘 예측이 없습니다.</p>

      <h4>본문 근거 ({{ sources.length }}건)</h4>
      <ul v-if="sources.length > 0" class="sources" data-test="outlook-sources">
        <li v-for="source in sources" :key="source.kind + source.label">
          <span class="kind">{{ sourceLabel(source) }}</span>
          {{ source.label }}
          <a v-if="source.url" :href="source.url" target="_blank" rel="noopener noreferrer">
            {{ source.url }}
          </a>
          <span v-if="source.published_at" class="muted"> · {{ source.published_at }}</span>
        </li>
      </ul>
      <p v-else class="state">본문에 연결된 근거가 없습니다.</p>

      <details class="admin" data-test="outlook-admin">
        <summary>관리자 진단 (독자용 아님)</summary>

        <h5>Google Search grounding</h5>
        <dl class="grounding" data-test="outlook-grounding">
          <div>
            <dt>상태</dt>
            <dd>{{ groundingState }}</dd>
          </div>
          <div v-if="grounding && grounding.web_search_queries.length > 0">
            <dt>검색 질의</dt>
            <dd>{{ grounding.web_search_queries.join(' · ') }}</dd>
          </div>
          <div v-if="grounding && grounding.chunk_uris.length > 0">
            <dt>출처</dt>
            <dd>
              <ul>
                <li v-for="(uri, index) in grounding.chunk_uris" :key="uri">
                  {{ grounding.chunk_titles[index] ?? '제목 없음' }} · {{ uri }}
                </li>
              </ul>
            </dd>
          </div>
          <div v-if="grounding && grounding.absence_reason">
            <dt>부재 사유</dt>
            <dd data-test="outlook-grounding-absence">{{ grounding.absence_reason }}</dd>
          </div>
          <div v-if="grounding && grounding.missing_queries_note">
            <dt>질의 기록</dt>
            <dd>{{ grounding.missing_queries_note }}</dd>
          </div>
        </dl>
        <div
          v-if="grounding && grounding.search_suggestions_html"
          class="suggestions"
          data-test="outlook-search-suggestions"
        >
          <h5>Search Suggestions (provider content)</h5>
          <!-- 제공자가 준 표시용 조각이다. 스크립트로 실행되지 않도록 텍스트로만 보관한다. -->
          <pre>{{ grounding.search_suggestions_html }}</pre>
        </div>

        <h5>자료별 확보 상태</h5>
        <table class="table" data-test="outlook-coverage">
          <thead>
            <tr>
              <th>자료</th>
              <th>상태</th>
              <th>사유</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="entry in coverage" :key="entry.topic + entry.state">
              <td>{{ entry.topic }}</td>
              <td :class="['state-chip', entry.state]">{{ coverageLabel(entry.state) }}</td>
              <td class="muted">{{ entry.detail ?? '' }}</td>
            </tr>
          </tbody>
        </table>

        <h5>검증에서 제외된 자료 ({{ rejectedOdds.length + rejectedMedia.length }}건)</h5>
        <ul
          v-if="rejectedOdds.length + rejectedMedia.length > 0"
          class="rejected"
          data-test="outlook-rejected"
        >
          <li v-for="row in rejectedOdds" :key="'odds-' + row.claim_id">
            {{ row.bookmaker ?? '업체 미상' }} / {{ row.market ?? '시장 미상' }} ·
            {{ row.rejection_reason ?? '사유 미기록' }}
          </li>
          <li v-for="row in rejectedMedia" :key="'media-' + row.claim_id">
            {{ row.publisher ?? '매체 미상' }} · {{ row.rejection_reason ?? '사유 미기록' }}
          </li>
        </ul>
        <p v-else class="state">제외된 자료가 없습니다.</p>

        <h5>내부 진단</h5>
        <ul v-if="diagnostics.length > 0" class="diagnostics" data-test="outlook-diagnostics">
          <li v-for="note in diagnostics" :key="note">{{ note }}</li>
        </ul>
        <p v-else class="state">내부 진단이 없습니다.</p>

        <p class="muted">
          배당 업체 근거 {{ bookmakerSources.length }}건 · 매체 근거
          {{ mediaSources.length }}건 · 제공자 예측 근거 {{ apiSources.length }}건
        </p>
      </details>
    </template>
  </section>
</template>

<style scoped>
.outlook-panel {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.hint,
.muted {
  color: #566;
  font-size: 0.85rem;
}
.state {
  margin: 0;
  padding: 0.5rem 0.75rem;
  border-radius: 0.375rem;
  background: #f4f6f8;
}
.state.error {
  background: #fdecec;
  color: #8a1c1c;
}
.summary,
.api,
.grounding {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
  gap: 0.5rem;
  margin: 0;
}
.summary dt,
.api dt,
.grounding dt {
  font-size: 0.75rem;
  color: #667;
}
.summary dd,
.api dd,
.grounding dd {
  margin: 0;
  font-size: 0.9rem;
}
.reader pre {
  margin: 0;
  padding: 0.75rem;
  border: 1px solid #e3e7ea;
  border-radius: 0.375rem;
  background: #fbfcfd;
  white-space: pre-wrap;
  font-family: inherit;
  line-height: 1.55;
}
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}
.table th,
.table td {
  padding: 0.35rem 0.5rem;
  border-bottom: 1px solid #e3e7ea;
  text-align: left;
  vertical-align: top;
}
.state-chip.available {
  color: #1c6b35;
}
.state-chip.call_error,
.state-chip.validation_rejected {
  color: #8a1c1c;
}
.state-chip.unknown,
.state-chip.api_not_provided,
.state-chip.not_run,
.state-chip.search_not_found {
  color: #7a4a00;
}
.media,
.sources,
.rejected,
.diagnostics {
  margin: 0;
  padding-left: 1.1rem;
  font-size: 0.88rem;
}
.media li,
.sources li {
  margin-bottom: 0.4rem;
}
.kind {
  font-size: 0.75rem;
  padding: 0.05rem 0.3rem;
  border-radius: 0.25rem;
  background: #eef2f5;
}
.suggestions pre {
  margin: 0;
  padding: 0.5rem;
  border-radius: 0.375rem;
  background: #f4f6f8;
  font-size: 0.75rem;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.admin h5 {
  margin: 0.75rem 0 0.25rem;
  font-size: 0.85rem;
  color: #445;
}
</style>
