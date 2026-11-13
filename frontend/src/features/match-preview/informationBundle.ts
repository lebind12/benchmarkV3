/**
 * 정보 원문 묶음(InformationBundle) — 화면용 타입과 방어적 파서 (PS-04).
 *
 * 기준 계약: `docs/implementation/match-preview/section-interface-manifest.md` §1·§4
 * (`INFORMATION_BUNDLE_VERSION = "mp11-information-bundle-3"`, 구현 `app/preview/information_bundle.py`).
 * 버전 3에서 `search_findings`(검색 단계 실제 반환 자료, 자료 유형 라벨 포함)가 더해졌다.
 * 이 파일은 A의 backend 계약을 **읽기만** 하며, backend 타입 파일을 고치지 않는다.
 *
 * 응답 모양(§4, 계획):
 *
 * ```json
 * { "run_id": "…",
 *   "availability": { "available": true, "reason": null, "artifact_id": "…" },
 *   "summary": { "bundle_id": "…", "source_count": 4, "usable_source_count": 3, … },
 *   "bundle": { "bundle_id": "…", "sources": [], "available_passages": [],
 *               "section_deliveries": [], "db_snapshot": {}, "odds": {},
 *               "discovery_groups": [], "diagnostics": [], "network_usage": {}, … } }
 * ```
 *
 * `available=false`면 `bundle`은 `null`이고 `reason`에 실제 사유가 온다. 화면은 빈 묶음을
 * 만들어 내지 않고 그 사유를 그대로 표시한다.
 *
 * 지키는 것:
 *
 * - 서버 응답은 `unknown`으로 들어온다. 여기서 한 번만 검사해 화면 타입으로 바꾼다.
 * - 없는 값은 `null`/빈 배열로 두고 새 값을 만들지 않는다.
 * - **전달 후보와 실제 전달을 섞지 않는다.** `sources[].passages`와
 *   `available_passages[]`는 수집·정규화된 **후보** 구간이다(각 항목 `delivered: false`).
 *   "모델에 실제로 보냈다"는 `section_deliveries[]`의 `SectionDelivery`만 밝힌다
 *   (`model_delivered`, `passage_ids`, `payload_sha256`, `input_chars`, `sent_attempts`).
 *   배당처럼 모델을 쓰지 않는 섹션은 `model_delivered=false`다.
 * - 전문은 `body_artifact_id`가 가리키는 아티팩트에 있고 묶음 dict에 다시 들어오지 않는다.
 * - `browser_used`·`cross_checked_with_db`·`requires_grounding_chunks`는 항상 false다.
 *   이 값이 true로 오면 화면에 그대로 드러낸다(계약 위반을 숨기지 않는다).
 * - 비밀값(쿠키·토큰·계정)은 이 타입에 없다. 서버도 내려주지 않는다.
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

function firstText(source: Record<string, unknown>, keys: readonly string[]): string | null {
  for (const key of keys) {
    const value = text(source[key])
    if (value !== null) return value
  }
  return null
}

function count(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

function strings(value: unknown): string[] {
  return list(value)
    .map((item) => text(item))
    .filter((item): item is string => item !== null)
}

/**
 * 작성 입력에 전달한 구간 하나(§1.2 `Passage`).
 *
 * `source_id`로 출처와 연결된다. 화면은 이 연결을 깨지 않고 출처별로 묶어 보여준다.
 */
export type BundlePassageView = {
  passageId: string | null
  sourceId: string | null
  ordinal: number | null
  text: string
  charCount: number | null
  heading: string | null
}

/**
 * 수집한 출처 하나(§1.2 `BundleSource`).
 *
 * `usable=false`(구간 없음 또는 `failure` 있음)은 "가져온 자료"가 아니다. 화면은 따로
 * 모아 보여준다.
 */
