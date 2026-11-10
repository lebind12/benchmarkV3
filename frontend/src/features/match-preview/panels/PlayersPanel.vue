<script setup lang="ts">
/**
 * R4 주목 선수 선정 패널.
 *
 * 이 패널은 **관리자 진단 화면**의 R4 결과 표현이다. 승인 단위는 이 패널이 아니라
 * `section_players` 섹션 워크플로우 결과이며, 사용자가 직접 승인한다.
 *
 * 표시 원칙(사용자 확정 2026-11-11):
 *
 * - `selected_player`(선정 선수)와 `selection_reason`(선정 이유)을 **분리해** 보여준다.
 *   두 값을 한 문장으로 합치지 않는다. 라벨은 '선정 선수'/'선정 이유'다.
 * - 이름은 DB 한국어 값이다. 확인하지 못한 이름은 원래 표기를 유지하고, 그 사실과
 *   사유를 관리자 영역에 남긴다. 화면에서 한국어 이름을 만들어 채우지 않는다.
 * - 실행 방식(mock/replay/live, 이전 R1 선정 재사용)을 항상 표시한다. 모의·재생
 *   결과를 실제 생성으로 읽지 않게 하기 위함이다.
 * - 원문 응답은 데이터로만 보여준다(HTML로 실행하지 않음).
 */
import { computed } from 'vue'
import {
  PLAYERS_DISPLAY_LABELS,
  displayablePlayers,
  mappingReasonLabel,
  mappingStatusLabel,
  originLabel,
  splitDisplayFields,
} from './players'
import type { PlayersR4ResultView, SelectedPlayerView } from './players'

const props = defineProps<{
  result: PlayersR4ResultView | null
  loading?: boolean
  errorMessage?: string | null
}>()

const labels = computed(() => ({
  selected_player: props.result?.display_labels?.selected_player ?? PLAYERS_DISPLAY_LABELS.selected_player,
  selection_reason: props.result?.display_labels?.selection_reason ?? PLAYERS_DISPLAY_LABELS.selection_reason,
}))

const players = computed<SelectedPlayerView[]>(() => displayablePlayers(props.result?.players))
const unmapped = computed(() => props.result?.unmapped ?? [])
const diagnostics = computed(() => props.result?.diagnostics ?? [])
const coverage = computed(() => props.result?.coverage ?? [])
const sources = computed(() => props.result?.reader_sources ?? [])
const uncertainties = computed(() => props.result?.uncertainties ?? [])
const droppedFacts = computed(() => props.result?.dropped_facts ?? [])
const unassertedPremises = computed(() => props.result?.unasserted_premises ?? [])

const modeText = computed(() => originLabel(props.result?.mode, props.result?.origin))
const isNotLive = computed(() => (props.result?.mode ?? '') !== 'live')
const mapping = computed(() => props.result?.mapping ?? {})
const hasUnmappedPlayers = computed(() =>
  unmapped.value.some((row) => row.kind === 'player'),
)

function rawText(value: string | null | undefined): string {
  if (!value) return '—'
  return value
}
</script>

