<script setup lang="ts">
/**
 * 실행 검사 화면 — MP-02.
 *
 * 저장된 실행 하나를 열어 모듈별 요청·원문 응답·정규화 변환·다음 입력과 결과 버전
 * 비교를 보여준다. 이 화면은 조회만 한다(GET). 새 실행이나 외부 호출을 일으키지
 * 않는다. 실행 방식(mock/replay/live)과 환경(dev/test/prod)을 항상 함께 표시해
 * 모의 기록을 실제 성공으로 읽지 않게 한다.
 */
import { computed, ref, watch } from 'vue'
import { previewRunsApi } from './api'
import ModuleResultPanel from './ModuleResultPanel.vue'
import RunVersionCompare from './RunVersionCompare.vue'
import AttemptPanel from './panels/AttemptPanel.vue'
import type { RunDetail, SectionResultView, UndoReport } from './types'

const props = defineProps<{
  runId: string
}>()

const emit = defineEmits<{ (event: 'closed'): void; (event: 'cancelled'): void }>()

const detail = ref<RunDetail | null>(null)
const loading = ref(true)
const errorMessage = ref<string | null>(null)
const activeModuleId = ref<string | null>(null)
const undoPreview = ref<UndoReport | null>(null)
const approvalPending = ref(false)
const approvalError = ref<string | null>(null)
const approvalNote = ref('')
const selectedWorkflowId = ref<string | null>(null)
const selectedSectionResultId = ref<string | null>(null)
const replayPending = ref(false)
const replayMessage = ref<string | null>(null)
const undoError = ref<string | null>(null)
const undoPending = ref(false)

async function load() {
  loading.value = true
  errorMessage.value = null
  const result = await previewRunsApi.detail(props.runId)
  loading.value = false
  if (!result.ok) {
    errorMessage.value = result.message
    return
  }
  detail.value = result.data
  if (!activeModuleId.value && result.data.inspector_modules.length > 0) {
    activeModuleId.value = result.data.inspector_modules[0].module_execution_id
  }
}

watch(() => props.runId, load, { immediate: true })

const activeModule = computed(
  () =>
    detail.value?.inspector_modules.find(
      (module) => module.module_execution_id === activeModuleId.value,
    ) ?? null,
)

const summary = computed(() => detail.value?.summary ?? null)

/** 이 실행의 섹션 본문 결과. 승인 근거는 노드 결과가 아니라 이 본문이다. */
const sectionResults = computed<SectionResultView[]>(() => detail.value?.section_results ?? [])

const activeSectionResult = computed<SectionResultView | null>(() => {
  const rows = sectionResults.value
  if (rows.length === 0) return null
  const selected = rows.find((row) => row.section_result_id === selectedSectionResultId.value)
  return selected ?? rows[0]
})

/** 승인 근거로 쓸 수 있는 섹션 결과. 모의 시연 결과뿐이면 null이다. */
const approvableSectionResult = computed<SectionResultView | null>(() => {
  const candidate = activeSectionResult.value
  if (!candidate || !candidate.approvable) return null
  return candidate
})

/**
 * 선택한 섹션 워크플로우를 승인한다.
 *
 * 승인 단위는 프리뷰 섹션을 만드는 완결된 워크플로우이며, 내부 노드나 D0에는 따로
 * 승인하지 않는다. 승인은 관리자가 결과를 확인한 뒤의 명시적 동작이므로 개발 완료
 * 보고나 테스트 통과로 대신할 수 없다. 섹션 결과가 아직 없는 지금은 서버가 거부하며,
 * 화면은 그 거부를 그대로 보여준다(승인된 것처럼 꾸미지 않는다).
 */
async function approveSection() {
  const workflowId = selectedWorkflowId.value
  if (!workflowId) {
    approvalError.value = '승인할 섹션을 선택하세요.'
    return
  }
  // 승인 근거는 실제 섹션 본문 결과다. 모의 시연 결과는 근거가 아니므로 화면에서도
  // 요청을 만들지 않는다(서버도 거부한다).
  const sectionResultId = approvableSectionResult.value?.section_result_id ?? null
  if (!sectionResultId) {
    approvalError.value = sectionResults.value.length
      ? '모의 시연 결과는 승인 근거가 아닙니다. 실제 생성 결과를 확인한 뒤 승인할 수 있습니다.'
      : '이 실행에는 승인 근거로 쓸 섹션 결과가 없습니다. 섹션 결과가 저장된 뒤에 승인할 수 있습니다.'
    return
  }

  approvalPending.value = true
  approvalError.value = null
  const result = await previewRunsApi.approveSection(workflowId, {
    run_id: props.runId,
    section_result_id: sectionResultId,
    note: approvalNote.value || undefined,
  })
  approvalPending.value = false
  if (!result.ok) {
    approvalError.value = result.message
    return
  }
  approvalNote.value = ''
  await load()
}

