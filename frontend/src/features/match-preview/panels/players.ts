/**
 * R4 주목 선수 선정 — 화면용 타입·표시 규칙.
 *
 * 사용자 확정(2026-11-11): 각 선정 항목은 **두 개의 독자 표시 필드**를 가진다.
 *
 * - `selected_player`: 선정 선수 (DB 한국어 이름)
 * - `selection_reason`: 선정 이유 (짧은 한국어 설명)
 *
 * 두 값을 한 문장으로 합치지 않는다. ID·출처·매핑 상태는 내부 메타데이터이며 표시
 * 필드가 아니다. 이 파일은 서버가 준 값을 **옮기기만** 하고 새로운 이름이나 사유를
 * 만들지 않는다.
 *
 * 이 파일의 소유는 R4 담당이다. 공통 검사 화면 연결(RunInspector 등)은 통합 담당이
 * 이 모듈을 불러 쓰는 방식으로 붙인다.
 */

/** 화면 라벨. 서버 payload의 `display_labels`가 있으면 그 값을 우선 쓴다. */
export const PLAYERS_DISPLAY_LABELS = {
  selected_player: '선정 선수',
  selection_reason: '선정 이유',
} as const

/** 이 모듈의 출력 계약 버전. 서버 `mp05p-r4-players-output-1`과 같은 값이다. */
export const PLAYERS_OUTPUT_CONTRACT_VERSION = 'mp05p-r4-players-output-1'

export const PLAYERS_MODULE_ID = 'R4'

export type PlayerMappingStatus = 'resolved' | 'unresolved' | 'resolver_not_injected' | string

export type PlayerNameSource = 'db_korean' | 'db_short_korean' | 'original' | string

/** 저장된 주목 선수 한 명. 표시 필드 두 개 + 내부 메타데이터. */
export type SelectedPlayerView = {
  /** 표시 필드 1 — 선정 선수. DB 한국어 이름(확인 실패 시 원래 표기). */
  selected_player: string
  /** 표시 필드 2 — 선정 이유. 이름과 합치지 않는다. */
  selection_reason: string
  /** 표시용 팀 이름(있으면 DB 한국어). */
  team?: string | null

  // --- 내부 메타데이터(표시 필드 아님) ---
  model_selected_player?: string | null
  model_team?: string | null
  player_id?: number | null
  external_id?: number | null
  id_space?: 'internal' | 'external' | string
  name_source?: PlayerNameSource
  mapping_status?: PlayerMappingStatus
  mapping_reason?: string | null
  mapping_detail?: string | null
  team_display_name?: string | null
  team_mapping?: string | null
  evidence?: string[]
  source_url?: string | null
  claim_id?: string | null
}

export type PlayersUnmappedView = {
  kind: string
  original: string
  display_name?: string | null
  reason: string
  detail?: string | null
}

export type PlayersR4ResultView = {
  module_id?: string
  output_contract_version?: string
  implementation_version?: string
  prompt_version?: string
  mode?: string
  /** 이 결과가 만들어진 경로. `live`가 아니면 실제 생성이 아니다. */
  origin?: string
  display_labels?: Record<string, string>
  players?: SelectedPlayerView[]
  unmapped?: PlayersUnmappedView[]
  mapping?: {
    resolved?: number
    unresolved?: number
    resolver_injected?: boolean | null
  }
  coverage?: { topic: string; state: string; detail: string | null }[]
  diagnostics?: string[]
  uncertainties?: string[]
  dropped_facts?: string[]
  unasserted_premises?: string[]
  search_note?: string | null
  raw_model_text?: string | null
  reader_sources?: { label?: string | null; url?: string | null; kind?: string; note?: string | null }[]
  selection_rule_note?: string
  attempt_count?: number
  external_calls?: number
}

/** 두 표시 필드를 안전하게 꺼낸다. 값이 없으면 빈 문자열이며 새 값을 만들지 않는다. */
export function splitDisplayFields(row: SelectedPlayerView): {
  selectedPlayer: string
  selectionReason: string
} {
  const name = typeof row.selected_player === 'string' ? row.selected_player.trim() : ''
  const reason = typeof row.selection_reason === 'string' ? row.selection_reason.trim() : ''
  return { selectedPlayer: name, selectionReason: reason }
}

