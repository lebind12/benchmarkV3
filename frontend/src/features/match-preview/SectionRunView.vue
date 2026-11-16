<script setup lang="ts">
/**
 * 섹션 워크플로우 실행 화면 (MP-05 통합).
 *
 * 사용자가 실제로 하는 일은 하나다.
 *
 *   저장된 경기 선택 -> 실행할 섹션 선택 -> 실행 -> 저장된 **본문과 근거** 확인
 *   -> (사용자가 판단한 뒤) 섹션 워크플로우 버전 승인
 *
 * 지키는 것:
 *
 * - 실행 방식(mock/live)을 화면에 항상 표시한다. 모의 시연은 승인 근거가 아니다.
 * - 승인 버튼은 사용자가 직접 눌러야 한다. 이 화면은 승인 행을 자동으로 만들지 않는다.
 * - 본문·근거를 먼저 보여주고, 노드 진단은 실행 검사 화면(`/admin/runs`)에서 펼친다.
 * - 실행되지 않은 섹션(구현 없음)은 실행 버튼을 열지 않고 그 사실을 그대로 표시한다.
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { previewRunsApi } from '@/features/match-preview/api'
import FixtureSelector from '@/features/match-preview/FixtureSelector.vue'
import BundleGenerationPanel from '@/features/match-preview/BundleGenerationPanel.vue'
import InlineEmphasis from '@/features/match-preview/InlineEmphasis.vue'
import InformationBundlePanel from '@/features/match-preview/InformationBundlePanel.vue'
import SectionRegenerationPanel from '@/features/match-preview/SectionRegenerationPanel.vue'
import CompositionPanel from '@/features/match-preview/CompositionPanel.vue'
import PlayerSectionProcessingView from '@/features/match-preview/PlayerSectionProcessingView.vue'
import SectionStructuredView from '@/features/match-preview/SectionStructuredView.vue'
import type { InformationBundleView } from '@/features/match-preview/informationBundle'
import { structuredFromSectionResult } from '@/features/match-preview/sectionStructured'
import type { FixtureCandidate } from '@/features/match-preview/fixtures'
import type {
  SectionAvailability,
  SectionAvailabilityResponse,
  SectionResultView,
  SectionRunResponse,
} from '@/features/match-preview/types'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const session = ref<{ user_id: number; role: string } | null>(null)
const loading = ref(true)
const errorMessage = ref<string | null>(null)

const selectedFixture = ref<FixtureCandidate | null>(null)
const availability = ref<SectionAvailabilityResponse | null>(null)
const selectedWorkflowId = ref<string | null>(null)
const mode = ref<'mock' | 'live'>('mock')
const running = ref(false)
const runError = ref<string | null>(null)
const runResult = ref<SectionRunResponse | null>(null)
const sectionResults = ref<SectionResultView[]>([])
const bundle = ref<InformationBundleView | null>(null)
const approvalNote = ref('')
const approving = ref(false)
const approvalError = ref<string | null>(null)
const approvalDone = ref<string | null>(null)
const replayMessage = ref<string | null>(null)
/** 구성본 실행 결과 안내(기준 실행 목록은 그대로 둔다). */
const compositionRunMessage = ref<string | null>(null)

const workflows = computed<SectionAvailability[]>(() =>
  (availability.value?.workflows ?? []).map((workflow) => ({
    workflow_id: workflow.workflow_id,
    display_name: workflow.display_name,
    module_ids: workflow.module_ids,
    output_contract_version: workflow.output_contract_version,
    implemented: workflow.implemented,
    missing_implementations: [],
    modes: [],
    demo_only: false,
    real_generation_available: false,
    note: null,
    ...(availability.value?.availability?.[workflow.workflow_id] ?? {}),
  })) as SectionAvailability[],
)

const activeWorkflow = computed(
  () => workflows.value.find((row) => row.workflow_id === selectedWorkflowId.value) ?? null,
)