/**
 * 저장된 원문으로 변환만 다시 한다. 외부 모델 호출은 0회다.
 *
 * 이 동작은 LangGraph 체크포인트 재실행(유료 time travel)이나 DB undo와 다르다.
 * 원본 결과는 그대로 남고 새 결과 버전이 추가된다.
 */
async function replayStoredResult() {
  const target = activeSectionResult.value
  const resultId = target?.result_ids.at(-1)
  if (!resultId) {
    replayMessage.value = '재생할 저장 결과가 없습니다.'
    return
  }
  replayPending.value = true
  replayMessage.value = null
  const result = await previewRunsApi.replayResult(resultId, 'inspector replay')
  replayPending.value = false
  if (!result.ok) {
    replayMessage.value = result.message
    return
  }
  replayMessage.value = `저장 응답 재생 완료 · 새 결과 버전 ${result.data.new_version} · 외부 호출 ${result.data.external_calls}회`
  await load()
}

async function loadUndoPreview() {
  undoError.value = null
  const result = await previewRunsApi.undoReport(props.runId)
  if (!result.ok) {
    undoError.value = result.message
    return
  }
  undoPreview.value = result.data
}

async function confirmUndo() {
  undoPending.value = true
  undoError.value = null
  const result = await previewRunsApi.cancelRun(props.runId, '개발 확인 후 정리')
  undoPending.value = false
  if (!result.ok) {
    undoError.value = result.message
    return
  }
  undoPreview.value = null
  emit('cancelled')
  await load()
}

function formatTime(value: string | null): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toISOString().replace('T', ' ').replace('.000Z', 'Z')
}
</script>