/** 두 필드가 모두 채워진 항목만 화면에 낸다. 빈 항목을 문장으로 꾸미지 않는다. */
export function displayablePlayers(rows: SelectedPlayerView[] | undefined): SelectedPlayerView[] {
  return (rows ?? []).filter((row) => {
    const { selectedPlayer, selectionReason } = splitDisplayFields(row)
    return Boolean(selectedPlayer && selectionReason)
  })
}

export function mappingStatusLabel(status: PlayerMappingStatus | undefined): string {
  if (status === 'resolved') return 'DB 한국어 확인'
  if (status === 'unresolved') return '미해결 · 원래 표기 유지'
  if (status === 'resolver_not_injected') return '이름 해석기 미주입'
  return status ?? '상태 없음'
}

export function mappingReasonLabel(reason: string | null | undefined): string {
  if (!reason) return '—'
  if (reason === 'ambiguous') return '같은 표기의 후보가 둘 이상이라 고르지 않음'
  if (reason === 'db_korean_missing') return 'DB에 한국어 이름이 없음'
  if (reason === 'not_found') return 'DB에서 일치하는 선수를 찾지 못함'
  if (reason === 'empty') return '이름이 비어 있음'
  if (reason === 'resolver_not_injected') return '이름 해석기가 주입되지 않음'
  return reason
}

/** 실행 방식 표기. mock·replay를 실제 생성으로 읽지 않게 문장으로 구분한다. */
export function originLabel(mode: string | undefined, origin: string | undefined): string {
  if (origin === 'reused_r1_selection') return '이전 R1 선정 재사용(새 R4 생성 아님)'
  if (origin && origin !== mode) return origin
  if (mode === 'live') return '실호출'
  if (mode === 'replay') return '저장 응답 재생(새 모델 호출 없음)'
  if (mode === 'mock') return '모의 실행(외부 호출 없음)'
  return mode ?? '실행 방식 미상'
}

/**
 * 저장된 artifact 본문을 **읽기 좋은 텍스트**로 만든다.
 *
 * `artifact.body`는 이미 직렬화된 JSON **문자열**이다. 그대로 `<pre>`에 넣으면
 * 한 줄로 뭉친 압축 JSON이 나온다(사용자가 "정리해서 보여달라"고 한 지점). 여기서
 * 파싱해 2칸 들여쓰기로 다시 쓴다.
 *
 * 규칙:
 * - JSON이 아니면(평문·비JSON) **원문 그대로** 돌려준다. 지어내지 않는다.
 * - 파싱에 실패해도 원문을 그대로 돌려준다(빈 문자열로 만들지 않는다).
 * - 필드를 빼거나 요약하지 않는다. 실제 구조와 값 타입을 그대로 보존한다.
 * - `content.parts[].text` 같은 **문자열 필드는 문자열 그대로** 둔다(객체로 바꾸지 않음).
 */
export function prettyJsonText(value: string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const text = value.trim()
  if (!text) return value
  // JSON처럼 보이지 않으면 파싱을 시도하지 않고 원문을 유지한다.
  const looksJson = text.startsWith('{') || text.startsWith('[')
  if (!looksJson) return value
  try {
    const parsed: unknown = JSON.parse(text)
    return JSON.stringify(parsed, null, 2)
  } catch {
    return value
  }
}

/**
 * 모델이 생성한 중첩 JSON 텍스트를 읽기 좋게 만든다(표시 전용).
 *
 * `candidates[].content.parts[].text`는 **문자열**이며, 그 안에 모델의 JSON이 들어
 * 있는 경우가 많다. 전체 원문 보기에서는 이 값을 문자열 그대로 두고, 사용자가 따로
 * 펼쳐 볼 때만 여기서 파싱한다.
 *
 * JSON이 아니면 `null`을 돌려준다(호출자는 이 뷰를 숨긴다). 원문을 변조하지 않는다.
 */
export function parseNestedModelJson(value: string | null | undefined): string | null {
  if (typeof value !== 'string') return null
  const text = value.trim()
  if (!text.startsWith('{') && !text.startsWith('[')) return null
  try {
    const parsed: unknown = JSON.parse(text)
    return JSON.stringify(parsed, null, 2)
  } catch {
    return null
  }
}