/**
 * 검색 단계가 **실제로 확보한** 자료 한 줄.
 *
 * `material_type`이 무엇인지 밝힌다. `search_snippet`만 검색 도구가 반환한 요약문이고,
 * `search_source_meta`는 도메인·주소만 온 메타데이터, `model_cited_span`·`model_note`는
 * **모델이 쓴 문장**이다. 화면은 이 이름을 바꿔 부르지 않는다.
 */
export type BundleSearchFindingView = {
  findingId: string
  discoveryGroup: string | null
  materialType: string
  /** 자료 유형 표기. 서버가 준 값을 그대로 보여준다. */
  label: string
  title: string | null
  url: string | null
  domain: string | null
  content: string | null
  contentChars: number
  capturedAt: string | null
  responseArtifactId: string | null
  /** 요약이 인용한 근거 주소들(여러 개). `url`은 그중 첫 번째 링크용 값이다. */
  sources: string[]
  /** 모델이 스스로 표시한 낮은 확신. 값을 바꾸지 않고 그대로 보여준다. */
  unverified: boolean
  /**
   * 주소 출처: `grounding_chunk`(검색 도구가 반환) / `model_provided`(모델이 제시) / `none`.
   * 도구가 반환한 주소와 모델이 적은 주소를 같은 이름으로 부르지 않는다.
   */
  urlProvenance: 'grounding_chunk' | 'model_provided' | 'none'
  urlProvenanceLabel: string | null
  isSearchSnippet: boolean
  /** 검색을 사용한 AI 조사 요약. 기사 원문도 도구 반환 스니펫도 아니다. */
  isAiSummary: boolean
  deliverable: boolean
  note: string | null
}

export type BundleSourceView = {
  sourceId: string
  discoveryGroup: string | null
  requestedUrl: string | null
  finalUrl: string | null
  /** 자료 성격(preview/news/past_match_report/stats/profile/squad/odds/unavailable/unknown). */
  nature: string | null
  method: string | null
  title: string | null
  publishedAt: string | null
  capturedAt: string | null
  httpStatus: number | null
  redirects: number | null
  extractor: string | null
  bodyChars: number | null
  failure: string | null
  notes: string[]
  /** 이 출처에서 모델에 전달한 구간. */
  passages: BundlePassageView[]
  usable: boolean
}

export type BundleStandingsRow = {
  teamId: number | null
  rank: number | null
  points: number | null
  played: number | null
  form: string | null
}

export type BundleInjuryRow = {
  playerName: string | null
  teamId: number | null
  status: string | null
  summary: string | null
}

export type BundleCoverageRow = {
  topic: string | null
  state: string | null
  detail: string | null
}

/** 읽기 전용 DB 스냅샷(§1.2 `DbSnapshot`). 읽지 못한 축은 비어 있고 `coverage`에 사유가 있다. */
export type BundleDbSnapshotView = {
  collectedAt: string | null
  readable: boolean
  teamIdSpace: string | null
  fixtureLabel: string | null
  fixtureId: number | null
  leagueId: number | null
  season: number | null
  kickoffAt: string | null
  standings: BundleStandingsRow[]
  injuries: BundleInjuryRow[]
  recentMatchCount: number
  rosterCount: number
  sourceTables: string[]
  coverage: BundleCoverageRow[]
  diagnostics: string[]
}

/** 배당 한 줄(§1.2 `OddsQuote`). 정규시간 1X2 소수점만 쓴다. */
export type BundleOddsQuoteView = {
  site: string
  market: string | null
  observedAt: string | null
  home: string | null
  draw: string | null
  away: string | null
  complete: boolean
}

export type BundleOddsMarketView = {
  quotes: BundleOddsQuoteView[]
  collectedAt: string | null
  unsupportedSites: string[]
  diagnostics: string[]
}

/** 외부 요청 사용량(§1.2 `NetworkUsage`). 리다이렉트·실패도 실제 전송으로 센다. */
export type BundleNetworkUsageView = {
  httpUsed: number | null
  httpFailed: number | null
  redirects: number | null
  apiUsed: number | null
  httpLimit: number | null
  apiLimit: number | null
  note: string | null
}

