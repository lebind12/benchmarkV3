<script setup lang="ts">
/**
 * 프리뷰 탭 안쪽의 **기간 수집 → 다경기 생성 → 저장 조회** 진행 영역.
 *
 * 사용자가 하는 일은 세 단계이고, 각 단계는 사용자가 버튼을 눌러야 시작한다.
 *
 * 1. 추천 경기 후보에서 정확히 두 경기를 고르고 기간·대상·실제 수집 범위를 확인한다.
 * 2. '기간 지정 수집'을 한 번 실행하고 결과를 본다. **수집이 끝나도 생성은 시작하지 않는다.**
 * 3. '선택 경기 프리뷰 생성'을 누르면 고른 경기를 순서대로 하나씩 생성하고, 끝난 경기마다
 *    DB를 다시 읽어 저장 상태를 판정한다. 한 경기가 실패해도 다음 경기는 계속한다.
 *
 * 지키는 것:
 *
 * - 진입·새로고침·폴링·문서 열기는 GET만 보낸다. POST는 사용자가 누른 두 버튼뿐이다.
 * - 수집 종료 이벤트가 생성을 호출하지 않는다(같은 함수에서 이어 부르지 않는다).
 * - 생성 요청마다 `request_id`를 보존한다. 응답을 못 받은 요청을 다시 보낼 때는 같은 값을,
 *   사용자가 새 실행을 명시하면 새 값을 쓴다. 같은 경기의 중복 클릭은 한 번만 나간다.
 * - 저장 판정은 받은 실행 ID로 다시 읽은 값이다. 다른 경기·다른 실행의 결과는 채택하지
 *   않는다. 생성 성공을 저장 성공으로 읽지 않는다.
 * - 늦게 도착한 이전 요청의 응답은 버린다(경기별 순번 비교).
 * - `/injuries`는 이번 수집에서 갱신되지 않는다. 화면은 그 사실을 먼저 적는다.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  isActiveRun,
  previewTestApi,
  type TestCandidate,
  type TestCandidates,
  type TestPlan,
  type TestCollectionEvidence,
  type TestRun,
} from '@/lib/api/previewTest'
import { generatePreview, getPreviewRun } from '@/lib/api/preview'
import { storageMismatchSections } from '@/lib/api/previewView'

const props = withDefaults(
  defineProps<{
    /** ADMIN만 수집·생성 UI를 연다. 서버도 같은 판정을 한다. */
    canGenerate?: boolean
  }>(),
  { canGenerate: false },
)

const emit = defineEmits<{
  /** 저장된 문서를 열어 달라는 요청(부모가 GET으로 연다). */
  openDocument: [payload: { runId: string; fixtureId?: number; kickoffAt?: string | null }]
}>()

/** 저장 판정. 생성 응답과 별개이며, 정본 재조회 결과만 담는다. */
type StorageOutcome =
  | { kind: 'persisted' }
  | { kind: 'mismatch'; sections: string[]; message: string }
  | { kind: 'unknown'; reason: string }

/**
 * 경기 하나의 진행 상태. 판별 유니온으로 두어 "실행 ID는 있는데 저장 판정이 없는" 중간
 * 상태를 표현할 수 없게 한다.
 */
type FixtureRunState =
  | { phase: 'idle' }
  | { phase: 'generating'; requestId: string }
  | {
      phase: 'saved'
      requestId: string
      runId: string
      status: string
      storage: StorageOutcome
    }
  | {
      phase: 'failed'
      requestId: string
      message: string
      /** 응답을 받지 못한 실패인지. 같은 요청을 다시 보낼 수 있는 유일한 경우다. */
      mayHaveReachedServer: boolean
    }

const route = useRoute()
const router = useRouter()

const SELECTION_QUERY = 'testFixtures'
const RUNS_QUERY = 'testRuns'
const COLLECTION_QUERY = 'testCollection'

const candidates = ref<TestCandidates | null>(null)
const candidatesError = ref<string | null>(null)
const candidatesLoading = ref(false)

const selectedIds = ref<number[]>([])
const plan = ref<TestPlan | null>(null)
const planError = ref<string | null>(null)
const planLoading = ref(false)

const collectionRun = ref<TestRun | null>(null)
const collectionError = ref<string | null>(null)
const collecting = ref(false)
const collectionNotice = ref<string | null>(null)

const states = ref<Record<number, FixtureRunState>>({})
const generating = ref(false)
const generateNotice = ref<string | null>(null)

let disposed = false
/** 늦은 응답을 버리기 위한 경기별 순번. 값을 바꾸면 이전 순번의 응답은 화면에 닿지 않는다. */
const tokens = new Map<number, number>()
/**
 * 새 실행 재생성 요청이 **아직 끝나지 않은** 경기.
 *
 * 진행 중인 요청이 있어도 사용자가 새 실행을 열 수 있어야 하므로(설계), `generating`
 * 하나로 버튼을 막으면 그 정상 동작이 사라진다. 대신 **재생성 요청이 응답을 기다리는
 * 동안**만 이 목록에 넣어, 그 사이 같은 버튼을 다시 눌러도 POST를 더 만들지 않는다.
 * 더블클릭·연속 클릭이 서로 다른 UUID로 실행을 두 벌 만드는 것을 막는 지점이다.
 */
const retryingNew = ref<number[]>([])
let pollTimer: ReturnType<typeof setInterval> | null = null

function isRetryingNew(fixtureId: number): boolean {
  return retryingNew.value.includes(fixtureId)
}

function nextToken(fixtureId: number): number {
  const token = (tokens.get(fixtureId) ?? 0) + 1
  tokens.set(fixtureId, token)
  return token
}

function stateOf(fixtureId: number): FixtureRunState {
  return states.value[fixtureId] ?? { phase: 'idle' }
}

function setState(fixtureId: number, next: FixtureRunState) {
  states.value = { ...states.value, [fixtureId]: next }
}

