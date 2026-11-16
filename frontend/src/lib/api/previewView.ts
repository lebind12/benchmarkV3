/**
 * 저장된 프리뷰 결과 → 확정 목업(MatchPreviewBody)이 읽는 표시 모델.
 *
 * 이 파일이 하는 일은 **옮기기**뿐이다. 저장된 reader 결과·섹션 결과·구조화 값에서
 * 표시에 필요한 값만 꺼내고, 없는 값은 `null`/빈 배열로 둔다. 문장을 새로 만들지 않는다.
 *
 * 지키는 것:
 *
 * - 보여줄 섹션 버전은 **reader가 고른 버전**이다. 서버가 구성본을 반영해 고른
 *   `preview.sections[].version`과 같은 버전의 섹션 결과 행만 쓴다. reader가 없을 때만
 *   섹션별 최신 1건을 쓴다(그 경우에도 섞지 않고 하나만 쓴다).
 * - 구조화 값이 없으면 저장된 섹션 `body`를 그대로 넘긴다. 본문이 있으면 숨기지 않는다.
 * - 선수·팀 사진 URL을 **추측하지 않는다.** 저장 값의 `player_id`(533 같은 값)는 내부 ID이고
 *   API-Football 사진 ID와 다르다. 외부 ID가 payload에 드러나지 않으므로 사진은 `null`이며
 *   화면은 사진 없이 이름을 그린다. 하드코딩 매핑을 만들지 않는다.
 * - 배당은 저장된 소스·1X2 값만 쓴다. 없는 칸은 비워 두고 합성값을 채우지 않는다.
 * - 본문에 내부 진단·면책 문구를 섞지 않는다. 진단은 화면의 접힌 영역이 맡는다.
 */
import {
  injuryStatusLabel,
  scoreText,
  structuredFromSectionResult,
  type StructuredSectionView,
} from '@/features/match-preview/sectionStructured'
import type {
  ReaderPreview,
  ReaderPreviewSection,
  SectionResultView,
  SectionResultsResponse,
} from '@/features/match-preview/types'
import type { FixtureCandidate } from '@/features/match-preview/fixtures'
import type { PreviewRunData } from '@/lib/api/preview'

export type MatchPreviewTeam = {
  name: string
  /**
   * 팀 로고 주소. **서버가 준 값만** 쓴다(`reader.fixture.*_team_logo_url`).
   * 예전 저장본에는 이 값이 없으므로 `null`이며, 화면은 로고 자리 없이 팀명만 그린다.
   * 내부 팀 ID로 API-Football 주소를 조립하지 않는다.
   */
  badge_url: string | null
  /** 외부(API-Football) 팀 ID. 서버가 줄 때만 있고, 없으면 `null`. */
  external_id: number | null
}

export type MatchPreviewFixture = {
  external_id: number | null
  home: MatchPreviewTeam
  away: MatchPreviewTeam
  league: string | null
  kickoff_at: string | null
  label: string
}

export type MatchPreviewForecast = {
  /** 전망 본문 문단. 저장 본문에서 카드가 이미 보여주는 줄만 뺀 나머지다. */
  forecastLines: string[]
  reasoning: string[]
  lean: 'home' | 'draw' | 'away' | null
  lean_label: string | null
  /** 구조화 값의 점수만. `2-0` 같은 형태가 아니면 `null`(0-0을 만들지 않는다). */
  score: { home: number; away: number } | null
}

export type MatchPreviewPlayer = {
  team: string | null
  player: string
  reason: string
  /** 서버가 준 사진 주소만. 없으면 `null`이고 화면은 이름을 그대로 보여준다. */
  photo_url: string | null
  /** 팀 외부 ID. 좌우(홈/원정) 판정에 쓴다. */
  team_external_id: number | null
  team_side?: 'home' | 'away' | null
}

export type MatchPreviewInjury = {
  team: string | null
  player: string
  status: 'out' | 'doubt'
  status_label: string
  detail: string | null
  /** 서버가 준 사진 주소만. 없으면 `null`. */
  photo_url: string | null
  team_external_id: number | null
  team_side?: 'home' | 'away' | null
}

export type MatchPreviewMedia = {
  publisher: string
  statement: string
  url: string | null
}

export type MatchPreviewOddsCell = { label: string; value: string | null }

export type MatchPreviewOddsRow = {
  source: string
  observed_at: string | null
  cells: MatchPreviewOddsCell[]
}

export type MatchPreviewSection = {
  section_id: string
  title: string
  /** 저장된 본문 그대로. 구조화 값이 없으면 이 본문을 표시한다. */
  body: string
  partial: boolean
  quality: string | null
  version: number | null
  sources: { label?: string; url?: string | null; kind?: string; note?: string | null }[]
  /**
   * 이 실행의 `/section-results` 행이 아니라 **reader 응답에만 있는** 섹션에서 온 본문인지.
   *
   * 두 경우가 있다. 구성본이 다른 실행의 결과를 골랐거나(이 실행의 행 목록에 없다),
   * 섹션 결과 조회가 실패해 행 목록을 확인하지 못했다. 어느 쪽이든 reader가 준 본문·근거를
   * 그대로 쓰며, 같은 섹션의 다른 버전으로 바꿔 넣지 않는다.
   */
  from_reader_selection?: boolean
}

