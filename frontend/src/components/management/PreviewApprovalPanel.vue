<script setup lang="ts">
/**
 * 관리 프리뷰 탭 내 섹션 워크플로우 버전 승인 패널.
 *
 * 저장된 프리뷰 본문·홈 반영 상태와 같은 화면에서 현재 표시 중인 섹션 결과를 단일
 * 선택으로 확인하고, 정확히 연결된 (workflow_id, run_id, section_result_id)에 대해서만
 * 워크플로우 버전 승인을 기록한다. 임의 최신 행 대체나 자동 재시도를 하지 않는다.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { previewRunsApi } from '@/features/match-preview/api'
import type { MatchPreviewView } from '@/lib/api/previewView'
import type { PreviewRunData } from '@/lib/api/preview'
import type {
  ApprovalsSummary,
  CompositionView,
  SectionApprovalRow,
  SectionApprovalStatus,
  SectionResultView,
} from '@/features/match-preview/types'

const props = defineProps<{
  openRunId: string
  runData: PreviewRunData
  previewView: MatchPreviewView | null
  composition: CompositionView | null
  compositionLoaded: boolean
  compositionError: string | null
  blockedSections: string[]
  canApproveRole: boolean
  fixtureId: number | null
  approvalsFallback?: ApprovalsSummary | null
  refreshWarning?: string | null
}>()

const emit = defineEmits<{
  approved: [payload: { runId: string; workflowId: string }]
}>()

const SECTION_ORDER = [
  'section_players',
  'section_availability',
  'section_outlook',
  'section_odds',
  'section_ai_forecast',
] as const

const SECTION_DISPLAY_NAMES: Record<string, string> = {
  section_players: '주목 선수',
  section_availability: '출전 불가·부상 변수',
  section_form_context: '최근 흐름·맞대결',
  section_odds: '배당 흐름',
  section_outlook: '매체 전망',
  section_ai_forecast: 'AI 경기 전망',
  section_synthesis: '종합 프리뷰',
}

const STATE_LABELS: Record<string, string> = {
  approved: '승인됨',
  unapproved: '미승인',
  superseded: '이전 버전 승인됨',
  reset: '초기화됨',
}

type ApprovalCandidateItem = {
  workflowId: string
  displayName: string
  statusLabel: string
  statusDetail: string | null
  activeVersion: string | null
  approvedAt: string | null
  boundRow: SectionResultView | null
  blockReason: string | null
}

const selectedWorkflowId = ref('')
const note = ref('')
const approving = ref(false)
const approvalError = ref<string | null>(null)
const approvalSuccess = ref<string | null>(null)

let contextSeq = 0
let disposed = false

onBeforeUnmount(() => {
  disposed = true
})

function orderWorkflows(ids: Iterable<string>): string[] {
  const unique = [...new Set(ids)]
  const known = SECTION_ORDER.filter((id) => unique.includes(id))
  const others = unique.filter((id) => !SECTION_ORDER.some((knownId) => knownId === id))
  return [...known, ...others]
}

function findExactRow(
  rows: SectionResultView[],
  resultId: string,
  preferredRunId?: string | null,
): SectionResultView | null {
  if (preferredRunId) {
    const exact = rows.find(
      (row) => row.section_result_id === resultId && row.run_id === preferredRunId,
    )
    if (exact) return exact
  }
  return rows.find((row) => row.section_result_id === resultId) ?? null
}

/**
 * 표시 중인 섹션에 실제로 대응하는 단일 저장 결과 행과 확정 불가 사유를 판별한다.
 * 구성본이 다른 실행(run_id)의 결과를 골랐다면 그 행과 원래 run_id를 그대로 쓴다.
 */