/**
 * 생성 요청 하나를 서버가 알아보게 하는 식별자(UUID v4 모양).
 *
 * 응답을 못 받은 요청을 다시 보낼 때 **같은 값**을 다시 쓰면 서버가 기존 실행을 돌려주므로
 * 두 번째 모델 호출이 생기지 않는다. 그래서 값이 비면 안 된다. `randomUUID`가 없는 환경은
 * `getRandomValues`, 그것도 없으면 `Math.random`으로 같은 모양을 만든다(식별 용도일 뿐
 * 비밀값이 아니다).
 */
function newRequestId(): string {
  const source = globalThis.crypto
  if (source && typeof source.randomUUID === 'function') return source.randomUUID()
  const bytes = new Uint8Array(16)
  if (source && typeof source.getRandomValues === 'function') {
    source.getRandomValues(bytes)
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256)
    }
  }
  // RFC 4122 v4 표식.
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

function momentKst(value: string | null): string {
  if (!value) return '시각 미상'
  const at = new Date(value)
  if (Number.isNaN(at.getTime())) return value
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(at)
}

function fixtureLabel(candidate: TestCandidate | null): string {
  if (!candidate) return '경기 미상'
  const home = candidate.home_name ?? '홈팀'
  const away = candidate.away_name ?? '원정팀'
  return `${home} vs ${away}`
}

function candidateOf(fixtureId: number): TestCandidate | null {
  return candidates.value?.candidates.find((row) => row.fixture_id === fixtureId) ?? null
}

const rows = computed(() => candidates.value?.candidates ?? [])

const selectedRows = computed(() =>
  selectedIds.value
    .map((id) => candidateOf(id))
    .filter((row): row is TestCandidate => row !== null),
)

/** 생성은 고른 경기가 하나 이상이면 실행할 수 있다(선택 전체를 순차 실행). */
const hasSelection = computed(() => selectedIds.value.length > 0)

/** 수집 API 계약은 정확히 두 경기다. 이 제약은 선택이 아니라 수집 버튼에만 적용한다. */
const collectionScopeReady = computed(() => selectedIds.value.length === 2)

const collectionActive = computed(
  () => collecting.value || isActiveRun(collectionRun.value?.status ?? null),
)

const canStartCollection = computed(
  () =>
    props.canGenerate &&
    collectionScopeReady.value &&
    plan.value?.can_collect === true &&
    !collectionActive.value,
)

const canGenerateSelection = computed(
  () => props.canGenerate && hasSelection.value && !generating.value && !collectionActive.value,
)

/**
 * 수집 버튼이 눌리지 않는 이유. 선택이 두 개가 아닐 때 화면이 그 사실을 말해 준다
 * (버튼만 흐리게 두면 사용자는 무엇을 고쳐야 하는지 알 수 없다).
 */
const collectionScopeHint = computed(() => {
  const count = selectedIds.value.length
  if (count === 2) return null
  return `기간 수집은 정확히 두 경기가 필요합니다(현재 ${count}경기 선택). 생성을 원하면 ${count}경기 전체를 그대로 실행할 수 있습니다.`
})

const planBlocked = computed(() => {
  const reasons = plan.value?.blocking_reasons ?? []
  return reasons.length > 0 ? reasons : null
})

/** 기간·대상 안내. 서버가 준 값을 그대로 보여준다(값을 만들어 넣지 않는다). */
const scopeLine = computed(() => {
  const current = plan.value
  if (!current) return null
  const start = momentKst(current.fixture_from)
  const end = momentKst(current.fixture_to)
  const names = current.targets
    .map((target) => `${target.league_name ?? '리그 미상'} ${target.season ?? '시즌 미상'}`)
    .join(', ')
  return `수집 기간 ${start} ~ ${end} (KST, 양 끝 포함) · 대상 ${names || '없음'}`
})

/**
 * 수량의 단위 표기.
 *
 * 서버가 `processing_units`라고 하면 그 값은 **경기 건수가 아니라 처리 단위**이고,
 * `legacy_unknown`이면 수량을 모른다. 화면이 이걸 "수집한 경기 N개"로 적으면 사용자는
 * 실제와 다른 규모를 읽는다. 그래서 단위를 값 옆에 붙이고, 모르면 숫자를 쓰지 않는다.
 */
function unitLabel(kind: string | null): string {
  if (kind === 'processing_units') return '처리 단위'
  if (kind === 'legacy_unknown') return '수량 미상'
  return ''
}

function countText(value: number | null, kind: string | null, itemTotalKnown: boolean | null): string {
  // 수량 미상이면 0으로 채우지 않는다(0건 수집과 구분되지 않는다).
  if (kind === 'legacy_unknown' || itemTotalKnown === false) return '미상'
  if (value === null) return '—'
  return String(value)
}

/** 근거 목록에서 꺼낼 키. 화면이 쓰는 네 목록만 다룬다. */
type EvidenceKey = 'planned' | 'stored' | 'detail_stored' | 'unverified'

const EVIDENCE_FIELD = {
  planned: 'planned_fixture_ids',
  stored: 'stored_fixture_ids',
  detail_stored: 'detail_stored_fixture_ids',
  unverified: 'unverified_fixture_ids',
} as const satisfies Record<EvidenceKey, keyof TestCollectionEvidence>

/** 생성 대상(선택 두 경기). 근거의 `scope`가 있으면 그것을, 없으면 서버 계획을 쓴다. */
const evidenceScopeIds = computed<number[]>(() => {
  const evidence = collectionRun.value?.collection_evidence
  if (evidence && evidence.scope_fixture_ids.length > 0) return evidence.scope_fixture_ids
  return plan.value?.fixture_ids ?? []
})