export type BundleDiscoveryGroupView = {
  group: string
  status: string | null
  candidateCount: number
  sentAttempts: number | null
}

/**
 * 섹션 하나에 **실제로 실린** 구간·근거 기록 (manifest §1.2 `SectionDelivery`).
 *
 * `sources[].passages`/`available_passages[]`는 **후보**다. 이 객체가 "그 중 무엇을
 * 실제로 보냈는지"를 밝힌다. `payloadSha256`은 섹션 요청 payload의 해시이므로 저장된
 * 요청 아티팩트와 대조할 수 있다.
 *
 * 배당(`section_odds`)처럼 모델을 쓰지 않는 섹션은 `modelDelivered=false`이고
 * `passageIds`가 비어 있으며 후보 전체가 `excludedPassageIds`에 남는다.
 */
export type BundleSectionDeliveryView = {
  sectionId: string
  logicalCallId: string | null
  /** 이 섹션이 모델 호출을 했는지. `false`면 전달된 구간이 없다. */
  modelDelivered: boolean
  /** 실제 payload에 실린 구간 ID. */
  passageIds: string[]
  sourceIds: string[]
  payloadSha256: string | null
  inputChars: number | null
  availablePassageIds: string[]
  excludedPassageIds: string[]
  /** 실제 payload에 실린 검색 자료 id(자료 유형은 searchFindings에서 대조). */
  searchFindingIds: string[]
  sentAttempts: number | null
  implementationVersion: string | null
  promptVersion: string | null
  createdAt: string | null
  note: string | null
}

export type InformationBundleView = {
  runId: string | null
  available: boolean
  unavailableReason: string | null
  bundleId: string | null
  bundleVersion: string | null
  bundleHash: string | null
  collectedAt: string | null
  asOf: string | null
  mode: string | null
  buildNote: string | null
  sources: BundleSourceView[]
  /**
   * 섹션이 **고를 수 있는 후보** 구간(출처 순서 유지). 실제 전달 기록이 아니다.
   * 화면은 이 목록을 "전달 후보"로만 부르고, 실제 전달은 `sectionDeliveries`로 표시한다.
   */
  availablePassages: BundlePassageView[]
  availableChars: number | null
  /** 섹션별 실제 전달 기록. 후보와 실제 전달을 구분하는 유일한 근거다. */
  sectionDeliveries: BundleSectionDeliveryView[]
  /** 서버가 주는 후보/실제 전달 구분 문장. 있으면 그대로 표시한다. */
  passageSemantics: string | null
  dbSnapshot: BundleDbSnapshotView | null
  odds: BundleOddsMarketView | null
  discoveryGroups: BundleDiscoveryGroupView[]
  /** 실제 검색 반환 자료(자료 유형 라벨 포함). 출처 목록과 다른 목록이다. */
  searchFindings: BundleSearchFindingView[]
  /** 자료 유형별 건수. 화면은 "검색 자료 n건"으로 뭉뚱그리지 않는다. */
  searchFindingsByType: Record<string, number>
  diagnostics: string[]
  networkUsage: BundleNetworkUsageView | null
  /** 계약상 항상 false여야 하는 값. true가 오면 화면에 그대로 표시한다. */
  honestyFlags: { browserUsed: boolean; crossCheckedWithDb: boolean; requiresGroundingChunks: boolean }
}

const EMPTY_BUNDLE: InformationBundleView = {
  runId: null,
  available: false,
  unavailableReason: null,
  bundleId: null,
  bundleVersion: null,
  bundleHash: null,
  collectedAt: null,
  asOf: null,
  mode: null,
  buildNote: null,
  sources: [],
  availablePassages: [],
  availableChars: null,
  sectionDeliveries: [],
  passageSemantics: null,
  dbSnapshot: null,
  odds: null,
  discoveryGroups: [],
  searchFindings: [],
  searchFindingsByType: {},
  diagnostics: [],
  networkUsage: null,
  honestyFlags: { browserUsed: false, crossCheckedWithDb: false, requiresGroundingChunks: false },
}

