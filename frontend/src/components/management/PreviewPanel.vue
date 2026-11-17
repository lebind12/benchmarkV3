<script setup lang="ts">
/**
 * 원래 관리 화면의 **프리뷰 탭** (BI-03).
 *
 * 사용자가 하는 일은 하나의 흐름이다.
 *
 *   API-Football 경기 번호 입력 → 저장된 대진·시각 확인 → 명시적 생성 클릭 →
 *   DB에 저장된 본문 확인 → (필요하면) 진단 펼치기
 *
 * 지키는 것:
 *
 * - **화면 진입은 아무것도 만들지 않는다.** 진입·번호 확인·다시 읽기·실행 열기·이력은 GET만이다.
 *   생성(POST)은 사용자가 생성 버튼을 누를 때 한 번만 나가고, 통신 오류를 자동 재전송하지 않는다.
 * - 확인한 번호와 지금 입력이 다르면 생성하지 않는다. 늦게 도착한 이전 응답은 버린다.
 * - 본문을 먼저 보여주고, 원문·전송 기록·재생성 같은 진단은 **사용자가 펼칠 때만** 마운트한다.
 * - 이 탭은 다른 관리 API(수집 대상·실행·번역)를 읽지 않는다. 그 조회가 실패해도 프리뷰는 열린다.
 * - `quality`/`complete` 같은 저장 표기는 진단일 뿐이다. 부분 결과라도 받은 본문을 숨기지
 *   않고, 새 모델 호출을 자동으로 만들지 않는다.
 * - 재생성 정책 문구는 "경기 한 번에 각 모듈 최초 포함 3회"다. 전체 8회·시험집합 누적 표현을 쓰지 않는다.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  generatePreview,
  getPreviewFixture,
  getPreviewRun,
  getPreviewComposition,
  listPreviewRuns,
  type PreviewRunData,
} from '@/lib/api/preview'
import { toMatchPreviewView, storageMismatchSections, withoutBlockedSections } from '@/lib/api/previewView'
import { getHomePreviewDocument, getHomeRecommendations } from '@/lib/api/homePreview'
import type { HomePreviewDocument } from '@/lib/api/homePreviewDocument'
import type { HomeRecommendations } from '@/lib/api/homeRecommendationsSchema'
import type { FixtureCandidate } from '@/features/match-preview/fixtures'
import { previewRunsApi } from '@/features/match-preview/api'
import { parseInformationBundle } from '@/features/match-preview/informationBundle'
import type {
  ApprovalsSummary,
  CompositionView,
  RunSummary,
  SectionRunResponse,
} from '@/features/match-preview/types'
import MatchPreviewBody from '@/components/home-preview/MatchPreviewBody.vue'
import InformationBundlePanel from '@/features/match-preview/InformationBundlePanel.vue'
import CompositionPanel from '@/features/match-preview/CompositionPanel.vue'
import SectionRegenerationPanel from '@/features/match-preview/SectionRegenerationPanel.vue'
import RunInspector from '@/features/match-preview/RunInspector.vue'
import PreviewApprovalPanel from '@/components/management/PreviewApprovalPanel.vue'
import PreviewTestPanel from '@/components/management/PreviewTestPanel.vue'

const props = withDefaults(
  defineProps<{
    /** ADMIN만 생성 UI를 연다. 서버도 같은 판정을 한다(BI-01). */
    canGenerate?: boolean
  }>(),
  { canGenerate: false },
)

const SECTION_ORDER = [
  'section_players',
  'section_availability',
  'section_outlook',
  'section_odds',
  'section_ai_forecast',
] as const

const fixtureNumber = ref('')
const checking = ref(false)
const checkedFixture = ref<FixtureCandidate | null>(null)
const lookupError = ref<string | null>(null)

const generating = ref(false)
const generateError = ref<string | null>(null)
/** 생성 중 화면에 남기는 "시작한 경기". 응답이 늦어도 무엇을 돌렸는지 안다. */
const startedFixture = ref<FixtureCandidate | null>(null)

const openRunId = ref<string | null>(null)
const openedFixtureId = ref<number | null>(null)
const openedKickoffAt = ref<string | null>(null)
const runData = ref<PreviewRunData | null>(null)
const runLoading = ref(false)
const runError = ref<string | null>(null)
const readVersion = ref(0)

const homeReflectionLoading = ref(false)
const homeReflectionFixtureId = ref<number | null>(null)
const homeReflectionKickoffAt = ref<string | null>(null)
const homeDoc = ref<HomePreviewDocument | null>(null)
const homeDocError = ref<string | null>(null)
const homeRec = ref<HomeRecommendations | null>(null)
const homeRecError = ref<string | null>(null)
let homeReflectionSequence = 0

const directRunId = ref('')
const directRunError = ref<string | null>(null)

const historyOpen = ref(false)
const history = ref<RunSummary[]>([])
const historyLoading = ref(false)
const historyError = ref<string | null>(null)

const approvalsFallback = ref<ApprovalsSummary | null>(null)
const approvalRefreshWarning = ref<string | null>(null)

const composition = ref<CompositionView | null>(null)
const compositionNote = ref<string | null>(null)
const compositionLoaded = ref(false)
const compositionError = ref<string | null>(null)
let compositionSequence = 0

const diagnosticsOpen = ref(false)
const bundleOpen = ref(false)
const inspectorOpen = ref(false)
const regenerationOpen = ref(false)
const selectedSectionId = ref<string>('')

const route = useRoute()
const router = useRouter()

/**
 * 이 탭의 실행 ID는 **전용 쿼리**(`previewRun`)로만 다룬다.
 *
 * 원래 관리 화면은 `run`/`retry` 쿼리를 수집 실행에 쓴다. 같은 키를 쓰면 수집 실행 이동과
 * 섞이므로 프리뷰는 자기 키만 읽고 쓴다. 주소를 복사해도 같은 저장 결과가 열린다.
 */
const PREVIEW_RUN_QUERY = 'previewRun'

/** 늦은 응답을 버리기 위한 순번. 번호를 바꾸면 이전 순번의 응답은 화면에 닿지 않는다. */
let lookupSequence = 0
let openSequence = 0
let disposed = false

const fixtureId = computed(() => {
  const raw = fixtureNumber.value.trim()
  const value = Number(raw)
  return /^\d+$/.test(raw) && Number.isSafeInteger(value) && value > 0 ? value : null
})

const confirmed = computed<FixtureCandidate | null>(() =>
  checkedFixture.value !== null && checkedFixture.value.fixture_id === fixtureId.value
    ? checkedFixture.value
    : null,
)

const canGenerateNow = computed(
  () =>
    props.canGenerate &&
    confirmed.value?.selectable === true &&
    !generating.value &&
    !checking.value,
)

const previewView = computed(() => {
  const data = runData.value
  if (!data) return null
  const view = toMatchPreviewView({
    ...data,
    fixture: data.run_id === openRunId.value ? startedFixture.value : null,
  })
  // 정본 저장 불일치 섹션은 정상 카드·본문을 그리지 않는다(아래 경고와 접힌 진단으로만 확인).
  const blocked = data.run_id === openRunId.value ? blockedSections.value : []
  return withoutBlockedSections(view, blocked)
})

/**
 * 이 실행에서 **정본 저장 행을 찾지 못한** 섹션. 저장 결과를 다시 읽은 값에서만 판정한다.
 *
 * `storage_mismatch`는 "생성 응답은 왔지만 정본 표에 행이 없다"는 뜻이다. 이 값을 정상
 * 문서로 그리면 사용자가 저장되지 않은 결과를 저장된 것으로 읽으므로, 위 `previewView`가
 * 해당 섹션을 비우고 아래 경고가 그 사실을 알린다.
 */
const blockedSections = computed(() =>
  runData.value ? storageMismatchSections(runData.value.sections) : [],
)

/** 불일치 섹션의 저장된 행. 원문 참고 진단에만 쓰고 본문에는 넣지 않는다. */
const blockedRows = computed(() => {
  const blocked = new Set(blockedSections.value)
  return (runData.value?.sections.section_results ?? []).filter((row) =>
    blocked.has(row.workflow_id),
  )
})

const blockedReason = computed(() => {
  const reasons = blockedRows.value
    .map((row) => (typeof row.storage_error === 'string' ? row.storage_error.trim() : ''))
    .filter((row) => row.length > 0)
  // 서버가 저장 오류 문장을 주지 않으면 섹션 이름만 알리고 사유를 지어내지 않는다.
  return reasons.length > 0 ? reasons.join(' / ') : null
})