function evidenceList(key: EvidenceKey): number[] | null {
  const evidence = collectionRun.value?.collection_evidence
  if (!evidence) return null
  return evidence[EVIDENCE_FIELD[key]]
}

/** 건수 표기. 목록이 아예 없는 키는 0이 아니라 `—`다(근거 없음과 0건을 구분). */
function evidenceCount(key: EvidenceKey): string {
  const evidence = collectionRun.value?.collection_evidence
  if (!evidence) return '—'
  const value = evidence.counts[key]
  if (value !== null) return String(value)
  const rows = evidenceList(key)
  return rows === null ? '—' : String(rows.length)
}

function idListText(ids: number[] | null): string {
  if (ids === null) return '기록 없음'
  if (ids.length === 0) return '없음(0건)'
  return ids.join(', ')
}

function syncQuery(ids: number[], runIds: Record<number, string>, collection: string | null) {
  const query: Record<string, string> = { ...(route.query as Record<string, string>) }
  query.tab = 'preview'
  if (ids.length > 0) query[SELECTION_QUERY] = ids.join(',')
  else delete query[SELECTION_QUERY]
  // 실행 ID는 **경기 번호와 함께** 남긴다. 순서만 남기면 첫 경기가 실패했을 때 둘째 경기의
  // 실행이 첫 경기 것처럼 복원되어 다른 경기의 저장 문서가 열린다.
  const pairs = ids
    .map((id) => (runIds[id] ? `${id}:${runIds[id]}` : ''))
    .filter((value) => value.length > 0)
  if (pairs.length > 0) query[RUNS_QUERY] = pairs.join(',')
  else delete query[RUNS_QUERY]
  if (collection) query[COLLECTION_QUERY] = collection
  else delete query[COLLECTION_QUERY]
  void router.replace({ query })
}

/**
 * 주소에 남길 실행 ID 목록. 경기 순서대로 저장해 새로고침 뒤에도 **같은 경기의 같은 실행**을
 * GET으로 다시 연다(자동 POST 없음).
 */
function persistedRunIds(): Record<number, string> {
  const map: Record<number, string> = {}
  for (const [key, value] of Object.entries(states.value)) {
    if (value.phase !== 'saved') continue
    map[Number(key)] = value.runId
  }
  return map
}

async function loadCandidates() {
  if (candidatesLoading.value) return
  candidatesLoading.value = true
  candidatesError.value = null
  const response = await previewTestApi.candidates()
  if (disposed) return
  candidatesLoading.value = false
  if (!response.ok) {
    candidatesError.value = response.message
    return
  }
  candidates.value = response.data
  // 주소에서 복원한 선택이 있으면 그대로 두고, 없으면 서버가 준 선두 두 경기를 고른다.
  if (selectedIds.value.length === 0) {
    selectedIds.value = response.data.candidates.slice(0, 2).map((row) => row.fixture_id)
  }
}

/** 선택이 바뀌면 이전 계획 응답을 버린다(늦게 온 값이 현재 선택의 안내를 덮지 않게). */
let planSequence = 0

async function loadPlan() {
  const sequence = ++planSequence
  // 계획은 수집 범위(정확히 두 경기)의 기간·대상을 해석하는 조회다. 세 경기 이상이면
  // 서버가 422로 거부하므로 보내지 않고, 수집 버튼이 이유를 안내한다.
  if (!collectionScopeReady.value) {
    plan.value = null
    planError.value = null
    planLoading.value = false
    return
  }
  const wanted = [...selectedIds.value]
  planLoading.value = true
  planError.value = null
  const response = await previewTestApi.plan(wanted)
  if (disposed || sequence !== planSequence) return
  planLoading.value = false
  if (!response.ok) {
    plan.value = null
    planError.value = response.message
    return
  }
  plan.value = response.data
}

/**
 * 후보 선택 토글.
 *
 * 생성은 **선택 전체**를 순차 실행하므로 세 개 이상을 허용하고, 사용자가 고른 것을
 * 자동으로 빼지 않는다(고른 경기가 소리 없이 사라지면 무엇을 생성할지 알 수 없다).
 * 수집만 API 계약이 정확히 두 경기이므로, 그 제약은 선택을 깎는 대신 **수집 버튼**에서
 * 안내한다.
 */
function toggleSelection(fixtureId: number) {
  if (collectionActive.value || generating.value) return
  const current = selectedIds.value
  selectedIds.value = current.includes(fixtureId)
    ? current.filter((id) => id !== fixtureId)
    : [...current, fixtureId]
  syncQuery(selectedIds.value, persistedRunIds(), collectionRun.value?.run_id ?? null)
}

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

/**
 * 수집 실행 상태를 GET으로 따라간다. 종료가 확인되면 폴링만 멈추고 **생성은 시작하지
 * 않는다**(이 함수 어디에서도 generate 를 부르지 않는다).
 */
function watchCollection(runId: string) {
  stopPolling()
  pollTimer = setInterval(() => {
    void refreshCollection(runId)
  }, 3000)
}

async function refreshCollection(runId: string) {
  const response = await previewTestApi.run(runId)
  if (disposed) return
  if (!response.ok) {
    collectionError.value = response.message
    return
  }
  collectionRun.value = response.data
  collectionError.value = null
  if (!isActiveRun(response.data.status)) {
    stopPolling()
    collecting.value = false
    collectionNotice.value = `수집 실행이 ${response.data.status} 상태로 끝났습니다. 생성은 시작하지 않았습니다. 아래 '선택 경기 프리뷰 생성'을 눌러야 실행됩니다.`
  }
}

