/**
 * 기간 수집 시험·다경기 생성이 쓰는 API 클라이언트.
 *
 * 수집 시험 API(`/api/v1/admin/management/preview-test`)만 별도 수집 프로세스로 간다.
 * 프리뷰 생성·조회는 기존 `preview.ts` 경로를 그대로 쓰고, 이 파일은 그 경로를 다시 만들지
 * 않는다.
 *
 * 지키는 것:
 *
 * - 조회는 GET만 보낸다. 수집 시작(POST)은 사용자가 버튼을 누를 때 한 번만 나간다.
 * - 응답은 경계에서 **한 번만** 해석한다(`parse*`). 모양이 계약과 다르면 빈 목록으로
 *   바꾸지 않고 해석 실패 사유를 돌려준다(자료 없음으로 위장하지 않는다).
 * - 없는 값을 추측해 채우지 않는다. 모르는 필드는 `null`이다.
 * - 수집 실행 응답은 기존 management run 형식을 재사용하고, 여기서 화면용 모양으로
 *   정규화한다(`parseRun`). 실행 ID는 `id`(기존 형식)와 `run_id` 표기를 모두 받는다.
 */
import { authenticatedFetch } from './session'
import type { ApiResult } from './http'

const COLLECTION_BASE = '/api/v1/admin/management/preview-test'

/** 추천 경기 후보 한 건. `fixture_id`는 외부(API-Football) 경기 ID다. */
export type TestCandidate = {
  fixture_id: number
  kickoff_at: string | null
  home_name: string | null
  away_name: string | null
  league_name: string | null
  season: number | null
  /** 추천 우선순위. 작을수록 앞선다. 서버가 주지 않으면 `null`. */
  priority: number | null
}

export type TestCandidates = {
  as_of: string | null
  /** 서버가 밝힌 시간대. 보통 `Asia/Seoul`. */
  timezone: string
  candidates: TestCandidate[]
  /** 후보가 부족한 사유(정상이면 `null`). */
  reason: string | null
}

export type TestPlanTarget = {
  id: number
  league_name: string | null
  season: number | null
  include_details: boolean
}

/** 기간 수집 계획. 서버가 활성 대상·기간을 해석한 결과다. */
export type TestPlan = {
  fixture_ids: number[]
  /** 수집 시작(KST 당일 00:00). 시간대 포함 ISO 문자열. */
  fixture_from: string
  /** 수집 끝(두 경기 중 마지막 킥오프). 시간대 포함 ISO 문자열. */
  fixture_to: string
  target_ids: number[]
  targets: TestPlanTarget[]
  can_collect: boolean
  blocking_reasons: string[]
  scope_notes: string[]
}

/**
 * 수집 대상별 진행 항목.
 *
 * **`total`/`saved`/`failed`는 경기 건수가 아니다.** 서버가 `counts_kind='processing_units'`로
 * 표시하면 처리 단위 수이고, `legacy_unknown`이면 수량 자체를 모른다. 이 값을 "수집한 경기
 * N개"로 읽으면 사용자는 실제보다 많은 경기가 수집됐다고 오해한다. 그래서 단위 표기를 함께
 * 보관하고, 모르는 값은 `null`로 둔다(0으로 채우지 않는다).
 */
export type TestRunItem = {
  target_id: number | null
  name: string
  season: number | null
  status: string
  total_known: boolean | null
  total: number | null
  saved: number | null
  failed: number | null
  pending: number | null
  stored_rows: number | null
}

/** 수집만 시험 실행의 화면용 요약. 기존 management run 응답에서 옮긴 값만 담는다. */
export type TestRun = {
  run_id: string
  status: string
  actor: string | null
  created_at: string | null
  started_at: string | null
  finished_at: string | null
  progress: number | null
  stage: string | null
  /**
   * 수량의 단위(`processing_units` | `legacy_unknown` | 그 밖의 서버 표기).
   * 경기 건수로 표시하면 안 되는 값을 화면이 구분하는 근거다.
   */
  counts_kind: string | null
  items: TestRunItem[]
  /** 로그에서 뽑은 오류 문장(최대 5개). 없으면 빈 배열. */
  errors: string[]
  warning_count: number
}

export type StartRunPayload = {
  fixture_ids: number[]
  fixture_from: string
  fixture_to: string
}

/** 진행 중으로 볼 상태. 이 밖의 값은 종료로 읽는다(기존 management run 상태 이름). */
const ACTIVE_STATUSES = new Set(['queued', 'running', 'cancel_requested'])

export function isActiveRun(status: string | null | undefined): boolean {
  return status !== null && status !== undefined && ACTIVE_STATUSES.has(status)
}