const runFixtureLabel = computed(
  () => startedFixture.value?.label ?? previewView.value?.fixture.label ?? '경기 미상',
)

/** 저장된 섹션 결과를 표시 순서로. 모르는 섹션은 뒤에 붙인다. */
const storedSections = computed(() => {
  const rows = runData.value?.sections.section_results ?? []
  const known = SECTION_ORDER.flatMap((id) => rows.filter((row) => row.workflow_id === id))
  const others = rows.filter(
    (row) => !SECTION_ORDER.some((id) => id === row.workflow_id),
  )
  return [...known, ...others]
})

const openRunFixtureId = computed<number | null>(
  () =>
    runData.value?.preview?.fixture.fixture_id ??
    runData.value?.detail?.fixture?.fixture_id ??
    startedFixture.value?.fixture_id ??
    openedFixtureId.value ??
    null,
)

const homeRecMatch = computed(() => {
  const fid = homeReflectionFixtureId.value
  if (fid === null || !homeRec.value) return null
  return homeRec.value.items.find((item) => item.fixture_id === fid) ?? null
})

type ExpectedSectionRef = {
  workflow_id: string
  section_result_id: string | null
}

type ExpectedSectionsState =
  | { state: 'none' }
  | { state: 'loading' }
  | { state: 'unverified'; reason: string }
  | { state: 'ready'; source: 'composition' | 'run'; items: ExpectedSectionRef[] }

type SectionDiffStatus = 'matched' | 'missing' | 'version_mismatch' | 'extra' | 'unverified'

type HomeSectionDiffItem = {
  workflow_id: string
  status: SectionDiffStatus
  label: string
  expectedId: string | null
  actualId: string | null
}

function orderWorkflowIds(ids: Iterable<string>): string[] {
  const unique = [...new Set(ids)]
  const known = SECTION_ORDER.filter((id) => unique.includes(id))
  const others = unique.filter((id) => !SECTION_ORDER.some((knownId) => knownId === id))
  return [...known, ...others]
}

const expectedRunSections = computed<ExpectedSectionsState>(() => {
  const runId = openRunId.value
  const data = runData.value
  if (!runId || !data || data.run_id !== runId) {
    return { state: 'none' }
  }
  if (!compositionLoaded.value) {
    return { state: 'loading' }
  }
  if (compositionError.value !== null) {
    return {
      state: 'unverified',
      reason: `구성본을 확인하지 못했습니다(${compositionError.value})`,
    }
  }
  const activeComposition = composition.value
  if (activeComposition && activeComposition.items.length > 0) {
    const byWorkflow = new Map<string, string>()
    for (const item of activeComposition.items) {
      if (item.unavailable || item.body_chars <= 0) continue
      if (!byWorkflow.has(item.section_id)) {
        byWorkflow.set(item.section_id, item.result_id)
      }
    }
    const items = orderWorkflowIds(byWorkflow.keys()).map((workflow_id) => ({
      workflow_id,
      section_result_id: byWorkflow.get(workflow_id) ?? null,
    }))
    return { state: 'ready', source: 'composition', items }
  }
  if (data.sections_error !== null) {
    return {
      state: 'unverified',
      reason: `열린 실행의 섹션 결과를 읽지 못했습니다(${data.sections_error})`,
    }
  }

  const blocked = new Set(blockedSections.value)
  const candidates = [
    ...(data.sections.section_results ?? []),
    ...(data.composed_sections ?? []),
  ].filter(
    (row) =>
      !blocked.has(row.workflow_id) &&
      !row.storage_mismatch &&
      !row.unavailable &&
      typeof row.body === 'string' &&
      row.body.trim().length > 0,
  )

  const byWorkflow = new Map<string, (typeof candidates)[number][]>()
  for (const row of candidates) {
    const list = byWorkflow.get(row.workflow_id) ?? []
    list.push(row)
    byWorkflow.set(row.workflow_id, list)
  }

  const shown = previewView.value?.sections ?? {}
  const workflowIds = orderWorkflowIds([
    ...byWorkflow.keys(),
    ...Object.entries(shown)
      .filter(([, sec]) => typeof sec.body === 'string' && sec.body.trim().length > 0)
      .map(([wf]) => wf),
  ])

  const items: ExpectedSectionRef[] = []
  for (const workflow_id of workflowIds) {
    const rows = byWorkflow.get(workflow_id) ?? []
    const shownVersion = shown[workflow_id]?.version ?? null
    let chosen =
      shownVersion !== null ? rows.find((row) => row.version === shownVersion) : undefined
    if (!chosen && rows.length > 0) {
      chosen = [...rows].sort((a, b) => {
        if (b.version !== a.version) return b.version - a.version
        return (b.created_at ?? '').localeCompare(a.created_at ?? '')
      })[0]
    }
    if (chosen) {
      items.push({ workflow_id, section_result_id: chosen.section_result_id })
    } else if (shown[workflow_id]) {
      items.push({ workflow_id, section_result_id: null })
    }
  }

  if (data.composed_error && items.some((item) => item.section_result_id === null)) {
    return {
      state: 'unverified',
      reason: `구성본 선택 섹션 결과를 읽지 못했습니다(${data.composed_error})`,
    }
  }
  return { state: 'ready', source: 'run', items }
})

const homeSectionComparison = computed(() => {
  const doc = homeDoc.value
  if (!doc || doc.status !== 'available') return null
  const expected = expectedRunSections.value
  if (expected.state === 'none') return null
  if (expected.state === 'loading') {
    return { status: 'loading' as const, reason: null, items: [] as HomeSectionDiffItem[] }
  }
  if (expected.state === 'unverified') {
    return {
      status: 'unverified' as const,
      reason: expected.reason,
      items: [] as HomeSectionDiffItem[],
    }
  }

  const expectedMap = new Map(expected.items.map((item) => [item.workflow_id, item]))
  const actualMap = new Map<string, (typeof doc.sections)[number]>()
  for (const sec of doc.sections) {
    if (!actualMap.has(sec.workflow_id)) {
      actualMap.set(sec.workflow_id, sec)
    }
  }

  const orderedWorkflows = orderWorkflowIds([...expectedMap.keys(), ...actualMap.keys()])
  const items: HomeSectionDiffItem[] = []
  for (const workflow_id of orderedWorkflows) {
    const exp = expectedMap.get(workflow_id)
    const pub = actualMap.get(workflow_id)
    if (exp && !pub) {
      items.push({
        workflow_id,
        status: 'missing',
        label: '누락',
        expectedId: exp.section_result_id,
        actualId: null,
      })
    } else if (!exp && pub) {
      items.push({
        workflow_id,
        status: 'extra',
        label: '추가 반영',
        expectedId: null,
        actualId: pub.section_result_id,
      })
    } else if (exp && pub) {
      if (!exp.section_result_id || !pub.section_result_id) {
        items.push({
          workflow_id,
          status: 'unverified',
          label: '확인 불가',
          expectedId: exp.section_result_id,
          actualId: pub.section_result_id,
        })
      } else if (exp.section_result_id === pub.section_result_id) {
        items.push({
          workflow_id,
          status: 'matched',
          label: '일치',
          expectedId: exp.section_result_id,
          actualId: pub.section_result_id,
        })
      } else {
        items.push({
          workflow_id,
          status: 'version_mismatch',
          label: '다른 버전',
          expectedId: exp.section_result_id,
          actualId: pub.section_result_id,
        })
      }
    }
  }

  if (items.some((item) => item.status === 'unverified')) {
    return { status: 'unverified' as const, reason: '섹션 결과 ID를 대조할 수 없습니다.', items }
  }
  if (items.some((item) => item.status === 'version_mismatch' || item.status === 'extra')) {
    return { status: 'mismatch' as const, reason: null, items }
  }
  if (items.some((item) => item.status === 'missing')) {
    return { status: 'partial_missing' as const, reason: null, items }
  }
  return { status: 'exact' as const, reason: null, items }
})