async function startCollection() {
  const current = plan.value
  if (!canStartCollection.value || !current) return
  // 끝 시각이 없으면 수집 기간이 성립하지 않는다. 서버도 실행 불가로 표시했으므로
  // 값을 만들어 보내지 않고 사유를 그대로 보여준다.
  if (current.fixture_to === null) {
    collectionError.value = '수집 끝 시각을 확인하지 못해 실행할 수 없습니다. 다른 경기를 선택하세요.'
    return
  }
  collecting.value = true
  collectionError.value = null
  collectionNotice.value = null
  const response = await previewTestApi.startRun({
    fixture_ids: [...current.fixture_ids],
    fixture_from: current.fixture_from,
    fixture_to: current.fixture_to,
  })
  if (disposed) return
  if (!response.ok) {
    collecting.value = false
    collectionError.value = response.message
    return
  }
  collectionRun.value = response.data
  syncQuery(selectedIds.value, persistedRunIds(), response.data.run_id)
  if (isActiveRun(response.data.status)) {
    watchCollection(response.data.run_id)
    return
  }
  collecting.value = false
  collectionNotice.value = `수집 실행이 ${response.data.status} 상태로 끝났습니다. 생성은 시작하지 않았습니다.`
}

/**
 * 실행 하나를 다시 읽어 저장 상태를 판정한다.
 *
 * - 같은 실행의 섹션 결과만 쓴다(`run_id` 일치 확인). 다른 실행/경기 결과는 채택하지 않는다.
 * - 섹션 결과 조회가 실패하면 "저장됨"으로 읽지 않는다(`unknown`).
 * - 신계약 `storage_mismatch`는 저장 불일치로 남긴다. 이때 원문은 문서 wrapper의 접힌 진단에만
 *   남고 정상 문서로 그리지 않는다.
 */
async function readStored(runId: string, fixtureId: number): Promise<StorageOutcome> {
  const data = await getPreviewRun(runId)
  const readerFixtureId = data.preview?.fixture.fixture_id ?? null
  // 다른 경기의 reader 본문이 오면 이 실행의 문서로 채택하지 않는다.
  if (readerFixtureId !== null && readerFixtureId !== fixtureId) {
    return {
      kind: 'unknown',
      reason: `저장 응답의 경기(${readerFixtureId})가 요청한 경기(${fixtureId})와 다릅니다.`,
    }
  }
  if (data.sections.run_id !== runId) {
    return {
      kind: 'unknown',
      reason: `섹션 결과가 다른 실행(${data.sections.run_id})의 것입니다.`,
    }
  }
  if (data.sections_error) {
    return { kind: 'unknown', reason: data.sections_error }
  }
  const mismatched = storageMismatchSections(data.sections)
  if (mismatched.length > 0) {
    return {
      kind: 'mismatch',
      sections: mismatched,
      message: `정본 저장 행을 찾지 못한 섹션: ${mismatched.join(', ')}`,
    }
  }
  if (data.preview === null && data.sections.section_results.length === 0) {
    return { kind: 'unknown', reason: data.preview_error ?? '저장된 결과를 읽지 못했습니다.' }
  }
  return { kind: 'persisted' }
}

/**
 * 경기 하나를 생성하고 저장을 확인한다. 실패해도 예외를 던지지 않는다(다음 경기를 막지 않는다).
 *
 * `requestId`가 비어 있으면 새로 만든다. 재전송이면 호출자가 같은 값을 넘긴다.
 */
async function generateOne(fixtureId: number, requestId: string): Promise<void> {
  const token = nextToken(fixtureId)
  setState(fixtureId, { phase: 'generating', requestId })
  const response = requestId
    ? await generatePreview(fixtureId, { requestId })
    : await generatePreview(fixtureId)
  if (disposed || tokens.get(fixtureId) !== token) return
  if (!response.ok) {
    setState(fixtureId, {
      phase: 'failed',
      requestId,
      message: response.message,
      // 통신 실패는 서버에 실행이 남았을 수 있다. 그때만 "같은 요청 재전송"을 연다.
      mayHaveReachedServer: response.kind === 'network',
    })
    return
  }
  const runId = response.data.run_id
  const storage = await readStored(runId, fixtureId)
  if (disposed || tokens.get(fixtureId) !== token) return
  setState(fixtureId, {
    phase: 'saved',
    requestId,
    runId,
    status: response.data.status,
    storage,
  })
}

/** 사용자가 누른 다경기 생성. 고른 순서대로 하나씩 처리하고, 실패는 다음 경기를 막지 않는다. */
async function generateSelection() {
  if (!canGenerateSelection.value) return
  generating.value = true
  generateNotice.value = null
  const targets = [...selectedIds.value]
  for (const fixtureId of targets) {
    if (disposed) return
    await generateOne(fixtureId, newRequestId())
  }
  if (disposed) return
  generating.value = false
  generateNotice.value = '선택한 경기의 생성 요청을 모두 마쳤습니다. 경기별 결과는 아래 표에서 확인하세요.'
  syncQuery(selectedIds.value, persistedRunIds(), collectionRun.value?.run_id ?? null)
}

/** 응답을 못 받은 요청을 **같은 식별자로** 다시 보낸다. 새 실행을 만들지 않는다. */
async function retrySameRequest(fixtureId: number) {
  const current = stateOf(fixtureId)
  if (current.phase !== 'failed' || !current.requestId) return
  generating.value = true
  await generateOne(fixtureId, current.requestId)
  if (disposed) return
  generating.value = false
  syncQuery(selectedIds.value, persistedRunIds(), collectionRun.value?.run_id ?? null)
}

/** 사용자가 **새 실행**을 명시한 재시도. 새 식별자로 보낸다.
 *
 * 요청이 끝나기 전의 두 번째 클릭은 무시한다. 그대로 두면 클릭마다 새 UUID가 만들어져
 * 같은 경기에 실행이 두 벌 생기고 모델 호출도 두 번 나간다.
 */