function parsePassage(raw: unknown): BundlePassageView | null {
  const row = record(raw)
  if (row === null) return null
  const body = text(row.text)
  if (body === null) return null
  return {
    passageId: text(row.passage_id),
    sourceId: text(row.source_id),
    ordinal: count(row.ordinal),
    text: body,
    charCount: count(row.char_count),
    heading: text(row.heading),
  }
}

function parseSource(raw: unknown): BundleSourceView | null {
  const row = record(raw)
  if (row === null) return null
  const sourceId = text(row.source_id)
  if (sourceId === null) return null
  const passages = list(row.passages)
    .map(parsePassage)
    .filter((item): item is BundlePassageView => item !== null)
  const failure = text(row.failure)
  return {
    sourceId,
    discoveryGroup: text(row.discovery_group),
    requestedUrl: text(row.requested_url),
    finalUrl: text(row.final_url),
    nature: text(row.nature),
    method: text(row.method),
    title: text(row.title),
    publishedAt: text(row.published_at),
    capturedAt: text(row.captured_at),
    httpStatus: count(row.http_status),
    redirects: count(row.redirects),
    extractor: text(row.extractor),
    bodyChars: count(row.body_chars),
    failure,
    notes: strings(row.notes),
    passages,
    // 서버가 `usable`을 주면 그 값을, 없으면 같은 규칙으로 판단한다(구간 있고 실패 없음).
    usable:
      typeof row.usable === 'boolean' ? row.usable : failure === null && passages.length > 0,
  }
}

function parseStandings(raw: unknown): BundleStandingsRow {
  const row = record(raw) ?? {}
  return {
    teamId: count(row.team_id),
    rank: count(row.rank),
    points: count(row.points),
    played: count(row.played),
    form: firstText(row, ['form', 'recent_form']),
  }
}

function parseInjury(raw: unknown): BundleInjuryRow {
  const row = record(raw) ?? {}
  return {
    playerName: firstText(row, ['player_name', 'player']),
    teamId: count(row.team_id),
    status: firstText(row, ['status', 'expected_status']),
    summary: firstText(row, ['summary', 'reason', 'detail']),
  }
}

function parseCoverage(raw: unknown): BundleCoverageRow {
  const row = record(raw) ?? {}
  return {
    topic: firstText(row, ['topic', 'axis', 'name']),
    state: firstText(row, ['state', 'status']),
    detail: firstText(row, ['detail', 'reason', 'note']),
  }
}

function parseDbSnapshot(raw: unknown): BundleDbSnapshotView | null {
  const row = record(raw)
  if (row === null) return null
  const fixture = record(row.fixture) ?? {}
  return {
    collectedAt: text(row.collected_at),
    readable: row.readable === true,
    teamIdSpace: text(row.team_id_space),
    fixtureLabel: firstText(fixture, ['label', 'fixture_label']),
    fixtureId: count(fixture.fixture_id) ?? count(fixture.internal_id),
    leagueId: count(fixture.league_id),
    season: count(fixture.season),
    kickoffAt: firstText(fixture, ['kickoff_at']),
    standings: list(row.standings).map(parseStandings),
    injuries: list(row.injuries).map(parseInjury),
    recentMatchCount: list(row.recent_matches).length,
    rosterCount: list(row.roster).length,
    sourceTables: strings(row.source_tables),
    coverage: list(row.coverage).map(parseCoverage),
    diagnostics: strings(row.diagnostics),
  }
}