function resolveBoundResult(workflowId: string): {
  row: SectionResultView | null
  resolutionError: string | null
} {
  const allRows = [
    ...(props.runData.sections.section_results ?? []),
    ...(props.runData.composed_sections ?? []),
  ]
  const localRows = (props.runData.sections.section_results ?? []).filter(
    (row) => row.workflow_id === workflowId,
  )
  const shown = props.previewView?.sections[workflowId] ?? null

  if (!props.compositionLoaded) {
    return { row: null, resolutionError: '구성본 선택 결과를 확인하는 중입니다.' }
  }
  if (props.compositionError !== null) {
    return {
      row: null,
      resolutionError: `구성본 조회에 실패해 승인 대상 결과 행을 확정할 수 없습니다(${props.compositionError}).`,
    }
  }

  const activeComposition = props.composition
  if (activeComposition && activeComposition.items.length > 0) {
    const compItem = activeComposition.items.find((item) => item.section_id === workflowId)
    if (compItem) {
      const exact = findExactRow(allRows, compItem.result_id, compItem.run_id)
      if (!exact) {
        const suffix = props.runData.composed_error
          ? `(${props.runData.composed_error})`
          : ''
        return {
          row: null,
          resolutionError: `구성본이 선택한 결과 행(${compItem.result_id})을 확인하지 못해 승인할 수 없습니다${suffix}.`,
        }
      }
      return { row: exact, resolutionError: null }
    }
    if (props.runData.sections_error !== null) {
      return {
        row: null,
        resolutionError: `섹션 결과 조회에 실패해 승인 대상을 확정할 수 없습니다(${props.runData.sections_error}).`,
      }
    }
    if (localRows.length === 1) {
      return { row: localRows[0], resolutionError: null }
    }
    if (localRows.length > 1) {
      return {
        row: null,
        resolutionError: '구성본에 포함되지 않은 중복 섹션 결과 행은 승인 대상으로 확정할 수 없습니다.',
      }
    }
    return { row: null, resolutionError: '구성본 및 현재 실행에 저장된 섹션 결과가 없습니다.' }
  }

  if (props.runData.sections_error !== null) {
    return {
      row: null,
      resolutionError: `섹션 결과 조회에 실패해 승인 대상을 확정할 수 없습니다(${props.runData.sections_error}).`,
    }
  }

  if (shown) {
    if (shown.from_reader_selection) {
      return {
        row: null,
        resolutionError:
          '독자 응답에만 포함된 섹션은 저장 결과 ID(section_result_id)가 확인되지 않아 승인할 수 없습니다.',
      }
    }
    const wfRows = allRows.filter((row) => row.workflow_id === workflowId)
    if (shown.version !== null) {
      const matches = wfRows.filter((row) => row.version === shown.version)
      if (matches.length === 1) {
        return { row: matches[0], resolutionError: null }
      }
      if (matches.length > 1) {
        return {
          row: null,
          resolutionError: '동일 버전의 섹션 결과 행이 여러 건 있어 승인 대상을 하나로 확정할 수 없습니다.',
        }
      }
      return {
        row: null,
        resolutionError: `표시 중인 버전(v${shown.version})에 해당하는 저장 결과 행을 찾지 못했습니다.`,
      }
    }
    if (wfRows.length === 1) {
      return { row: wfRows[0], resolutionError: null }
    }
    if (wfRows.length > 1) {
      return {
        row: null,
        resolutionError: '표시 버전을 확정할 수 없는 다중 결과는 임의 최신 행으로 승인하지 않습니다.',
      }
    }
    return {
      row: null,
      resolutionError: '표시 중인 섹션의 저장 결과 행(section_result_id)이 없습니다.',
    }
  }

  if (localRows.length === 1) {
    return { row: localRows[0], resolutionError: null }
  }
  if (localRows.length > 1) {
    return {
      row: null,
      resolutionError: '표시되지 않은 다중 섹션 결과는 단일 대상으로 확정할 수 없습니다.',
    }
  }
  return { row: null, resolutionError: '이 실행에 저장된 섹션 결과가 없습니다.' }
}

function buildBlockReason(
  workflowId: string,
  approvalRow: SectionApprovalRow | null,
  boundRow: SectionResultView | null,
  resolutionError: string | null,
): string | null {
  if (!props.canApproveRole) {
    return '관리자(ADMIN) 권한에서만 섹션 워크플로우를 승인할 수 있습니다.'
  }
  if (props.runData.detail_error !== null) {
    return `실행 상세 조회에 실패해 승인 상태를 확인할 수 없습니다(${props.runData.detail_error}).`
  }
  if (approvalRow && approvalRow.implemented === false) {
    return approvalRow.unrunnable_reason ?? '아직 구현되지 않은 섹션 워크플로우입니다.'
  }
  if (resolutionError) {
    return resolutionError
  }
  if (!boundRow) {
    return '승인 근거로 사용할 저장 섹션 결과 행을 확인하지 못했습니다.'
  }
  if (props.blockedSections.includes(workflowId) || boundRow.storage_mismatch) {
    return '정본 저장 행 불일치(storage_mismatch) 섹션은 승인 근거로 사용할 수 없습니다.'
  }
  if (boundRow.mode === 'mock') {
    return '모의 시연(mock) 실행 결과는 승인 근거로 사용할 수 없습니다. 실제 실행 결과를 확인한 뒤 승인하세요.'
  }
  if (boundRow.unavailable || typeof boundRow.body !== 'string' || !boundRow.body.trim()) {
    return '본문이 비어 있거나 사용할 수 없는(unavailable) 섹션 결과는 승인할 수 없습니다.'
  }
  if (boundRow.approvable !== true) {
    return '서버가 승인 가능(approvable=true)으로 확인한 결과만 승인할 수 있습니다.'
  }
  return null
}