async function retryNewRequest(fixtureId: number) {
  if (isRetryingNew(fixtureId)) return
  retryingNew.value = [...retryingNew.value, fixtureId]
  generating.value = true
  try {
    await generateOne(fixtureId, newRequestId())
  } finally {
    // 화면이 이미 사라졌어도 목록은 정리한다(다음 진입을 막지 않는다).
    retryingNew.value = retryingNew.value.filter((id) => id !== fixtureId)
  }
  if (disposed) return
  generating.value = false
  syncQuery(selectedIds.value, persistedRunIds(), collectionRun.value?.run_id ?? null)
}

function openDocument(fixtureId: number) {
  const current = stateOf(fixtureId)
  if (current.phase !== 'saved') return
  const row = candidateOf(fixtureId)
  emit('openDocument', {
    runId: current.runId,
    fixtureId,
    kickoffAt: row?.kickoff_at ?? null,
  })
}

/**
 * 표에 그릴 값. 상태 유니온을 템플릿에서 다시 해석하지 않도록 script 의 함수로만 꺼낸다
 * (템플릿 캐스트는 상태 판별을 흐린다).
 */
function generationLabel(fixtureId: number): string {
  const current = stateOf(fixtureId)
  if (current.phase === 'generating') return '생성 중'
  if (current.phase === 'saved') return '생성 응답 성공'
  if (current.phase === 'failed') return '실패'
  return '시작 안 함'
}

function generationDetail(fixtureId: number): string | null {
  const current = stateOf(fixtureId)
  if (current.phase === 'saved') return `실행 ${current.runId}`
  if (current.phase === 'failed') return current.message
  return null
}

function generationTone(fixtureId: number): 'busy' | 'ok' | 'bad' | 'none' {
  const phase = stateOf(fixtureId).phase
  if (phase === 'generating') return 'busy'
  if (phase === 'saved') return 'ok'
  if (phase === 'failed') return 'bad'
  return 'none'
}

type StorageTone = 'none' | 'ok' | 'bad' | 'warn'

function storageTone(fixtureId: number): StorageTone {
  const current = stateOf(fixtureId)
  if (current.phase !== 'saved') return 'none'
  if (current.storage.kind === 'persisted') return 'ok'
  if (current.storage.kind === 'mismatch') return 'bad'
  return 'warn'
}

function storageLabel(fixtureId: number): string {
  const current = stateOf(fixtureId)
  if (current.phase !== 'saved') return '—'
  if (current.storage.kind === 'persisted') return '저장 확인'
  if (current.storage.kind === 'mismatch') return '저장 불일치(문서 차단)'
  return '저장 확인 불가'
}

function storageNote(fixtureId: number): string | null {
  const current = stateOf(fixtureId)
  if (current.phase !== 'saved') return null
  if (current.storage.kind === 'mismatch') return current.storage.message
  if (current.storage.kind === 'unknown') return current.storage.reason
  return null
}

function runIdOf(fixtureId: number): string | null {
  const current = stateOf(fixtureId)
  return current.phase === 'saved' ? current.runId : null
}

/** 통신 실패만 "같은 요청 재전송"을 연다(서버에 남았을 수 있는 유일한 경우). */
function canRetrySame(fixtureId: number): boolean {
  const current = stateOf(fixtureId)
  return current.phase === 'failed' && current.mayHaveReachedServer && current.requestId.length > 0
}

/**
 * 명시적 새 실행은 **실패한 경기**와 **응답이 오지 않는 진행 중 경기**에서 연다.
 *
 * 진행 중인 요청을 사용자가 기다리지 않고 새로 시작할 수 있어야 하고, 그때 먼저 보낸 요청의
 * 늦은 응답이 새 실행의 표시를 덮으면 사용자는 어느 결과가 현재 것인지 알 수 없다.
 */
function canRetryNew(fixtureId: number): boolean {
  const phase = stateOf(fixtureId).phase
  return phase === 'failed' || phase === 'generating'
}

watch(selectedIds, () => {
  void loadPlan()
})

/** 주소에 남은 실행·선택을 GET으로만 복원한다. 새 POST는 만들지 않는다. */
async function restoreFromQuery() {
  const ids = String(route.query[SELECTION_QUERY] ?? '')
    .split(',')
    .map((token) => Number(token.trim()))
    .filter((value) => Number.isSafeInteger(value) && value > 0)
  // 생성은 두 경기로 제한되지 않으므로 선택도 개수 제한 없이 복원한다. 수집 버튼의
  // "정확히 두 경기" 조건은 선택을 깎지 않고 버튼에서만 안내한다.
  if (ids.length > 0) selectedIds.value = ids

  await loadCandidates()
  if (disposed) return

  const collectionId = route.query[COLLECTION_QUERY]
  if (typeof collectionId === 'string' && collectionId.trim()) {
    const response = await previewTestApi.run(collectionId.trim())
    if (disposed) return
    if (response.ok) {
      collectionRun.value = response.data
      if (isActiveRun(response.data.status)) watchCollection(response.data.run_id)
    } else {
      collectionError.value = response.message
    }
  }

  const runIds = String(route.query[RUNS_QUERY] ?? '')
    .split(',')
    .map((token) => token.trim())
    .filter((token) => token.length > 0)
  if (runIds.length === 0) return
  // 실행은 `경기번호:실행ID` 짝으로 남아 있다. 짝이 없는 실행 ID는 어느 경기의 것인지
  // 알 수 없으므로 채택하지 않는다(추측해서 다른 경기에 붙이지 않는다).
  const pairs = runIds
    .map((token) => {
      const [fixtureToken, runId] = token.split(':')
      const fixtureId = Number((fixtureToken ?? '').trim())
      const trimmedRun = (runId ?? '').trim()
      if (!Number.isSafeInteger(fixtureId) || fixtureId <= 0 || trimmedRun.length === 0) return null
      if (!selectedIds.value.includes(fixtureId)) return null
      return { fixtureId, runId: trimmedRun }
    })
    .filter((pair): pair is { fixtureId: number; runId: string } => pair !== null)
  if (pairs.length === 0) return
  await Promise.all(
    pairs.map(async ({ fixtureId, runId }) => {
      const storage = await readStored(runId, fixtureId)
      if (disposed) return
      setState(fixtureId, {
        phase: 'saved',
        // 복원은 조회다. 재전송에 쓸 요청 식별자는 알 수 없으므로 비워 둔다.
        requestId: '',
        runId,
        status: 'persisted',
        storage,
      })
    }),
  )
}