<template>
  <section class="players-panel" data-testid="players-panel">
    <header class="players-panel__head">
      <h3 class="players-panel__title">주목 선수 선정 (R4)</h3>
      <span class="chip" data-testid="players-panel-mode">{{ modeText }}</span>
    </header>

    <p class="players-panel__note">
      노드 진단 화면입니다. 사용자 승인 단위는 <code>section_players</code> 섹션 워크플로우
      결과 본문이며, 이 패널은 그 결과를 대신 승인하지 않습니다.
    </p>

    <p v-if="loading" class="players-panel__state">R4 결과를 읽는 중입니다.</p>
    <p v-else-if="errorMessage" class="players-panel__state players-panel__state--error" data-testid="players-panel-error">
      {{ errorMessage }}
    </p>
    <p v-else-if="!result" class="players-panel__state" data-testid="players-panel-empty">
      아직 R4 선정 결과가 없습니다. 경기력(R1) 결과와 별개의 실행입니다.
    </p>

    <template v-else>
      <p v-if="isNotLive" class="players-panel__notice" data-testid="players-panel-replay-notice">
        실제 모델 호출로 만든 결과가 아닙니다({{ modeText }}). 사용자 승인 근거가 아니며,
        새 R4 생성으로 표시하지 않습니다.
      </p>

      <div class="players-panel__selected" data-testid="players-panel-selected">
        <h4 class="players-panel__subhead">선정 결과 ({{ players.length }}명)</h4>
        <ul v-if="players.length" class="players-panel__list">
          <li
            v-for="(row, index) in players"
            :key="row.claim_id ?? `player-${index}`"
            class="players-panel__item"
            :data-testid="`players-panel-item-${index}`"
          >
            <div class="players-panel__field">
              <span class="players-panel__label">{{ labels.selected_player }}</span>
              <strong class="players-panel__value" :data-testid="`players-panel-name-${index}`">
                {{ splitDisplayFields(row).selectedPlayer }}
              </strong>
              <span v-if="row.team" class="players-panel__team" :data-testid="`players-panel-team-${index}`">
                {{ row.team }}
              </span>
            </div>
            <div class="players-panel__field">
              <span class="players-panel__label">{{ labels.selection_reason }}</span>
              <p class="players-panel__reason" :data-testid="`players-panel-reason-${index}`">
                {{ splitDisplayFields(row).selectionReason }}
              </p>
            </div>
            <p class="players-panel__meta measured">
              <span :data-testid="`players-panel-mapping-${index}`">
                {{ mappingStatusLabel(row.mapping_status) }}
                <template v-if="row.name_source && row.name_source !== 'original'">
                  ({{ row.name_source }})
                </template>
              </span>
              <span v-if="row.mapping_reason"> · {{ mappingReasonLabel(row.mapping_reason) }}</span>
              <span v-if="row.model_selected_player && row.model_selected_player !== row.selected_player">
                · 모델 표기: {{ row.model_selected_player }}
              </span>
              <span v-if="row.team_mapping"> · 팀 이름 미해결({{ mappingReasonLabel(row.team_mapping) }})</span>
            </p>
          </li>
        </ul>
        <p v-else class="players-panel__state" data-testid="players-panel-no-players">
          이름과 이유가 모두 채워진 선정 항목이 없습니다. 빈 항목을 문장으로 채우지 않았습니다.
        </p>
      </div>

      <div
        v-if="unmapped.length"
        class="players-panel__unmapped"
        data-testid="players-panel-unmapped"
      >
        <h4 class="players-panel__subhead">이름 매핑 미해결 ({{ unmapped.length }})</h4>
        <p class="players-panel__note">
          DB 한국어 값으로 확정하지 못한 이름입니다. 원래 표기를 유지했으며 한국어 이름을
          만들어 넣지 않았습니다. 관리자 확인이 필요합니다.
        </p>
        <ul>
          <li
            v-for="(row, index) in unmapped"
            :key="`unmapped-${index}`"
            :data-testid="`players-panel-unmapped-${index}`"
          >
            <strong>{{ row.original || '이름 없음' }}</strong>
            <span class="measured"> · {{ mappingReasonLabel(row.reason) }}</span>
            <span v-if="row.detail" class="players-panel__note">{{ row.detail }}</span>
          </li>
        </ul>
      </div>

      <p
        v-if="hasUnmappedPlayers"
        class="players-panel__notice"
        data-testid="players-panel-unresolved-notice"
      >
        일부 선수의 한국어 표시를 확정하지 못했습니다. 요구사항 충족으로 표시하지 않습니다.
      </p>

      <div v-if="coverage.length" class="players-panel__coverage" data-testid="players-panel-coverage">
        <h4 class="players-panel__subhead">자료 확보 상태</h4>
        <ul>
          <li v-for="(entry, index) in coverage" :key="`coverage-${index}`">
            {{ entry.topic }} — {{ entry.state }}
            <span v-if="entry.detail" class="players-panel__note">{{ entry.detail }}</span>
          </li>
        </ul>
      </div>

      <div v-if="sources.length" class="players-panel__sources" data-testid="players-panel-sources">
        <h4 class="players-panel__subhead">검색 출처 ({{ sources.length }})</h4>
        <ul>
          <li v-for="(source, index) in sources" :key="`source-${index}`">
            <a v-if="source.url" :href="source.url" rel="noreferrer noopener" target="_blank">
              {{ source.label ?? source.url }}
            </a>
            <span v-else>{{ source.label ?? '출처 없음' }}</span>
            <span v-if="source.note" class="players-panel__note">{{ source.note }}</span>
          </li>
        </ul>
      </div>

      <div v-if="uncertainties.length" class="players-panel__uncertainties" data-testid="players-panel-uncertainties">
        <h4 class="players-panel__subhead">확인하지 못한 항목</h4>
        <ul>
          <li v-for="(line, index) in uncertainties" :key="`uncertainty-${index}`">{{ line }}</li>
        </ul>
      </div>

      <div
        v-if="droppedFacts.length || unassertedPremises.length"
        class="players-panel__dropped"
        data-testid="players-panel-dropped"
      >
        <h4 class="players-panel__subhead">검증에서 덜어낸 사실·전제</h4>
        <p class="players-panel__note">
          확인되지 않은 사실 조각과 그 사실을 전제로 삼은 부분입니다. 관리자 진단이며 독자용
          본문에는 들어가지 않습니다.
        </p>
        <ul>
          <li v-for="(line, index) in droppedFacts" :key="`dropped-${index}`">사실: {{ line }}</li>
          <li v-for="(line, index) in unassertedPremises" :key="`premise-${index}`">전제: {{ line }}</li>
        </ul>
      </div>

      <div v-if="diagnostics.length" class="players-panel__diagnostics" data-testid="players-panel-diagnostics">
        <h4 class="players-panel__subhead">진단 메시지</h4>
        <ul>
          <li v-for="(line, index) in diagnostics" :key="`diag-${index}`">{{ line }}</li>
        </ul>
      </div>

      <dl class="players-panel__summary" data-testid="players-panel-summary">
        <div>
          <dt>이름 매핑</dt>
          <dd>
            확인 {{ mapping.resolved ?? 0 }} · 미해결 {{ mapping.unresolved ?? 0 }}
            <span v-if="mapping.resolver_injected === false" class="players-panel__note">
              (이름 해석기 미주입 — 이 실행에서는 DB 한국어 이름을 확인하지 않았습니다)
            </span>
          </dd>
        </div>
        <div>
          <dt>모델 호출</dt>
          <dd>{{ result.attempt_count ?? 0 }}회 · 외부 호출 {{ result.external_calls ?? 0 }}회</dd>
        </div>
        <div>
          <dt>버전</dt>
          <dd>
            구현 {{ result.implementation_version ?? '—' }} · 프롬프트
            {{ result.prompt_version ?? '—' }} · 출력 계약
            {{ result.output_contract_version ?? '—' }}
          </dd>
        </div>
        <div v-if="result.search_note">
          <dt>검색 메모</dt>
          <dd>{{ result.search_note }}</dd>
        </div>
      </dl>

      <details class="players-panel__raw" data-testid="players-panel-raw">
        <summary>원문 응답(데이터로만 표시)</summary>
        <pre class="players-panel__pre">{{ rawText(result.raw_model_text) }}</pre>
      </details>

      <p v-if="result.selection_rule_note" class="players-panel__note">
        {{ result.selection_rule_note }}
      </p>
    </template>
  </section>
