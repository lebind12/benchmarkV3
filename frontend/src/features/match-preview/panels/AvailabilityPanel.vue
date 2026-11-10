<script setup lang="ts">
/**
 * R2 부상·결장 영향 패널 (MP-06).
 *
 * 이 패널은 **관리자 진단 화면**의 모듈 결과 표현이다. 승인 단위는 이 패널이 아니라
 * `section_availability` 섹션 워크플로우다. 노드마다 승인을 요구하지 않는다.
 *
 * 표시 원칙:
 *
 * - API 원문 표기(`Questionable` 등)를 결장 확정으로 바꾸지 않는다. 화면에서도
 *   원문 표기와 정규화 상태를 따로 보여준다.
 * - 빈 부상 응답을 "부상자 없음"으로 쓰지 않는다. 서버가 준 자료 상태 문장을 그대로 쓴다.
 * - 상충하는 자료는 숨기지 않고 양쪽을 함께 보여준다.
 * - 영향 해석은 근거가 붙은 것만 보여주고, 근거 없는 해석은 채택하지 않은 목록에 둔다.
 * - 검색 출처가 없으면 그 사실을 진단 영역에만 적는다(독자용 본문에는 없다).
 * - Search Suggestions HTML은 제공된 그대로 실행 없는 `<iframe>`에 넣는다.
 */
import { computed } from 'vue'

export type AvailabilityStatusValue =
  | 'doubtful'
  | 'confirmed_absence'
  | 'available'
  | 'unknown'
  | string

export type AvailabilityRetrievedSource = {
  uri: string
  title?: string | null
  domain?: string | null
}

export type AvailabilityR2ResearchView = {
  material_state: string
  material_detail: string | null
  facts: {
    evidence_id: string
    player_id: number
    player_name: string | null
    team_id: number | null
    type_marker: string | null
    reason: string | null
    uncertainty: string
    expected_status: string
    collected_at: string | null
    snapshot_id: string | null
    adopted: boolean
  }[]
  player_updates: {
    player_id: number | null
    player_name: string | null
    team_id: number | null
    status: AvailabilityStatusValue
    summary: string
    evidence: string[]
    conflict: boolean
    api_status: string | null
  }[]
  reported_absences: {
    player_name: string
    team_id: number | null
    summary: string
    evidence: string[]
  }[]
  impacts: { team_id: number | null; summary: string; basis: string[] }[]
  uncertainties: string[]
  search_note: string | null
  rejected: string[]
  grounding: {
    available: boolean
    sources: AvailabilityRetrievedSource[]
    queries: string[]
    supports: Record<string, unknown>[]
    search_entry_point: { rendered_content?: string | null; sdk_blob?: string | null } | null
  }
  search_snapshot_id: string | null
  team_names: Record<string, string>
  fixture_label: string | null
}

export type AvailabilityR2ResultView = {
  module_id: string
  implementation_version: string
  prompt_version: string
  mode: string
  claims: {
    claim_id: string
    kind: string
    text: string
    decision: string
    decision_reason: string | null
    source_url: string | null
  }[]
  coverage: { topic: string; state: string; detail: string | null }[]
  research: AvailabilityR2ResearchView
  raw_grounding: AvailabilityR2ResearchView['grounding']
  model_text: string | null
  attempt_count: number
  /** 실행 상태. 이 패널은 모듈 결과를 보여줄 뿐 승인하지 않는다. */
  status?: string
  quality?: string
}

const props = defineProps<{
  result: AvailabilityR2ResultView | null
  loading?: boolean
  errorMessage?: string | null
}>()

const STATUS_LABELS: Record<string, string> = {
  doubtful: '출전 불확실',
  confirmed_absence: '결장(확정 표기)',
  available: '출전 가능 표기',
  unknown: '표기 없음',
}

const MODE_LABELS: Record<string, string> = {
  live: '실호출',
  replay: '저장 응답 재생',
  mock: '모의 실행 (외부 호출 없음)',
}