export type MatchPreviewView = {
  fixture: MatchPreviewFixture
  generated_at: string | null
  forecast: MatchPreviewForecast
  /** 선수 카드가 그리지 않는 나머지 저장 문장(도입 문장 등). */
  playerIntro: string[]
  players: MatchPreviewPlayer[]
  injuries: MatchPreviewInjury[]
  media: MatchPreviewMedia[]
  odds: MatchPreviewOddsRow[]
  /** reader가 고른 섹션만. 없는 섹션 키는 없다(빈 카드를 만들지 않는다). */
  sections: Record<string, MatchPreviewSection>
  /** 필수 섹션 본문이 모두 있는지. `false`여도 본문 표시를 막지 않는다. */
  complete: boolean | null
  /** 표시 모델에서 비어 있는 이유(사진 등 API 값 부족). 본문에는 넣지 않는다. */
  missing: string[]
  /**
   * 저장된 `korean_labels`에서 만든 팀 이름 별칭표. 같은 팀의 다른 언어 표기를 한 묶음으로
   * 묶는 데만 쓴다. 화면은 이 값으로 좌(홈)/우(원정)를 판정하고, 이름을 새로 만들지 않는다.
   */
  team_aliases: TeamAliases
}

/**
 * 서버가 사진 주소를 주지 않았을 때의 진단 문장. **실제로 사진이 빠진 항목이 있을 때만**
 * 이 값을 채운다. 예전 저장본(사진 필드 없음)과 일부만 온 경우를 같은 문장으로 알린다.
 */
export const MISSING_PLAYER_PHOTOS =
  '일부 선수 사진이 저장 결과에 없습니다. 사진 주소가 없으면 이름만 표시하며, 내부 선수 ID로 주소를 만들지 않습니다.'

/**
 * 배당 표를 그리지 못한 이유 접두사. **관리자 진단 영역**에서만 쓰며 본문에는 넣지 않는다.
 *
 * 배당은 저장된 정규시간 1X2 값이 있을 때만 표시한다. 값이 없는데 표를 만들거나
 * "연결됨"처럼 보이게 하지 않고, 저장된 사유(섹션 결과의 `unavailable_reason`)를 그대로
 * 붙여 자료 미제공과 표시 오류를 구분할 수 있게 한다.
 */
export const MISSING_ODDS_PREFIX = '배당 표를 표시하지 않았습니다.'

/**
 * 구성본이 고른 다른 실행의 섹션 결과를 읽지 못했을 때의 진단 문장 접두사.
 *
 * 이 실행의 `/section-results`에 행이 없는 섹션은 구성본이 원 실행 결과를 가리킨다.
 * 그 행을 읽지 못하면 카드(사진·구조 값) 대신 reader 본문만 남으므로, **본문은 그대로
 * 두고** 이 사실을 진단 목록(`missing`)에 남긴다. 본문에 진단 문구를 섞지 않는다.
 */
export const MISSING_COMPOSED_PREFIX =
  '구성본이 고른 다른 실행의 섹션 결과를 읽지 못해 카드 대신 저장 본문으로 표시합니다.'

/** 섹션 결과 응답의 행. 서버가 구조화 값을 덧붙이면 `structured`가 있다. */
type DecoratedSectionResult = SectionResultView & { structured?: unknown }

/**
 * 팀별 묶음. `side`는 **확인된 값으로만** 채운다.
 *
 * `null`은 "홈/원정을 확인하지 못했다"는 뜻이며, 배열 순서로 추측해 채우지 않는다.
 * 화면은 `resolveSides`로 좌우를 확정한다.
 */
export type TeamGroup<T> = { team: string | null; side: 0 | 1 | null; rows: T[] }

function text(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : null
}

function splitMatchup(label: string | null): { home: string | null; away: string | null } {
  if (!label) return { home: null, away: null }
  const match = /^(.*?)\s+vs\.?\s+(.+)$/i.exec(label.trim())
  if (!match) return { home: null, away: null }
  return { home: text(match[1]), away: text(match[2]) }
}