const homeDocumentReflectionText = computed(() => {
  if (homeReflectionLoading.value) return '홈 공개 문서를 확인하는 중…'
  if (homeDocError.value) {
    return `홈 공개 문서를 읽지 못했습니다: ${homeDocError.value} (문서 없음이 아닙니다)`
  }
  const doc = homeDoc.value
  if (!doc) return '홈 공개 문서를 아직 확인하지 않았습니다.'
  if (doc.status === 'none') {
    const reasonMap: Record<string, string> = {
      no_approved_version: '승인된 섹션 버전이 없어 홈에 미반영 상태입니다(no_approved_version).',
      no_stored_run: '저장된 실행이 없어 홈에 미반영 상태입니다(no_stored_run).',
      no_displayable_section: '표시 가능한 섹션 본문이 없어 홈에 미반영 상태입니다(no_displayable_section).',
    }
    return (
      reasonMap[doc.reason ?? ''] ??
      doc.reason_text ??
      doc.reason ??
      '홈에 표시되는 문서가 없습니다.'
    )
  }
  const requiredSummary = doc.complete
    ? `필수 섹션 완전 반영(complete=true · 홈 섹션 ${doc.sections.length}개)`
    : `필수 섹션 부분 반영(complete=false · 홈 섹션 ${doc.sections.length}개)`
  const comparison = homeSectionComparison.value
  if (!comparison) {
    return `홈에 저장 실행(${doc.run_id ?? '미상'})이 반영되어 있습니다 · ${requiredSummary}`
  }
  if (comparison.status === 'loading') {
    return `열린 실행(${openRunId.value}) 섹션·구성본과 홈(${doc.run_id ?? '미상'}) 대조 중… · ${requiredSummary}`
  }
  if (comparison.status === 'unverified') {
    return `열린 실행(${openRunId.value})과 대조 미확인(${comparison.reason}) · 홈 run: ${doc.run_id ?? '미상'} · ${requiredSummary}`
  }
  if (comparison.status === 'exact') {
    if (openRunId.value && doc.run_id === openRunId.value) {
      return `현재 연 실행(${doc.run_id})의 섹션 결과 ID까지 홈과 일치합니다 · ${requiredSummary}`
    }
    return `열린 구성·선택 섹션 결과가 홈(${doc.run_id ?? '미상'})에 모두 일치 반영되었습니다 · ${requiredSummary}`
  }
  if (comparison.status === 'partial_missing') {
    const missingNames = comparison.items
      .filter((item) => item.status === 'missing')
      .map((item) => item.workflow_id)
      .join(', ')
    return `홈(${doc.run_id ?? '미상'})에 열린 결과의 섹션(${missingNames})이 누락되었습니다 · ${requiredSummary}`
  }
  return `홈(${doc.run_id ?? '미상'})에 열린 결과와 다른 버전 또는 차이가 있습니다 · ${requiredSummary}`
})

const hasUnresolvedPlayers = computed(() => {
  const viewPlayers = previewView.value?.players ?? []
  const viewInjuries = previewView.value?.injuries ?? []
  if (
    viewPlayers.some((row) => !row.photo_url) ||
    viewInjuries.some((row) => !row.photo_url)
  ) {
    return true
  }
  for (const section of homeDoc.value?.sections ?? []) {
    const structured = section.structured as Record<string, unknown> | null | undefined
    if (!structured) continue
    for (const key of ['players', 'injuries'] as const) {
      const items = structured[key]
      if (!Array.isArray(items)) continue
      for (const raw of items) {
        if (!raw || typeof raw !== 'object') continue
        const item = raw as Record<string, unknown>
        if (
          item.unresolved === true ||
          item.external_player_id === null ||
          item.external_player_id === undefined ||
          !item.photo_url
        ) {
          return true
        }
      }
    }
  }
  return false
})

const sectionChoices = computed(() =>
  SECTION_ORDER.filter((id) => storedSections.value.some((row) => row.workflow_id === id)),
)

const regenerationResults = computed(() =>
  storedSections.value.filter((row) => row.workflow_id === selectedSectionId.value),
)

/**
 * 재생성 뒤에도 **그대로 남길** 다른 섹션 결과 ID(지금 화면이 보여주는 버전).
 *
 * 화면이 표시 중인 버전(`previewView.sections[].version`)과 같은 버전의 저장 행에서
 * 결과 ID를 고른다. 그래야 새 run의 구성본이 지금 읽고 있는 본문을 유지하고, 이 패널이
 * 다시 만든 섹션만 교체된다. 이 실행의 행이 없는(reader 응답에만 있는) 섹션은 결과 ID를
 * 알 수 없으므로 보내지 않는다 — 추측한 ID를 만들지 않는다.
 */
const otherSectionResultIds = computed<string[]>(() => {
  const shown = previewView.value?.sections ?? {}
  const ids: string[] = []
  for (const [sectionId, section] of Object.entries(shown)) {
    if (sectionId === selectedSectionId.value) continue
    const version = section.version
    if (version === null) continue
    const row = storedSections.value.find(
      (item) => item.workflow_id === sectionId && item.version === version,
    )
    if (row) ids.push(row.section_result_id)
  }
  return ids
})

/**
 * 이 실행의 `/section-results`에는 없고 **reader 응답에만 있는** 섹션.
 *
 * 두 경우가 있다. 둘 다 "이 실행의 행 목록에 없다"는 사실은 같지만 사유가 다르므로
 * 화면 문구를 나눈다(조회 실패를 구성본 선택으로 표현하지 않는다).
 *
 * - 구성본이 다른 실행의 결과를 골랐다 → 그 본문은 이 실행의 행 목록에 없다.
 * - 섹션 결과 조회가 실패했다 → 행 목록 자체를 확인하지 못했다.
 *
 * 화면 본문은 `previewView.sections`가 reader 블록으로 채우고, 이 값은 같은 본문의
 * 근거를 진단 영역에서 확인하기 위한 목록이다.
 */
const readerSelectedSections = computed(() =>
  Object.values(previewView.value?.sections ?? {}).filter(
    (section) => section.from_reader_selection === true,
  ),
)

const readerSelectedHeading = computed(() =>
  runData.value?.sections_error
    ? '독자 응답에서 읽은 섹션'
    : '구성본이 고른 다른 실행의 섹션',
)

const readerSelectedNote = computed(() =>
  runData.value?.sections_error
    ? '섹션 결과 조회가 실패해 이 실행의 행 목록을 확인하지 못했습니다. 독자 응답이 준 본문·근거를 그대로 표시합니다.'
    : '이 실행의 섹션 결과에는 없지만, 저장된 구성본이 그 본문을 선택했으므로 독자 응답의 본문·근거를 그대로 표시합니다. 임의의 최신 버전으로 바꾸지 않습니다.',
)

/**
 * 재생성 패널에 넘길 **이 run의 저장 정보 원문 묶음 ID**.
 *
 * 재사용 재생성은 서버가 요구하는 `bundle_id`가 있어야 열린다. 그 값은 이 run의 기존
 * `GET /runs/{id}/information-bundle` 응답에만 있으므로, 사용자가 재생성 영역을 열 때
 * 그 경로를 **한 번** 조회해 `parseInformationBundle`로 읽는다(새 값을 만들지 않는다).
 *
 * 지키는 것:
 *
 * - 자동 실행이 아니다. 사용자가 `섹션 재생성·저장 응답 재처리`를 펼 때만 조회한다.
 * - 조회 실패를 "묶음 없음"으로 바꾸지 않는다. 실패면 재사용 재생성을 막고 사유를 보인다.
 * - run이 바뀌면 이전 run의 응답을 붙이지 않는다(순번 비교로 늦은 응답을 버린다).
 */
const bundleLookupRunId = ref<string | null>(null)
const bundleStatus = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const bundleId = ref<string | null>(null)
const bundleError = ref<string | null>(null)
/** 재생성 성공 실행. 사용자가 열기 전에는 자동으로 열지 않는다. */
const regeneratedRunId = ref<string | null>(null)
let bundleSequence = 0

async function loadBundleForRegeneration() {
  const runId = openRunId.value
  if (!runId) return
  if (bundleLookupRunId.value === runId && bundleStatus.value !== 'error') return
  const sequence = ++bundleSequence
  bundleLookupRunId.value = runId
  bundleStatus.value = 'loading'
  bundleId.value = null
  bundleError.value = null
  const response = await previewRunsApi.informationBundle(runId)
  // 늦게 도착한 이전 run의 응답은 버린다.
  if (disposed || sequence !== bundleSequence || openRunId.value !== runId) return
  if (!response.ok) {
    bundleStatus.value = 'error'
    bundleError.value = response.message
    return
  }
  const parsed = parseInformationBundle(response.data)
  bundleId.value = parsed.bundleId
  bundleStatus.value = 'ready'
}

/** 재생성 영역을 펼 때만 묶음을 조회한다(접힌 상태에서는 요청 0회). */
function toggleRegeneration(event: Event) {
  const open = (event.target as HTMLDetailsElement).open
  regenerationOpen.value = open
  if (!open) return
  void loadBundleForRegeneration()
}