const MATERIAL_STATE_LABELS: Record<string, string> = {
  available: 'API 부상 자료 수신',
  empty_response: '응답 성공 · 부상 항목 비어 있음(부상자 0명의 증거 아님)',
  api_not_provided: 'API가 부상 자료를 제공하지 않음',
  call_error: '부상 자료 API 호출 실패',
  not_run: '부상 자료 수집 미실행',
}

const research = computed<AvailabilityR2ResearchView | null>(() => props.result?.research ?? null)
const updates = computed(() => research.value?.player_updates ?? [])
const absences = computed(() => research.value?.reported_absences ?? [])
const impacts = computed(() => research.value?.impacts ?? [])
const facts = computed(() => research.value?.facts ?? [])
const rejected = computed(() => research.value?.rejected ?? [])
const coverage = computed(() => props.result?.coverage ?? [])
const sources = computed(() => research.value?.grounding.sources ?? [])
const suggestions = computed(() => research.value?.grounding.search_entry_point ?? null)
const conflicts = computed(() => updates.value.filter((update) => update.conflict))

const modeLabel = computed(() => MODE_LABELS[props.result?.mode ?? ''] ?? props.result?.mode ?? '')
const materialStateLabel = computed(
  () => MATERIAL_STATE_LABELS[research.value?.material_state ?? ''] ?? research.value?.material_state ?? '',
)

function teamLabel(teamId: number | null): string {
  if (teamId === null || teamId === undefined) return '팀 미확인'
  const name = research.value?.team_names?.[String(teamId)]
  return name ?? `팀 ${teamId}`
}

function playerLabel(playerId: number | null, playerName: string | null): string {
  if (playerName) return playerName
  // 이름을 만들지 않는다. 저장된 자료가 이름을 주지 않으면 식별자만 쓴다.
  return playerId === null ? '선수 미확인' : `선수 ID ${playerId}`
}

function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status
}

function decisionLabel(decision: string): string {
  if (decision === 'adopted') return '채택'
  if (decision === 'conflict') return '상충 보존'
  if (decision === 'excluded') return '제외'
  return decision
}

function hasSuggestions(): boolean {
  const html = suggestions.value?.rendered_content
  return typeof html === 'string' && html.trim().length > 0
}
</script>