function parseOddsQuote(raw: unknown): BundleOddsQuoteView | null {
  const row = record(raw)
  if (row === null) return null
  const site = firstText(row, ['site', 'bookmaker'])
  if (site === null) return null
  return {
    site,
    market: text(row.market),
    observedAt: text(row.observed_at),
    home: text(row.home_decimal),
    draw: text(row.draw_decimal),
    away: text(row.away_decimal),
    complete: row.complete === true,
  }
}

function parseOdds(raw: unknown): BundleOddsMarketView | null {
  const row = record(raw)
  if (row === null) return null
  const quotes = list(row.quotes)
    .map(parseOddsQuote)
    .filter((item): item is BundleOddsQuoteView => item !== null)
  const diagnostics = strings(row.diagnostics)
  const unsupported = strings(row.unsupported_sites)
  if (quotes.length === 0 && diagnostics.length === 0 && unsupported.length === 0) return null
  return {
    quotes,
    collectedAt: text(row.collected_at),
    unsupportedSites: unsupported,
    diagnostics,
  }
}

function parseDiscoveryGroup(raw: unknown): BundleDiscoveryGroupView | null {
  const row = record(raw)
  if (row === null) return null
  const group = firstText(row, ['group', 'name'])
  if (group === null) return null
  return {
    group,
    status: text(row.status),
    candidateCount: list(row.candidate_urls).length,
    sentAttempts: count(row.sent_attempts),
  }
}

function parseNetworkUsage(raw: unknown): BundleNetworkUsageView | null {
  const row = record(raw)
  if (row === null) return null
  return {
    httpUsed: count(row.http_used),
    httpFailed: count(row.http_failed),
    redirects: count(row.redirects),
    apiUsed: count(row.api_used),
    httpLimit: count(row.http_limit),
    apiLimit: count(row.api_limit),
    note: text(row.note),
  }
}

function parseSectionDelivery(raw: unknown): BundleSectionDeliveryView | null {
  const row = record(raw)
  if (row === null) return null
  const sectionId = text(row.section_id)
  if (sectionId === null) return null
  return {
    sectionId,
    logicalCallId: text(row.logical_call_id),
    modelDelivered: row.model_delivered === true,
    passageIds: strings(row.passage_ids),
    sourceIds: strings(row.source_ids),
    payloadSha256: text(row.payload_sha256),
    inputChars: count(row.input_chars),
    availablePassageIds: strings(row.available_passage_ids),
    excludedPassageIds: strings(row.excluded_passage_ids),
    searchFindingIds: strings(row.search_finding_ids),
    sentAttempts: count(row.sent_attempts),
    implementationVersion: text(row.implementation_version),
    promptVersion: text(row.prompt_version),
    createdAt: text(row.created_at),
    note: text(row.note),
  }
}

function parseSearchFinding(raw: unknown): BundleSearchFindingView | null {
  const row = record(raw)
  if (row === null) return null
  const findingId = text(row.finding_id)
  if (findingId === null) return null
  const materialType = text(row.material_type) ?? 'unknown'
  return {
    findingId,
    discoveryGroup: text(row.discovery_group),
    materialType,
    label: text(row.label) ?? materialLabel(materialType),
    title: text(row.title),
    url: text(row.url),
    domain: text(row.domain),
    content: text(row.content),
    contentChars: count(row.content_chars) ?? 0,
    capturedAt: text(row.captured_at),
    responseArtifactId: text(row.response_artifact_id),
    sources: strings(row.sources),
    unverified: row.unverified === true,
    urlProvenance:
      row.url_provenance === 'grounding_chunk' || row.url_provenance === 'model_provided'
        ? row.url_provenance
        : 'none',
    urlProvenanceLabel: text(row.url_provenance_label),
    isSearchSnippet: row.is_search_snippet === true,
    // 서버가 준 플래그가 없으면 자료 유형으로 판정한다(값을 만들어 내지 않는다).
    isAiSummary: row.is_ai_summary === true || materialType === 'search_ai_summary',
    deliverable: row.deliverable === true,
    note: text(row.note),
  }
}