const approvalRowMap = computed(() => {
  const map = new Map<string, SectionApprovalRow>()
  for (const row of props.runData.detail?.section_approvals ?? []) {
    map.set(row.workflow_id, row)
  }
  return map
})

const fallbackWorkflowMap = computed<Record<string, SectionApprovalStatus>>(
  () => props.approvalsFallback?.workflows ?? {},
)

const candidateItems = computed<ApprovalCandidateItem[]>(() => {
  const ids = orderWorkflows([
    ...approvalRowMap.value.keys(),
    ...Object.keys(fallbackWorkflowMap.value),
    ...(props.composition?.items.map((item) => item.section_id) ?? []),
    ...(props.runData.sections.section_results ?? []).map((row) => row.workflow_id),
    ...(props.runData.composed_sections ?? []).map((row) => row.workflow_id),
    ...Object.keys(props.previewView?.sections ?? {}),
  ])

  return ids.map((workflowId) => {
    const approvalRow = approvalRowMap.value.get(workflowId) ?? null
    const fallbackStatus = fallbackWorkflowMap.value[workflowId] ?? null
    const shown = props.previewView?.sections[workflowId] ?? null
    const { row: boundRow, resolutionError } = resolveBoundResult(workflowId)
    const blockReason = buildBlockReason(workflowId, approvalRow, boundRow, resolutionError)

    const displayName =
      approvalRow?.display_name ||
      shown?.title ||
      boundRow?.title ||
      SECTION_DISPLAY_NAMES[workflowId] ||
      workflowId

    let statusLabel = '상태 미확인'
    let statusDetail: string | null = null
    let activeVersion: string | null = null
    let approvedAt: string | null = null

    if (props.runData.detail_error !== null && !fallbackStatus) {
      statusLabel = '조회 오류'
    } else if (approvalRow) {
      statusLabel = approvalRow.label || STATE_LABELS[approvalRow.state] || approvalRow.state
      statusDetail = approvalRow.detail
      activeVersion = approvalRow.active_approval?.workflow_version ?? null
      approvedAt = approvalRow.active_approval?.approved_at ?? null
    } else if (fallbackStatus) {
      statusLabel = STATE_LABELS[fallbackStatus.state] ?? fallbackStatus.state
      activeVersion = fallbackStatus.active_approval?.workflow_version ?? null
      approvedAt = fallbackStatus.active_approval?.approved_at ?? null
    }

    return {
      workflowId,
      displayName,
      statusLabel,
      statusDetail,
      activeVersion,
      approvedAt,
      boundRow,
      blockReason,
    }
  })
})

watch(
  candidateItems,
  (items) => {
    if (!items.length) {
      selectedWorkflowId.value = ''
      return
    }
    if (items.some((item) => item.workflowId === selectedWorkflowId.value)) return
    const firstEligible = items.find((item) => item.blockReason === null)
    selectedWorkflowId.value = (firstEligible ?? items[0]).workflowId
  },
  { immediate: true },
)

watch(
  [() => props.openRunId, () => props.fixtureId, selectedWorkflowId],
  () => {
    contextSeq += 1
    approving.value = false
    approvalError.value = null
    approvalSuccess.value = null
    note.value = ''
  },
)

const selectedItem = computed<ApprovalCandidateItem | null>(
  () => candidateItems.value.find((item) => item.workflowId === selectedWorkflowId.value) ?? null,
)

function selectWorkflow(workflowId: string) {
  selectedWorkflowId.value = workflowId
}

function formatMoment(iso: string | null): string {
  if (!iso) return '미기록'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(date)
}