</template>

<style scoped>
.players-panel {
  border: 1px solid var(--line, #d8d8d8);
  border-radius: var(--radius-panel, 10px);
  padding: 1rem;
  display: grid;
  gap: 1rem;
}

.players-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.players-panel__title {
  margin: 0;
  font-size: 1rem;
}

.players-panel__subhead {
  margin: 0 0 0.35rem;
  font-size: 0.9rem;
}

.players-panel__state {
  margin: 0;
}

.players-panel__state--error {
  color: #b42318;
}

.players-panel__notice {
  margin: 0;
  padding: 0.5rem 0.75rem;
  border-radius: 8px;
  background: #fff4e5;
  color: #7a4b00;
}

.players-panel__note {
  margin: 0.25rem 0 0;
  font-size: 0.85rem;
  opacity: 0.8;
}

.players-panel__list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 0.75rem;
}

.players-panel__item {
  border: 1px solid var(--line, #e3e3e3);
  border-radius: 8px;
  padding: 0.6rem 0.75rem;
  display: grid;
  gap: 0.35rem;
}

/* 선정 선수와 선정 이유를 시각적으로도 분리한다(한 문장으로 합치지 않음). */
.players-panel__field {
  display: grid;
  gap: 0.15rem;
}

.players-panel__label {
  font-size: 0.75rem;
  letter-spacing: 0.02em;
  text-transform: none;
  opacity: 0.7;
}

.players-panel__value {
  font-size: 0.98rem;
}

.players-panel__team {
  font-size: 0.85rem;
  opacity: 0.8;
}

.players-panel__reason {
  margin: 0;
  line-height: 1.5;
}

.players-panel__meta {
  margin: 0.2rem 0 0;
  font-size: 0.8rem;
  opacity: 0.75;
}

.players-panel__summary {
  margin: 0;
  display: grid;
  gap: 0.35rem;
}

.players-panel__summary > div {
  display: flex;
  gap: 0.5rem;
}

.players-panel__summary dt {
  min-width: 6.5rem;
  font-weight: 600;
  font-size: 0.85rem;
}

.players-panel__summary dd {
  margin: 0;
  font-size: 0.85rem;
}

.players-panel__pre {
  max-height: 18rem;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.78rem;
}

.players-panel__unmapped ul,
.players-panel__coverage ul,
.players-panel__sources ul,
.players-panel__uncertainties ul,
.players-panel__dropped ul,
.players-panel__diagnostics ul {
  margin: 0;
  padding-left: 1.1rem;
  display: grid;
  gap: 0.35rem;
}
</style>