/**
 * 재생성 요청이 성공했다. 사용자가 바로 실제 본문을 확인할 수 있게 **새 run을 여는
 * 버튼**만 제공한다. 자동으로 열지 않는 이유: 열기는 GET이지만 사용자가 방금 만든
 * 결과를 언제 볼지 정하는 동작이며, 실패한 재생성 뒤 화면이 바뀌면 혼동된다.
 */
function onSectionRegenerated(payload: SectionRunResponse) {
  regeneratedRunId.value = payload.run_id
}

async function openRegeneratedRun() {
  const runId = regeneratedRunId.value
  if (!runId) return
  await openStoredRun(runId, startedFixture.value)
}

const generationState = computed(() => {
  if (!generating.value || !startedFixture.value) return null
  const fixture = startedFixture.value
  return `${fixture.label} (경기 번호 ${fixture.fixture_id}) 프리뷰를 생성하고 저장하는 중입니다.`
})

const completeLabel = computed(() => {
  const value = previewView.value?.complete
  if (value === null || value === undefined) return '서버 표기 없음'
  return value ? '모두 있음' : '일부 없음(부분 결과)'
})

function kstDateOf(value: string | null): string | undefined {
  if (!value) return undefined
  const ms = Date.parse(value)
  if (!Number.isFinite(ms)) return undefined
  return new Date(ms + 9 * 3600000).toISOString().slice(0, 10)
}

function clearHomeReflection() {
  homeReflectionSequence += 1
  homeReflectionLoading.value = false
  homeReflectionFixtureId.value = null
  homeReflectionKickoffAt.value = null
  homeDoc.value = null
  homeDocError.value = null
  homeRec.value = null
  homeRecError.value = null
}

async function refreshHomeReflection(fixtureIdValue: number, kickoffAtValue: string | null) {
  const sequence = ++homeReflectionSequence
  homeReflectionFixtureId.value = fixtureIdValue
  homeReflectionKickoffAt.value = kickoffAtValue
  homeReflectionLoading.value = true
  homeDoc.value = null
  homeDocError.value = null
  homeRec.value = null
  homeRecError.value = null
  const dateParam = kstDateOf(kickoffAtValue)
  const [docRes, recRes] = await Promise.allSettled([
    getHomePreviewDocument(fixtureIdValue),
    getHomeRecommendations(undefined, dateParam),
  ])
  if (disposed || sequence !== homeReflectionSequence) return
  homeReflectionLoading.value = false
  if (docRes.status === 'fulfilled') {
    homeDoc.value = docRes.value
  } else {
    homeDocError.value =
      docRes.reason instanceof Error ? docRes.reason.message : '홈 공개 문서 조회 실패'
  }
  if (recRes.status === 'fulfilled') {
    homeRec.value = recRes.value
  } else {
    homeRecError.value =
      recRes.reason instanceof Error ? recRes.reason.message : '홈 추천 상태 조회 실패'
  }
}

function clearResultState() {
  runData.value = null
  runError.value = null
  openRunId.value = null
  openedFixtureId.value = null
  openedKickoffAt.value = null
  compositionSequence += 1
  composition.value = null
  compositionNote.value = null
  compositionLoaded.value = false
  compositionError.value = null
  diagnosticsOpen.value = false
  bundleOpen.value = false
  inspectorOpen.value = false
  regenerationOpen.value = false
  selectedSectionId.value = ''
  bundleLookupRunId.value = null
  bundleStatus.value = 'idle'
  bundleId.value = null
  bundleError.value = null
  regeneratedRunId.value = null
  approvalsFallback.value = null
  approvalRefreshWarning.value = null
  clearHomeReflection()
}

async function checkFixture() {
  // 생성 중에만 막는다. 확인 중에 번호를 바꿔 다시 확인하면, 새 요청이 이전 요청을 앞지른다
  // (아래 순번 비교가 늦게 온 이전 응답을 버린다). 막아 버리면 화면이 이전 응답을 기다린다.
  if (generating.value) return
  const requested = fixtureId.value
  lookupError.value = null
  if (requested === null) {
    lookupError.value = 'API-Football 경기 번호를 양의 정수로 입력하세요.'
    checkedFixture.value = null
    return
  }
  const sequence = ++lookupSequence
  checking.value = true
  checkedFixture.value = null
  const response = await getPreviewFixture(requested)
  if (disposed || sequence !== lookupSequence) return
  checking.value = false
  if (!response.ok) {
    lookupError.value =
      response.status === 404
        ? '이 번호의 저장된 경기가 없습니다. 경기 목록과 외부 경기 번호를 확인하세요.'
        : response.status === 503
          ? '저장된 경기 DB를 읽을 수 없습니다. 관리자에게 DB 연결·조회 권한 확인이 필요합니다.'
          : response.message
    return
  }
  // 응답이 오는 사이 사용자가 번호를 바꿨다면 이 응답은 현재 입력의 것이 아니다.
  if (fixtureId.value !== requested) return
  checkedFixture.value = response.data
  void refreshHomeReflection(response.data.fixture_id, response.data.kickoff_at)
}

async function openStoredRun(
  runId: string,
  sourceFixture: FixtureCandidate | null,
  explicitFixture: { fixtureId?: number; kickoffAt?: string | null } = {},
) {
  const trimmed = runId.trim()
  if (!trimmed) {
    directRunError.value = '실행 ID를 입력하세요.'
    return
  }
  // 주소에도 남긴다(새로고침·복사로 같은 저장 결과를 다시 연다). 수집 실행의 `run`과 섞이지 않게
  // 전용 키만 쓴다.
  if (route.query[PREVIEW_RUN_QUERY] !== trimmed) {
    void router.replace({ query: { ...route.query, [PREVIEW_RUN_QUERY]: trimmed } })
  }
  const sequence = ++openSequence
  // 실행 전환 시 이전 실행의 본문과 홈 반영 상태를 즉시 비워 새 실행 ID 아래 잔상이 남지 않게 한다.
  runData.value = null
  runError.value = null
  directRunError.value = null
  runLoading.value = true
  compositionSequence += 1
  composition.value = null
  compositionNote.value = null
  compositionLoaded.value = false
  compositionError.value = null
  diagnosticsOpen.value = false
  bundleOpen.value = false
  inspectorOpen.value = false
  regenerationOpen.value = false
  selectedSectionId.value = ''
  // 이전 run의 묶음 조회 결과·재생성 결과를 다음 run에 붙이지 않는다.
  bundleLookupRunId.value = null
  bundleStatus.value = 'idle'
  bundleId.value = null
  bundleError.value = null
  regeneratedRunId.value = null
  approvalsFallback.value = null
  approvalRefreshWarning.value = null
  clearHomeReflection()
  startedFixture.value = sourceFixture
  openedFixtureId.value = explicitFixture.fixtureId ?? sourceFixture?.fixture_id ?? null
  openedKickoffAt.value = explicitFixture.kickoffAt ?? sourceFixture?.kickoff_at ?? null
  openRunId.value = trimmed
  const data = await getPreviewRun(trimmed)
  if (disposed || sequence !== openSequence || openRunId.value !== trimmed || data.run_id !== trimmed) {
    return
  }
  runLoading.value = false
  if (data.preview === null && data.sections.section_results.length === 0) {
    // 읽힌 본문이 하나도 없을 때만 실행 전체를 오류로 표시한다. 이때 섹션 결과 조회가
    // 실패했다면 그 사유를 **함께** 남긴다(조회 실패를 "자료 없음"으로 바꾸지 않는다).
    const reasons = [data.preview_error]
    if (data.sections_error) {
      reasons.push(`저장된 섹션 결과를 읽지 못했습니다. ${data.sections_error}`)
    }
    runError.value =
      reasons.filter(Boolean).join(' ') || '이 실행의 저장된 결과를 읽지 못했습니다.'
    runData.value = null
    return
  }
  runData.value = data
  readVersion.value += 1
  void refreshOpenRunComposition(trimmed)
  const resolvedFixtureId = openRunFixtureId.value
  const resolvedKickoffAt =
    data.detail?.fixture?.kickoff_at ??
    startedFixture.value?.kickoff_at ??
    openedKickoffAt.value ??
    null
  if (resolvedFixtureId !== null) {
    void refreshHomeReflection(resolvedFixtureId, resolvedKickoffAt)
  }
}