onMounted(async () => {
  // 선택이 정해지면 아래 watch가 계획을 한 번 조회한다(여기서 또 부르지 않는다).
  await restoreFromQuery()
})

onBeforeUnmount(() => {
  disposed = true
  stopPolling()
})
</script>

<template>
  <section class="ptp" data-testid="preview-test-panel" aria-labelledby="ptp-title">
    <header class="ptp__head">
      <h3 id="ptp-title">기간 수집과 여러 경기 생성</h3>
      <p class="ptp__hint">
        추천 경기 두 개를 골라 기간 수집을 먼저 실행하고, 결과를 확인한 뒤 생성 버튼으로 각
        경기의 프리뷰를 만듭니다. 수집이 끝나도 생성은 자동으로 시작되지 않습니다.
      </p>
      <p class="ptp__hint" data-testid="ptp-injuries-note">
        이번 기간 수집은 events·statistics·lineups·players 항목만 갱신합니다. 부상
        자료(/injuries)는 이번 수집에서 갱신되지 않으므로, 부상 카드의 값은 기존 저장 자료이며
        수집 시각과 다를 수 있습니다.
      </p>
    </header>

    <p v-if="candidatesLoading" class="ptp__status" role="status" data-testid="ptp-candidates-loading">
      추천 경기를 불러오는 중입니다.
    </p>
    <p v-if="candidatesError" class="ptp__alert" role="alert" data-testid="ptp-candidates-error">
      추천 경기를 읽지 못했습니다. {{ candidatesError }}
    </p>
    <p v-if="candidates?.reason" class="ptp__hint" data-testid="ptp-candidates-reason">
      {{ candidates.reason }}
    </p>

    <div v-if="rows.length" class="ptp__candidates">
      <p class="ptp__hint">
        후보 {{ rows.length }}경기 · 기준 시각 {{ momentKst(candidates?.as_of ?? null) }} (KST).
        정확히 두 경기를 선택합니다.
      </p>
      <ul class="ptp__list" data-testid="ptp-candidate-list">
        <li v-for="row in rows" :key="row.fixture_id" class="ptp__candidate">
          <label class="ptp__pick">
            <input
              type="checkbox"
              :data-testid="`ptp-candidate-${row.fixture_id}`"
              :checked="selectedIds.includes(row.fixture_id)"
              :disabled="collectionActive || generating"
              @change="toggleSelection(row.fixture_id)"
            />
            <span class="ptp__candidate-label">{{ fixtureLabel(row) }}</span>
          </label>
          <span class="ptp__meta">
            {{ momentKst(row.kickoff_at) }} (KST) · {{ row.league_name ?? '리그 미상' }} ·
            시즌 {{ row.season ?? '—' }} · 경기 {{ row.fixture_id }}
            <template v-if="row.priority !== null"> · 추천 {{ row.priority }}</template>
          </span>
        </li>
      </ul>
    </div>

    <p v-if="!hasSelection" class="ptp__hint" data-testid="ptp-selection-hint">
      경기를 하나 이상 선택해야 시작할 수 있습니다(현재 0경기).
    </p>

    <p v-if="planLoading" class="ptp__status" role="status">수집 기간과 대상을 확인하는 중입니다.</p>
    <p v-if="planError" class="ptp__alert" role="alert" data-testid="ptp-plan-error">
      수집 기간·대상을 확인하지 못했습니다. {{ planError }}
    </p>
    <div v-if="plan" class="ptp__plan" data-testid="ptp-plan">
      <p v-if="scopeLine" class="ptp__scope" data-testid="ptp-scope">{{ scopeLine }}</p>
      <p class="ptp__hint" data-testid="ptp-scope-split">
        위 기간 안의 경기 자료가 실제 수집 범위입니다. 수집 시험의 대상은 이 계획의 두
        경기({{ plan.fixture_ids.join(', ') }})이고, 생성 대상은 아래 선택입니다. 둘은
        범위가 다릅니다.
      </p>
      <ul v-if="plan.scope_notes.length" class="ptp__notes" data-testid="ptp-scope-notes">
        <li v-for="note in plan.scope_notes" :key="note">{{ note }}</li>
      </ul>
      <ul v-if="planBlocked" class="ptp__blocked" data-testid="ptp-blocked">
        <li v-for="(reason, index) in planBlocked" :key="`${reason.code ?? 'reason'}-${index}`">
          {{ reason.message }}
        </li>
      </ul>
    </div>

    <div v-if="canGenerate" class="ptp__actions">
      <button
        type="button"
        class="mm-button mm-button--primary"
        data-testid="ptp-start-collection"
        :disabled="!canStartCollection"
        @click="startCollection"
      >
        {{ collectionActive ? '기간 수집 진행 중…' : '기간 지정 수집' }}
      </button>
      <p class="ptp__hint">수집은 자료만 갱신합니다. 프리뷰 생성은 아래 별도 버튼입니다.</p>
      <p
        v-if="collectionScopeHint"
        class="ptp__hint"
        data-testid="ptp-collection-scope-hint"
      >
        {{ collectionScopeHint }}
      </p>
    </div>

    <p v-if="collectionError" class="ptp__alert" role="alert" data-testid="ptp-collection-error">
      {{ collectionError }}
    </p>
    <p
      v-if="collectionNotice"
      class="ptp__status"
      role="status"
      data-testid="ptp-collection-notice"
    >
      {{ collectionNotice }}
    </p>

    <div v-if="collectionRun" class="ptp__run" data-testid="ptp-collection-run">
      <p class="ptp__run-head">
        수집 실행 {{ collectionRun.run_id }} · 상태 {{ collectionRun.status }}
        <template v-if="collectionRun.progress !== null"> · {{ collectionRun.progress }}%</template>
        <template v-if="collectionRun.stage"> · {{ collectionRun.stage }}</template>
      </p>
      <p class="ptp__meta">
        시작 {{ momentKst(collectionRun.started_at) }} · 종료
        {{ collectionRun.finished_at ? momentKst(collectionRun.finished_at) : '진행 중' }}
      </p>
      <ul v-if="collectionRun.items.length" class="ptp__list" data-testid="ptp-collection-items">
        <li v-for="item in collectionRun.items" :key="`${item.name}-${item.season}`" class="ptp__item">
          <span class="ptp__item-name">{{ item.name }} {{ item.season ?? '' }}</span>
          <span class="ptp__meta" :data-testid="`ptp-item-${item.target_id ?? item.name}`">
            {{ item.status }} · 저장 {{ countText(item.saved, collectionRun.counts_kind, item.total_known) }}
            / 실패 {{ countText(item.failed, collectionRun.counts_kind, item.total_known) }}
            / 전체 {{ countText(item.total, collectionRun.counts_kind, item.total_known) }}
            <template v-if="unitLabel(collectionRun.counts_kind)">
              {{ unitLabel(collectionRun.counts_kind) }}
            </template>
            <template v-if="item.stored_rows !== null"> · 기록 {{ item.stored_rows }}행</template>
          </span>
        </li>
      </ul>
      <ul v-if="collectionRun.errors.length" class="ptp__blocked" data-testid="ptp-collection-errors">
        <li v-for="message in collectionRun.errors" :key="message">{{ message }}</li>
      </ul>
      <p v-if="collectionRun.warning_count" class="ptp__hint">
        경고 {{ collectionRun.warning_count }}건이 기록에 있습니다.
      </p>

      <!--
        실제 수집 근거. 처리 단위 카운터와 다른 축이므로 그 아래에 따로 둔다.
        생성 대상(선택 두 경기)과 기간 안 수집 범위를 합쳐 한 숫자로 보이지 않게 한다.
      -->
      <div class="ptp__evidence" data-testid="ptp-evidence">
        <p class="ptp__run-head">기간 안 실제 수집 근거</p>
        <template v-if="collectionRun.collection_evidence">
          <p class="ptp__hint" data-testid="ptp-evidence-scope">
            생성 대상(선택한 두 경기): {{ idListText(evidenceScopeIds) }}. 아래 목록은 기간 안
            수집 범위이며 이 두 경기와 별개입니다.
          </p>
          <p
            v-if="collectionRun.collection_evidence.partial"
            class="ptp__hint"
            data-testid="ptp-evidence-partial"
          >
            수집 범위 일부를 확인하지 못했습니다. 아래 건수는 확인된 범위 기준입니다.
          </p>
          <details class="ptp__evidence-detail" data-testid="ptp-evidence-detail">
            <summary>
              계획 {{ evidenceCount('planned') }} · 저장 확인 {{ evidenceCount('stored') }} ·
              상세 응답 저장 {{ evidenceCount('detail_stored') }} · 미확인
              {{ evidenceCount('unverified') }}
            </summary>
            <dl class="ptp__facts">
              <dt>계획(기간 내)</dt>
              <dd data-testid="ptp-evidence-planned">{{ idListText(evidenceList('planned')) }}</dd>
              <dt>저장 확인</dt>
              <dd data-testid="ptp-evidence-stored">{{ idListText(evidenceList('stored')) }}</dd>
              <dt>상세 응답 저장</dt>
              <dd data-testid="ptp-evidence-detail-stored">
                {{ idListText(evidenceList('detail_stored')) }}
              </dd>
              <dt>저장 미확인</dt>
              <dd data-testid="ptp-evidence-unverified">
                {{ idListText(evidenceList('unverified')) }}
              </dd>
            </dl>
            <ul v-if="collectionRun.collection_evidence.notes.length" class="ptp__notes">
              <li v-for="note in collectionRun.collection_evidence.notes" :key="note">
                {{ note }}
              </li>
            </ul>
          </details>
          <p class="ptp__hint">
            저장 미확인은 실패로 단정하지 않습니다. 상세 응답 저장은 정상 빈 응답도 포함하므로
            자료가 채워졌다는 뜻이 아닙니다. 부상 자료(/injuries)는 이번 수집에 포함되지
            않습니다.
          </p>
        </template>
        <p v-else class="ptp__hint" data-testid="ptp-evidence-missing">
          이 실행에는 아직 실제 수집 근거가 기록되지 않았습니다(0건으로 추정하지 않습니다).
          아래 처리 단위 수량은 경기 수와 다른 값입니다.
        </p>
      </div>
      <button
        type="button"
        class="mm-button mm-button--quiet"
        data-testid="ptp-collection-refresh"
        @click="refreshCollection(collectionRun.run_id)"
      >
        수집 상태 다시 읽기
      </button>
    </div>

    <div v-if="canGenerate" class="ptp__actions">
      <button
        type="button"
        class="mm-button mm-button--primary"
        data-testid="ptp-generate"
        :disabled="!canGenerateSelection"
        @click="generateSelection"
      >
        {{ generating ? '선택 경기 생성 중…' : `선택 ${selectedIds.length}경기 프리뷰 생성` }}
      </button>
      <p class="ptp__hint">
        고른 순서대로 한 경기씩 생성합니다. 한 경기가 실패해도 다음 경기는 계속 진행합니다.
      </p>
    </div>
    <p v-if="generateNotice" class="ptp__status" role="status" data-testid="ptp-generate-notice">
      {{ generateNotice }}
    </p>

    <table v-if="selectedRows.length" class="ptp__table" data-testid="ptp-fixture-table">
      <caption class="ptp__hint">선택한 경기의 생성·저장 결과</caption>
      <thead>
        <tr>
          <th scope="col">경기</th>
          <th scope="col">생성</th>
          <th scope="col">저장 조회</th>
          <th scope="col">문서</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in selectedRows" :key="row.fixture_id" :data-testid="`ptp-row-${row.fixture_id}`">
          <th scope="row">
            <span class="ptp__item-name">{{ fixtureLabel(row) }}</span>
            <span class="ptp__meta">{{ momentKst(row.kickoff_at) }} (KST) · {{ row.fixture_id }}</span>
          </th>
          <td>
            <span
              class="ptp__badge"
              :class="{
                'ptp__badge--busy': generationTone(row.fixture_id) === 'busy',
                'ptp__badge--ok': generationTone(row.fixture_id) === 'ok',
                'ptp__badge--bad': generationTone(row.fixture_id) === 'bad',
              }"
              :data-testid="`ptp-generation-${row.fixture_id}`"
            >
              {{ generationLabel(row.fixture_id) }}
            </span>
            <span
              v-if="generationDetail(row.fixture_id)"
              class="ptp__meta"
              :data-testid="`ptp-generation-detail-${row.fixture_id}`"
            >
              {{ generationDetail(row.fixture_id) }}
            </span>
          </td>
          <td>
            <span
              class="ptp__badge"
              :class="{
                'ptp__badge--ok': storageTone(row.fixture_id) === 'ok',
                'ptp__badge--bad': storageTone(row.fixture_id) === 'bad',
                'ptp__badge--warn': storageTone(row.fixture_id) === 'warn',
              }"
              :data-testid="`ptp-storage-${row.fixture_id}`"
            >
              {{ storageLabel(row.fixture_id) }}
            </span>
            <span
              v-if="storageNote(row.fixture_id)"
              class="ptp__meta"
              :data-testid="`ptp-storage-note-${row.fixture_id}`"
            >
              {{ storageNote(row.fixture_id) }}
            </span>
          </td>
          <td>
            <button
              v-if="runIdOf(row.fixture_id)"
              type="button"
              class="mm-button"
              :data-testid="`ptp-open-${row.fixture_id}`"
              @click="openDocument(row.fixture_id)"
            >
              저장된 문서 보기
            </button>
            <template v-else-if="canRetryNew(row.fixture_id)">
              <button
                v-if="canRetrySame(row.fixture_id)"
                type="button"
                class="mm-button"
                :data-testid="`ptp-retry-same-${row.fixture_id}`"
                @click="retrySameRequest(row.fixture_id)"
              >
                같은 요청 재전송
              </button>
              <button
                type="button"
                class="mm-button mm-button--quiet"
                :data-testid="`ptp-retry-new-${row.fixture_id}`"
                :disabled="isRetryingNew(row.fixture_id)"
                @click="retryNewRequest(row.fixture_id)"
              >
                {{ isRetryingNew(row.fixture_id) ? '재생성 중…' : '새 실행으로 다시 생성' }}
              </button>
            </template>
            <span v-else class="ptp__meta">—</span>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.ptp {
  display: grid;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-card);
  min-width: 0;
}