function record(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function text(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : null
}

function intOf(value: unknown): number | null {
  if (typeof value === 'number' && Number.isSafeInteger(value)) return value
  if (typeof value === 'string' && /^-?\d+$/.test(value.trim())) {
    const parsed = Number(value.trim())
    return Number.isSafeInteger(parsed) ? parsed : null
  }
  return null
}

export type Parsed<T> = { ok: true; value: T } | { ok: false; reason: string }

function bad<T>(reason: string): Parsed<T> {
  return { ok: false, reason }
}

function textList(value: unknown): string[] {
  return list(value)
    .map((entry) => (typeof entry === 'string' ? entry.trim() : ''))
    .filter((entry) => entry.length > 0)
}

export function parseCandidates(payload: unknown): Parsed<TestCandidates> {
  const root = record(payload)
  if (!root) return bad('후보 응답이 객체가 아닙니다.')
  const rows = list(root.candidates)
  if (!Array.isArray(root.candidates)) return bad('후보 응답에 candidates 배열이 없습니다.')
  const candidates: TestCandidate[] = []
  for (const raw of rows) {
    const row = record(raw)
    if (!row) continue
    const fixtureId = intOf(row.fixture_id)
    if (fixtureId === null) continue
    candidates.push({
      fixture_id: fixtureId,
      kickoff_at: text(row.kickoff_at),
      home_name: text(row.home_name),
      away_name: text(row.away_name),
      league_name: text(row.league_name),
      season: intOf(row.season),
      priority: intOf(row.priority),
    })
  }
  return {
    ok: true,
    value: {
      as_of: text(root.as_of),
      timezone: text(root.timezone) ?? 'Asia/Seoul',
      candidates,
      reason: text(root.reason),
    },
  }
}

export function parsePlan(payload: unknown): Parsed<TestPlan> {
  const root = record(payload)
  if (!root) return bad('수집 계획 응답이 객체가 아닙니다.')
  const fixtureFrom = text(root.fixture_from)
  const fixtureTo = text(root.fixture_to)
  if (fixtureFrom === null || fixtureTo === null) {
    return bad('수집 계획 응답에 기간(fixture_from/fixture_to)이 없습니다.')
  }
  const targets: TestPlanTarget[] = []
  for (const raw of list(root.targets)) {
    const row = record(raw)
    if (!row) continue
    const id = intOf(row.id)
    if (id === null) continue
    targets.push({
      id,
      league_name: text(row.league_name),
      season: intOf(row.season),
      include_details: row.include_details === true,
    })
  }
  const fixtureIds = list(root.fixture_ids)
    .map((entry) => intOf(entry))
    .filter((entry): entry is number => entry !== null)
  return {
    ok: true,
    value: {
      fixture_ids: fixtureIds,
      fixture_from: fixtureFrom,
      fixture_to: fixtureTo,
      target_ids: list(root.target_ids)
        .map((entry) => intOf(entry))
        .filter((entry): entry is number => entry !== null),
      targets,
      // 실행 가능 여부를 주지 않으면 실행 불가로 읽는다(없는 허가를 만들지 않는다).
      can_collect: root.can_collect === true,
      blocking_reasons: textList(root.blocking_reasons),
      scope_notes: textList(root.scope_notes),
    },
  }
}

export function parseRun(payload: unknown): Parsed<TestRun> {
  const root = record(payload)
  if (!root) return bad('수집 실행 응답이 객체가 아닙니다.')
  const runId = text(root.id) ?? text(root.run_id)
  if (runId === null) return bad('수집 실행 응답에 실행 ID가 없습니다.')
  const status = text(root.status)
  if (status === null) return bad('수집 실행 응답에 상태가 없습니다.')
  const items: TestRunItem[] = []
  for (const raw of list(root.items)) {
    const row = record(raw)
    if (!row) continue
    items.push({
      target_id: intOf(row.target_id),
      name: text(row.name) ?? '대상 미상',
      season: intOf(row.season),
      status: text(row.status) ?? '상태 미상',
      total_known: typeof row.total_known === 'boolean' ? row.total_known : null,
      total: intOf(row.total),
      saved: intOf(row.saved),
      failed: intOf(row.failed),
      pending: intOf(row.pending),
      stored_rows: intOf(row.stored_rows),
    })
  }
  const errors: string[] = []
  let warningCount = 0
  for (const raw of list(root.logs)) {
    const row = record(raw)
    if (!row) continue
    if (row.level === 'error') {
      const message = text(row.message)
      if (message !== null && errors.length < 5) errors.push(message)
    } else if (row.level === 'warning') {
      warningCount += 1
    }
  }
  return {
    ok: true,
    value: {
      run_id: runId,
      status,
      actor: text(root.actor),
      created_at: text(root.created_at),
      started_at: text(root.started_at),
      finished_at: text(root.finished_at),
      progress: intOf(root.progress),
      stage: text(root.stage),
      counts_kind: text(root.counts_kind),
      items,
      errors,
      warning_count: warningCount,
    },
  }
}

type Sent = { ok: true; status: number; payload: unknown } | { ok: false; failure: ApiResult<never> }

/**
 * 수집 시험 경로 전송. 기존 정식 access token을 그대로 붙인다(로그인 흐름은 건드리지 않는다).
 *
 * 연결 실패는 `network`로 남긴다. 화면은 그 사실을 "수집 서버 미설정/미응답"으로 구분해
 * 보여주고, 자동으로 다른 서버로 다시 보내지 않는다.
 */
async function send(path: string, init: RequestInit = {}): Promise<Sent> {
  let response: Response
  try {
    response = await authenticatedFetch(`${COLLECTION_BASE}${path}`, {
      ...init,
      headers: {
        ...(init.body ? { 'content-type': 'application/json' } : {}),
        accept: 'application/json',
        ...init.headers,
      },
    })
  } catch {
    return {
      ok: false,
      failure: {
        ok: false,
        kind: 'network',
        status: 0,
        message:
          '수집 시험 서버에 연결하지 못했습니다. 같은 오리진 프록시 설정(BENCHMARK_COLLECTION_BACKEND_URL)을 확인하세요.',
      },
    }
  }

  let payload: unknown = null
  if ((response.headers.get('content-type') ?? '').includes('application/json')) {
    payload = await response.json().catch(() => null)
  }
  if (response.ok) return { ok: true, status: response.status, payload }

  const detail =
    payload && typeof payload === 'object' && 'detail' in payload
      ? String((payload as { detail: unknown }).detail)
      : null
  const message =
    detail ??
    (response.status === 401
      ? '로그인이 필요합니다.'
      : response.status === 403
        ? '관리자 권한이 없는 계정입니다.'
        : response.status >= 500
          ? '수집 시험 서버가 요청을 처리하지 못했습니다.'
          : '요청을 처리하지 못했습니다.')
  return {
    ok: false,
    failure: {
      ok: false,
      kind:
        response.status === 401
          ? 'unauthenticated'
          : response.status === 403
            ? 'forbidden'
            : response.status >= 500
              ? 'server'
              : 'unknown',
      status: response.status,
      message,
    },
  }
}

/** 해석 실패를 화면이 그대로 보여줄 실패 값으로 바꾼다(빈 값으로 대체하지 않는다). */
function parseFailure(reason: string): ApiResult<never> {
  return {
    ok: false,
    kind: 'server',
    status: 200,
    message: `서버 응답을 해석하지 못했습니다: ${reason}`,
  }
}

async function getParsed<T>(path: string, parse: (payload: unknown) => Parsed<T>): Promise<ApiResult<T>> {
  const sent = await send(path)
  if (!sent.ok) {
    // 실패 값을 그대로 넘긴다. 성공/실패 판별은 호출자의 몫이다.
    return sent.failure as ApiResult<T>
  }
  const parsed = parse(sent.payload)
  return parsed.ok ? { ok: true, data: parsed.value } : parseFailure(parsed.reason)
}

export const previewTestApi = {
  /** 추천 후보(읽기 전용). 서버가 부족 사유를 함께 준다. */
  candidates(): Promise<ApiResult<TestCandidates>> {
    return getParsed('/candidates', parseCandidates)
  },

  /** 선택한 정확히 두 경기의 수집 기간·활성 대상. 서버가 실행 직전 다시 검증한다. */
  plan(fixtureIds: number[]): Promise<ApiResult<TestPlan>> {
    const params = new URLSearchParams()
    for (const id of fixtureIds) params.append('fixture_ids', String(id))
    const suffix = params.size > 0 ? `?${params.toString()}` : ''
    return getParsed(`/plan${suffix}`, parsePlan)
  },

  /** 사용자가 누른 기간 수집 시작. 생성은 이 요청에 포함되지 않는다. */
  async startRun(payload: StartRunPayload): Promise<ApiResult<TestRun>> {
    const sent = await send('/runs', { method: 'POST', body: JSON.stringify(payload) })
    if (!sent.ok) return sent.failure as ApiResult<TestRun>
    const parsed = parseRun(sent.payload)
    return parsed.ok ? { ok: true, data: parsed.value } : parseFailure(parsed.reason)
  },

  /** 실행 하나의 현재 상태(부작용 없는 조회). */
  run(runId: string): Promise<ApiResult<TestRun>> {
    return getParsed(`/runs/${encodeURIComponent(runId)}`, parseRun)
  },
}