async function refreshAfterApproval({ runId }: { runId: string }) {
  const seq = openSequence
  approvalRefreshWarning.value = null
  const resolvedFixtureId = openRunFixtureId.value ?? homeReflectionFixtureId.value
  const resolvedKickoffAt =
    runData.value?.detail?.fixture?.kickoff_at ??
    startedFixture.value?.kickoff_at ??
    openedKickoffAt.value ??
    homeReflectionKickoffAt.value ??
    null

  const detailPromise = previewRunsApi.detail(runId)
  const homePromise =
    resolvedFixtureId !== null
      ? refreshHomeReflection(resolvedFixtureId, resolvedKickoffAt)
      : Promise.resolve()

  const [detailRes] = await Promise.all([detailPromise, homePromise])
  if (disposed || seq !== openSequence || openRunId.value !== runId) return

  if (detailRes.ok) {
    if (runData.value && runData.value.run_id === runId) {
      runData.value = {
        ...runData.value,
        detail: detailRes.data,
        detail_error: null,
      }
    }
    if (detailRes.data.section_approvals && detailRes.data.section_approvals.length > 0) {
      approvalsFallback.value = null
      return
    }
  }

  const fallbackRes = await previewRunsApi.approvals()
  if (disposed || seq !== openSequence || openRunId.value !== runId) return
  if (fallbackRes.ok) {
    approvalsFallback.value = fallbackRes.data
  } else if (!detailRes.ok) {
    approvalRefreshWarning.value = `승인은 기록됐으나 최신 승인 상태를 다시 읽지 못했습니다: ${detailRes.message}`
  }
}

/** 생성 버튼. 사용자가 직접 눌러야만 POST가 한 번 나간다. */
async function generate() {
  const fixture = confirmed.value
  if (!fixture?.selectable || generating.value || checking.value) return
  generating.value = true
  generateError.value = null
  startedFixture.value = fixture
  clearResultState()
  const response = await generatePreview(fixture.fixture_id)
  if (disposed) return
  generating.value = false
  if (!response.ok) {
    generateError.value =
      response.kind === 'network'
        ? '응답을 받지 못했습니다. 서버에 실행이 남아 있을 수 있으니 아래 실행 이력에서 확인하세요. 자동으로 다시 보내지 않습니다.'
        : response.message
    return
  }
  // 생성 응답은 실행 ID만 준다. 본문은 같은 실행의 저장 결과를 GET으로 다시 읽는다.
  await openStoredRun(response.data.run_id, fixture)
}

async function reread() {
  if (!openRunId.value) return
  await openStoredRun(openRunId.value, startedFixture.value)
}

async function loadHistory() {
  historyOpen.value = !historyOpen.value
  if (!historyOpen.value || history.value.length > 0 || historyLoading.value) return
  historyLoading.value = true
  historyError.value = null
  const response = await listPreviewRuns()
  if (disposed) return
  historyLoading.value = false
  if (!response.ok) {
    historyError.value = response.message
    return
  }
  history.value = response.data.runs
}

async function refreshOpenRunComposition(runId: string) {
  const sequence = ++compositionSequence
  compositionLoaded.value = false
  compositionError.value = null
  const response = await getPreviewComposition(runId)
  if (disposed || sequence !== compositionSequence || openRunId.value !== runId) return
  compositionLoaded.value = true
  if (!response.ok) {
    compositionError.value = response.message
    compositionNote.value = response.message
    return
  }
  composition.value = response.data.composition
  compositionNote.value = response.data.available ? null : response.data.reason
}

/** 진단 펼침. 저장된 구성본만 조회한다(모델 호출 없음). */
async function toggleDiagnostics(event: Event) {
  const open = (event.target as HTMLDetailsElement).open
  diagnosticsOpen.value = open
  if (!open || !openRunId.value) return
  if (compositionLoaded.value && compositionError.value === null) return
  await refreshOpenRunComposition(openRunId.value)
}

function openRunFromHistory(run: RunSummary) {
  directRunId.value = run.run_id
  void openStoredRun(run.run_id, null)
}

/**
 * 다경기 시험 표에서 "저장된 문서 보기". 이미 저장 판정을 마친 실행 ID를 그대로 열어
 * 같은 실행의 본문을 읽는다(GET만). 생성 요청을 다시 보내지 않는다.
 */
function openDocumentFromTest(payload: { runId: string; fixtureId?: number; kickoffAt?: string | null }) {
  directRunId.value = payload.runId
  void openStoredRun(payload.runId, null, {
    fixtureId: payload.fixtureId,
    kickoffAt: payload.kickoffAt ?? null,
  })
}

function formatMoment(value: string | null): string {
  if (!value) return '—'
  return value.slice(0, 16).replace('T', ' ')
}

/**
 * 진입 시 주소에 실행 ID가 있으면 그 저장 결과를 연다. 이 동작도 GET만 보낸다.
 * 생성은 하지 않고, 없던 번호를 만들지도 않는다.
 */
onMounted(() => {
  const fromQuery = route.query[PREVIEW_RUN_QUERY]
  if (typeof fromQuery !== 'string' || !fromQuery.trim()) return
  directRunId.value = fromQuery
  void openStoredRun(fromQuery, null)
})

onBeforeUnmount(() => {
  disposed = true
})
</script>

