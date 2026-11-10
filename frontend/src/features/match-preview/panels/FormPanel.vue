<script setup lang="ts">
/**
 * R1 경기력·주목 선수 패널 (MP-05).
 *
 * 이 패널은 노드 단위 **진단**이다. 사용자 승인 단위는 섹션 워크플로우 본문이며,
 * 본문과 근거는 검사 화면의 섹션 결과 영역이 먼저 보여준다.
 *
 * 표시 원칙:
 *
 * - 확인된 사실(`fact`)과 AI 해석(`ai_interpretation`)을 섞지 않는다.
 * - 제외된 항목과 그 사유를 지운다면 안 된다. 왜 채택하지 않았는지 그대로 보여준다.
 * - 실행 방식(mock/replay/live)을 항상 함께 표시한다. 모의 결과를 실제 조사로 읽지
 *   않게 하기 위함이다.
 * - 검색 근거를 확보하지 못한 사실은 관리자 화면에만 남긴다(독자용 본문에는 없다).
 */
import { computed } from 'vue'
import type { ClaimView, ModuleInspection, SectionResultSource, SectionResultView } from '../types'

const props = defineProps<{
  module: ModuleInspection
  /** 같은 실행의 섹션 결과. 독자용 본문·출처를 함께 보여줄 때 쓴다. */
  sectionResult?: SectionResultView | null
}>()

const claims = computed<ClaimView[]>(() => props.module.tabs.transform.claims ?? [])
const adoptedFacts = computed(() =>
  claims.value.filter((claim) => claim.decision === 'adopted' && claim.kind === 'fact'),
)
const adoptedInterpretations = computed(() =>
  claims.value.filter(
    (claim) => claim.decision === 'adopted' && claim.kind === 'ai_interpretation',
  ),
)
const otherAdopted = computed(() =>
  claims.value.filter(
    (claim) =>
      claim.decision === 'adopted' &&
      claim.kind !== 'fact' &&
      claim.kind !== 'ai_interpretation',
  ),
)
const excluded = computed(() => claims.value.filter((claim) => claim.decision !== 'adopted'))

const coverage = computed(() => props.module.tabs.transform.coverage ?? [])
const searchCoverage = computed(
  () => coverage.value.find((entry) => entry.topic.includes('검색')) ?? null,
)
const diagnostics = computed(() => props.module.tabs.transform.diagnostics ?? [])

const sources = computed<SectionResultSource[]>(() => props.sectionResult?.sources ?? [])
const searchSources = computed(() => sources.value.filter((source) => source.kind === 'search'))
const apiSources = computed(() => sources.value.filter((source) => source.kind === 'api'))

const modeLabel = computed(() => props.module.run_mode.label)
const isMock = computed(() => props.module.run_mode.mode !== 'live')

function decisionLabel(decision: string): string {
  if (decision === 'adopted') return '채택'
  if (decision === 'excluded') return '제외'
  if (decision === 'conflict') return '충돌'
  return decision
}
</script>