async function submitApproval() {
  const item = selectedItem.value
  if (!item || !item.boundRow || item.blockReason !== null || approving.value) return

  const requestContextSeq = contextSeq
  const requestRunId = props.openRunId
  const requestFixtureId = props.fixtureId
  const targetWorkflowId = item.workflowId
  const targetSourceRunId = item.boundRow.run_id
  const targetResultId = item.boundRow.section_result_id
  const targetWorkflowVersion = item.boundRow.workflow_version
  const trimmedNote = note.value.trim()

  approving.value = true
  approvalError.value = null
  approvalSuccess.value = null

  const response = await previewRunsApi.approveSection(targetWorkflowId, {
    run_id: targetSourceRunId,
    section_result_id: targetResultId,
    note: trimmedNote || undefined,
  })

  if (
    disposed ||
    requestContextSeq !== contextSeq ||
    props.openRunId !== requestRunId ||
    props.fixtureId !== requestFixtureId ||
    selectedWorkflowId.value !== targetWorkflowId
  ) {
    return
  }

  approving.value = false

  if (!response.ok) {
    approvalError.value = response.message
    return
  }

  note.value = ''
  const approvedVersion = response.data.workflow_version ?? targetWorkflowVersion
  approvalSuccess.value = `${item.displayName}(${targetWorkflowId}) ${approvedVersion} 승인이 기록됐습니다. 승인 상태와 홈 반영을 다시 확인합니다.`
  emit('approved', { runId: requestRunId, workflowId: targetWorkflowId })
}
</script>

<template>
  <section
    class="preview-approval"
    data-testid="preview-approval"
    aria-labelledby="preview-approval-title"
  >
    <header class="preview-approval__head">
      <div>
        <h3 id="preview-approval-title">섹션 워크플로우 승인</h3>
        <p class="preview-approval__scope" data-testid="preview-approval-scope-note">
          승인은 <strong>경기별 승인이 아니라 섹션 워크플로우 버전 단위</strong>입니다. 승인하면
          현재 버전과 구성 모듈·출력 계약이 이후 모든 경기의 기본 프리뷰 생성 및 홈 공개 기준에
          적용되며, 아래에서 고른 단일 표시 결과 행을 승인 근거로 기록합니다.
        </p>
      </div>
    </header>

    <div
      v-if="candidateItems.length"
      class="preview-approval__list"
      role="group"
      aria-label="승인할 섹션 워크플로우 선택"
      data-testid="preview-approval-list"
    >
      <button
        v-for="item in candidateItems"
        :key="item.workflowId"
        type="button"
        class="preview-approval__item"
        :class="{ 'is-selected': item.workflowId === selectedWorkflowId }"
        :aria-pressed="item.workflowId === selectedWorkflowId"
        :data-selected="item.workflowId === selectedWorkflowId ? 'true' : 'false'"
        :data-testid="`preview-approval-item-${item.workflowId}`"
        @click="selectWorkflow(item.workflowId)"
      >
        <div class="preview-approval__item-top">
          <strong>{{ item.displayName }}</strong>
          <span class="preview-approval__badge">{{ item.statusLabel }}</span>
        </div>
        <div class="preview-approval__item-meta">
          <span>{{ item.workflowId }}</span>
          <span v-if="item.activeVersion">활성 승인 {{ item.activeVersion }}</span>
          <span v-else>활성 승인 없음</span>
        </div>
        <div class="preview-approval__item-meta">
          <template v-if="item.boundRow">
            <span>{{ item.boundRow.mode_label || item.boundRow.mode }}</span>
            <span>{{ item.boundRow.workflow_version }} (v{{ item.boundRow.version }})</span>
            <span v-if="item.boundRow.run_id !== openRunId">
              구성본 원본 실행 {{ item.boundRow.run_id }}
            </span>
          </template>
          <span v-else>연결된 결과 행 미확정</span>
        </div>
      </button>
    </div>
    <p v-else class="preview-approval__hint">승인 상태를 확인할 섹션이 없습니다.</p>

    <div
      v-if="selectedItem"
      class="preview-approval__selected"
      data-testid="preview-approval-selected"
    >
      <div class="preview-approval__summary">
        <strong>{{ selectedItem.displayName }}</strong>
        <span class="preview-approval__muted">{{ selectedItem.workflowId }}</span>
        <span class="preview-approval__badge">{{ selectedItem.statusLabel }}</span>
      </div>

      <p v-if="selectedItem.statusDetail" class="preview-approval__hint">
        {{ selectedItem.statusDetail }}
      </p>

      <dl class="preview-approval__facts">
        <dt>현재 활성 승인 버전</dt>
        <dd data-testid="preview-approval-active-version">
          {{ selectedItem.activeVersion ?? '없음' }}
          <template v-if="selectedItem.approvedAt">
            ({{ formatMoment(selectedItem.approvedAt) }})
          </template>
        </dd>
        <dt>승인 근거 실행 ID</dt>
        <dd data-testid="preview-approval-target-run">
          <template v-if="selectedItem.boundRow">
            {{ selectedItem.boundRow.run_id }}
            <span v-if="selectedItem.boundRow.run_id !== openRunId">
              (구성본이 선택한 다른 실행)
            </span>
          </template>
          <template v-else>미확정</template>
        </dd>
        <dt>승인 근거 섹션 결과</dt>
        <dd data-testid="preview-approval-target-result">
          <template v-if="selectedItem.boundRow">
            {{ selectedItem.boundRow.section_result_id }} ·
            {{ selectedItem.boundRow.workflow_version }} (v{{ selectedItem.boundRow.version }}) ·
            {{ selectedItem.boundRow.mode_label || selectedItem.boundRow.mode }} ·
            {{ selectedItem.boundRow.quality }}
          </template>
          <template v-else>미확정</template>
        </dd>
      </dl>

      <p
        v-if="selectedItem.blockReason"
        class="preview-approval__blocked"
        role="alert"
        data-testid="preview-approval-blocked-reason"
      >
        {{ selectedItem.blockReason }}
      </p>

      <div class="preview-approval__actions">
        <label class="preview-approval__note-field">
          <span>검토 메모 (선택)</span>
          <input
            v-model="note"
            type="text"
            placeholder="이 버전을 승인하는 이유나 확인 내용을 남기세요"
            :disabled="approving || selectedItem.blockReason !== null"
            data-testid="preview-approval-note"
          />
        </label>
        <button
          type="button"
          class="mm-button mm-button--primary"
          :disabled="approving || selectedItem.blockReason !== null"
          data-testid="preview-approval-submit"
          @click="submitApproval"
        >
          {{ approving ? '승인 저장 중…' : '이 섹션 버전 승인' }}
        </button>
      </div>

      <p
        v-if="approvalError"
        class="preview-approval__alert"
        role="alert"
        data-testid="preview-approval-error"
      >
        {{ approvalError }}
      </p>
      <p
        v-if="approvalSuccess"
        class="preview-approval__done"
        role="status"
        data-testid="preview-approval-success"
      >
        {{ approvalSuccess }}
      </p>
      <p
        v-if="refreshWarning"
        class="preview-approval__alert"
        role="alert"
        data-testid="preview-approval-refresh-warning"
      >
        {{ refreshWarning }}
      </p>
    </div>
  </section>