<template>
  <section class="inspector" data-testid="run-inspector">
    <header class="inspector__head">
      <div>
        <h2 class="inspector__title">실행 검사</h2>
        <p class="inspector__id measured" data-testid="inspector-run-id">{{ runId }}</p>
      </div>
      <button class="button button--quiet" type="button" data-testid="inspector-close" @click="emit('closed')">
        닫기
      </button>
    </header>

    <p v-if="errorMessage" class="notice notice--error" role="alert" data-testid="inspector-error">
      {{ errorMessage }}
    </p>

    <div v-else-if="loading" class="skeleton" aria-busy="true">
      <span class="visually-hidden">실행 기록을 불러오는 중입니다.</span>
      <div class="skeleton__row" />
      <div class="skeleton__row" />
      <div class="skeleton__row" />
    </div>

    <template v-else-if="detail && summary">
      <div
        class="banner"
        :class="{ 'banner--mock': summary.mode !== 'live' }"
        data-testid="mode-banner"
      >
        <strong>{{ detail.mode_detail.label }}</strong>
        <span>{{ detail.mode_detail.note }}</span>
        <span class="banner__env measured">환경 {{ summary.environment }}</span>
      </div>

      <dl class="facts" data-testid="inspector-summary">
        <dt>상태</dt>
        <dd class="measured">{{ summary.status }} / {{ summary.quality }}</dd>
        <dt>경기</dt>
        <dd>{{ summary.fixture_label ?? '표시 정보 없음' }}</dd>
        <dt>요청 시각</dt>
        <dd class="measured">{{ formatTime(summary.requested_at) }}</dd>
        <dt>완료 시각</dt>
        <dd class="measured">{{ formatTime(summary.finished_at) }}</dd>
        <dt>모듈 실행</dt>
        <dd class="measured">{{ summary.module_count }}건</dd>
        <dt>시도 / 재시도</dt>
        <dd class="measured">{{ summary.attempt_count }} / {{ summary.retry_count }}</dd>
        <dt>계약 버전</dt>
        <dd class="measured">{{ detail.contract_versions.contract }}</dd>
        <dt>설정 버전</dt>
        <dd class="measured">{{ detail.config_version }}</dd>
      </dl>

      <p class="inspector__note" data-testid="availability-note">{{ detail.availability_note }}</p>

      <section
        v-if="sectionResults.length"
        class="section-result"
        aria-labelledby="section-result-title"
        data-testid="section-result"
      >
        <header class="section-result__head">
          <h3 id="section-result-title" class="section-result__title">
            {{ activeSectionResult?.title }}
          </h3>
          <p class="section-result__meta measured" data-testid="section-result-meta">
            {{ activeSectionResult?.workflow_id }} · v{{ activeSectionResult?.version }} ·
            {{ activeSectionResult?.mode_label }}
          </p>
        </header>

        <p
          v-if="sectionResults.length > 1"
          class="section-result__versions"
          data-testid="section-result-versions"
        >
          <button
            v-for="row in sectionResults"
            :key="row.section_result_id"
            class="section-result__version-button"
            type="button"
            :aria-current="row.section_result_id === activeSectionResult?.section_result_id"
            :data-testid="`section-result-${row.version}`"
            @click="selectedSectionResultId = row.section_result_id"
          >
            v{{ row.version }}
          </button>
        </p>

        <p
          v-if="activeSectionResult?.unavailable"
          class="notice notice--info"
          data-testid="section-result-unavailable"
        >
          이 섹션은 본문이 생성되지 않았습니다. 원인은 아래 진단에 남아 있습니다.
        </p>
        <div v-else class="section-result__body" data-testid="section-result-body">
          <p v-for="(paragraph, index) in activeSectionResult?.body.split('\n\n')" :key="index">
            {{ paragraph }}
          </p>
        </div>

        <div v-if="activeSectionResult?.sources.length" data-testid="section-result-sources">
          <h4 class="section-result__subtitle">근거</h4>
          <ul class="section-result__sources">
            <li v-for="(source, index) in activeSectionResult?.sources" :key="index">
              <a v-if="source.url" :href="source.url" rel="noreferrer noopener" target="_blank">
                {{ source.label ?? source.url }}
              </a>
              <span v-else>{{ source.label ?? '출처 표시 없음' }}</span>
              <span v-if="source.note" class="section-result__source-note">{{ source.note }}</span>
            </li>
          </ul>
        </div>
      </section>

      <nav class="module-list" aria-label="모듈 실행 목록" data-testid="module-list">
        <button
          v-for="module in detail.inspector_modules"
          :key="module.module_execution_id"
          type="button"
          class="module-list__button"
          :aria-current="module.module_execution_id === activeModuleId"
          :data-testid="`module-tab-${module.module_id}`"
          @click="activeModuleId = module.module_execution_id"
        >
          <span>{{ module.panel.display_name }}</span>
          <span class="measured module-list__status">{{ module.status }}</span>
        </button>
        <p v-if="detail.inspector_modules.length === 0" class="inspector__note">
          이 실행에는 저장된 모듈 실행이 없습니다.
        </p>
      </nav>

      <details v-if="activeModule" class="diagnostics" data-testid="node-diagnostics">
        <summary class="diagnostics__summary">
          노드·모듈 진단 정보 (요청·원문 응답·변환·다음 입력)
        </summary>
        <p class="inspector__note">
          문제를 찾을 때 펼쳐 보는 진단 영역입니다. 승인은 이 노드 단위가 아니라 섹션 워크플로우
          결과 단위로 이뤄집니다.
        </p>
        <ModuleResultPanel
          :key="activeModule.module_execution_id"
          :module="activeModule"
        />
        <AttemptPanel :attempts="activeModule.tabs.request.attempts" />
      </details>

      <RunVersionCompare
        v-if="activeModule"
        :key="`compare-${activeModule.module_execution_id}`"
        :run-id="runId"
        :module-execution-id="activeModule.module_execution_id"
      />

      <section class="approval" data-testid="inspector-approval">
        <h3 class="undo__title">섹션 워크플로우 승인</h3>
        <p class="inspector__note">{{ detail.approval_note }}</p>

        <table v-if="detail.section_approvals.length" class="table" data-testid="section-approvals">
          <caption>승인 현황 {{ detail.section_approvals.length }}개 섹션</caption>
          <thead>
            <tr>
              <th scope="col">섹션</th>
              <th scope="col">구성</th>
              <th scope="col">상태</th>
              <th scope="col">승인 근거</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in detail.section_approvals" :key="row.workflow_id">
              <td>
                <button
                  class="approval__select"
                  type="button"
                  :data-testid="`approve-section-${row.workflow_id}`"
                  @click="selectedWorkflowId = row.workflow_id"
                >
                  {{ row.display_name }}
                </button>
                <span class="approval__id measured">{{ row.workflow_id }}</span>
                <span v-if="!row.implemented" class="approval__id">
                  {{ row.unrunnable_reason }}
                </span>
              </td>
              <td class="measured">{{ row.module_ids.join(' + ') }}</td>
              <td data-testid="approval-state">{{ row.label }}</td>
              <td class="measured">
                {{ row.active_approval ? row.active_approval.workflow_version : '없음' }}
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="inspector__note" data-testid="approvals-empty">
          승인 현황을 불러오지 못했습니다.
        </p>

        <p
          v-if="detail.section_approvals.length && !approvableSectionResult"
          class="notice notice--info"
          data-testid="approval-no-evidence"
        >
          {{
            sectionResults.length
              ? '모의 시연 결과는 승인 근거가 아닙니다. 실제 생성 결과를 확인한 뒤 승인할 수 있습니다.'
              : '이 실행에는 승인 근거로 쓸 섹션 결과가 아직 없습니다. 승인은 섹션 본문 결과를 확인한 뒤에만 만들 수 있습니다.'
          }}
        </p>

        <div class="approval__form" data-testid="replay-controls">
          <p class="inspector__note">
            저장 응답 재생은 저장된 원문으로 변환만 다시 하는 동작입니다. 외부 모델을 다시
            호출하지 않으며, LangGraph 체크포인트 재실행이나 DB undo와 다릅니다.
          </p>
          <button
            class="button button--quiet"
            type="button"
            :disabled="replayPending || !activeSectionResult?.result_ids.length"
            data-testid="replay-result"
            @click="replayStoredResult"
          >
            {{ replayPending ? '재생하는 중…' : '저장 응답으로 변환 다시 하기' }}
          </button>
          <p v-if="replayMessage" class="notice notice--info" data-testid="replay-message">
            {{ replayMessage }}
          </p>
        </div>

        <div v-if="selectedWorkflowId" class="approval__form">
          <label class="label" for="approval-note">검토 메모 (선택)</label>
          <input
            id="approval-note"
            v-model="approvalNote"
            class="input"
            type="text"
            maxlength="1000"
            data-testid="approval-note"
            placeholder="결과를 어떻게 확인했는지 남깁니다"
          />
          <button
            class="button"
            type="button"
            :disabled="approvalPending"
            data-testid="approval-submit"
            @click="approveSection"
          >
            {{ approvalPending ? '승인하는 중…' : '이 섹션 버전 승인' }}
          </button>
        </div>
        <p
          v-if="approvalError"
          class="notice notice--error"
          role="alert"
          data-testid="approval-error"
        >
          {{ approvalError }}
        </p>
      </section>

      <section class="undo" data-testid="inspector-undo">
        <h3 class="undo__title">개발 기록 취소</h3>
        <p class="inspector__note">
          이 실행이 만든 preview_dev 기록만 취소합니다. 기존 경기·계정 자료와 다른 실행의 기록은
          대상이 아닙니다. 취소 표시는 감사용으로 남습니다.
        </p>

        <p
          v-if="detail.undo.state === 'cancelled'"
          class="notice notice--info"
          data-testid="undo-cancelled"
        >
          이미 취소된 실행입니다. 취소 시각 {{ formatTime(detail.undo.cancelled_at) }} · 사유
          {{ detail.undo.reason }}
        </p>
        <p
          v-else-if="detail.undo.blocked_reason"
          class="notice notice--info"
          data-testid="undo-blocked"
        >
          {{ detail.undo.blocked_reason }}
        </p>
        <template v-else>
          <button
            class="button button--quiet"
            type="button"
            data-testid="undo-preview"
            @click="loadUndoPreview"
          >
            무엇이 지워지는지 확인
          </button>
          <p v-if="undoError" class="notice notice--error" role="alert" data-testid="undo-error">
            {{ undoError }}
          </p>
          <div v-if="undoPreview" class="undo__confirm" data-testid="undo-confirm">
            <ul>
              <li v-for="(count, table) in undoPreview.would_remove" :key="table" class="measured">
                {{ table }}: {{ count }}건
              </li>
            </ul>
            <button
              class="button"
              type="button"
              data-testid="undo-confirm-button"
              :disabled="undoPending"
              @click="confirmUndo"
            >
              {{ undoPending ? '취소하는 중…' : '이 실행 기록 취소' }}
            </button>
          </div>
        </template>
      </section>
    </template>
  </section>