/**
 * 자료 유형 표기. **서버가 준 라벨이 없을 때만** 쓰는 화면 폴백이다.
 * 검색 스니펫과 모델 산문을 같은 이름으로 부르지 않기 위해 문구를 고정한다.
 */
function materialLabel(materialType: string): string {
  switch (materialType) {
    case 'search_ai_summary':
      return '검색을 사용한 AI 조사 요약(기사 원문 아님)'
    case 'search_snippet':
      return '검색 도구가 반환한 요약문'
    case 'search_source_meta':
      return '검색 도구가 반환한 출처 메타(도메인·주소)'
    case 'model_cited_span':
      return '모델이 쓴 문장(검색 요약문 아님)'
    case 'model_note':
      return '모델이 쓴 페이지 설명(검색 요약문 아님)'
    default:
      return '자료 유형 미확인'
  }
}

function searchFindingCounts(raw: unknown): Record<string, number> {
  const row = record(raw)
  const out: Record<string, number> = {}
  if (row === null) return out
  for (const [key, value] of Object.entries(row)) {
    const parsed = count(value)
    if (parsed !== null) out[key] = parsed
  }
  return out
}

/**
 * `GET /runs/{run_id}/information-bundle` 응답을 화면 타입으로 바꾼다.
 *
 * `bundle`이 `null`이면 `available=false` + `reason`을 그대로 담는다(빈 묶음을 만들지
 * 않는다). 응답이 객체가 아니어도 예외를 던지지 않는다 — 진단 화면이 응답 모양 때문에
 * 통째로 죽지 않게 하기 위해서다.
 */
export function parseInformationBundle(payload: unknown): InformationBundleView {
  const root = record(payload)
  if (root === null) return { ...EMPTY_BUNDLE }

  const availability = record(root.availability) ?? {}
  const bundle = record(root.bundle)
  const runId = text(root.run_id)
  if (bundle === null) {
    return {
      ...EMPTY_BUNDLE,
      runId,
      available: availability.available === true,
      unavailableReason: text(availability.reason),
    }
  }

  // 후보 구간이다(실제 전달 아님). 서버가 주는 `delivered:` 키는 후보 표시일 뿐이므로
  // 읽지 않는다 — 실제 전달은 section_deliveries가 밝힌다.
  const available = list(bundle.available_passages)
    .map(parsePassage)
    .filter((item): item is BundlePassageView => item !== null)

  return {
    runId,
    available: availability.available === true || bundle !== null,
    unavailableReason: text(availability.reason),
    bundleId: text(bundle.bundle_id),
    bundleVersion: text(bundle.bundle_version),
    bundleHash: text(bundle.bundle_hash),
    collectedAt: text(bundle.collected_at),
    asOf: text(bundle.as_of),
    mode: text(bundle.mode),
    buildNote: text(bundle.build_note),
    sources: list(bundle.sources)
      .map(parseSource)
      .filter((item): item is BundleSourceView => item !== null),
    availablePassages: available,
    availableChars: count(bundle.available_chars),
    sectionDeliveries: list(bundle.section_deliveries)
      .map(parseSectionDelivery)
      .filter((item): item is BundleSectionDeliveryView => item !== null),
    passageSemantics: text(bundle.passage_semantics),
    dbSnapshot: parseDbSnapshot(bundle.db_snapshot),
    odds: parseOdds(bundle.odds),
    discoveryGroups: list(bundle.discovery_groups)
      .map(parseDiscoveryGroup)
      .filter((item): item is BundleDiscoveryGroupView => item !== null),
    searchFindings: list(bundle.search_findings)
      .map(parseSearchFinding)
      .filter((item): item is BundleSearchFindingView => item !== null),
    // 응답에 유형별 건수가 없으면 실제 목록에서 직접 센다(값을 만들어 내지 않는다).
    searchFindingsByType: (() => {
      const given = searchFindingCounts(bundle.search_findings_by_type)
      if (Object.keys(given).length > 0) return given
      const counted: Record<string, number> = {}
      for (const item of list(bundle.search_findings).map(parseSearchFinding)) {
        if (item === null) continue
        counted[item.materialType] = (counted[item.materialType] ?? 0) + 1
      }
      return counted
    })(),
    diagnostics: strings(bundle.diagnostics),
    networkUsage: parseNetworkUsage(bundle.network_usage),
    honestyFlags: {
      browserUsed: bundle.browser_used === true,
      crossCheckedWithDb: bundle.cross_checked_with_db === true,
      requiresGroundingChunks: bundle.requires_grounding_chunks === true,
    },
  }
}