</template>

<style scoped>
.preview-approval {
  display: grid;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-card);
  min-width: 0;
}

.preview-approval__head h3 {
  margin: 0 0 6px;
  font-size: 15px;
}

.preview-approval__scope,
.preview-approval__hint {
  margin: 0;
  color: var(--color-muted);
  font-size: 13px;
  line-height: 1.55;
}

.preview-approval__list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 8px;
}

.preview-approval__item {
  display: grid;
  gap: 4px;
  text-align: left;
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg);
  color: var(--color-fg);
  font: inherit;
  cursor: pointer;
}

.preview-approval__item.is-selected {
  border-color: var(--color-fg);
  box-shadow: inset 0 0 0 1px var(--color-fg);
}

.preview-approval__item-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.preview-approval__item-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12px;
  color: var(--color-muted);
}

.preview-approval__badge {
  display: inline-block;
  padding: 2px 7px;
  border-radius: 999px;
  border: 1px solid var(--color-border);
  background: var(--color-card);
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

.preview-approval__selected {
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg);
}

.preview-approval__summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.preview-approval__muted {
  color: var(--color-muted);
  font-size: 12px;
}

.preview-approval__facts {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 4px 12px;
  margin: 0;
  font-size: 12px;
}

.preview-approval__facts dt {
  color: var(--color-muted);
}

.preview-approval__facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.preview-approval__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: flex-end;
}

.preview-approval__note-field {
  display: grid;
  gap: 4px;
  flex: 1 1 240px;
  font-size: 12px;
  color: var(--color-muted);
}

.preview-approval__note-field input {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-bg);
  color: var(--color-fg);
  font: inherit;
}

.preview-approval__blocked,
.preview-approval__alert {
  margin: 0;
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-left: 3px solid #dc2626;
  border-radius: 6px;
  font-size: 13px;
}

.preview-approval__done {
  margin: 0;
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-left: 3px solid #16a34a;
  border-radius: 6px;
  font-size: 13px;
}
</style>
