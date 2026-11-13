/**
 * 섹션 결과의 **구조화 표시** — 화면용 타입과 방어적 파서 (PS-04).
 *
 * 관리자 화면은 저장된 섹션 결과를 `body`(본문)와 `sources`(근거)로 먼저 보여준다.
 * 이 파일은 그 위에 **표·목록으로 읽기 좋은 구조**를 더할 때 쓰는 값만 다룬다.
 *
 * 원칙:
 *
 * - 서버가 구조화 값을 주면 그 값을 그대로 옮긴다. 화면에서 선수·점수·배당을
 *   만들어 채우지 않는다.
 * - 구조화 값이 없으면 `body`에서 **기록된 라벨**(`선정 선수:` / `선정 이유:`)만
 *   읽는다. 라벨이 없는 본문은 해석하지 않고 본문 그대로 둔다.
 * - 팀별 상한(선수 2명·부상 2명), 매체 3곳은 **표시 상한**이지 자료를 지우는 규칙이
 *   아니다. 넘는 값이 오면 자르지 않고 그대로 보여준다(서버 계약 위반을 숨기지 않음).
 * - 불확실 상태(`unknown`)를 확정 부상으로 바꾸지 않는다. 상태 문자열을 그대로 쓴다.
 * - 배당은 **정규시간 1X2 소수점**만 표로 만든다. 값이 없으면 빈 칸으로 두고 추정하지
 *   않는다.
 *
 * 잠정 필드 지도(A manifest 확정 전): 서버가 `structured`(또는 `sections`) 객체를
 * 주면 종류별로 읽는다. 이름이 확정되면 이 파일의 `readStructured`만 고친다.
 */

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

/** 정수 ID만 인정한다. 문자열 숫자는 받되, 그 밖의 값은 `null`(추정 금지). */
function intId(value: unknown): number | null {
  if (typeof value === 'number' && Number.isSafeInteger(value) && value > 0) return value
  if (typeof value === 'string' && /^\d+$/.test(value.trim())) {
    const parsed = Number(value.trim())
    return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null
  }
  return null
}

/**
 * 사진 주소. **서버가 준 값만** 쓴다.
 *
 * 내부 ID로 API-Football 주소를 조립하지 않는다. 저장된 `player_id`(533)를 사진 ID로
 * 착각하면 다른 선수 사진이 나온다. 허용한 스킴(http/https)의 문자열만 통과시킨다.
 */