/** 실제 생성 구현이 있는 섹션인지. 없으면 live 실행을 열지 않는다. */
const activeSectionReal = computed(() => Boolean(activeWorkflow.value?.real_generation_available))

const activeResult = computed<SectionResultView | null>(
  () => sectionResults.value[sectionResults.value.length - 1] ?? null,
)

const canApprove = computed(
  () =>
    Boolean(activeResult.value?.approvable) &&
    Boolean(selectedWorkflowId.value) &&
    !approving.value,
)

async function redirectToLogin() {
  const next = typeof route.fullPath === 'string' && route.fullPath.startsWith('/') ? route.fullPath : '/admin/sections'
  await router.push({ name: 'login', query: { next } })
}

async function load() {
  loading.value = true
  errorMessage.value = null
  const verified = auth.verified && auth.user ? true : await auth.verifySession()
  if (!verified || !auth.user) {
    loading.value = false
    await redirectToLogin()
    return
  }
  if (!auth.isAdmin) {
    loading.value = false
    await router.push({ name: 'not-found' })
    return
  }
  session.value = { user_id: auth.user.id, role: auth.role }

  const sectionsResult = await previewRunsApi.sections()
  loading.value = false
  if (!sectionsResult.ok) {
    if (sectionsResult.kind === 'unauthenticated') {
      auth.logout()
      await redirectToLogin()
      return
    }
    errorMessage.value = sectionsResult.message
    return
  }
  availability.value = sectionsResult.data
  const implemented = (sectionsResult.data.workflows ?? []).find(
    (workflow) => sectionsResult.data.availability?.[workflow.workflow_id]?.real_generation_available,
  )
  selectedWorkflowId.value = implemented?.workflow_id ?? null
}

function chooseFixture(fixture: FixtureCandidate) {
  selectedFixture.value = fixture
  runResult.value = null
  sectionResults.value = []
  runError.value = null
  approvalDone.value = null
  approvalError.value = null
}

function chooseWorkflow(workflowId: string) {
  selectedWorkflowId.value = workflowId
  runResult.value = null
  sectionResults.value = []
  runError.value = null
}

async function runSection() {
  const workflowId = selectedWorkflowId.value
  if (!workflowId) {
    runError.value = '실행할 섹션을 고르세요.'
    return
  }
  if (mode.value === 'live' && !activeSectionReal.value) {
    runError.value = '이 섹션은 실제 조사 구현이 아직 없어 live로 실행할 수 없습니다.'
    return
  }
  if (mode.value === 'live' && !selectedFixture.value) {
    runError.value = '실제 실행에는 저장된 경기를 먼저 선택해야 합니다.'
    return
  }

  running.value = true
  runError.value = null
  runResult.value = null
  sectionResults.value = []
  approvalDone.value = null

  const payload: Parameters<typeof previewRunsApi.runSection>[0] = {
    workflow_id: workflowId,
    mode: mode.value,
    fixture_label: selectedFixture.value?.label,
  }
  if (selectedFixture.value) {
    Object.assign(payload, {
      fixture_id: selectedFixture.value.fixture_id,
      league_id: selectedFixture.value.league_id,
      season: selectedFixture.value.season,
      home_team_id: selectedFixture.value.home_team_id ?? undefined,
      away_team_id: selectedFixture.value.away_team_id ?? undefined,
      kickoff_at: selectedFixture.value.kickoff_at,
    })
  }

  const result = await previewRunsApi.runSection(payload)
  running.value = false
  if (!result.ok) {
    runError.value = result.message
    return
  }
  runResult.value = result.data
  await loadSectionResults(result.data.run_id)
}

async function loadSectionResults(runId: string) {
  const detail = await previewRunsApi.detail(runId)
  if (!detail.ok) {
    runError.value = detail.message
    return
  }
  sectionResults.value = detail.data.section_results ?? []
}

/**
 * 정보 원문 패널이 조회한 묶음을 받는다.
 *
 * 조회는 그 패널 한 곳에서만 한다(같은 실행을 두 번 읽지 않는다). 이 값의 묶음 ID가
 * 재생성 패널의 "저장된 정보 원문 재사용"을 여는 열쇠다. 받기만 하고 실행은 하지 않는다.
 */