.ptp__head {
  display: grid;
  gap: 6px;
}

.ptp__head h3 {
  margin: 0;
  font-size: 15px;
}

.ptp__hint,
.ptp__meta,
.ptp__status {
  margin: 0;
  color: var(--color-muted);
  font-size: 12px;
  line-height: 1.6;
}

.ptp__alert {
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

.ptp__candidates,
.ptp__plan,
.ptp__run,
.ptp__actions {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.ptp__scope {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
}

.ptp__list,
.ptp__notes,
.ptp__blocked {
  display: grid;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 12px;
}

.ptp__blocked {
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-left: 3px solid #a3262b;
  border-radius: 6px;
  color: #7a1c20;
}

.ptp__candidate,
.ptp__item {
  display: grid;
  gap: 2px;
  padding: 6px 0;
  border-bottom: 1px solid var(--color-border);
}

.ptp__pick {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 13px;
  font-weight: 700;
}

.ptp__candidate-label,
.ptp__item-name {
  font-weight: 700;
  font-size: 13px;
}

.ptp__run-head {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  overflow-wrap: anywhere;
}

.ptp__evidence {
  display: grid;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg);
}

.ptp__evidence-detail > summary {
  cursor: pointer;
  font-size: 12px;
  color: var(--color-muted);
}

.ptp__facts {
  display: grid;
  grid-template-columns: minmax(0, max-content) minmax(0, 1fr);
  gap: 4px 12px;
  margin: 6px 0 0;
  font-size: 12px;
}

.ptp__facts dt {
  color: var(--color-muted);
}

.ptp__facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.ptp__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.ptp__table caption {
  text-align: left;
  padding-bottom: 6px;
}

.ptp__table th,
.ptp__table td {
  padding: 8px 6px;
  border-bottom: 1px solid var(--color-border);
  text-align: left;
  vertical-align: top;
}

.ptp__table thead th {
  color: var(--color-muted);
  font-weight: 600;
}

.ptp__badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 999px;
  border: 1px solid var(--color-border);
  font-size: 11px;
}

.ptp__badge--ok {
  border-color: #b4d6bb;
  background: #eef7ef;
  color: #1f5b2c;
}

.ptp__badge--bad {
  border-color: #e5c3c3;
  background: #fbeceb;
  color: #7a1c20;
}

.ptp__badge--warn {
  border-color: #e2d3ad;
  background: #fbf5e6;
  color: #6b5118;
}

.ptp__badge--busy {
  border-color: var(--color-border);
  background: var(--color-bg);
  color: var(--color-muted);
}
</style>