</template>

<style scoped>
.inspector {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.inspector__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}

.inspector__title {
  font-size: var(--text-title);
}

.inspector__id {
  font-size: var(--text-sm);
  color: var(--color-muted);
  overflow-wrap: anywhere;
}

.inspector__note {
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.banner {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-2);
  padding: var(--space-3);
  border-radius: var(--radius-control);
  border: var(--rule-hair) solid var(--color-rule-2);
  background: var(--color-paper-3);
  font-size: var(--text-sm);
  color: var(--color-ink-2);
}

.banner--mock {
  border-color: var(--color-accent);
  background: var(--color-accent-soft);
  color: var(--color-ink);
}

.banner__env {
  margin-left: auto;
  color: var(--color-muted);
}

.facts {
  display: grid;
  grid-template-columns: minmax(7rem, 10rem) 1fr;
  gap: var(--space-1) var(--space-3);
  font-size: var(--text-sm);
  margin: 0;
}

.facts dt {
  color: var(--color-muted);
}

.facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.module-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.module-list__button {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  background: var(--color-paper-3);
  border: var(--rule-hair) solid var(--color-rule);
  border-radius: var(--radius-control);
  color: var(--color-ink-2);
  font-family: var(--font-body);
  font-size: var(--text-sm);
  padding: var(--space-1) var(--space-3);
  cursor: pointer;
}