function onBundleLoaded(payload: InformationBundleView | null) {
  bundle.value = payload
}

/** 재생성 후 새 실행 결과를 다시 읽는다. 다른 성공 섹션은 다시 만들지 않는다. */
async function onRegenerated(payload: SectionRunResponse) {
  runResult.value = payload
  await loadSectionResults(payload.run_id)
}

/**
 * 구성본으로 **마지막 AI만** 다시 만든 결과.
 *
 * 기준 실행(구성본 원본)과 그 결과 목록은 그대로 둔다. 새 실행으로 목록을 바꾸면 방금
 * 고른 구성본의 섹션들이 화면에서 사라지기 때문이다. 새 결과는 실행 ID로만 알린다.
 */
function onCompositionRan(payload: SectionRunResponse) {
  compositionRunMessage.value =
    `마지막 AI 결과 버전 ${payload.section_result_version ?? '-'} · 실행 ${payload.run_id.slice(0, 8)} · ` +
    `전송 ${payload.external_calls}회 · 품질 ${payload.quality}`
}

/** 저장된 응답 재처리(0회) — 결과 단위 경로를 쓰고 새 결과 버전을 다시 읽는다. */
async function onReprocess(payload: { resultId: string; note: string | null }) {
  replayMessage.value = null
  const response = await previewRunsApi.replayResult(payload.resultId, payload.note ?? undefined)
  if (!response.ok) {
    approvalError.value = response.message
    return
  }
  replayMessage.value =
    `저장된 응답으로 다시 변환해 새 결과 버전 v${response.data.new_version}을 저장했습니다. ` +
    `외부 호출 ${response.data.external_calls}회(모델 호출 없음).`
  if (runResult.value) await loadSectionResults(runResult.value.run_id)
}

/** 재생성 패널의 승인 요청. 사용자가 버튼을 눌렀을 때만 도달한다. */
async function onRegeneratedApprove(payload: { sectionResultId: string; note: string | null }) {
  const workflowId = selectedWorkflowId.value
  if (!workflowId || !runResult.value) return
  approving.value = true
  approvalError.value = null
  const response = await previewRunsApi.approveSection(workflowId, {
    run_id: runResult.value.run_id,
    section_result_id: payload.sectionResultId,
    note: payload.note ?? undefined,
  })
  approving.value = false
  if (!response.ok) {
    approvalError.value = response.message
    return
  }
  approvalDone.value = '이 섹션 워크플로우 버전의 승인이 기록됐습니다.'
}

async function approve() {
  const workflowId = selectedWorkflowId.value
  const result = activeResult.value
  if (!workflowId || !result || !runResult.value) return
  if (!result.approvable) {
    approvalError.value =
      '모의 시연 결과는 승인 근거가 아닙니다. 실제 실행 본문을 확인한 뒤 승인하세요.'
    return
  }
  approving.value = true
  approvalError.value = null
  const response = await previewRunsApi.approveSection(workflowId, {
    run_id: runResult.value.run_id,
    section_result_id: result.section_result_id,
    note: approvalNote.value || undefined,
  })
  approving.value = false
  if (!response.ok) {
    approvalError.value = response.message
    return
  }
  approvalDone.value = '이 섹션 워크플로우 버전의 승인이 기록됐습니다.'
  approvalNote.value = ''
}

function openInspector() {
  if (!runResult.value) return
  router.push({ name: 'preview-runs', query: { run: runResult.value.run_id } })
}

/** 종합 섹션 결과는 독자용 프리뷰 화면에서 연다(진단은 그 화면의 접힌 영역). */
function openReaderPreview() {
  if (!runResult.value) return
  router.push({
    name: 'preview-reader',
    params: { runId: runResult.value.run_id },
  })
}

const readerPreviewAvailable = computed<boolean>(
  () => runResult.value?.workflow_id === 'section_synthesis',
)