function photoHref(value: unknown): string | null {
  const found = text(value)
  if (found === null) return null
  if (!/^https?:\/\//i.test(found)) return null
  return found
}

/**
 * 서버가 준 추가 필드만 골라 덧붙인다.
 *
 * 값이 없으면 키 자체를 만들지 않는다. 그래야 예전 저장본에서 파서 결과 모양이 바뀌지 않고,
 * 화면은 "사진 정보 없음"을 `undefined`로 읽어 사진만 생략한다.
 */
function withPhotoFields(row: Record<string, unknown>): {
  playerId?: number
  externalPlayerId?: number
  teamExternalId?: number
  photoUrl?: string
} {
  const extra: {
    playerId?: number
    externalPlayerId?: number
    teamExternalId?: number
    photoUrl?: string
  } = {}
  const playerId = intId(row.player_id ?? row.playerId)
  if (playerId !== null) extra.playerId = playerId
  const externalPlayerId = intId(row.external_player_id ?? row.externalPlayerId)
  if (externalPlayerId !== null) extra.externalPlayerId = externalPlayerId
  const teamExternalId = intId(row.team_external_id ?? row.teamExternalId)
  if (teamExternalId !== null) extra.teamExternalId = teamExternalId
  const photoUrl = photoHref(row.photo_url ?? row.photoUrl)
  if (photoUrl !== null) extra.photoUrl = photoUrl
  return extra
}

function firstText(source: Record<string, unknown>, keys: readonly string[]): string | null {
  for (const key of keys) {
    const value = text(source[key])
    if (value !== null) return value
  }
  return null
}

/**
 * 선수 한 명. 선정 선수와 선정 이유는 **합치지 않는다**.
 *
 * `playerId`는 **내부 ID**다(예: 533 = 홀란드). API-Football 사진 ID(1100)와 다른 값이며
 * 서로 바꿔 쓸 수 없다. 사진 주소는 서버가 `photo_url`로 줄 때만 존재하고, 이 파일은
 * 내부 ID로 URL을 만들지 않는다.
 */
export type StructuredPlayer = {
  player: string
  reason: string
  team: string | null
  /**
   * 아래 세 값은 **서버가 실제로 준 경우에만** 채워진다(선택 필드).
   *
   * 예전 저장본에는 이 키들이 없으므로 객체 모양이 그대로 유지된다. 새 필드가 없을 때
   * `undefined`이고, 화면은 사진 없이 이름만 그린다.
   */
  /** 내부 선수 ID. 표시용 사진 주소를 만드는 데 쓰지 않는다. */
  playerId?: number | null
  /** 외부(API-Football) 선수 ID. */
  externalPlayerId?: number | null
  /** 팀 외부 ID. 팀 좌우 판정에 쓴다. */
  teamExternalId?: number | null
  /** 서버가 준 사진 주소만. 없으면 `null`(추측해 만들지 않는다). */
  photoUrl?: string | null
}

export type StructuredInjury = {
  player: string
  team: string | null
  /** 서버·원문의 상태 표기 그대로. 확정 부상으로 바꾸지 않는다. */
  status: string | null
  summary: string | null
  /** 선수와 같은 규칙: 서버가 준 경우에만 채워지는 선택 필드. */
  playerId?: number | null
  externalPlayerId?: number | null
  teamExternalId?: number | null
  photoUrl?: string | null
}

export type StructuredMedia = {
  publisher: string
  statement: string
  predictedScore: string | null
  publishedAt: string | null
  url: string | null
}

/** 배당 한 행. 홈·무·원정은 소수점 표기 문자열 그대로 둔다. */
export type StructuredOdds = {
  bookmaker: string
  observedAt: string | null
  home: string | null
  draw: string | null
  away: string | null
  market: string | null
}

export type StructuredForecast = {
  /** `home` | `draw` | `away`만 인정한다. 그 밖의 값은 표시하지 않는다. */
  lean: 'home' | 'draw' | 'away' | null
  score: string | null
  reasoning: string[]
  note: string | null
}

export type StructuredSectionView = {
  players: StructuredPlayer[]
  injuries: StructuredInjury[]
  media: StructuredMedia[]
  odds: StructuredOdds[]
  forecast: StructuredForecast | null
}

const EMPTY: StructuredSectionView = {
  players: [],
  injuries: [],
  media: [],
  odds: [],
  forecast: null,
}

/** 화면·검사가 쓰는 빈 구조 값. 없는 값을 만들지 않고 "없음"을 표현한다. */
export const EMPTY_STRUCTURED: StructuredSectionView = EMPTY

/**
 * `선정 선수: X` / `선정 이유: Y` 쌍을 본문에서 읽는다.
 *
 * 기록된 R4 본문 형식만 읽는다(`r4-information-bundle-trial.md`의 생성 본문). 다른
 * 문장을 선수·사유로 해석하지 않는다. 팀은 본문에 없으므로 만들지 않는다.
 */
export function playersFromBody(body: string): StructuredPlayer[] {
  const rows: StructuredPlayer[] = []
  let pendingPlayer: string | null = null
  for (const rawLine of body.split('\n')) {
    const line = rawLine.trim()
    const playerMatch = /^선정 선수\s*[:：]\s*(.+)$/.exec(line)
    if (playerMatch) {
      pendingPlayer = playerMatch[1].trim()
      continue
    }
    const reasonMatch = /^선정 이유\s*[:：]\s*(.+)$/.exec(line)
    if (reasonMatch && pendingPlayer) {
      const reason = reasonMatch[1].trim()
      if (pendingPlayer && reason) {
        // 본문 라벨에는 ID·사진 주소가 없다. 키를 만들지 않는다(추측 금지).
        rows.push({ player: pendingPlayer, reason, team: null })
      }
      pendingPlayer = null
    }
  }
  return rows
}

function parsePlayer(raw: unknown): StructuredPlayer | null {
  const row = record(raw)
  if (row === null) return null
  // 서버가 두 필드를 다른 이름으로 줄 수 있다. 어느 쪽이든 **분리 유지**한다.
  const player = firstText(row, ['player', 'selected_player', 'name', 'player_name'])
  const reason = firstText(row, ['reason', 'selection_reason', 'why'])
  if (player === null || reason === null) return null
  return {
    player,
    reason,
    team: firstText(row, ['team', 'team_name', 'team_label']),
    ...withPhotoFields(row),
  }
}

function parseInjury(raw: unknown): StructuredInjury | null {
  const row = record(raw)
  if (row === null) return null
  const player = firstText(row, ['player', 'player_name', 'selected_player', 'name'])
  if (player === null) return null
  return {
    player,
    team: firstText(row, ['team', 'team_name', 'team_label']),
    status: firstText(row, ['status', 'expected_status', 'state']),
    summary: firstText(row, ['summary', 'reason', 'impact', 'detail', 'note']),
    ...withPhotoFields(row),
  }
}

function parseMedia(raw: unknown): StructuredMedia | null {
  const row = record(raw)
  if (row === null) return null
  const statement = firstText(row, ['statement', 'text', 'forecast', 'summary'])
  const publisher = firstText(row, ['publisher', 'media', 'source', 'outlet'])
  if (statement === null) return null
  return {
    publisher: publisher ?? '매체 미상',
    statement,
    // 점수 미제시 기사는 null로 둔다. 0-0 같은 값을 만들지 않는다.
    predictedScore: firstText(row, ['predicted_score', 'score', 'prediction']),
    publishedAt: firstText(row, ['published_at', 'observed_at', 'date']),
    url: firstText(row, ['url', 'link']),
  }
}

function parseOdds(raw: unknown): StructuredOdds | null {
  const row = record(raw)
  if (row === null) return null
  const bookmaker = firstText(row, ['bookmaker', 'site', 'provider', 'publisher'])
  const home = firstText(row, ['home', 'home_win', 'home_odds'])
  const draw = firstText(row, ['draw', 'draw_odds'])
  const away = firstText(row, ['away', 'away_win', 'away_odds'])
  if (bookmaker === null && home === null && draw === null && away === null) return null
  return {
    bookmaker: bookmaker ?? '사이트 미상',
    // 서버는 이 값을 `observedAt`으로 내고(`section_structured._odds`), 저장 payload는
    // `observed_at`을 쓴다. 둘 다 같은 뜻이므로 서버 정본을 먼저 읽고 예전 표기도 계속 읽는다.
    // 시각이 없으면 `null`이며 화면은 시각을 만들지 않는다.
    observedAt: firstText(row, [
      'observedAt',
      'observed_at',
      'collected_at',
      'capture_time',
      'time',
    ]),
    home,
    draw,
    away,
    market: firstText(row, ['market']),
  }
}

function parseForecast(raw: unknown): StructuredForecast | null {
  const row = record(raw)
  if (row === null) return null
  const leanRaw = firstText(row, ['lean', 'outcome', 'prediction'])
  const lean = leanRaw === 'home' || leanRaw === 'draw' || leanRaw === 'away' ? leanRaw : null
  const reasoning = list(row.reasoning ?? row.reasons)
    .map((item) => text(item))
    .filter((item): item is string => item !== null)
  const score = firstText(row, ['score', 'predicted_score', 'score_line'])
  const note = firstText(row, ['note'])
  if (lean === null && score === null && reasoning.length === 0 && note === null) return null
  return { lean, score, reasoning, note }
}

/**
 * 저장된 섹션 결과 payload에서 구조화 값을 읽는다.
 *
 * `payload`는 저장된 섹션 결과의 원본 payload다(없으면 `null`). 여러 겹으로 감싼
 * 응답을 만나도 **읽기만** 하며, 어떤 값도 새로 만들지 않는다.
 */
export function readStructured(payload: unknown): StructuredSectionView {
  const root = record(payload)
  if (root === null) return EMPTY
  // `payload.payload`처럼 한 겹 더 들어간 저장 모양을 허용한다(store의 저장 형태).
  const inner = record(root.payload)
  const scopes = [root, inner].filter((item): item is Record<string, unknown> => item !== null)
  for (const scope of scopes) {
    const structured = record(scope.structured ?? scope.sections ?? scope.display)
    if (structured !== null) {
      const players = list(structured.players ?? structured.players_to_watch)
        .map(parsePlayer)
        .filter((item): item is StructuredPlayer => item !== null)
      const injuries = list(structured.injuries ?? structured.availability ?? structured.absences)
        .map(parseInjury)
        .filter((item): item is StructuredInjury => item !== null)
      const media = list(structured.media ?? structured.external_outlook)
        .map(parseMedia)
        .filter((item): item is StructuredMedia => item !== null)
      const odds = list(structured.odds)
        .map(parseOdds)
        .filter((item): item is StructuredOdds => item !== null)
      const forecast = parseForecast(structured.forecast ?? structured.ai_prediction)
      return { players, injuries, media, odds, forecast }
    }
  }
  return EMPTY
}

/** 구조화 값이 하나도 없는지. 없으면 화면은 구조 블록을 만들지 않는다. */
export function isStructuredEmpty(view: StructuredSectionView): boolean {
  return (
    view.players.length === 0 &&
    view.injuries.length === 0 &&
    view.media.length === 0 &&
    view.odds.length === 0 &&
    view.forecast === null
  )
}

/**
 * 저장된 **섹션 결과**에서 구조화 값을 읽는다.
 *
 * 섹션 결과의 공개 필드는 `body`·`sources`뿐이다. 구조화 값은 서버가 섹션 결과에
 * `structured`(또는 `payload.structured`)를 더해 줄 때만 존재한다. 그 값이 없으면
 * 본문의 기록된 라벨(`선정 선수:` / `선정 이유:`)만 읽는다 — 즉 선수만 구조화되고,
 * 부상·매체·배당·예측은 본문 그대로 둔다(본문을 해석해 표를 만들지 않는다).
 */
export function structuredFromSectionResult(result: unknown): StructuredSectionView {
  const row = record(result)
  if (row === null) return EMPTY
  const structured = readStructured(row)
  if (!isStructuredEmpty(structured)) return structured
  const body = text(row.body)
  if (body === null) return EMPTY
  return { ...EMPTY, players: playersFromBody(body) }
}

/**
 * 팀 이름을 키로 묶는다. 팀 이름이 없는 항목은 `null` 그룹에 모은다(팀을 만들지 않음).
 * 그룹 순서는 처음 나온 순서를 지켜 서버 순서를 뒤집지 않는다.
 */
export function groupByTeam<T extends { team: string | null }>(
  rows: readonly T[],
): { team: string | null; rows: T[] }[] {
  const groups: { team: string | null; rows: T[] }[] = []
  for (const row of rows) {
    const existing = groups.find((group) => group.team === row.team)
    if (existing) {
      existing.rows.push(row)
    } else {
      groups.push({ team: row.team, rows: [row] })
    }
  }
  return groups
}

/** 상태 표기의 화면 라벨. 모르는 표기는 원문 그대로 보여준다. */
export function injuryStatusLabel(status: string | null): string {
  if (status === null) return '상태 미확인'
  const normalized = status.toLowerCase()
  if (normalized === 'out' || normalized === 'confirmed_absence') return '결장'
  if (normalized === 'doubtful' || normalized === 'questionable') return '출전 불투명'
  if (normalized === 'available' || normalized === 'fit') return '출전 가능'
  if (normalized === 'unknown') return '상태 미확인'
  return status
}

/** 예상 스코어 표기 검사. `2-1` 같은 실제 점수만 통과시킨다(빈 값·문장은 null). */
export function scoreText(value: string | null): string | null {
  if (value === null) return null
  const match = /^(\d{1,2})\s*[-–:]\s*(\d{1,2})$/.exec(value.trim())
  if (match === null) return value
  return `${match[1]}-${match[2]}`
}