<template>
  <section class="preview-tab mpv-admin" data-testid="preview-panel" aria-labelledby="preview-tab-title">
    <header class="preview-tab__head">
      <div>
        <h2 id="preview-tab-title">경기 프리뷰</h2>
        <p>
          API-Football 경기 번호로 저장된 대진을 확인하고, 이 경기의 프리뷰를 생성해 DB에 저장한
          뒤 같은 실행의 본문을 다시 읽습니다.
        </p>
      </div>
      <p class="preview-tab__policy">
        생성은 사용자가 누를 때만 실행됩니다. 한 경기 생성에서 각 AI 모듈은 최초 전송을 포함해
        최대 3회까지 시도하며, 기술 실패만 서버가 다시 시도합니다. 화면은 요청을 반복하지 않습니다.
      </p>
      <nav
        v-if="canGenerate"
        class="preview-tab__admin-links"
        data-testid="preview-admin-links"
        aria-label="프리뷰 관리 이동"
      >
        <RouterLink
          to="/admin/sections"
          class="mm-button"
          data-testid="preview-open-sections"
        >
          섹션 실행 워크플로우
        </RouterLink>
        <RouterLink
          :to="openRunId ? { name: 'admin', query: { tab: 'preview', previewRun: openRunId } } : { name: 'admin', query: { tab: 'preview' } }"
          class="mm-button mm-button--quiet"
          data-testid="preview-open-runs"
          @click="!historyOpen && loadHistory()"
        >
          실행 이력 보기
        </RouterLink>
      </nav>
    </header>

    <!--
      기간 수집 → 다경기 생성 → 저장 문서 확인. 기존 단일 경기 흐름 **위**에 두어, 사용자가
      추천 경기에서 시작해 수집 결과를 먼저 보고 생성으로 넘어가는 순서를 그대로 따른다.
      수집·생성 모두 사용자가 누른 버튼으로만 시작한다.
    -->
    <PreviewTestPanel
      v-if="canGenerate"
      :can-generate="canGenerate"
      @open-document="openDocumentFromTest"
    />

    <h3 class="preview-tab__block-title" data-testid="preview-single-heading">
      경기 번호로 직접 확인
    </h3>
    <form class="preview-tab__form" data-testid="preview-fixture-form" @submit.prevent="checkFixture">
      <label for="preview-fixture-number">경기 번호</label>
      <div class="preview-tab__controls">
        <input
          id="preview-fixture-number"
          v-model="fixtureNumber"
          data-testid="preview-fixture-number"
          inputmode="numeric"
          autocomplete="off"
          :disabled="generating"
          placeholder="예: 1557474"
        />
        <button
          type="submit"
          class="mm-button"
          data-testid="preview-check-fixture"
          :disabled="checking || generating"
        >
          {{ checking ? '경기 확인 중…' : '경기 확인' }}
        </button>
      </div>
      <p class="preview-tab__hint">
        번호 확인은 저장된 경기 자료를 읽기만 합니다(모델·외부 API 호출 없음).
      </p>
    </form>

    <p v-if="lookupError" class="preview-tab__alert" role="alert" data-testid="preview-lookup-error">
      {{ lookupError }}
    </p>

    <div v-if="confirmed" class="preview-tab__fixture" data-testid="preview-confirmed-fixture">
      <strong>{{ confirmed.label }}</strong>
      <p>
        {{ confirmed.league_name ?? '리그 미상' }} · 시즌 {{ confirmed.season }} ·
        {{ formatMoment(confirmed.kickoff_at) }} (UTC)
      </p>
      <p class="preview-tab__hint">
        경기 번호 {{ confirmed.fixture_id }} · 저장된 경기 자료(읽기 전용)
      </p>
      <p v-if="!confirmed.selectable" class="preview-tab__alert" role="alert">
        이 경기는 지금 실행할 수 없습니다. 저장된 경기 정보를 확인하세요.
      </p>
    </div>

    <div v-if="canGenerate" class="preview-tab__actions">
      <button
        type="button"
        class="mm-button mm-button--primary"
        data-testid="preview-generate"
        :disabled="!canGenerateNow"
        @click="generate"
      >
        {{ generating ? '프리뷰 생성 중…' : '이 경기 전체 프리뷰 생성' }}
      </button>
      <p class="preview-tab__hint">
        생성 응답은 실행 ID만 돌려줍니다. 본문은 같은 실행의 저장 결과를 다시 조회해 표시합니다.
      </p>
    </div>

    <p v-if="generationState" class="preview-tab__status" role="status" data-testid="preview-generating">
      {{ generationState }}
    </p>
    <p v-if="generateError" class="preview-tab__alert" role="alert" data-testid="preview-generate-error">
      {{ generateError }}
    </p>

    <section class="preview-tab__open" aria-labelledby="preview-open-title">
      <h3 id="preview-open-title">저장된 결과 열기</h3>
      <form
        class="preview-tab__controls"
        data-testid="preview-run-form"
        @submit.prevent="openStoredRun(directRunId, null)"
      >
        <input
          v-model="directRunId"
          data-testid="preview-run-id"
          autocomplete="off"
          placeholder="실행 ID"
          aria-label="실행 ID"
        />
        <button type="submit" class="mm-button" data-testid="preview-open-run">열기</button>
      </form>
      <p class="preview-tab__hint">저장된 실행을 여는 동작은 조회(GET)만 합니다.</p>
      <p v-if="directRunError" class="preview-tab__alert" role="alert">{{ directRunError }}</p>

      <button
        type="button"
        class="mm-button mm-button--quiet"
        data-testid="preview-history-toggle"
        @click="loadHistory"
      >
        {{ historyOpen ? '실행 이력 접기' : '실행 이력 보기' }}
      </button>
      <div v-if="historyOpen" class="preview-tab__history" data-testid="preview-history">
        <p v-if="historyLoading" role="status">실행 목록을 읽는 중…</p>
        <p v-else-if="historyError" class="preview-tab__alert" role="alert">{{ historyError }}</p>
        <p v-else-if="!history.length" class="preview-tab__hint">저장된 실행이 없습니다.</p>
        <ul v-else>
          <li v-for="run in history" :key="run.run_id">
            <button type="button" class="preview-tab__run" @click="openRunFromHistory(run)">
              <span class="preview-tab__run-label">{{ run.fixture_label ?? '경기 미상' }}</span>
              <span class="preview-tab__run-meta">
                {{ formatMoment(run.requested_at) }} · {{ run.mode }} · {{ run.status }}
              </span>
              <span class="preview-tab__run-id">{{ run.run_id }}</span>
            </button>
          </li>
        </ul>
      </div>
    </section>

    <section
      v-if="homeReflectionFixtureId !== null"
      class="preview-tab__home"
      data-testid="preview-home-reflection"
    >
      <div class="preview-tab__bar">
        <div>
          <strong>홈 반영 상태 (경기 {{ homeReflectionFixtureId }})</strong>
          <p class="preview-tab__hint" data-testid="preview-home-document-status">
            {{ homeDocumentReflectionText }}
          </p>
          <p
            v-if="homeDoc?.status === 'available' && homeSectionComparison?.status === 'unverified'"
            class="preview-tab__hint"
            data-testid="preview-home-section-diff"
          >
            섹션 대조 미확인: {{ homeSectionComparison.reason }}
          </p>
          <ul
            v-else-if="
              homeDoc?.status === 'available' &&
              homeSectionComparison &&
              homeSectionComparison.items.length > 0
            "
            class="preview-tab__section-diff"
            data-testid="preview-home-section-diff"
          >
            <li
              v-for="item in homeSectionComparison.items"
              :key="item.workflow_id"
              :data-testid="`preview-home-section-diff-${item.workflow_id}`"
            >
              <span>{{ item.workflow_id }}: {{ item.label }}</span>
              <span class="preview-tab__muted">
                (열린/선택 {{ item.expectedId ?? '없음' }} · 홈 {{ item.actualId ?? '없음' }})
              </span>
            </li>
          </ul>
          <p
            v-if="homeRecError"
            class="preview-tab__alert"
            role="alert"
            data-testid="preview-home-recommendations-error"
          >
            공개 추천 목록을 읽지 못했습니다: {{ homeRecError }}
          </p>
          <p
            v-else-if="homeRecMatch"
            class="preview-tab__hint"
            data-testid="preview-home-recommendation-status"
          >
            공개 추천 상태: {{ homeRecMatch.preview.state }} · 제공:
            {{ homeRecMatch.preview.served ?? '없음' }} · 기준:
            {{
              homeRecMatch.preview.as_of === null
                ? '자료 기준 미기록'
                : formatMoment(homeRecMatch.preview.as_of)
            }}
          </p>
          <p
            v-else-if="homeRec"
            class="preview-tab__hint"
            data-testid="preview-home-recommendation-status"
          >
            해당 날짜 공개 추천 목록에는 이 경기가 없습니다(직접 문서 조회 기준 사용).
          </p>
          <p
            v-if="hasUnresolvedPlayers"
            class="preview-tab__hint"
            data-testid="preview-home-unresolved-note"
          >
            선수 DB 연결·사진 미확인 항목은 NULL/미확인 상태로 유지되며 저장 오류가 아닙니다.
          </p>
        </div>
        <div class="preview-tab__home-actions">
          <button
            type="button"
            class="mm-button mm-button--quiet"
            data-testid="preview-home-reflection-refresh"
            :disabled="homeReflectionLoading"
            @click="refreshHomeReflection(homeReflectionFixtureId, homeReflectionKickoffAt)"
          >
            홈 반영 새로고침
          </button>
          <RouterLink
            :to="{ path: '/', query: { fixtureId: String(homeReflectionFixtureId) } }"
            class="mm-button mm-button--quiet"
            data-testid="preview-home-link"
          >
            홈에서 확인
          </RouterLink>
        </div>
      </div>
    </section>

    <p v-if="runLoading" class="preview-tab__status" role="status" data-testid="preview-run-loading">
      저장된 결과를 읽는 중…
    </p>
    <p v-if="runError" class="preview-tab__alert" role="alert" data-testid="preview-run-error">
      {{ runError }}
    </p>

    <template v-if="previewView && openRunId">
      <div class="preview-tab__bar" data-testid="preview-run-bar">
        <div>
          <strong>실행 {{ openRunId }}</strong>
          <p class="preview-tab__hint">
            {{ runFixtureLabel }} · 저장된 본문을 그대로 표시합니다.
          </p>
        </div>
        <button type="button" class="mm-button" data-testid="preview-reread" @click="reread">
          저장 결과 다시 읽기
        </button>
      </div>

      <p
        v-if="runData?.preview_error"
        class="preview-tab__alert"
        role="alert"
        data-testid="preview-preview-error"
      >
        이 실행에는 독자용 본문이 없습니다. 아래 접힌 영역의 저장 섹션 결과와 진단에서 확인하세요.
      </p>

      <!-- 본문 우선. 진단은 아래 접힌 영역에서 사용자가 펼칠 때만 연다. -->
      <p
        v-if="blockedSections.length"
        class="preview-tab__alert"
        role="alert"
        data-testid="preview-storage-blocked"
      >
        정본 저장 행을 찾지 못한 섹션이 있어 정상 문서로 그리지 않았습니다:
        {{ blockedSections.join(', ') }}.
        {{ blockedReason ?? '저장 불일치 사유는 서버 응답에 기록되지 않았습니다.' }}
        아래 접힌 진단의 원문 참고 응답에서 응답 본문을 확인할 수 있습니다.
      </p>
      <div class="preview-tab__body" data-testid="preview-body">
        <MatchPreviewBody :key="`${openRunId}:${readVersion}`" :preview="previewView" />
      </div>

      <PreviewApprovalPanel
        v-if="runData"
        :open-run-id="openRunId"
        :run-data="runData"
        :preview-view="previewView"
        :composition="composition"
        :composition-loaded="compositionLoaded"
        :composition-error="compositionError"
        :blocked-sections="blockedSections"
        :can-approve-role="canGenerate"
        :fixture-id="openRunFixtureId"
        :approvals-fallback="approvalsFallback"
        :refresh-warning="approvalRefreshWarning"
        @approved="refreshAfterApproval"
      />

      <details
        class="preview-tab__diagnostics"
        data-testid="preview-diagnostics"
        @toggle="toggleDiagnostics"
      >
        <summary>저장 상태·섹션 결과·진단 보기</summary>
        <div v-if="diagnosticsOpen" class="preview-tab__diag-body">
          <p class="preview-tab__hint">
            아래 값은 저장된 사실과 진단입니다. 품질 표기가 낮아도 위 본문은 그대로 저장된
            결과이며, 자동으로 다시 생성하지 않습니다.
          </p>
          <dl class="preview-tab__facts">
            <dt>실행 ID</dt>
            <dd>{{ openRunId }}</dd>
            <dt>경기 번호</dt>
            <dd>{{ openRunFixtureId ?? '—' }}</dd>
            <dt>필수 섹션 본문</dt>
            <dd data-testid="preview-complete">{{ completeLabel }}</dd>
            <dt>표시 모델에서 비어 있는 항목</dt>
            <dd data-testid="preview-missing">
              {{ previewView.missing.length ? previewView.missing.join(' / ') : '없음' }}
            </dd>
          </dl>

          <h4>저장된 섹션 결과</h4>
          <!--
            조회 실패와 실제 미저장을 같은 문구로 쓰지 않는다. 실패면 사유를 그대로 보이고,
            같은 실행의 다른 읽힌 본문(reader 본문·실행 상세)은 아래에서 계속 보여준다.
          -->
          <p
            v-if="runData?.sections_error"
            class="preview-tab__alert"
            role="alert"
            data-testid="preview-sections-error"
          >
            저장된 섹션 결과를 읽지 못했습니다(자료 없음이 아닙니다). {{ runData.sections_error }}
          </p>
          <p v-else-if="!storedSections.length" class="preview-tab__hint">
            저장된 섹션 결과가 없습니다.
          </p>
          <ul v-if="storedSections.length" class="preview-tab__sections" data-testid="preview-section-list">
            <li v-for="row in storedSections" :key="row.section_result_id">
              <span class="preview-tab__section-title">{{ row.title }}</span>
              <span class="preview-tab__run-meta">
                v{{ row.version }} · {{ row.workflow_id }} · {{ row.mode }} · {{ row.quality }}
                <template v-if="row.unavailable_reason"> · {{ row.unavailable_reason }}</template>
              </span>
            </li>
          </ul>

          <p v-if="compositionNote" class="preview-tab__hint" data-testid="preview-composition-note">
            {{ compositionNote }}
          </p>
          <ul v-if="composition" class="preview-tab__sections" data-testid="preview-composition">
            <li v-for="item in composition.items" :key="item.result_id">
              <span class="preview-tab__section-title">{{ item.section_id }}</span>
              <span class="preview-tab__run-meta">선택 v{{ item.version }} · 실행 {{ item.run_id }}</span>
            </li>
          </ul>

          <p v-if="runData?.detail_error" class="preview-tab__alert" role="alert">
            실행 상세를 읽지 못했습니다. {{ runData.detail_error }}
          </p>

          <!--
            저장 불일치 섹션의 생성 응답 원문. **접힌 참고 진단으로만** 둔다. 문서 위 본문에는
            넣지 않는다(저장된 정본으로 오인되지 않게).
          -->
          <details
            v-if="blockedSections.length"
            class="preview-tab__nested"
            data-testid="preview-blocked-raw"
          >
            <summary>저장 불일치 섹션의 원문 참고 응답</summary>
            <p class="preview-tab__hint">
              아래 본문은 생성 응답에 담긴 값이며 정본 DB에서 확인한 내용이 아닙니다. 위 문서에는
              표시하지 않았습니다.
            </p>
            <div
              v-for="row in blockedRows"
              :key="`blocked-${row.section_result_id}`"
              class="preview-tab__blocked"
            >
              <h5>{{ row.title }} ({{ row.workflow_id }})</h5>
              <p v-if="row.storage_error" class="preview-tab__hint">{{ row.storage_error }}</p>
              <pre>{{ row.body || '(본문 없음)' }}</pre>
            </div>
          </details>

          <details class="preview-tab__nested" data-testid="preview-bundle" @toggle="bundleOpen = ($event.target as HTMLDetailsElement).open">
            <summary>정보 원문·검색·전달 기록</summary>
            <InformationBundlePanel v-if="bundleOpen" :run-id="openRunId" />
          </details>

          <details class="preview-tab__nested" data-testid="preview-inspector" @toggle="inspectorOpen = ($event.target as HTMLDetailsElement).open">
            <summary>노드별 요청·원문 응답·재생(실행 검사)</summary>
            <RunInspector v-if="inspectorOpen" :run-id="openRunId" hide-approval />
          </details>

          <details class="preview-tab__nested" data-testid="preview-regeneration" @toggle="toggleRegeneration">
            <summary>섹션 재생성·저장 응답 재처리</summary>
            <div v-if="regenerationOpen" class="preview-tab__regen">
              <p class="preview-tab__hint">
                사용자가 버튼을 눌러야만 요청이 나갑니다. 저장 응답 재처리는 모델 호출 0회이며,
                받은 모델 전송 수는 응답에 표시됩니다.
                <!--
                  배당(section_odds)도 **실행 방식에 따라 모델 호출이 다르다**. 저장된 정보
                  원문 재사용(reuse)은 모델 0회이고 남는 자리가 있으면 배당 API를 1회 보완할
                  수 있지만, 새 수집(refresh)은 자료 검색 모델이 실제로 호출된다. 이 영역은
                  사용자가 고른 동작을 알 수 없으므로 **모델 0회를 단정하지 않고** 두 경우를
                  함께 적는다. 결과의 모델 0회 여부는 패널이 응답 값으로 표시한다.
                -->
                <template v-if="selectedSectionId === 'section_odds'">
                  배당 섹션은 저장된 정보 원문 재사용 시 모델 호출이 0회이며(필요 시 배당
                  API 1회 보완), 새 수집 재생성은 자료 조사를 위한 모델 호출과 외부 API
                  조회를 포함합니다. 실제 제공자 전송 수는 이 화면에서 확인하지 않습니다.
                </template>
                <template v-else>
                  재생성은 새 호출을 포함하며, 받은 모델 전송 수는 응답에 표시됩니다.
                </template>
              </p>
              <p v-if="runData?.sections_error" class="preview-tab__hint" data-testid="preview-regeneration-unavailable">
                섹션 결과를 읽지 못해 재생성할 섹션을 고를 수 없습니다. 저장된 결과가 없다는 뜻이
                아닙니다.
              </p>
              <p v-else-if="!sectionChoices.length" class="preview-tab__hint">재생성할 섹션이 없습니다.</p>
              <template v-else>
                <label class="preview-tab__select">
                  <span>섹션</span>
                  <select v-model="selectedSectionId" data-testid="preview-regeneration-section">
                    <option value="">선택하세요</option>
                    <option v-for="id in sectionChoices" :key="id" :value="id">{{ id }}</option>
                  </select>
                </label>
                <p
                  v-if="bundleStatus === 'loading'"
                  class="preview-tab__hint"
                  data-testid="preview-regeneration-bundle-loading"
                >
                  이 실행의 저장 정보 원문 묶음을 확인하는 중입니다.
                </p>
                <p
                  v-else-if="bundleStatus === 'error'"
                  class="preview-tab__alert"
                  role="alert"
                  data-testid="preview-regeneration-bundle-error"
                >
                  저장 정보 원문 묶음을 읽지 못했습니다(묶음 없음이 아닙니다). {{ bundleError }}
                </p>
                <SectionRegenerationPanel
                  v-if="selectedSectionId"
                  :workflow-id="selectedSectionId"
                  :fixture-id="openRunFixtureId"
                  :results="regenerationResults"
                  :bundle-id="bundleId"
                  :selected-result-ids="otherSectionResultIds"
                  :show-approval="false"
                  @regenerated="onSectionRegenerated"
                />
                <div
                  v-if="regeneratedRunId && regeneratedRunId !== openRunId"
                  class="preview-tab__regen-done"
                  data-testid="preview-regeneration-result"
                >
                  <p class="preview-tab__hint">
                    새 실행 {{ regeneratedRunId }}이 저장됐습니다. 아래 버튼으로 그 실행의
                    저장 본문을 확인하세요.
                  </p>
                  <button
                    type="button"
                    class="mm-button"
                    data-testid="preview-regeneration-open"
                    @click="openRegeneratedRun"
                  >
                    재생성된 실행 열기
                  </button>
                </div>
              </template>
            </div>
          </details>

          <details class="preview-tab__nested" data-testid="preview-composition-panel">
            <summary>섹션 결과 버전 선택(구성본)과 마지막 AI</summary>
            <!--
              섹션 결과 조회가 실패했으면 이 패널을 열지 않는다. 빈 목록을 넘기면 패널이
              "저장된 섹션 결과가 없습니다"라고 말해 조회 실패를 자료 없음으로 위장한다.
            -->
            <p v-if="runData?.sections_error" class="preview-tab__hint" data-testid="preview-composition-unavailable">
              섹션 결과를 읽지 못해 구성본을 만들 수 없습니다. 저장된 결과가 없다는 뜻이 아닙니다.
            </p>
            <CompositionPanel
              v-else-if="openRunFixtureId !== null"
              :key="`composition-${openRunId}`"
              :run-id="openRunId"
              :results="runData?.sections.section_results ?? []"
              :fixture-id="openRunFixtureId"
            />
            <p v-else class="preview-tab__hint">
              저장된 섹션 결과와 경기 번호가 있어야 구성본을 만들 수 있습니다.
            </p>
          </details>

          <div v-if="storedSections.some((row) => row.sources.length)" class="preview-tab__sources">
            <h4>저장된 근거</h4>
            <ul class="preview-tab__sections">
              <template v-for="row in storedSections" :key="`sources-${row.section_result_id}`">
                <li v-for="(source, index) in row.sources" :key="`${row.section_result_id}-${index}`">
                  <a v-if="source.url" :href="source.url" target="_blank" rel="noreferrer noopener">
                    {{ source.label ?? source.url }}
                  </a>
                  <span v-else>{{ source.label ?? '출처 표시 없음' }}</span>
                </li>
              </template>
            </ul>
          </div>
          <div
            v-if="readerSelectedSections.length"
            class="preview-tab__sources"
            data-testid="preview-reader-sections"
          >
            <h4>{{ readerSelectedHeading }}</h4>
            <p class="preview-tab__hint">
              {{ readerSelectedNote }}
            </p>
            <ul class="preview-tab__sections">
              <template v-for="section in readerSelectedSections" :key="`reader-${section.section_id}`">
                <li>
                  <span class="preview-tab__section-title">{{ section.title }}</span>
                  <span class="preview-tab__run-meta">
                    {{ section.section_id }}
                    <template v-if="section.version !== null"> · v{{ section.version }}</template>
                    · 구성본 선택
                  </span>
                </li>
                <li v-for="(source, index) in section.sources" :key="`reader-${section.section_id}-${index}`">
                  <a v-if="source.url" :href="source.url" target="_blank" rel="noreferrer noopener">
                    {{ source.label ?? source.url }}
                  </a>
                  <span v-else>{{ source.label ?? '출처 표시 없음' }}</span>
                </li>
              </template>
            </ul>
          </div>
        </div>
      </details>
    </template>

    <p v-else-if="!openRunId && !runLoading" class="preview-tab__hint" data-testid="preview-empty">
      경기 번호를 확인한 뒤 생성하거나, 저장된 실행 ID로 이미 만든 결과를 열 수 있습니다.
    </p>
  </section>