/** 화면이 "보여줄 것이 없다"고 판단할 수 있는지. 빈 카드를 만들지 않기 위한 값이다. */
export function isBundleEmpty(bundle: InformationBundleView): boolean {
  return (
    !bundle.available &&
    bundle.sources.length === 0 &&
    bundle.dbSnapshot === null &&
    bundle.odds === null &&
    bundle.availablePassages.length === 0 &&
    bundle.sectionDeliveries.length === 0 &&
    bundle.searchFindings.length === 0 &&
    bundle.diagnostics.length === 0
  )
}

/** 출처의 표시 URL. 최종 URL이 있으면 그것을, 없으면 요청 URL을 쓴다. */
export function sourceHref(source: BundleSourceView): string | null {
  return source.finalUrl ?? source.requestedUrl
}

/** 요청 주소와 최종 주소가 다르면 리다이렉트 사실을 알린다. */
export function redirectNote(source: BundleSourceView): string | null {
  if (!source.requestedUrl || !source.finalUrl) return null
  if (source.requestedUrl === source.finalUrl) return null
  return '요청 주소와 최종 주소가 다릅니다(리다이렉트).'
}

/** 가져온 자료로 쓸 수 있는 출처(§1.2 `usable`). 실패·빈 출처는 여기 없다. */
export function usableSources(bundle: InformationBundleView): BundleSourceView[] {
  return bundle.sources.filter((source) => source.usable)
}

/** 가져오지 못한 출처. 사유를 함께 보여주기 위해 따로 모은다. */
export function failedSources(bundle: InformationBundleView): BundleSourceView[] {
  return bundle.sources.filter((source) => !source.usable)
}

/**
 * 이 묶음에서 **모델 호출로 실제 전달된** 구간 ID 전체.
 *
 * `modelDelivered=false`인 섹션(배당)의 구간은 여기에 들어오지 않는다. 후보 목록
 * (`availablePassages`)과 섞지 않기 위해 별도 함수로 둔다.
 */
export function deliveredPassageIds(bundle: InformationBundleView): Set<string> {
  const ids = new Set<string>()
  for (const delivery of bundle.sectionDeliveries) {
    if (!delivery.modelDelivered) continue
    for (const id of delivery.passageIds) ids.add(id)
  }
  return ids
}

/**
 * 섹션 하나의 실제 전달 기록. 같은 섹션에 기록이 여러 개면 마지막 것을 쓴다
 * (재생성 이력은 남고, 화면은 최근 전달을 보여준다).
 */
export function deliveryForSection(
  bundle: InformationBundleView,
  sectionId: string | null,
): BundleSectionDeliveryView | null {
  if (sectionId === null) return null
  const rows = bundle.sectionDeliveries.filter((row) => row.sectionId === sectionId)
  return rows.length > 0 ? rows[rows.length - 1] : null
}

/**
 * 구간이 이 섹션에 **실제로 전달됐는지**.
 *
 * 전달 기록이 아예 없으면 `false`다. "후보였으니 전달됐을 것"이라고 추정하지 않는다.
 */
export function passageDeliveredTo(
  delivery: BundleSectionDeliveryView | null,
  passageId: string | null,
): boolean {
  if (delivery === null || passageId === null) return false
  return delivery.passageIds.includes(passageId)
}