<template>
  <section class="form-panel" data-testid="form-panel">
    <header class="form-panel__head">
      <h3 class="form-panel__title">경기력·주목 선수 조사 (R1)</h3>
      <span class="chip" data-testid="form-panel-mode">{{ modeLabel }}</span>
    </header>

    <p v-if="isMock" class="form-panel__notice" data-testid="form-panel-mock-notice">
      모의 시연 결과입니다. 실제 모델 호출로 만든 조사 결과가 아니며 승인 근거가 아닙니다.
    </p>

    <div class="form-panel__search" data-testid="form-panel-search">
      <h4 class="form-panel__subhead">검색 근거</h4>
      <p v-if="searchCoverage" class="form-panel__line" data-testid="form-panel-search-state">
        {{ searchCoverage.topic }} — {{ searchCoverage.state }}
        <span v-if="searchCoverage.detail" class="measured">{{ searchCoverage.detail }}</span>
      </p>
      <p v-else class="form-panel__line">검색 근거 상태가 기록되지 않았습니다.</p>
      <ul v-if="searchSources.length" class="form-panel__sources" data-testid="form-panel-search-sources">
        <li v-for="(source, index) in searchSources" :key="`${source.url}-${index}`">
          <a v-if="source.url" :href="source.url" rel="noreferrer noopener" target="_blank">
            {{ source.label ?? source.url }}
          </a>
          <span v-else>{{ source.label ?? '출처 없음' }}</span>
          <span v-if="source.note" class="form-panel__note">{{ source.note }}</span>
        </li>
      </ul>
      <p v-else class="form-panel__note" data-testid="form-panel-no-search-sources">
        이 실행에는 검색 출처가 저장되지 않았습니다. 검색 미확보 사실은 관리자 진단이며
        독자용 본문에는 표시하지 않습니다.
      </p>
    </div>

    <div class="form-panel__facts" data-testid="form-panel-facts">
      <h4 class="form-panel__subhead">확인된 사실 ({{ adoptedFacts.length }})</h4>
      <ul v-if="adoptedFacts.length">
        <li v-for="claim in adoptedFacts" :key="claim.claim_id" :data-testid="`form-fact-${claim.claim_id}`">
          <p class="form-panel__text">{{ claim.text }}</p>
          <p class="form-panel__meta measured">
            {{ claim.claim_id }}
            <span v-if="claim.decision_reason"> · {{ claim.decision_reason }}</span>
          </p>
        </li>
      </ul>
      <p v-else class="form-panel__note">채택된 사실이 없습니다.</p>
    </div>

    <div class="form-panel__interpretation" data-testid="form-panel-interpretation">
      <h4 class="form-panel__subhead">
        AI 해석 ({{ adoptedInterpretations.length }})
      </h4>
      <p class="form-panel__note">
        아래 문장은 확인된 사실과 구분되는 해석입니다. 기사·매체의 의견이 아닙니다.
      </p>
      <ul v-if="adoptedInterpretations.length">
        <li
          v-for="claim in adoptedInterpretations"
          :key="claim.claim_id"
          :data-testid="`form-interpretation-${claim.claim_id}`"
        >
          <p class="form-panel__text">{{ claim.text }}</p>
          <p class="form-panel__meta measured">{{ claim.claim_id }}</p>
        </li>
      </ul>
      <p v-else class="form-panel__note">채택된 해석이 없습니다.</p>
    </div>

    <div v-if="otherAdopted.length" class="form-panel__other" data-testid="form-panel-other">
      <h4 class="form-panel__subhead">그 밖의 채택 근거 ({{ otherAdopted.length }})</h4>
      <ul>
        <li v-for="claim in otherAdopted" :key="claim.claim_id">
          <p class="form-panel__text">{{ claim.text }}</p>
          <p class="form-panel__meta measured">{{ claim.kind }} · {{ claim.claim_id }}</p>
        </li>
      </ul>
    </div>

    <div class="form-panel__excluded" data-testid="form-panel-excluded">
      <h4 class="form-panel__subhead">제외·충돌 항목 ({{ excluded.length }})</h4>
      <p class="form-panel__note">
        채택하지 않은 항목과 사유입니다. 관리자 진단이며 독자용 본문에는 들어가지 않습니다.
      </p>
      <ul v-if="excluded.length">
        <li
          v-for="claim in excluded"
          :key="claim.claim_id"
          :data-testid="`form-excluded-${claim.claim_id}`"
        >
          <p class="form-panel__text">{{ claim.text }}</p>
          <p class="form-panel__meta measured">
            <strong>{{ decisionLabel(claim.decision) }}</strong>
            <span v-if="claim.decision_reason"> · {{ claim.decision_reason }}</span>
          </p>
        </li>
      </ul>
      <p v-else class="form-panel__note">제외된 항목이 없습니다.</p>
    </div>

    <div v-if="apiSources.length" class="form-panel__api" data-testid="form-panel-api-sources">
      <h4 class="form-panel__subhead">API 자료 출처 ({{ apiSources.length }})</h4>
      <ul>
        <li v-for="(source, index) in apiSources" :key="`api-${index}`">
          <span>{{ source.label ?? 'API 자료' }}</span>
          <span v-if="source.note" class="form-panel__note">{{ source.note }}</span>
        </li>
      </ul>
    </div>

    <div v-if="diagnostics.length" class="form-panel__diagnostics" data-testid="form-panel-diagnostics">
      <h4 class="form-panel__subhead">진단 메시지</h4>
      <ul>
        <li v-for="(line, index) in diagnostics" :key="index">{{ line }}</li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.form-panel {
  border: 1px solid var(--line, #d8d8d8);
  border-radius: var(--radius-panel, 10px);
  padding: 1rem;
  display: grid;
  gap: 1rem;
}

.form-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.form-panel__title {
  margin: 0;
  font-size: 1rem;
}

.form-panel__subhead {
  margin: 0 0 0.35rem;
  font-size: 0.9rem;
}

.form-panel__notice {
  margin: 0;
  padding: 0.5rem 0.75rem;
  border-radius: 8px;
  background: #fff4e5;
  color: #7a4b00;
}

.form-panel__line {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.form-panel__text {
  margin: 0;
}

.form-panel__meta {
  margin: 0.2rem 0 0;
  font-size: 0.8rem;
  opacity: 0.75;
}

.form-panel__note {
  margin: 0.25rem 0 0;
  font-size: 0.85rem;
  opacity: 0.8;
}

.form-panel__sources,
.form-panel__facts ul,
.form-panel__interpretation ul,
.form-panel__other ul,
.form-panel__excluded ul,
.form-panel__api ul,
.form-panel__diagnostics ul {
  margin: 0;
  padding-left: 1.1rem;
  display: grid;
  gap: 0.5rem;
}
</style>