<template>
  <section class="availability-panel" data-test="availability-panel">
    <header>
      <h3>R2 부상·결장 영향</h3>
      <p class="hint">
        API 부상 사실과 검색 근거를 구분해 보여주는 관리자 진단입니다. 승인 단위는 이 패널이
        아니라 섹션 워크플로우(<code>section_availability</code>)입니다.
      </p>
    </header>

    <p v-if="loading" class="state">R2 결과를 읽는 중입니다.</p>
    <p v-else-if="errorMessage" class="state error" data-test="r2-error">{{ errorMessage }}</p>
    <p v-else-if="!result" class="state" data-test="r2-empty">
      아직 R2 조사 결과가 없습니다.
    </p>

    <template v-else>
      <dl class="summary" data-test="r2-summary">
        <div>
          <dt>실행 방식</dt>
          <dd data-test="r2-mode">{{ modeLabel }}</dd>
        </div>
        <div>
          <dt>부상 자료 상태</dt>
          <dd data-test="r2-material-state">
            {{ materialStateLabel }}
            <span v-if="research?.material_detail" class="muted">— {{ research.material_detail }}</span>
          </dd>
        </div>
        <div>
          <dt>모델 호출</dt>
          <dd data-test="r2-attempts">{{ result.attempt_count }}회</dd>
        </div>
        <div>
          <dt>버전</dt>
          <dd>구현 {{ result.implementation_version }} · 프롬프트 {{ result.prompt_version }}</dd>
        </div>
      </dl>

      <h4>선수별 원문 표기 → 정규화 상태</h4>
      <table v-if="facts.length > 0" class="facts" data-test="r2-facts">
        <thead>
          <tr>
            <th>선수</th>
            <th>팀</th>
            <th>API 원문 표기</th>
            <th>사유</th>
            <th>분류</th>
            <th>수집 시각</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="fact in facts" :key="fact.evidence_id">
            <td>{{ playerLabel(fact.player_id, fact.player_name) }}</td>
            <td>{{ teamLabel(fact.team_id) }}</td>
            <td class="mono">{{ fact.type_marker ?? '표기 없음' }}</td>
            <td class="muted">{{ fact.reason ?? '—' }}</td>
            <td>
              <span :class="['chip', fact.expected_status]" data-test="r2-fact-status">
                {{ statusLabel(fact.expected_status) }}
              </span>
              <span v-if="!fact.adopted" class="muted"> (확정 사실로 채택하지 않음)</span>
            </td>
            <td class="muted mono">{{ fact.collected_at ?? '시각 미상' }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="state" data-test="r2-no-facts">
        저장된 부상 행이 없습니다. 이는 '부상자 없음'의 증거가 아닙니다.
      </p>

      <h4>검증된 결장·출전 불확실</h4>
      <ul v-if="updates.length > 0 || absences.length > 0" class="updates" data-test="r2-updates">
        <li v-for="(update, index) in updates" :key="`u-${index}`" :class="{ conflict: update.conflict }">
          <strong>{{ teamLabel(update.team_id) }}</strong>
          {{ playerLabel(update.player_id, update.player_name) }} ·
          <span :class="['chip', update.status]" data-test="r2-update-status">
            {{ statusLabel(update.status) }}
          </span>
          <span v-if="update.conflict" class="conflict-note" data-test="r2-conflict">
            API 표기({{ statusLabel(update.api_status ?? 'unknown') }})와 검색 보도가 다릅니다. 양쪽을
            함께 보존했습니다.
          </span>
          <p>{{ update.summary }}</p>
          <p class="muted">근거: {{ update.evidence.join(', ') }}</p>
        </li>
        <li v-for="(absence, index) in absences" :key="`a-${index}`">
          <strong>{{ teamLabel(absence.team_id) }}</strong>
          {{ absence.player_name }} · <span class="chip confirmed_absence">결장 보도</span>
          <p>{{ absence.summary }}</p>
          <p class="muted">근거: {{ absence.evidence.join(', ') }}</p>
        </li>
      </ul>
      <p v-else class="state" data-test="r2-no-updates">
        검증을 통과한 결장·출전 불확실 항목이 없습니다. 본문을 만들지 않습니다.
      </p>

      <h4>전력 영향 (근거에 기반한 해석)</h4>
      <ul v-if="impacts.length > 0" class="impacts" data-test="r2-impacts">
        <li v-for="(impact, index) in impacts" :key="`i-${index}`">
          <strong>{{ teamLabel(impact.team_id) }}</strong>
          {{ impact.summary }}
          <p class="muted">근거: {{ impact.basis.join(', ') }}</p>
        </li>
      </ul>
      <p v-else class="state" data-test="r2-no-impacts">
        근거가 연결된 영향 해석이 없습니다. 근거 없는 해석은 채택하지 않았습니다.
      </p>

      <h4>검색 출처</h4>
      <p v-if="sources.length === 0" class="state" data-test="r2-no-sources">
        이번 호출의 검색 grounding 출처가 비어 있습니다. API 사실만으로 결과를 만들었습니다.
        (독자용 본문에는 이 안내를 넣지 않습니다.)
      </p>
      <ul v-else class="sources" data-test="r2-sources">
        <li v-for="source in sources" :key="source.uri">
          <a :href="source.uri" rel="noreferrer noopener" target="_blank">
            {{ source.title ?? source.domain ?? source.uri }}
          </a>
          <span class="muted mono">{{ source.uri }}</span>
        </li>
      </ul>
      <p v-if="research && research.grounding.queries.length > 0" class="muted" data-test="r2-queries">
        검색어: {{ research.grounding.queries.join(' · ') }}
      </p>

      <!--
        Search Suggestions는 Google이 준 rendered_content를 그대로 넣는다. 스크립트 실행이
        없는 sandbox iframe이며, 임의 HTML을 만들어 넣지 않는다.
      -->
      <div v-if="hasSuggestions()" class="suggestions" data-test="r2-suggestions">
        <h4>Search Suggestions</h4>
        <iframe
          :srcdoc="suggestions?.rendered_content ?? ''"
          sandbox=""
          referrerpolicy="no-referrer"
          title="Search Suggestions"
        ></iframe>
      </div>

      <h4>자료별 확보 상태</h4>
      <table class="coverage" data-test="r2-coverage">
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
            <td :class="['chip', entry.state]" data-test="r2-coverage-state">{{ entry.state }}</td>
            <td class="muted">{{ entry.detail ?? '' }}</td>
          </tr>
        </tbody>
      </table>

      <details v-if="conflicts.length > 0" class="rejected" data-test="r2-conflict-details">
        <summary>상충 항목 {{ conflicts.length }}건</summary>
        <ul>
          <li v-for="(update, index) in conflicts" :key="`c-${index}`">
            {{ playerLabel(update.player_id, update.player_name) }} — API
            {{ statusLabel(update.api_status ?? 'unknown') }} / 검색 보도
            {{ statusLabel(update.status) }}
          </li>
        </ul>
      </details>

      <details v-if="rejected.length > 0" class="rejected" data-test="r2-rejected">
        <summary>채택하지 않은 항목 ({{ rejected.length }}건)</summary>
        <ul>
          <li v-for="(note, index) in rejected" :key="`r-${index}`">{{ note }}</li>
        </ul>
      </details>

      <details v-if="result.claims.length > 0" class="claims" data-test="r2-claims">
        <summary>근거 claim ({{ result.claims.length }}건)</summary>
        <ul>
          <li v-for="claim in result.claims" :key="claim.claim_id">
            <span class="chip">{{ claim.kind }}</span>
            <span class="chip">{{ decisionLabel(claim.decision) }}</span>
            {{ claim.text }}
            <span v-if="claim.source_url" class="mono muted">{{ claim.source_url }}</span>
          </li>
        </ul>
      </details>

      <details v-if="result.model_text" class="raw" data-test="r2-model-text">
        <summary>모델 응답 본문(원문)</summary>
        <pre>{{ result.model_text }}</pre>
      </details>
    </template>
  </section>
</template>

<style scoped>
.availability-panel {
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
.summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
  gap: 0.5rem;
  margin: 0;
}
.summary dt {
  font-size: 0.75rem;
  color: #667;
}
.summary dd {
  margin: 0;
  font-size: 0.9rem;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}
th,
td {
  padding: 0.35rem 0.5rem;
  border-bottom: 1px solid #e3e7ea;
  text-align: left;
  vertical-align: top;
}
.chip {
  font-size: 0.75rem;
  padding: 0.05rem 0.35rem;
  border-radius: 0.25rem;
  background: #eef2f5;
  white-space: nowrap;
}
.chip.doubtful {
  background: #fff4e0;
  color: #7a4a00;
}
.chip.confirmed_absence {
  background: #fdecec;
  color: #8a1c1c;
}
.chip.available {
  background: #eaf7ef;
  color: #1c6b35;
}
.chip.unknown {
  background: #f0f0f3;
  color: #444;
}
.chip.source_conflict {
  background: #f2ecff;
  color: #4b2a86;
}
.updates,
.impacts,
.sources {
  margin: 0;
  padding-left: 1.1rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
.updates li.conflict {
  border-left: 3px solid #4b2a86;
  padding-left: 0.5rem;
}
.conflict-note {
  display: block;
  font-size: 0.8rem;
  color: #4b2a86;
}
.suggestions iframe {
  width: 100%;
  min-height: 12rem;
  border: 1px solid #e3e7ea;
  border-radius: 0.375rem;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 0.78rem;
}
pre {
  white-space: pre-wrap;
  word-break: break-word;
  background: #f8f9fb;
  padding: 0.5rem;
  border-radius: 0.375rem;
}
</style>