function normalizeTeam(name: string): string {
  return name.toLowerCase().replace(/[\s.,'’()-]/g, '')
}

/**
 * 저장된 payload의 `korean_labels`에서 만든 **팀 이름 별칭표**.
 *
 * 저장 결과는 섹션마다 같은 팀을 다른 언어로 적는다. 실제 저장본에서는 부상 섹션이
 * `Manchester City`/`Fulham`, 선수 섹션이 `맨체스터 시티`/`풀럼`을 쓴다. 경기 라벨은
 * 한국어라서, 별칭이 없으면 어느 팀이 홈인지 판정하지 못한다. 저장된 번역 쌍만 읽어
 * 같은 팀을 하나로 묶는다(새 번역·새 이름을 만들지 않는다).
 */
type TeamAliases = Map<string, string>

function teamAliasesFrom(payloads: readonly unknown[]): TeamAliases {
  const canonical = new Map<string, string>()
  const addLabels = (labels: unknown[]) => {
    for (const raw of labels) {
      const row = record(raw)
      if (!row || row.kind !== 'team') continue
      const original = text(row.original)
      const korean = text(row.korean)
      if (!original || !korean) continue
      // 같은 팀의 표기들을 한 키로 모은다. 이미 묶인 표기가 있으면 그것을 따른다.
      const key = canonical.get(normalizeTeam(original)) ?? normalizeTeam(korean)
      canonical.set(normalizeTeam(original), key)
      canonical.set(normalizeTeam(korean), key)
    }
  }
  for (const payload of payloads) {
    // 섹션 결과 payload는 `korean_labels`를 한 겹 안(`payload`)에 두기도 한다.
    for (const scope of [record(payload), record(record(payload)?.payload)]) {
      if (scope) addLabels(list(scope.korean_labels))
    }
  }
  return canonical
}

/** 정수 ID만 인정한다(문자열 숫자 허용). 그 밖의 값은 `null`이며 추정하지 않는다. */
function intId(value: unknown): number | null {
  if (typeof value === 'number' && Number.isSafeInteger(value) && value > 0) return value
  if (typeof value === 'string' && /^\d+$/.test(value.trim())) {
    const parsed = Number(value.trim())
    return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null
  }
  return null
}

/** 서버가 준 http(s) 주소만 통과시킨다. 내부 ID로 주소를 조립하지 않는다. */
function logoHref(value: unknown): string | null {
  const found = text(value)
  if (found === null) return null
  return /^https?:\/\//i.test(found) ? found : null
}

function record(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

/**
 * 팀 → 좌(홈)/우(원정) 판정에 쓰는 확인된 식별자.
 *
 * 우선순위는 **확정된 값**부터다.
 *
 * 1. 외부(API-Football) 팀 ID — 서버가 `team_external_id`와 `home/away_team_external_id`를
 *    함께 줬을 때. 숫자 비교이므로 언어·표기와 무관하다.
 * 2. 저장된 한국어 라벨로 접은 팀 이름.
 *
 * 둘 다 맞지 않으면 `null`이다. 그러면 묶음은 **나온 순서**를 유지하고, 화면은 배열 순서를
 * 홈/원정으로 단정하지 않는다(`resolveSides`가 판단한다).
 */
export type TeamIdentity = {
  homeExternalId: number | null
  awayExternalId: number | null
  homeName: string | null
  awayName: string | null
  aliases: TeamAliases
}

function sideOfTeam(
  team: string | null,
  externalId: number | null,
  identity: TeamIdentity,
  teamSide?: 'home' | 'away' | null,
): 0 | 1 | null {
  // 1) 확정된 외부 팀 ID가 양쪽에 있으면 ID로만 판정한다(이름 표기와 무관).
  if (externalId !== null) {
    if (identity.homeExternalId !== null && externalId === identity.homeExternalId) return 0
    if (identity.awayExternalId !== null && externalId === identity.awayExternalId) return 1
    // 외부 ID가 있는데 어느 쪽도 아니면 이름으로 넘어가지 않는다(다른 팀일 수 있다).
    if (identity.homeExternalId !== null || identity.awayExternalId !== null) return null
  }
  // 2) 이름 비교(저장된 한국어 라벨 별칭 적용).
  if (team !== null) {
    const resolve = (name: string) =>
      identity.aliases.get(normalizeTeam(name)) ?? normalizeTeam(name)
    const key = resolve(team)
    if (identity.homeName && resolve(identity.homeName) === key) return 0
    if (identity.awayName && resolve(identity.awayName) === key) return 1
  }
  if (teamSide === 'home') return 0
  if (teamSide === 'away') return 1
  return null
}

/**
 * 팀별 묶음. 같은 팀(이름 또는 확인된 ID)은 한 묶음으로 합치고 나온 순서를 지킨다.
 *
 * `side`는 **확인된 값으로만** 정한다. 확인할 수 없으면 `null`이며, 배열 순서로 홈/원정을
 * 만들어 넣지 않는다. 화면은 `resolveSides`로 좌우를 정한다.
 */
export function groupByTeam<T extends { team: string | null; team_side?: 'home' | 'away' | null }>(
  rows: readonly T[],
  identity: TeamIdentity,
  externalIdOf?: (row: T) => number | null,
): TeamGroup<T>[] {
  const groups: TeamGroup<T>[] = []
  for (const row of rows) {
    const externalId = externalIdOf ? externalIdOf(row) : null
    const side = sideOfTeam(row.team, externalId, identity, row.team_side ?? null)
    // 같은 묶음 = 같은 팀 이름, 또는 같은 확인된 좌/우.
    const existing = groups.find(
      (group) =>
        group.team === row.team ||
        (side !== null && group.side !== null && group.side === side),
    )
    if (existing) {
      existing.rows.push(row)
      if (existing.side === null && side !== null) existing.side = side
      continue
    }
    groups.push({ team: row.team, side, rows: [row] })
  }
  return groups
}

/**
 * 한 묶음의 화면 배치.
 *
 * `column`은 **어느 열에 그릴지**(0=왼쪽, 1=오른쪽)이고, `side`는 **홈/원정을 확인했는지**다.
 * 둘을 나눈 이유:
 *
 * - 열 위치는 확정된 팀 ID/이름으로만 정한다. 배열 순서로 팀의 자리를 **바꾸지 않는다**.
 * - 확인하지 못한 묶음은 `side`가 `null`이며, 화면은 "홈"/"원정" 글자를 쓰지 않는다.
 *   근거가 없는데 홈이라고 적으면 저장 결과에 없는 사실을 만드는 것이기 때문이다.
 */
export type PlacedGroup<T> = { group: TeamGroup<T>; column: 0 | 1; side: 0 | 1 | null }

/**
 * 묶음 배치를 확정한다.
 *
 * - 확인된 묶음은 자기 열(홈=왼쪽, 원정=오른쪽)에 둔다.
 * - 확인되지 않은 묶음은 **남은 열**에, 저장된 순서를 유지해 들어간다.
 *   확인된 묶음이 있으면 그 자리를 빼앗지 않는다.
 */
export function resolveSides<T>(groups: readonly TeamGroup<T>[]): PlacedGroup<T>[] {
  const confirmed = groups.filter((group) => group.side !== null)
  const unknown = groups.filter((group) => group.side === null)
  const taken = new Set(confirmed.map((group) => group.side as 0 | 1))
  const free: (0 | 1)[] = ([0, 1] as const).filter((column) => !taken.has(column))
  const placed: PlacedGroup<T>[] = confirmed.map((group) => ({
    group,
    column: group.side as 0 | 1,
    side: group.side as 0 | 1,
  }))
  for (const group of unknown) {
    // 확인된 자리를 피해 남은 열로. 열이 없으면(이미 둘 다 참) 첫 열을 쓴다.
    const column = free.shift() ?? 0
    // 확인된 묶음이 하나라도 있으면 남은 열은 반대편이므로 side 를 알 수 있다.
    const side: 0 | 1 | null =
      confirmed.length === 1 ? (column as 0 | 1) : null
    placed.push({ group, column, side })
  }
  return placed.sort((left, right) => left.column - right.column)
}

/**
 * 표시 모델 기준 팀 묶음. 본문 컴포넌트가 같은 규칙을 쓰도록 여기서만 계산한다.
 *
 * 좌우는 **확정된 팀 ID → 저장된 이름** 순서로 판정하고, 확인되지 않으면 배열 순서를
 * 홈/원정으로 만들지 않는다(`resolveSides` 참고).
 */
export function teamGroups<T extends { team: string | null; team_external_id?: number | null }>(
  rows: readonly T[],
  view: MatchPreviewView,
): TeamGroup<T>[] {
  return groupByTeam(
    rows,
    {
      homeExternalId: view.fixture.home.external_id,
      awayExternalId: view.fixture.away.external_id,
      homeName: view.fixture.home.name,
      awayName: view.fixture.away.name,
      aliases: view.team_aliases,
    },
    (row) => row.team_external_id ?? null,
  )
}

/**
 * 저장된 행이 **확인해 둔** 팀 외부 ID → 표시 이름.
 *
 * 우세 문구에 실제 팀명을 쓰려면 이름이 필요하다. 경기 라벨에 팀명이 없거나(`fixture
 * 1557474`) fixture 이름이 홈팀/원정팀 fallback 인 경우가 있어, 구조화 행이 함께 저장한
 * `team` + `team_external_id` 쌍에서 **ID로만** 이름을 찾는다.
 *
 * 지키는 것: ID를 추측하거나 ID→이름을 새로 만들지 않는다. 이름도 저장된 표기 그대로 쓰며,
 * 같은 ID에 서로 다른 이름이 오면 확정하지 않는다. 확인되지 않으면 이름을 지어내지 않고
 * 호출자가 기존 문구를 유지한다.
 */
function teamNamesByExternalId(
  rows: readonly { team: string | null; team_external_id: number | null }[],
): Map<number, string> {
  const seen = new Map<number, string | null>()
  for (const row of rows) {
    const external = intId(row.team_external_id)
    const name = text(row.team)
    if (external === null || name === null) continue
    const current = seen.get(external)
    if (current === undefined) {
      seen.set(external, name)
      continue
    }
    // 같은 ID에 다른 이름이 오면 그 ID는 확정하지 않는다.
    if (current !== null && current !== name) seen.set(external, null)
  }
  const out = new Map<number, string>()
  for (const [external, name] of seen) {
    if (name !== null) out.set(external, name)
  }
  return out
}

/**
 * 우세 표시 문구. **무승부는 그대로** 두고, 홈/원정 우세는 확인된 **실제 팀명**으로 쓴다.
 *
 * 우선순위: ① fixture/candidate 이름(단, 홈팀/원정팀 같은 fallback 은 이름으로 쓰지 않음)
 * ② 저장된 구조화 행이 확인해 둔 외부 ID → 팀명. 어느 쪽도 확인되지 않으면 팀명을 지어내지
 * 않고 중립 문구(`홈팀 우세`/`원정팀 우세`)를 유지한다.
 */
function leanLabel(
  lean: 'home' | 'draw' | 'away' | null,
  options: { homeName: string; awayName: string; fallbackNames: Set<string> },
): string | null {
  if (lean === 'draw') return '무승부'
  if (lean !== 'home' && lean !== 'away') return null
  const name = lean === 'home' ? options.homeName : options.awayName
  const usable = text(name) !== null && !options.fallbackNames.has(name.trim())
  if (!usable) return lean === 'home' ? '홈팀 우세' : '원정팀 우세'
  return `${name.trim()} 우세`
}

/**
 * 저장 본문에서 **이미 카드가 그리는 줄**만 빼고 남은 문단을 돌려준다.
 *
 * 빼는 것은 카드가 같은 내용을 그대로 보여주는 줄뿐이다.
 *
 * - `#` 제목: 카드의 제목이 이미 그 자리에 있다.
 * - 기록된 라벨 줄(`선정 선수:` / `선정 이유:`): 선수 카드가 이름과 이유를 따로 그린다
 *   (`sectionStructured.ts`가 읽는 것과 같은 라벨 규칙만 쓴다).
 * - 구조화 예상 스코어와 같은 줄, 근거 목록과 **완전히 같은** 목록 항목.
 *
 * 그 밖의 줄은 문장을 만들지 않고 그대로 남긴다. 즉 구조화 값이 일부만 있어도 본문의
 * 나머지 문장(도입 문장·설명)은 사라지지 않는다.
 */
function introLines(
  body: string,
  options: {
    reasoning?: readonly string[]
    score?: { home: number; away: number } | null
    dropLabels?: readonly RegExp[]
  } = {},
): string[] {
  const reasoning = options.reasoning ?? []
  const scoreLine = options.score ? `${options.score.home}-${options.score.away}` : null
  const labels = options.dropLabels ?? []
  const kept: string[] = []
  for (const raw of body.split('\n')) {
    const line = raw.trim()
    if (!line) continue
    if (line.startsWith('#')) continue
    if (labels.some((label) => label.test(line))) continue
    if (scoreLine !== null && line === scoreLine) continue
    const bullet = /^[-*]\s+(.*)$/.exec(line)
    const content = bullet ? bullet[1].trim() : line
    if (reasoning.some((reason) => reason === content)) continue
    kept.push(content)
  }
  return kept
}

/** 선수 카드가 그리는 라벨 줄. 이 두 접두사만 본문에서 제거한다. */
const PLAYER_LABELS = [/^선정\s*선수\s*[:：]/, /^선정\s*이유\s*[:：]/]

/** reader가 고른 버전의 섹션 결과 행. reader가 없을 때만 섹션별 최신 1건을 쓴다. */
function pickSections(
  response: SectionResultsResponse,
  preview: ReaderPreview | null,
): Record<string, DecoratedSectionResult> {
  const rows = (response.section_results ?? []) as DecoratedSectionResult[]
  const picked: Record<string, DecoratedSectionResult> = {}
  const chosen = preview?.sections ?? []
  if (chosen.length > 0) {
    for (const block of chosen) {
      const version = typeof block.version === 'number' ? block.version : null
      const match = rows.find(
        (row) =>
          row.workflow_id === block.section_id && (version === null || row.version === version),
      )
      if (match) picked[block.section_id] = match
    }
    return picked
  }
  for (const row of rows) {
    const current = picked[row.workflow_id]
    if (!current || (row.version ?? 0) > (current.version ?? 0)) picked[row.workflow_id] = row
  }
  return picked
}

function toSectionView(
  row: DecoratedSectionResult,
  block: ReaderPreviewSection | null,
): MatchPreviewSection {
  return {
    section_id: row.workflow_id,
    title: block?.title ?? row.title,
    body: row.body ?? '',
    partial: block?.partial ?? Boolean(row.unavailable_reason),
    quality: block?.quality ?? row.quality ?? null,
    version: row.version ?? null,
    sources: (row.sources ?? []).map((source) => ({
      label: source.label,
      url: source.url ?? null,
      kind: source.kind,
      note: source.note ?? null,
    })),
  }
}

/**
 * 이 실행의 `/section-results`에 **없는** reader 선택 섹션의 표시 블록.
 *
 * 구성본은 다른 실행의 섹션 결과를 고를 수 있다(예: 마지막 AI만 다시 실행한 run은 앞 섹션
 * 본문을 부모 실행에서 선택해 쓴다). 서버 reader 응답에는 그 본문·근거가 있지만 이 실행의
 * 행 목록에는 없으므로, 로컬 행이 있는 섹션은 그대로 두고 **없는 섹션만** reader 블록으로
 * 채운다. 같은 섹션의 다른 버전이나 최신 행으로 바꿔 넣지 않는다(reader 선택이 우선).
 */
function readerOnlySections(
  preview: ReaderPreview | null,
  picked: Record<string, DecoratedSectionResult>,
): Record<string, MatchPreviewSection> {
  const out: Record<string, MatchPreviewSection> = {}
  for (const block of preview?.sections ?? []) {
    if (picked[block.section_id]) continue
    const body = typeof block.body === 'string' ? block.body : ''
    const sources = (block.sources ?? []).map((source) => ({
      label: source.label,
      url: source.url ?? null,
      kind: source.kind,
      note: source.note ?? null,
    }))
    // 보여줄 것이 전혀 없는 블록은 넣지 않는다(빈 카드를 만들지 않는다).
    if (body.trim() === '' && sources.length === 0) continue
    out[block.section_id] = {
      section_id: block.section_id,
      title: block.title,
      body,
      partial: Boolean(block.partial),
      quality: block.quality ?? null,
      version: typeof block.version === 'number' ? block.version : null,
      sources,
      from_reader_selection: true,
    }
  }
  return out
}

function fixtureOf(
  preview: ReaderPreview | null,
  candidate: FixtureCandidate | null,
): MatchPreviewFixture {
  const identity = preview?.fixture ?? null
  const label = text(candidate?.label) ?? text(identity?.label) ?? ''
  const fromLabel = splitMatchup(label)
  const homeName = text(candidate?.home_team_name) ?? fromLabel.home
  const awayName = text(candidate?.away_team_name) ?? fromLabel.away
  return {
    external_id: candidate?.fixture_id ?? identity?.fixture_id ?? null,
    home: {
      name: homeName ?? '홈팀',
      badge_url: logoHref(identity?.home_team_logo_url),
      external_id: intId(identity?.home_team_external_id),
    },
    away: {
      name: awayName ?? '원정팀',
      badge_url: logoHref(identity?.away_team_logo_url),
      external_id: intId(identity?.away_team_external_id),
    },
    league: text(candidate?.league_name) ?? text(identity?.league),
    kickoff_at: text(identity?.kickoff_at) ?? text(candidate?.kickoff_at),
    label,
  }
}

function toOddsRows(
  structured: StructuredSectionView,
  fixture: MatchPreviewFixture,
): MatchPreviewOddsRow[] {
  return structured.odds.map((row) => ({
    source: row.bookmaker,
    observed_at: row.observedAt,
    // 소스 하나당 1X2 세 칸. 값이 없으면 null로 두고 화면이 빈 칸으로 그린다.
    cells: [
      { label: `${fixture.home.name} 승`, value: row.home },
      { label: '무승부', value: row.draw },
      { label: `${fixture.away.name} 승`, value: row.away },
    ],
  }))
}

function toInjuryRows(structured: StructuredSectionView): MatchPreviewInjury[] {
  return structured.injuries.map((row) => {
    // 저장 표기를 확정 부상으로 승격하지 않는다. 결장/불투명 두 갈래만 색으로 구분한다.
    const status: 'out' | 'doubt' =
      row.status === 'out' || row.status === 'confirmed_absence' ? 'out' : 'doubt'
    return {
      team: row.team,
      player: row.player,
      status,
      status_label: injuryStatusLabel(row.status),
      detail: row.summary,
      // 서버가 준 사진 주소만 쓴다. 없으면(키 없음 포함) null 이고 화면은 이름을 그대로 그린다.
      photo_url: row.photoUrl ?? null,
      team_external_id: row.teamExternalId ?? null,
      ...(row.teamSide ? { team_side: row.teamSide } : {}),
    }
  })
}

/**
 * 저장된 섹션 행의 **미제공 사유**. 진단 영역에서 "왜 표시하지 않았는지"를 확인하는 값이다.
 *
 * 독자 응답은 본문이 없는 선택 섹션(배당 등)을 블록에서 빼므로 `pickSections`에 없다.
 * 그래서 reader가 고른 버전이 있으면 그 버전 행을, 없으면 그 섹션의 저장 행 중 최신 1건을
 * 본다. 어느 쪽도 없으면 `null`이며 사유를 지어내지 않는다.
 */
function reasonOf(
  sectionId: string,
  response: SectionResultsResponse,
  preview: ReaderPreview | null,
): string | null {
  const rows = (response.section_results ?? []).filter((row) => row.workflow_id === sectionId)
  if (rows.length === 0) return null
  const chosenVersion = (preview?.sections ?? []).find(
    (block) => block.section_id === sectionId,
  )?.version
  const version = typeof chosenVersion === 'number' ? chosenVersion : null
  const row =
    (version === null ? undefined : rows.find((item) => item.version === version)) ??
    rows.reduce((latest, item) => ((item.version ?? 0) > (latest.version ?? 0) ? item : latest))
  return text(row.unavailable_reason)
}

/**
 * 구성본이 다른 실행에서 고른 행을 **이 실행 행이 없는 섹션에만** 더한다.
 *
 * 새 run은 다시 만든 섹션 1건만 자기 행으로 갖는다. 나머지 섹션의 카드(사진·배당·AI 제목)를
 * 그리려면 구성본이 고른 그 결과 행의 구조화 값이 필요하다. 여기서는 **이미 선택된 행**을
 * 옮겨 담기만 하며, 같은 섹션의 최신 버전이나 다른 경기 결과로 바꾸지 않는다.
 */
function withComposedRows(
  picked: Record<string, DecoratedSectionResult>,
  composed: readonly SectionResultView[] | undefined,
): Record<string, DecoratedSectionResult> {
  if (!composed || composed.length === 0) return picked
  const merged = { ...picked }
  for (const row of composed) {
    if (!row?.workflow_id || !row.section_result_id) continue
    if (merged[row.workflow_id]) continue
    merged[row.workflow_id] = row as DecoratedSectionResult
  }
  return merged
}

/** 저장 결과를 확정 목업이 읽는 표시 모델로 옮긴다. 값은 만들지 않고 고르기만 한다. */
export function toMatchPreviewView(
  input: PreviewRunData & { fixture?: FixtureCandidate | null },
): MatchPreviewView {
  const preview = input.preview
  // 구성본이 다른 실행에서 고른 섹션 결과 행. reader 선택과 **같은 섹션 키**로만 채우고,
  // 이 실행의 행이 있는 섹션은 덮어쓰지 않는다(선택된 정확한 버전이 정본).
  const picked = withComposedRows(pickSections(input.sections, preview), input.composed_sections)
  const fixture = fixtureOf(preview, input.fixture ?? null)

  const sections: Record<string, MatchPreviewSection> = {}
  for (const [sectionId, row] of Object.entries(picked)) {
    const block = preview?.sections?.find((item) => item.section_id === sectionId) ?? null
    sections[sectionId] = toSectionView(row, block)
  }
  // 이 실행의 행이 없는 reader 선택 섹션(구성본이 다른 실행 결과를 고른 경우)은
  // reader가 준 본문·근거로 표시한다. 로컬 행이 있는 섹션은 덮어쓰지 않는다.
  for (const [sectionId, section] of Object.entries(readerOnlySections(preview, picked))) {
    if (sections[sectionId]) continue
    sections[sectionId] = section
  }

  const nearest = (sectionId: string): StructuredSectionView | null =>
    picked[sectionId] ? structuredFromSectionResult(picked[sectionId]) : null

  const forecastStructured = nearest('section_ai_forecast')
  const playersStructured = nearest('section_players')
  const injuriesStructured = nearest('section_availability')
  const mediaStructured = nearest('section_outlook')
  const oddsStructured = nearest('section_odds')

  const structuredForecast = forecastStructured?.forecast ?? null
  const reasoning = structuredForecast?.reasoning ?? []
  const normalizedScore = structuredForecast ? scoreText(structuredForecast.score) : null
  const scoreMatch = normalizedScore ? /^(\d{1,2})-(\d{1,2})$/.exec(normalizedScore) : null
  const score = scoreMatch
    ? { home: Number(scoreMatch[1]), away: Number(scoreMatch[2]) }
    : null

  // 우세 문구에 쓸 실제 팀명. fixture/candidate 이름이 fallback(홈팀/원정팀)이면 저장된
  // 구조화 행의 **확인된 외부 ID → 팀명**으로만 대체한다(ID 추측·새 매핑 없음).
  const fallbackNames = new Set(['홈팀', '원정팀'])
  const verifiedTeamNames = teamNamesByExternalId([
    ...(playersStructured?.players ?? []).map((row) => ({
      team: row.team,
      team_external_id: row.teamExternalId ?? null,
    })),
    ...(injuriesStructured?.injuries ?? []).map((row) => ({
      team: row.team,
      team_external_id: row.teamExternalId ?? null,
    })),
  ])
  const nameForSide = (external: number | null, current: string): string => {
    const id = intId(external)
    if (id === null) return current
    const verified = verifiedTeamNames.get(id)
    // fixture 이름이 실제 팀명이면 그것을 우선한다.
    if (text(current) !== null && !fallbackNames.has(current.trim())) return current
    return verified ?? current
  }
  const homeDisplayName = nameForSide(fixture.home.external_id, fixture.home.name)
  const awayDisplayName = nameForSide(fixture.away.external_id, fixture.away.name)

  const missing: string[] = []
  const hasPlayers = (playersStructured?.players.length ?? 0) > 0
  const hasInjuries = (injuriesStructured?.injuries.length ?? 0) > 0
  const playerPhotos = playersStructured?.players ?? []
  const injuryPhotos = injuriesStructured?.injuries ?? []
  // 사진이 **하나라도 빠졌을 때만** 안내한다. 모두 있으면 이 줄은 만들지 않는다.
  // 선택 필드이므로 키가 없으면 `undefined`다. null 만 비교하면 이전 저장본을 놓친다.
  const photosMissing =
    playerPhotos.some((row) => (row.photoUrl ?? null) === null) ||
    injuryPhotos.some((row) => (row.photoUrl ?? null) === null)
  if ((hasPlayers || hasInjuries) && photosMissing) missing.push(MISSING_PLAYER_PHOTOS)

  // 구성본 조회에서 빠진 섹션이 있으면 그 사실을 진단에 남긴다(카드가 빈 이유).
  const composedError = text(input.composed_error ?? null)
  if (composedError !== null) missing.push(`${MISSING_COMPOSED_PREFIX} ${composedError}`)

  const odds = oddsStructured ? toOddsRows(oddsStructured, fixture) : []
  // 배당 표를 그리지 못했을 때 **저장된 사유**를 관리자 진단에 남긴다. 값이 없는데 표를
  // 만들지 않고, 실제 배당이 연결된 것처럼도 표시하지 않는다. 사유가 저장돼 있지 않으면
  // 지어내지 않는다. 독자 선택이 배당 섹션을 빼도(본문이 비어 있음) 사유는 이 실행의
  // 저장 행에서 읽는다.
  if (odds.length === 0) {
    const reason = reasonOf('section_odds', input.sections, preview)
    if (reason !== null) missing.push(`${MISSING_ODDS_PREFIX} ${reason}`)
  }

  return {
    fixture,
    generated_at: text(preview?.generated_at),
    forecast: {
      // 구조화 전망이 없으면 이 카드를 그리지 않고 본문을 통째로 아래에 남긴다.
      forecastLines: structuredForecast
        ? introLines(picked.section_ai_forecast?.body ?? '', { reasoning, score })
        : [],
      reasoning: structuredForecast ? [...reasoning] : [],
      lean: structuredForecast?.lean ?? null,
      lean_label: leanLabel(structuredForecast?.lean ?? null, {
        homeName: homeDisplayName,
        awayName: awayDisplayName,
        fallbackNames,
      }),
      score,
    },
    playerIntro: hasPlayers
      ? introLines(picked.section_players?.body ?? '', { dropLabels: PLAYER_LABELS })
      : [],
    players: (playersStructured?.players ?? []).map((row) => ({
      team: row.team,
      player: row.player,
      reason: row.reason,
      // 서버가 준 사진 주소만. 내부 player_id(533)로 CDN 주소를 만들지 않는다.
      photo_url: row.photoUrl ?? null,
      team_external_id: row.teamExternalId ?? null,
      ...(row.teamSide ? { team_side: row.teamSide } : {}),
    })),
    injuries: injuriesStructured ? toInjuryRows(injuriesStructured) : [],
    // 표시 상한은 매체 3곳이다. 서버가 더 줘도 화면은 3곳만 그린다.
    media: (mediaStructured?.media ?? []).slice(0, 3).map((row) => ({
      publisher: row.publisher,
      statement: row.statement,
      url: row.url,
    })),
    odds,
    sections,
    complete: preview?.complete ?? null,
    missing,
    // 저장된 한국어 라벨(실행 상세의 R4 payload)과 섹션 구조 값을 함께 읽어 별칭표를 만든다.
    // 새 번역을 만들지 않고, 저장돼 있지 않으면 빈 표다.
    team_aliases: teamAliasesFrom([
      ...Object.values(picked),
      ...(input.detail?.results ?? []).map((row) => row.payload),
    ]),
  }
}

/** 저장 본문을 표시 블록으로 나눈다. 구조화 값이 없을 때 **본문 그대로** 보여주기 위한 최소 해석. */
export type BodyBlock =
  | { kind: 'heading'; level: 2 | 3; text: string }
  | { kind: 'paragraph'; text: string }
  | { kind: 'list'; items: string[] }

export function bodyBlocks(body: string): BodyBlock[] {
  const blocks: BodyBlock[] = []
  let listItems: string[] = []
  const flush = () => {
    if (listItems.length === 0) return
    blocks.push({ kind: 'list', items: listItems })
    listItems = []
  }
  for (const raw of body.split('\n')) {
    const line = raw.trim()
    if (!line) {
      flush()
      continue
    }
    const heading = /^(#{2,3})\s+(.+)$/.exec(line)
    if (heading) {
      flush()
      blocks.push({
        kind: 'heading',
        level: heading[1].length === 2 ? 2 : 3,
        text: heading[2].trim(),
      })
      continue
    }
    const bullet = /^[-*]\s+(.+)$/.exec(line)
    if (bullet) {
      listItems.push(bullet[1].trim())
      continue
    }
    flush()
    blocks.push({ kind: 'paragraph', text: line })
  }
  flush()
  return blocks
}