</template>

<style scoped>
.preview-tab {
  display: grid;
  gap: 16px;
  padding: 20px;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-bg);
  color: var(--color-fg);
  min-width: 0;
}

.preview-tab__head {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.preview-tab__head h2 {
  margin: 0;
  font-size: 18px;
}

.preview-tab__head p,
.preview-tab__policy,
.preview-tab__hint {
  margin: 0;
  color: var(--color-muted);
  font-size: 13px;
  line-height: 1.6;
}

.preview-tab__policy {
  max-width: 76ch;
  padding: 10px 12px;
  border-left: 2px solid var(--color-border);
  background: var(--color-card);
}

.preview-tab__admin-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.preview-tab__form,
.preview-tab__open {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.preview-tab__form label {
  font-size: 13px;
  font-weight: 700;
}

.preview-tab__controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.preview-tab__controls input {
  min-width: min(100%, 22rem);
}

.preview-tab__actions {
  display: grid;
  gap: 6px;
  justify-items: start;
}

.preview-tab__alert {
  margin: 0;
  padding: 10px 12px;
  border: 1px solid #e5c3c3;
  border-left: 3px solid #a3262b;
  border-radius: 6px;
  background: #fbeceb;
  color: #7a1c20;
  font-size: 13px;
  line-height: 1.6;
}

.preview-tab__status {
  margin: 0;
  color: var(--color-muted);
  font-size: 13px;
}

.preview-tab__fixture {
  display: grid;
  gap: 4px;
  padding: 12px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
}

.preview-tab__fixture strong {
  font-size: 15px;
}

.preview-tab__fixture p {
  margin: 0;
  font-size: 13px;
  color: var(--color-muted);
}

.preview-tab__history ul {
  display: grid;
  gap: 6px;
  margin: 8px 0 0;
  padding: 0;
  list-style: none;
  max-height: 18rem;
  overflow-y: auto;
}

.preview-tab__run {
  display: grid;
  gap: 2px;
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-bg);
  color: var(--color-fg);
  text-align: left;
  font: inherit;
  cursor: pointer;
}

.preview-tab__run:hover {
  background: var(--color-card-hover);
}

.preview-tab__run-label {
  font-weight: 700;
  font-size: 13px;
}

.preview-tab__run-meta {
  color: var(--color-muted);
  font-size: 12px;
}

.preview-tab__run-id {
  color: var(--color-muted);
  font-size: 11px;
  font-family: ui-monospace, monospace;
  overflow-wrap: anywhere;
}

.preview-tab__bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
}