.module-list__button[aria-current='true'] {
  border-color: var(--color-accent);
  color: var(--color-ink);
}

.module-list__status {
  color: var(--color-muted);
}

.approval {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  border-top: var(--rule-hair) solid var(--color-rule);
  padding-top: var(--space-4);
}

.approval__panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  font-size: var(--text-sm);
}

.approval__state {
  color: var(--color-ink);
}

.section-result {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  border-top: var(--rule-hair) solid var(--color-rule);
  padding-top: var(--space-4);
}

.section-result__head {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.section-result__title {
  font-size: var(--text-title);
}

.section-result__meta,
.section-result__source-note {
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.section-result__versions {
  display: flex;
  gap: var(--space-2);
}

.section-result__version-button {
  background: transparent;
  border: var(--rule-hair) solid var(--color-rule);
  border-radius: var(--radius-control);
  color: var(--color-ink-2);
  cursor: pointer;
  font-family: var(--font-measured);
  font-size: var(--text-sm);
  padding: var(--space-1) var(--space-2);
}

.section-result__version-button[aria-current='true'] {
  border-color: var(--color-accent);
  color: var(--color-ink);
}

.section-result__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  max-width: 60ch;
  color: var(--color-ink);
}

.section-result__subtitle {
  font-size: var(--text-base);
}

.section-result__sources {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0;
  padding-left: var(--space-4);
  font-size: var(--text-sm);
  color: var(--color-ink-2);
}

.diagnostics {
  border-top: var(--rule-hair) solid var(--color-rule);
  padding-top: var(--space-3);
}

.diagnostics__summary {
  cursor: pointer;
  color: var(--color-ink);
  font-size: var(--text-sm);
  margin-bottom: var(--space-2);
}

.approval__id {
  display: block;
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.approval__select {
  background: transparent;
  border: 0;
  padding: 0;
  color: var(--color-accent);
  font-family: var(--font-measured);
  font-size: var(--text-sm);
  cursor: pointer;
  text-decoration: underline;
}

.approval__form {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  align-items: flex-start;
}

.approval__form .input {
  width: 100%;
}

.undo {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  border-top: var(--rule-hair) solid var(--color-rule);
  padding-top: var(--space-4);
}

.undo__title {
  font-size: var(--text-base);
}

.undo__confirm {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  font-size: var(--text-sm);
}

.undo__confirm ul {
  margin: 0;
  padding-left: var(--space-4);
  color: var(--color-ink-2);
}

@media (max-width: 40rem) {
  .facts {
    grid-template-columns: 1fr;
  }
}
</style>