/** 이 섹션 결과에 구조화 값이 있으면 표·목록을 더 보여준다(없으면 본문만). */
const activeStructured = computed(() =>
  activeResult.value ? structuredFromSectionResult(activeResult.value) : null,
)

/** 재사용할 저장 묶음 ID. 없으면 재사용 모드를 열지 않는다. */
const reuseBundleId = computed<string | null>(() => bundle.value?.bundleId ?? null)

onMounted(load)
</script>

<template>
  <main class="workspace">
    <header class="workspace__head">
      <h1>프리뷰 생성·섹션 실행</h1>
      <p class="hint">
        경기를 고르고 섹션을 실행하면 저장된 <strong>본문과 근거</strong>를 먼저 보여줍니다.
        노드 요청·원문 같은 진단은 실행 검사 화면에서 펼쳐 봅니다.
      </p>
    </header>

    <p v-if="loading" class="state">세션과 섹션 목록을 확인하는 중입니다.</p>
    <p v-else-if="errorMessage" class="state error" data-testid="workspace-error">
      {{ errorMessage }}
    </p>

    <template v-else>
      <BundleGenerationPanel :fixture="selectedFixture" @select="chooseFixture" />
      <section class="panel" data-testid="workspace-fixtures">
        <h2>1. 경기 선택</h2>
        <FixtureSelector @select="chooseFixture" />
        <p v-if="selectedFixture" class="chosen" data-testid="workspace-chosen-fixture">
          선택한 경기: <strong>{{ selectedFixture.label }}</strong>
          <span class="muted">
            · fixture_id {{ selectedFixture.fixture_id }} · {{ selectedFixture.kickoff_at }}
          </span>
        </p>
        <p v-else class="state" data-testid="workspace-no-fixture">
          아직 경기를 고르지 않았습니다. 위 목록에서 하나를 고르세요.
        </p>
      </section>

      <section class="panel" data-testid="workspace-sections">
        <h2>2. 섹션 선택과 실행</h2>
        <ul class="workflows">
          <li v-for="workflow in workflows" :key="workflow.workflow_id">
            <button
              type="button"
              class="workflows__button"
              :aria-current="workflow.workflow_id === selectedWorkflowId"
              :data-testid="`workspace-section-${workflow.workflow_id}`"
              @click="chooseWorkflow(workflow.workflow_id)"
            >
              <span>{{ workflow.display_name }}</span>
              <span class="muted">
                {{ workflow.real_generation_available ? '실제 구현 있음' : '실제 구현 없음' }}
              </span>
            </button>
          </li>
        </ul>

        <div v-if="activeWorkflow" class="run-controls">
          <label class="label" for="run-mode">실행 방식</label>
          <select id="run-mode" v-model="mode" data-testid="workspace-mode">
            <option value="mock">모의 시연 (외부 호출 없음, 승인 근거 아님)</option>
            <option value="live" :disabled="!activeSectionReal">
              실제 실행 (모델 호출, 승인 근거)
            </option>
          </select>
          <p v-if="!activeSectionReal" class="state" data-testid="workspace-no-real-implementation">
            이 섹션은 실제 조사·생성 구현이 아직 없습니다. 모의 시연만 실행할 수 있습니다.
          </p>
          <button
            type="button"
            class="button"
            :disabled="running"
            data-testid="workspace-run"
            @click="runSection"
          >
            {{ running ? '실행 중…' : '이 섹션 실행' }}
          </button>
          <p v-if="runError" class="state error" role="alert" data-testid="workspace-run-error">
            {{ runError }}
          </p>
        </div>
      </section>

      <section v-if="runResult" class="panel" data-testid="workspace-result">
        <h2>3. 실행 결과</h2>
        <dl class="facts">
          <dt>실행</dt>
          <dd class="measured">{{ runResult.run_id }}</dd>
          <dt>실행 방식</dt>
          <dd class="measured" data-testid="workspace-result-mode">{{ runResult.mode }}</dd>
          <dt>상태 / 품질</dt>
          <dd class="measured">{{ runResult.status }} / {{ runResult.quality }}</dd>
          <dt>외부 호출</dt>
          <dd class="measured">{{ runResult.external_calls }}회</dd>
        </dl>
        <p class="note" data-testid="workspace-result-note">{{ runResult.note }}</p>

        <template v-if="activeResult">
          <h3 class="result-title">{{ activeResult.title }}</h3>
          <p class="measured" data-testid="workspace-result-meta">
            {{ activeResult.workflow_id }} · v{{ activeResult.version }} · {{ activeResult.mode_label }}
          </p>
          <p
            v-if="activeResult.storage_mismatch"
            class="error"
            data-testid="section-storage-mismatch"
          >
            저장 불일치: {{ activeResult.storage_error || '신규 선수/부상 섹션 전용 테이블 행이 없습니다.' }}
          </p>
          <p
            v-if="activeResult.unavailable"
            class="state"
            data-testid="workspace-result-unavailable"
          >
            이 섹션은 본문이 만들어지지 않았습니다. 원인은 실행 검사 화면의 진단에 남아 있습니다.
          </p>
          <div v-else class="body" data-testid="workspace-result-body">
            <p v-for="(paragraph, index) in activeResult.body.split('\n\n')" :key="index">
              <InlineEmphasis :text="paragraph" />
            </p>
          </div>

          <div v-if="activeResult.sources.length" data-testid="workspace-result-sources">
            <h3 class="result-title">근거</h3>
            <ul class="sources">
              <li v-for="(source, index) in activeResult.sources" :key="index">
                <a v-if="source.url" :href="source.url" rel="noreferrer noopener" target="_blank">
                  {{ source.label ?? source.url }}
                </a>
                <span v-else>{{ source.label ?? '출처 표시 없음' }}</span>
                <span v-if="source.note" class="muted"> — {{ source.note }}</span>
              </li>
            </ul>
          </div>

          <!--
            구조화 표시. 서버가 구조화 값을 준 경우에만 표·목록을 더한다. 선수 이름과
            선정 이유를 분리해 보여주며, 값이 없으면 이 블록 자체가 없다.
          -->
          <SectionStructuredView
            v-if="activeStructured"
            :structured="activeStructured"
            class="structured-host"
          />

          <PlayerSectionProcessingView
            v-if="activeResult.player_section_processing"
            :processing="activeResult.player_section_processing"
          />

          <!--
            정보 원문. 본문·근거 다음에 저장된 출처를 보여주고, 전달 구간·DB 스냅샷·
            전체 모델 응답은 펼치는 진단으로 둔다. 조회 전용이다.
          -->
          <InformationBundlePanel
            v-if="runResult"
            :run-id="runResult.run_id"
            @loaded="onBundleLoaded"
            class="bundle-host"
          />

          <p v-if="compositionRunMessage" class="state ok" data-testid="workspace-composition-done">
            {{ compositionRunMessage }}
          </p>

          <p v-if="replayMessage" class="state ok" data-testid="workspace-replay-done">
            {{ replayMessage }}
          </p>

          <!--
            조정·재생성. 사용자가 동작을 고르고 눌러야만 요청이 나간다. 승인 블록은 위에
            이미 있으므로 여기서는 그리지 않는다(승인 경로 이중화 금지).
          -->
          <!--
            섹션 결과 버전 선택 → 구성본 저장 → 마지막 AI 실행. 섹션 결과가 있어야 열린다.
            저장·실행 모두 사용자가 버튼을 눌러야만 요청이 나간다.
          -->
          <CompositionPanel
            v-if="sectionResults.length && runResult"
            :key="`composition-${runResult.run_id}`"
            :run-id="runResult.run_id"
            :results="sectionResults"
            :fixture-id="selectedFixture?.fixture_id ?? null"
            class="composition-host"
            @ran="onCompositionRan"
          />

          <SectionRegenerationPanel
            v-if="selectedWorkflowId"
            :workflow-id="selectedWorkflowId"
            :fixture-id="selectedFixture?.fixture_id ?? null"
            :results="sectionResults"
            :bundle-id="reuseBundleId"
            :show-approval="false"
            class="regen-host"
            @regenerated="onRegenerated"
            @approved="onRegeneratedApprove"
            @reprocess="onReprocess"
          />

          <!--
            승인은 **마지막**이다. 사용자가 본문·근거·정보 원문을 확인하고, 필요하면
            재생성·비교를 거친 뒤 직접 누른다. 이 화면은 승인 행을 자동으로 만들지 않는다.
          -->
          <div class="approval">
            <h3 class="result-title">섹션 워크플로우 버전 승인</h3>
            <p class="note">
              승인은 위 본문·근거와 정보 원문을 직접 확인한 뒤 <strong>사용자가</strong> 누르는
              동작입니다. 개발 완료 보고나 테스트 통과는 승인이 아닙니다.
            </p>
            <p
              v-if="!activeResult.approvable"
              class="state"
              data-testid="workspace-approval-blocked"
            >
              이 결과는 승인 근거로 쓸 수 없습니다(모의 시연이거나 본문이 없음).
            </p>
            <template v-else>
              <label class="label" for="approval-note">검토 메모 (선택)</label>
              <input
                id="approval-note"
                v-model="approvalNote"
                class="input"
                type="text"
                maxlength="1000"
                data-testid="workspace-approval-note"
              />
              <button
                type="button"
                class="button"
                :disabled="!canApprove"
                data-testid="workspace-approve"
                @click="approve"
              >
                {{ approving ? '기록 중…' : '이 섹션 버전 승인' }}
              </button>
            </template>
            <p v-if="approvalError" class="state error" data-testid="workspace-approval-error">
              {{ approvalError }}
            </p>
            <p v-if="approvalDone" class="state ok" data-testid="workspace-approval-done">
              {{ approvalDone }}
            </p>
          </div>
        </template>

        <div class="workspace__actions">
          <button
            v-if="readerPreviewAvailable"
            type="button"
            class="button"
            data-testid="workspace-open-reader-preview"
            @click="openReaderPreview"
          >
            독자용 프리뷰 열기
          </button>
          <button type="button" class="button button--quiet" data-testid="workspace-open-inspector" @click="openInspector">
            실행 검사 화면에서 진단 보기
          </button>
        </div>
      </section>
    </template>
  </main>