.preview-tab__bar strong {
  font-size: 13px;
  overflow-wrap: anywhere;
}

.preview-tab__body {
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--mpv-paper);
}

.preview-tab__diagnostics {
  border-top: 1px solid var(--color-border);
  padding-top: 12px;
}

.preview-tab__diagnostics > summary {
  cursor: pointer;
  font-size: 13px;
  color: var(--color-muted);
}

.preview-tab__diag-body {
  display: grid;
  gap: 10px;
  margin-top: 10px;
  font-size: 13px;
  min-width: 0;
}

.preview-tab__diag-body h4 {
  margin: 8px 0 0;
  font-size: 13px;
}

.preview-tab__facts {
  display: grid;
  grid-template-columns: minmax(0, max-content) minmax(0, 1fr);
  gap: 4px 12px;
  margin: 0;
}

.preview-tab__facts dt {
  color: var(--color-muted);
}

.preview-tab__facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.preview-tab__sections {
  display: grid;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.preview-tab__sections li {
  display: grid;
  gap: 2px;
  padding: 6px 0;
  border-bottom: 1px solid var(--color-border);
}

.preview-tab__section-title {
  font-weight: 700;
  font-size: 13px;
}

.preview-tab__block-title {
  margin: 8px 0 0;
  padding-top: 12px;
  border-top: 1px solid var(--color-border);
  font-size: 14px;
}

.preview-tab__blocked {
  display: grid;
  gap: 4px;
}

.preview-tab__blocked h5 {
  margin: 6px 0 0;
  font-size: 12px;
}

.preview-tab__blocked pre {
  margin: 0;
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-bg);
  font-size: 11px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 16rem;
  overflow-y: auto;
}

.preview-tab__nested {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 8px 10px;
}

.preview-tab__nested > summary {
  cursor: pointer;
  font-size: 13px;
  color: var(--color-muted);
}

.preview-tab__regen {
  display: grid;
  gap: 10px;
  margin-top: 8px;
}

.preview-tab__select {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 13px;
}

.preview-tab__section-diff {
  margin: 6px 0 0;
  padding-left: 18px;
  display: grid;
  gap: 2px;
  font-size: 12px;
}

.preview-tab__sources a {
  color: var(--color-fg);
  text-underline-offset: 0.2em;
  overflow-wrap: anywhere;
}
</style>