</template>

<style scoped>
.workspace__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.workspace {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding: 1.5rem;
  max-width: 1100px;
  margin: 0 auto;
}
.workspace__head h1 {
  margin: 0 0 0.35rem;
}
.panel {
  border: 1px solid #dde2e8;
  border-radius: 0.75rem;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.workflows {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.5rem;
}
.workflows__button {
  width: 100%;
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.6rem 0.75rem;
  border: 1px solid #cdd5df;
  border-radius: 0.5rem;
  background: #fff;
  cursor: pointer;
  text-align: left;
}
.workflows__button[aria-current='true'] {
  border-color: #2b6cb0;
  box-shadow: 0 0 0 1px #2b6cb0 inset;
}
.run-controls {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-width: 34rem;
}
.body p {
  margin: 0 0 0.75rem;
  line-height: 1.7;
  /* 본문은 빈 줄로 문단을 나누고, 한 줄짜리 줄바꿈도 의미가 있다(예: R4의
     `선정 선수:` / `선정 이유:`). `pre-line`으로 줄바꿈을 그대로 살린다. */
  white-space: pre-line;
}
.sources {
  margin: 0;
  padding-left: 1.1rem;
}
.hint,
.muted,
.note {
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
  color: #8a1f1f;
}
.state.ok {
  background: #eaf7ee;
  color: #1c5c2e;
}
.facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  gap: 0.5rem 1rem;
  margin: 0;
}
.facts dt {
  font-size: 0.75rem;
  color: #566;
}
.facts dd {
  margin: 0;
}
</style>
