# 섹션 워크플로우 연결 계약 (section interface manifest)

작성·소유: PS-01 통합 책임자(A), 2026-11-11 KST. 근거 문서:
[확정 설계](../../superpowers/specs/2026-11-11-preview-sections-design.md),
[실행 계획](../../superpowers/plans/2026-11-11-preview-sections-implementation.md),
[연결 사실 조사](section-workflow-integration-facts.md).

이 문서는 **실제로 존재하는 이름**을 적는다. 계획만 있는 항목은 "계획"이라고 표시하고,
구현이 끝나면 이 문서를 고친 뒤 조정자에게 알린다. B/C/D는 이 문서의 이름을 그대로 쓰고,
이름을 바꿔야 하면 **이 문서를 먼저 고치고 조정자에게 통지**한다. 타입 파일을 서로 고쳐
계약을 맞추지 않는다.

## SF-01 계약 변경 (검색 자료·선택 구성본) — 2026-11-11

구현자 SF-01이 추가한 계약이다. 의존 작업(B/C/D)은 이 이름을 그대로 쓴다.

### 검색 자료 — `search_findings` (v4: 검색 기반 AI 요약 포함)

사용자 확정(`검색 기반 AI 요약도 활용`)에 따라 **조사 응답이 요약을 낸다**:

- 조사 프롬프트(`discovery_people/v2`, `discovery_outlook/v2`)는 URL만이 아니라
  `summary[]`(`topic`·`text`·`sources`·`publisher`·`predicted_score`·`unverified`)를 낸다.
- `material_type="search_ai_summary"`로 묶음에 보존하고 **작성 입력으로 실제 사용**한다.
  라벨은 `검색을 사용한 AI 조사 요약(기사 원문 아님)`이며, 기사 스니펫·원문 발췌로
  부르지 않는다. `grounding_chunks`/`supports`가 0이어도 요약을 반려하지 않는다.
- 요약의 인용 주소는 `sources[]`로, 모델이 표시한 낮은 확신은 `unverified`로 남긴다.
- 작성 입력 우선순위: `search_ai_summary` → 내용 있는 인용/스니펫 → 주소만 있는 메타.



- 묶음 버전: `INFORMATION_BUNDLE_VERSION = "mp11-information-bundle-5"`.
- 위치: `InformationBundle.search_findings`(저장 JSON `search_findings`),
  조사 그룹에도 `DiscoveryGroup.search_findings`로 같은 줄이 남는다.
  **수집 단계(`retrieval.collect_with_bodies`)가 `search_findings_from_groups()`로 조사
  그룹의 줄을 묶음 최상위로 접는다**(SF-02 차단 1 수정).
- 자료 유형 `SEARCH_MATERIAL_TYPES`:
  `search_ai_summary`(검색을 사용한 AI 조사 요약) / `search_snippet`(검색 도구가 실제
  반환한 요약문) / `search_source_meta`(도메인·주소만 온 메타) /
  `model_cited_span`(모델이 쓴 인용 문장) / `model_note`(모델이 쓴 한 줄 페이지 설명).
- **주소 출처 표시** `SearchFinding.url_provenance` — `grounding_chunk`(검색 도구가 반환한
  주소) / `model_provided`(모델이 제시한 주소, 도구 메타 미확인) / `none`. 표기는
  `SEARCH_URL_PROVENANCE_LABELS`를 그대로 쓰며, 대조는 표시 구분일 뿐 요약을 버리는
  조건이 아니다(추가 증명 게이트 없음).
- **자료 우선순위**(작성 프롬프트 4개 공통): 수집 본문 → 검색 자료 → DB. 더 믿을 만한
  자료를 먼저 쓰라는 뜻이며, 아래 계층 자료를 근거 없이 버리라는 뜻이 아니다.
- 표기 `SEARCH_MATERIAL_LABELS`를 화면·프롬프트에 그대로 쓴다. 서로 합쳐 부르지 않는다.
- 실제 확인: 저장된 Google Search 응답에서 `grounding_chunks[].web`은
  `domain`·`title`·`uri`만 오고 `title`이 도메인과 같다. 요약 필드는 없다.
  그래서 `search_snippet`은 응답에 요약 필드가 **실제로 있을 때만** 생긴다.

### 선택 결과 구성본 — `/runs/{run_id}/composition`

| 항목 | 값 |
|---|---|
| 저장 | `store.save_composition` / `store.load_composition`, 기록 유형 `section_composition` |
| API | `POST /api/v1/admin/preview/runs/{run_id}/composition`, `GET .../composition` |
| 해석 | `bundle_pipeline.resolve_selected_results`(선택 ID마다 **자기 실행**에서 조회) |
| 거부 | `bundle_pipeline.CompositionRefused`, 응답 `refused[]`(다른 경기·없는 결과·중복 섹션) |
| 최종 AI 입력 | `bundle_pipeline.composition_upstream` → `build_bundle_section(upstream=...)` |
| 실행 연결 | `run_section_regeneration()`이 `store.load_composition`으로 **저장 구성본을 직접 읽고** `composition_upstream`으로 넘긴다(SF-02 차단 2 수정) |
| API 연결 | `POST /section-runs`의 `composition_id`(선택) · `selected_result_ids`(선택). 저장 값과 다른 `composition_id`는 422 |
| 응답 표시 | `SectionRunResponse.composition_id` — 이 실행이 실제로 쓴 구성본(안 썼으면 null) |
| 화면 | `CompositionPanel.vue`: 섹션별 버전 1개 선택 → 저장 → 마지막 AI 실행 |

### 독자 투영·진단

- `section_preview.build_bundle_reader_view`: 저장 섹션 본문을 표시 순서로 내보낸다. 옛 S1
  경로보다 **먼저** 쓰이며, 필수 섹션 본문이 없으면 `complete=false`와 사유를 남긴다.
- **섹션당 버전 1개**(`_select_rows`): 저장 구성본의 선택 ID가 있으면 그 버전만, 없으면
  최신 1개만 쓴다. 같은 섹션 v1·v2를 독자 본문에 함께 싣지 않는다(SF-02 §4-a).
- `section_preview.build_selected_inputs_view`: 진단 응답의 `composition_inputs`
  (프론트 `ReaderPreviewDiagnostics.composition_inputs` 타입 과 `CompositionItem[]`).

### 시험 run 집합 (모듈별 3회 계수)

| 항목 | 값 |
|---|---|
| 태그 | `bundle_pipeline.TRIAL_TAG_PREFIX = "trial-set:"`, 실행 `label`에 붙는다 |
| 읽기 | `trial_set_of(label)` |
| 집합 시작 | `run_bundle_pipeline(trial_set_id=...)`, 재생성은 부모 label의 태그를 이어받는다 |
| 재계수 | `scripts/preview_bundle_live_once.py`가 **같은 태그의 실행만** 장부에서 다시 센다 |
| 초기화 금지 | 새 run·재시작으로 0이 되지 않는다. 과거 3run(0d938572·216d11ca·270baa93)의 계수는 보존되고 이번 집합과 섞이지 않는다 |
| 저장 그릇 | 새 schema 없음. 기존 `preview_runs.label` + `preview_write_audit(send_charged)` 재사용 |
- 검색/본문/DB 수집 실패 사유는 진단·관리자 화면에만 둔다.

## 0. 지금 상태 (이 시각 기준)

| 항목 | 상태 | 위치 |
|---|---|---|
| 정보 원문 묶음 계약(`InformationBundle` 등) | **구현 완료** | `app/preview/information_bundle.py` |
| 전송 사용량 내구 장부 | **구현 완료** | `app/preview/send_ledger.py` |
| 조사 묶음(2회) | B 구현 중 | `app/preview/discovery.py` |
| 공통 수집(브라우저 없는 HTTP) | B 구현 중 | `app/preview/retrieval.py` (아직 없음) |
| 섹션 작성(bundle 기반) | **E 인계 후 A 소유** | `modules/bundle_sections.py` (mp11-bundle-sections-3) |
| 관리자 화면 | D 구현 중 | `frontend/src/features/match-preview/` |
| `GET /runs/{run_id}/information-bundle` | **구현 완료** | `app/api/v1/preview_admin.py` |
| `GET /runs/{run_id}/information-bundle/sources/{source_id}` | **구현 완료** | 같은 파일. 이 실행 소유 전문 아티팩트만 연다 |
| 묶음 저장·조회(JSONB 그릇) | **구현 완료** | `store.save_information_bundle` / `load_information_bundle` |
| 전문 아티팩트 저장·조회 | **구현 완료** | `store.save_information_bundle_with_bodies` / `load_source_body` |
| 섹션 재생성 요청/응답 필드 | 계획 (§5) | `app/api/v1/preview_admin.py` |

## 1. 정보 원문 묶음 — `app.preview.information_bundle`

계약 버전: `INFORMATION_BUNDLE_VERSION = "mp11-information-bundle-2"`.
필드 의미가 바뀌면 이 값을 올리고 이 문서와 조정자 통지를 먼저 한다.

### 1.1 상수

```python
INFORMATION_BUNDLE_VERSION = "mp11-information-bundle-2"

# 두 조사 묶음 (설계 ②)
DISCOVERY_GROUP_PLAYERS_INJURY = "players_injury"   # 선수·부상
DISCOVERY_GROUP_MEDIA_ODDS = "media_odds"           # 외부 전망·배당
DISCOVERY_GROUPS = (DISCOVERY_GROUP_PLAYERS_INJURY, DISCOVERY_GROUP_MEDIA_ODDS)
# B의 discovery.py 표기를 canonical 값으로 맞추는 별칭 (양쪽 다 검증 통과)
DISCOVERY_GROUP_ALIASES = {"people": "players_injury", "outlook": "media_odds"}

DISCOVERY_STATUSES = ("completed", "not_run", "failed",
                      "configuration_error", "budget_exhausted")

SOURCE_NATURES = ("preview", "news", "past_match_report", "stats", "profile",
                  "squad", "odds", "unavailable", "unknown")
COLLECTION_METHODS = ("fresh_http", "stored_capture", "public_api",
                      "static_json", "text_fallback", "unavailable")
ODDS_MARKET_REGULATION_1X2 = "1x2_regulation"

SECTION_PLAYERS       = "section_players"
SECTION_AVAILABILITY  = "section_availability"
SECTION_OUTLOOK       = "section_outlook"
SECTION_ODDS          = "section_odds"
SECTION_AI_FORECAST   = "section_ai_forecast"
SECTION_IDS = (SECTION_PLAYERS, SECTION_AVAILABILITY, SECTION_OUTLOOK,
               SECTION_ODDS, SECTION_AI_FORECAST)

# 섹션 → 읽는 자료 축. 작성이 다른 섹션 자료를 끌어다 쓰지 않게 한다.
SECTION_MATERIAL_KEYS = {
    SECTION_PLAYERS:      ("db", "web_players"),
    SECTION_AVAILABILITY: ("db", "web_injury"),
    SECTION_OUTLOOK:      ("db", "web_outlook"),
    SECTION_ODDS:         ("odds",),                     # 모델 호출 없음
    SECTION_AI_FORECAST:  ("db", "web_players", "web_injury",
                           "web_outlook", "sections"),
}

MAX_SOURCES_PER_SECTION = 6
MAX_PASSAGES_PER_SOURCE = 3
MAX_PASSAGE_CHARS = 1500
MAX_WEB_SECTION_CHARS = 16000
MAX_BUNDLE_INPUT_CHARS = 32000     # DB 포함 정보 원문 총량
```

### 1.2 자료 구조 (모두 frozen dataclass, `to_dict()`/`from_dict()` 제공)

```python
Passage             passage_id, source_id, ordinal, text,
                    char_count=None, heading=None
                    .to_dict()  # char_count 미지정 시 len(text)로 채움

BundleSource        source_id, discovery_group, requested_url, final_url,
                    nature, method, title=None, published_at=None,
                    captured_at=None, stored_capture_at=None,
                    http_status=None, redirects=None, extractor=None,
                    body_chars=None, body_sha256=None,
                    body_artifact_id=None, passages=(),
                    failure=None, notes=()
                    .usable -> bool            # passages 있고 failure 없음
                    .to_dict()["delivered_chars"]

DiscoveryGroup      group, status, logical_call_id=None, provider=None,
                    model=None, prompt_version=None,
                    response_artifact_id=None, candidate_urls=(), diagnostics=(),
                    sent_attempts=0, started_at=None, finished_at=None

DbSnapshot          fixture, team_id_space, collected_at=None, teams=(),
                    standings=(), injuries=(), recent_matches=(), roster=(),
                    source_tables=(), coverage=(), diagnostics=(),
                    artifact_id=None, readable=False

OddsQuote           source_id, site, market, observed_at,
                    home_decimal, draw_decimal, away_decimal, note=None
                    .complete -> bool          # 1x2_regulation + 세 값 모두 있음
OddsMarket          quotes=(), collected_at=None, diagnostics=(), unsupported_sites=()

NetworkUsage        http_used=0, http_failed=0, redirects=0, api_used=0,
                    http_limit=None, api_limit=None, note=None

InformationBundle   bundle_id, fixture, team_id_space, collected_at,
                    sources=(), db_snapshot=None, discovery_groups=(),
                    odds=None, diagnostics=(), network_usage=NetworkUsage(),
                    bundle_version=INFORMATION_BUNDLE_VERSION, mode="live",
                    as_of=None, build_note=None, bundle_hash=None
                    .usable_sources -> tuple[BundleSource, ...]
                    .delivered_passages() -> tuple[Passage, ...]
                    .to_dict() / .from_dict()
DeliveryLimits      max_sources_per_section=6, max_passages_per_source=3,
                    max_passage_chars=1500, max_web_section_chars=16000,
                    max_bundle_input_chars=32000
```

`InformationBundle.to_dict()`가 내보내는 키(관리자 API 응답과 저장 아티팩트가 같은 모양):

```
bundle_id, bundle_version, fixture, team_id_space, collected_at, as_of, mode,
sources[], db_snapshot, discovery_groups[], odds, section_deliveries[],
available_passages[],          # 출처 순서 유지, 각 항목 "delivered": false
passage_semantics,             # 후보/실제 전달 구분 문장
diagnostics[], network_usage, delivery_limits,
build_note, usable_source_count, available_chars,
browser_used=false, cross_checked_with_db=false, requires_grounding_chunks=false,
bundle_hash
```

**전달 후보 vs 실제 전달 (중요).** `sources[].passages`와 `available_passages[]`는
수집·정규화로 **고를 수 있게 된 후보** 구간이다. "모델에 실제로 보냈다"는 뜻이 아니다.
실제 전달은 `section_deliveries[]`의 `SectionDelivery`가 밝힌다:
`section_id, logical_call_id, model_delivered, passage_ids[], source_ids[],
payload_sha256, input_chars, available_passage_ids[], excluded_passage_ids[],
sent_attempts, implementation_version, prompt_version, created_at, note`.
`payload_sha256`은 그 섹션 요청 payload를 정규화한 해시이므로 저장된 요청 아티팩트와
대조해 "무엇이 실제로 전달됐는지" 확인할 수 있다. 배당처럼 모델을 쓰지 않는 섹션은
`model_delivered=false`이고 `excluded_passage_ids`가 후보 전체다.

정직성 필드 의미:

- `browser_used`는 항상 `false`다. 이 경로는 브라우저 렌더를 쓰지 않는다.
- `cross_checked_with_db`는 항상 `false`다. 기사와 DB를 교차 대조해 탈락시키지 않는다.
- `requires_grounding_chunks`는 항상 `false`다. Google 인용 메타데이터는 필수 조건이 아니다.
- `available_passages[]`는 섹션이 **고를 수 있는 후보** 구간이다(실제 전달 아님).
  실제 모델 전달은 `section_deliveries[]`가 밝힌다. 전문은
  `BundleSource.body_artifact_id`가 가리키는 아티팩트에 있고 묶음 dict에 다시 넣지 않는다.

### 1.3 함수

```python
new_bundle_id(prefix="bundle") -> str
canonical_discovery_group(value: str) -> str
bundle_hash(payload: Mapping[str, Any]) -> str
bundle_to_dict(bundle) -> dict[str, Any]
bundle_summary(bundle) -> dict[str, Any]              # 실행·인계 보고용 짧은 요약
# summary 키: available_passages / available_chars / section_delivery_count /
#            odds_adopted_quotes ...
describe_bundle(bundle) -> dict[str, Any]             # 관리자 검사용 전체 설명
collect_available_passages(bundle) -> tuple[dict, ...]
source_index(bundle) -> dict[str, dict]               # source_id → 출처 요약
passage_char_total(bundle) -> int
adopted_odds_quotes(bundle) -> tuple[dict, ...]      # 채택 가능한 배당 줄
describe_odds(bundle) -> dict                        # 채택/미채택 사유
build_section_delivery(*, section_id, payload, passage_ids, source_ids,
                       available_passage_ids, logical_call_id, model_delivered,
                       input_chars, sent_attempts, implementation_version,
                       prompt_version, created_at, note) -> SectionDelivery
delivery_hash(payload) -> str
iter_source_urls(bundle) -> tuple[str, ...]
validate_information_bundle(bundle, *, limits=None) -> tuple[str, ...]   # 위반 목록
ensure_valid_bundle(bundle, *, limits=None) -> None                     # 위반 시 예외
BundleBuildError(ValueError)
```

`bundle_summary()` 키: `bundle_id, bundle_version, bundle_hash, fixture_id,
team_id_space, mode, collected_at, source_count, usable_source_count,
failed_source_count, delivered_passages, delivered_chars, web_chars_used,
discovery_groups{group: status}, db_readable, db_injuries, odds_quotes,
odds_complete_quotes, network_usage, diagnostic_count, browser_used`.

## 2. B가 채우는 자리 — 조사·수집

B는 자기 파일(`discovery.py`, `retrieval.py`, `sources/player_stats.py`,
`prompts/discovery_*.md`)만 만든다. 공유 파일을 고치지 않는다.

- `discovery.discover_candidates(...) -> DiscoveryResult` (이미 구현됨, B 소유).
  묶음 이름 표기는 `people`/`outlook`이며, 묶음에 넣을 때
  `canonical_discovery_group()`로 `players_injury`/`media_odds`에 맞춘다.
- `retrieval.collect_information_bundle(...) -> CollectionResult` (**B 구현, B 소유**).
  - 입력: `candidates`, `fixture`, `budget`, `http=None`, `now=None`, `max_sources`,
    `include_odds`, `odds_urls`, `home_team_names`, `away_team_names`, `target_checker`.
  - 출력: `CollectionResult(sources_, diagnostics, network_usage, odds, budget_snapshot)`.
    B는 자사 모양을 그대로 유지한다(반환형 변경 불필요).
  - 모델 작성을 실행하지 않는다(LLM 0회). 저장도 하지 않는다.
  - 실패한 후보도 같은 목록에 `failure`/`failure_detail`로 남는다.
  - `network_usage = {"used", "failed", "redirects", "limit", "remaining", "counted"}`이며
    리다이렉트 홉·실패·직접 수집을 모두 센다. HTTP 상한은 기존 24회를 공유한다.
- **A 소유 어댑터**가 B 결과를 계약으로 옮긴다(양쪽 파일을 고치지 않는다):

```python
bundle_from_collection(*, collection, fixture, team_id_space, db_snapshot=None,
                       discovery_groups=(), collected_at=None, mode="live",
                       diagnostics=(), odds_source_id="src:odds",
                       odds_site="public-table", bundle_id=None,
                       build_note=None) -> InformationBundle
bundle_source_from_collection(source, *, group) -> BundleSource
odds_market_from_observation(observation, *, source_id, site) -> OddsMarket
discovery_group_from_result(result) -> DiscoveryGroup
network_usage_from_collection(usage, *, api_limit=None) -> NetworkUsage
```

  - B의 `people`/`outlook` 표기는 `players_injury`/`media_odds`로 정규화된다.
  - B 출처 종류(`article/preview/list/stats/profile/odds/other`)는 계약 자료 성격으로
    매핑된다(확정 못 하면 `unknown`). 실패한 출처는 `method="unavailable"`이고 구간이 없다.
  - B `Passage`의 본문 텍스트가 계약 `Passage.text`로 옮겨진다(B `to_dict()`는 본문을
    빼므로 객체 속성을 읽는다).
  - `OddsObservation(available=False)`는 빈 시장 + 사유만 남기고 숫자를 만들지 않는다.
- 배당은 모델 없이 `OddsMarket`으로 정리한다. 값을 모르면 `None`이고 그 줄은
  `complete=False`다. **불완전·미지원 배당은 선택 섹션 진단일 뿐이며 묶음 검증이나
  필수 작성(AI 전망·점수·주목 선수)을 막지 않는다.** 채택 여부는
  `adopted_odds_quotes()` / `describe_odds()`로 구분한다.

## 3. C가 채우는 자리 — 섹션 작성

C는 `modules/bundle_sections.py`(신규)와 기존 모듈/프롬프트만 고친다.

```python
# 계획 (C 소유) — 이름·시그니처를 이대로 맞춘다.
build_bundle_section(
    *,
    section_id: str,                  # SECTION_IDS 중 하나
    bundle: InformationBundle | Mapping[str, Any],
    transport,                        # app.preview.provider.ProviderTransport
    context,                          # app.preview.contracts.ExecutionContext
    budget,                           # app.preview.retry.RunBudget
    session=None,
    upstream: Mapping[str, Any] | None = None,   # AI 전망이 읽는 앞 섹션 결과
    fixture_names: Mapping[str, Any] | None = None,
) -> SectionDraft
```

**E 인계 확정.** `build_bundle_section`은 아래 인자를 모두 받는다:
`section_id, bundle, transport, context, budget, session, upstream, fixture_names,
resolver, player_candidates, limits, now`. A는 `REQUIRED_BUILDER_PARAMS`로 이 계약을
검사하고, 없으면 `BuilderContractError`로 멈춘다(조용히 빼지 않는다).

- `fixture_names = {"home_team", "away_team", "league"}` — DB 팀 이름을 우선한다.
- `resolver` — `DisplayNames` 또는 기존 파사드. 없으면 같은 응답의 한글 표기를 쓴다.
- `player_candidates` — DB 통계의 `player_id`·표시 이름·기록. 프롬프트 후보 목록이 된다.
- 전망 `structured.forecast = {lean, score, reasoning}`이며, **score가 없으면 `insufficient`**이고
  부분 본문은 보존한다.
- 프롬프트 버전: players/availability/forecast `-prompt-2`.
- 구현 버전 **mp11-bundle-sections-3**: 출력 상한 `max_output_tokens`를 2048 → **40000**으로
  올렸다. 2048에서는 추론(thoughts) 토큰이 예산을 다 써 JSON이 절단됐다(실측 thoughts 1964 +
  candidates 68 = 2032). 이 값은 **출력 토큰 상한**이며 모델 호출 횟수 상한과 무관하다.
  출력이 달라지므로 승인 축 버전이 올라가며, 기존 승인 버전을 덮어쓰지 않는다.

`SectionDraft`(C 소유) 최소 필드: `section_id`, `title`, `body`,
`sources`, `structured`(선수명/선정이유 분리, 부상 최대2/팀, 매체 3곳/점수 미제시,
1X2 표), `quality`, `unavailable_reason`, `prompt_version`, `implementation_version`,
`diagnostics`. A는 이 값을 `runner.NodeOutcome`/`store.save_section_result`로 옮긴다.

### 3.1 실제 전달 기록을 C가 A로 넘기는 방법 (확정)

C가 만든 요청 payload와 실제로 넣은 구간 ID를 **그대로** 넘긴다. A가 후보 목록에서
"아마 이걸 보냈을 것"이라고 추정해 채우지 않는다.

```python
# C가 SectionDraft에 함께 담아 넘긴다(권장: 필드 이름 고정).
SectionDraft.delivery = SectionDelivery(...)   # 또는 아래 함수로 만든 값

# A는 이 값을 그대로 묶음에 붙이고 저장한다.
bundle = bundle.with_section_delivery(draft.delivery)
store.save_information_bundle(session, run_id=run_id, bundle=bundle, actor_id=...)
```

`SectionDelivery`를 만드는 A 소유 함수(계약 §1.3):

```python
build_section_delivery(
    *,
    section_id,                     # SECTION_IDS 중 하나
    payload,                        # 실제 요청에 넣은 payload(dict 그대로)
    passage_ids=(),                 # 그 payload에 실제로 들어간 구간 ID
    source_ids=(),
    available_passage_ids=(),       # 묶음이 제공한 후보 전체(선택)
    logical_call_id=None,
    model_delivered=True,           # 배당은 False
    input_chars=None,
    sent_attempts=0,
    implementation_version=None,
    prompt_version=None,
    created_at=None,
    note=None,
) -> SectionDelivery
```

- `input_chars`를 넘기지 않으면 payload 직렬화 길이를 쓴다. C가 실제 전달 글자 수를
  알고 있으면 그 값을 넘긴다(모델 입력 상한 계산과 같은 값이 된다).
- `payload_sha256`은 `delivery_hash(payload)`로 계산되어 저장된다. 나중에 요청 아티팩트
  (`attempt.request_artifact_id`)와 대조하면 실제 전달을 확인할 수 있다.
- `model_delivered=False`(배당)면 `payload_sha256`은 `None`이고 `passage_ids`는 비어야
  한다. 후보 전체는 `excluded_passage_ids`로 남는다.
- **C가 delivery를 넘기지 않으면** A는 `section_deliveries`에 아무것도 넣지 않는다.
  후보 구간 수를 "전달했다"고 표시하지 않는다.

작성 규칙(설계 고정):

- 작성 3회(선수·부상·매체)는 `provider.request_model`만 쓰고 **검색 도구를 넣지 않는다**.
- 배당(`section_odds`)은 모델 호출 0회다.
- 최종 `section_ai_forecast`는 1회 호출이며 확보된 섹션 결과와 DB 경기력 자료를 읽는다.
- 기사와 DB를 교차 검증해 탈락시키지 않는다. `grounding_chunks`/`supports` 부재로
  기사를 버리지 않는다. 진단 문장은 본문에 넣지 않는다.
- 정상 6회 = 조사 2 + 작성 3 + 최종 1.

## 4. A가 여는 API — 관리자 조회

기존 경로를 유지하고 확장한다. 새 경로는 GET 하나다.

| 경로 | 상태 | 응답 |
|---|---|---|
| `GET /api/v1/admin/preview/runs/{run_id}` | 유지·확장 | 실행 상세(기존 구조 + 아래 키) |
| `GET /api/v1/admin/preview/runs/{run_id}/information-bundle` | **계획 (A)** | `{"run_id", "bundle", "summary", "availability"}` |
| `GET /api/v1/admin/preview/runs/{run_id}/section-results` | 유지 | 저장 섹션 결과 목록 |
| `POST /api/v1/admin/preview/section-runs` | 유지·확장 | 섹션 실행. 아래 §5 필드 추가 |
| `POST /api/v1/admin/preview/bundle-runs` | **구현 완료** | 새 기본 경로 전체 실행(조사2+작성3+최종1) → `run_id` |
| `POST /api/v1/admin/preview/section-runs` (새 경로 섹션, live) | **구현 완료** | 실제 묶음 재사용/갱신 재생성(검토 F5) |
| `GET /api/v1/admin/preview/sections` | 유지·확장 | 섹션 목록 + `bundle_inputs` 가용성 |
| `GET/POST /api/v1/admin/preview/sections/{workflow_id}/approvals` | 유지 | 승인 현황/승인 |
| `GET /api/v1/admin/preview/runs/{run_id}/preview` | 유지 | 독자용 투영(ADMIN 전용) |

`POST /bundle-runs` 요청/응답(구현):

```json
// 요청
{ "fixture_id": 1557474, "league_id": 39, "season": 2026,
  "home_team_id": 13, "away_team_id": 4, "kickoff_at": "…",
  "mode": "live", "label": "…" }
// 응답
{ "run_id": "…", "mode": "live", "status": "succeeded|failed",
  "quality": "ready|insufficient", "bundle_id": "…", "bundle_hash": "…",
  "bundle_artifact_id": "…", "section_result_ids": {"section_players": "…"},
  "section_quality": {"section_players": "ready"},
  "section_unavailable": {"section_availability": "이유…"},
  "discovery_status": {"people": "completed", "outlook": "completed"},
  "external_calls": 6, "budget": {"model_requests": 8, "model_used": 6, "…": "…"},
  "unavailable_reason": null, "note": "…" }
```

`mode=mock`은 422로 거부한다(새 경로는 모의 응답으로 본문을 채우지 않는다). 모의 화면
확인은 섹션 단위 `/section-runs`로 한다.

`GET /runs/{run_id}/information-bundle` 응답(구현):

```json
{
  "run_id": "…",
  "availability": {"available": true, "reason": null, "artifact_id": "…"},
  "summary": { "bundle_id": "…", "bundle_hash": "…", "source_count": 4,
               "usable_source_count": 3, "available_chars": 5120, "…": "…" },
  "bundle": { "bundle_id": "…", "sources": [], "available_passages": [],
              "section_deliveries": [], "db_snapshot": {}, "odds": {},
              "discovery_groups": [], "diagnostics": [], "network_usage": {},
              "…": "…" }
}
```

응답의 `availability`는 **중첩 객체**다(검토 F6):
`{"availability": {"available": bool, "reason": str|null, "artifact_id": str|null,
"sequence": int|null}, "bundle": {...}|null, "summary": {...}|null,
"passages_omitted"?: true, "passage_note"?: str}`. 평면 키(`available`/`reason`)는 더 이상
내보내지 않는다 — 프론트 파서가 중첩을 읽으므로 평면이면 사유가 화면에서 사라진다.

`available=false`일 때 `bundle`은 `null`이고 `availability.reason`에 실제 사유가 들어간다
("이 실행에는 정보 원문 묶음이 없습니다"). 묶음이 없는데 빈 묶음을 만들어 내지 않는다.
`include_passages=false`면 후보 구간 본문을 빼고 `passages_omitted=true`를 낸다.

### 4.1 전문(본문) 조회

묶음 인라인에는 **후보 구간**만 있고 전문은 아티팩트에 있다. 출처 전문은 다음 경로로
연다. 응답 모양: `{run_id, available, source_id, reason, artifact_id, body}`.

| 상황 | `available` | `reason` |
|---|---|---|
| 이 실행 소유 아티팩트가 있음 | `true` | `null` |
| 묶음에 그 출처가 없음 | `false` | "이 정보 원문 묶음에 해당 출처가 없습니다." |
| 본문 미확보(후보/실패 출처) | `false` | "전문 아티팩트가 없습니다…" |
| 재사용·부모 실행 원문 | `false` | "이 실행 소유가 아니어서 열 수 없습니다." |
| 보관 기간 만료 | `false` | "보관 기간이 지나 본문을 열 수 없습니다." |

`body`는 `{record_type:"source_body", source_id, requested_url, final_url, captured_at,
extractor, extraction, html_sha256, body_sha256, body_chars, text}`다. Google 원문
응답은 여기 복제하지 않는다(기존 실행 상세 artifacts·`attempt.response_artifact_id`).

저장 함수:

**호출 순서(확정).** `collect_with_bodies` 1회 → `save_information_bundle_with_bodies` 1회.
후자가 `.bundle`을 꺼내 전문을 `record_type="source_body"` 아티팩트로 저장하고
`BundleSource.body_artifact_id`를 채운 뒤 묶음을 저장한다. 수집을 두 번 하지 않는다.

```python
store.save_information_bundle(session, *, run_id, bundle, actor_id=0,
                              secret_values=(), now=None) -> dict
store.save_information_bundle_with_bodies(session, *, run_id, collection, actor_id=0,
                                          secret_values=(), now=None,
                                          db_snapshot=None) -> dict
store.load_information_bundle(session, run_id) -> dict
store.load_source_body(session, run_id, source_id) -> dict
```

## 5. 섹션 재생성 — 요청/응답 필드

`POST /section-runs` 본문에 추가(계획, 이름 고정):

```json
{
  "workflow_id": "section_players",
  "mode": "live",
  "fixture_id": 1557474, "league_id": 39, "season": 2026,
  "home_team_id": 13, "away_team_id": 4, "kickoff_at": "…",
  "source_mode": "reuse",              // "reuse" | "refresh"
  "bundle_id": "bundle-…",             // reuse일 때 필수
  "base_run_id": "…",                  // 선택: 비교 기준 실행
  "base_result_id": "…",               // 선택: 비교 기준 결과 버전
  "selected_result_ids": []            // section_ai_forecast용
}
```

- 새 경로 섹션(`section_players`/`section_availability`/`section_outlook`/`section_odds`/
  `section_ai_forecast`)의 `mode=live` 재생성은 **실제 묶음 작성 경로**로 실행된다
  (`bundle_pipeline.run_section_regeneration`). 옛 조사 노드를 돌려 놓고 "묶음 재사용"이라고
  표시하지 않는다(검토 F5). `mode=mock` 재생성은 묶음 재사용 실적으로 인정하지 않는다(422).
- `source_mode="reuse"`: 저장된 묶음·원문 재사용. **새 수집·새 검색 호출 없음**.
  작성 호출만 발생한다(섹션별 1회, 배당 0회).
- `source_mode="refresh"`: 새 수집을 포함한다. 예상 전송 범위를 응답에 표시한다.
- 저장 응답만 재처리하는 동작은 **무전송**이며 별도 표시다
  (`POST /runs/{run_id}/results/{module_execution_id}/replay` 기존 경로).
- 섹션 재생성은 부모 실행과 연결된 새 실행으로 남기고, 다른 성공 섹션을 자동 재호출하지
  않는다.

응답 필드(`SectionRunResponse` 확장, 계획):

```
run_id, workflow_id, workflow_version, mode, status, quality,
section_result_id, section_result_version, external_calls, budget,
unavailable_reason, note,
source_mode, bundle_id, bundle_reused, expected_model_calls,
parent_run_id, base_result_id, new_version, no_model_call
```

## 6. 실행 예산과 전송 보존

- 정상 모델 6회(조사 2 + 작성 3 + 최종 1), 전체 실제 전송 상한 8회, 동시 2.
- 미시작 정상 호출 6회의 몫을 예약하고, 시작하지 않기로 확정되면 그 예약을 **반환**한다.
  반환해도 전체 상한 8회는 늘어나지 않는다.
- 비모델 HTTP/API 상한 24회를 수집 HTTP와 외부 API가 공유한다. 동시 2, 요청 30초,
  실행 기한 1800초. 리다이렉트·실패도 전송으로 센다.
- 전송 사용량은 `app/preview/send_ledger.py`가 **전송 전 예약 + 응답 직후 결과**를 각각
  독립 트랜잭션으로 남긴다. 후처리 예외·실행 롤백·프로세스 재시작에도 8회 상한이
  초기화되지 않는다.
  - 전송 전 예약(`outcome="pending"`)도 **사용량으로 센다.** 전송 직전/직후에 프로세스가
    죽어 결과를 확정할 수 없는 경우 상한을 잃지 않기 위한 보수적 선택이다.
  - 결과 행이 없는 예약은 `unresolved_sends()`로 보고하며 성공/실패로 단정하지 않는다.
  - 설정 부족(`not_sent=True`)은 실제 전송이 아니므로 세지 않는다.
  - 예상 밖 전송 예외는 `outcome="unknown"`으로 남기고 예약분을 그대로 사용량으로 둔다.

```python
# app.preview.send_ledger
CHARGE_ACTION = "send_charged"
bind_send_session_factory(factory) -> None
send_session_factory() -> sessionmaker
journal_send(*, run_id, actor_id, logical_call_id, attempt_ordinal, request_class,
             provider, model, mode, request_body, response_body=None,
             http_status=None, outcome="pending", error_class=None,
             error_message=None, usage=None, not_sent=False, note=None,
             secret_values=(), now=None) -> JournalOutcome
charged_requests(session, *, run_id, request_class=None) -> int
charged_model_attempts(session, *, run_id, logical_call_id) -> int
reconcile_budget_from_journal(budget, session, *, run_id) -> dict
send_ledger.audit_row_count(session, *, run_id) -> int
SendJournalUnavailable(RuntimeError)
```

## 6.5 섹션 결과 구조화 값 (`GET /runs/{run_id}/section-results`)

`include_structured=true`(기본)면 각 섹션 결과 행에 `structured`와 `available`이 붙는다.
`structured`는 **저장된 module payload에서만** 뽑는다(새 사실·선정·예측 없음).

```json
{
  "run_id": "…", "structured_version": "mp11-structured-1",
  "section_results": [
    { "section_result_id": "…", "workflow_id": "section_players",
      "body": "…", "sources": [], "…": "…",
      "available": true,
      "structured": {
        "structured_version": "mp11-structured-1",
        "workflow_id": "section_players",
        "players":   [{"player": "…", "reason": "…", "team": "…"}],
        "injuries":  [{"player": "…", "team": "…", "status": "…", "summary": "…"}],
        "media":     [{"publisher": "…", "statement": "…", "predictedScore": null,
                       "publishedAt": null, "url": null}],
        "odds":      [{"bookmaker": "…", "observedAt": null, "home": "2.1",
                       "draw": "3.4", "away": "3.2", "market": "1x2_regulation"}],
        "forecast":  {"lean": "home", "score": "2-1", "reasoning": ["…"], "note": null}
      } } ] }
```

정직성 규칙(구현됨):

- 선수는 `selected_player`+`selection_reason`이 **둘 다** 있을 때만 행이 된다(합쳐 쓰지 않음).
- 부상 `status`는 원문 표기 그대로다. `unknown`을 확정 부상으로 바꾸지 않는다.
- 매체는 점수를 안 주면 `predictedScore=null`이다.
- 배당은 `market=1x2_regulation`만 표에 넣고, 값이 없거나 1.0~1000 밖이면 `null`이다.
- `forecast.lean`은 `home`/`draw`/`away`만 인정한다.
- payload가 없으면 `structured`는 빈 값이고 `available=false`다.
- 팀별 상한은 표시 상한이며 넘는 값을 자르지 않는다.

## 6.6 전송 장부 노출 (`GET /runs/{run_id}`)

실행 상세 응답에 `send_ledger`가 붙는다(저장된 감사 행만 읽음, 외부 호출 0회).

```json
"send_ledger": {
  "charged_requests": 6,
  "unresolved_sends": [
    {"logical_call_id": "section_players", "attempt_ordinal": 0, "outcome": "pending",
     "note": "전송 후 결과 행이 없습니다. 사용량으로는 세었습니다.", "audit_id": "…"}
  ],
  "ledger_action": "send_charged"
}
```

- `charged_requests`는 **실제 live 전송** 수다(mock/replay·설정 부족은 세지 않음).
- `unresolved_sends`는 예약만 남고 결과 행이 없는 전송이다. **성공/실패로 단정하지 않는다.**
  프로세스가 전송 직전·직후에 멈춘 경우가 여기 나타나며, 사용량으로는 이미 셌다.
- 상세에 값이 없으면 키를 만들지 않는다(0으로 꾸미지 않음).

## 7. 화면(D)이 기대할 수 있는 것

- `section_results[]` 항목은 기존 `store._section_result_view()` 모양을 유지한다
  (`section_result_id, run_id, workflow_id, workflow_version, version, title, body,
  sources, mode, environment, quality, module_execution_ids, result_ids, diagnostics,
  unavailable_reason, unavailable, output_contract_version, contract_version,
  created_at, supersedes_section_result_id`).
- 본문·근거를 먼저 보여주고, 정보 원문·모델 전체응답은 펼치는 진단으로 둔다.
- 필수 섹션은 AI 전망·AI 예상 스코어·주목 선수다. 선택(부상·매체·배당)은 자료가 없으면
  독자 화면에서 생략한다.
- `mode=mock`/`replay`는 실제 생성이 아니며 승인 근거가 아니다. placeholder 응답을
  live로 표시하지 않는다.

## 7.5 새 기본 경로 실행기 (`app/preview/bundle_pipeline.py`)

정보 원문 묶음 → 섹션 5개 → 저장을 한 번에 도는 통합 진입점이다. A 소유.

```python
run_bundle_pipeline(session, *, fixture, actor_id, transport, reader=None, http=None,
                    limits=None, label=None, mode=None, now=None,
                    home_team=None, away_team=None, league=None, db_context=None,
                    target_checker=None) -> BundlePipelineOutcome
build_db_snapshot(session, *, fixture, reader, run_id, actor_id, now=None) -> DbSnapshot
BUNDLE_PIPELINE_VERSION = "mp11-bundle-pipeline-1"
```

순서와 호출 수:

| 단계 | 하는 일 | 모델 | HTTP |
|---|---|---|---|
| D0 | 저장 DB 읽기 → `DbSnapshot`(+아티팩트) | 0 | 0 |
| 조사 A/B | `discovery.discover_candidates`(people/outlook) | 2 | 0 |
| 공통 수집 | `retrieval.collect_with_bodies` **1회** | 0 | ≤24 (공유) |
| 묶음 저장 | `store.save_information_bundle_with_bodies` | 0 | 0 |
| 작성 | `bundle_sections.build_bundle_section` × (선수·부상·매체) | 3 | 0 |
| 배당 | 같은 함수(`section_odds`) | 0 | 0 |
| 최종 전망 | 같은 함수(`section_ai_forecast`) + 앞 섹션 `upstream` | 1 | 0 |
| 저장 | 섹션 결과 버전 + 최종 묶음(전달 기록 포함) | 0 | 0 |

`BundlePipelineOutcome` 키: `run_id, mode, status, quality, bundle_id, bundle_hash,
bundle_artifact_id, section_result_ids{}, section_quality{}, section_unavailable{},
discovery_status{}, external_calls, model_calls_after, budget, unavailable_reason,
diagnostics[], pipeline_version`.

정직성 규칙(구현됨):

- 필수 섹션(AI 전망·주목 선수)의 본문이 없으면 `status=failed`,
  `quality=insufficient`이고 `unavailable_reason`에 빠진 섹션이 적힌다. 정상 완료로
  위장하지 않는다.
- 작성 가능한 자료(웹 본문·DB 경기력·앞 섹션 결과)가 모두 없으면 최종 전망 요청을
  보내지 않고 예약을 반환한다.
- 한 섹션·한 조사 실패가 다른 섹션 저장을 지우지 않는다(진단·`section_unavailable`).
- 같은 후보 URL을 두 번 수집하지 않고, 같은 논리 호출을 두 번 보내지 않는다.

## 8. 소유권 (요약)

| 파일 | 소유 |
|---|---|
| `app/preview/information_bundle.py`, `send_ledger.py`, `bundle_pipeline.py`, `section_structured.py` | A |
| `app/preview/discovery.py`, `retrieval.py`, `sources/player_stats.py`, `prompts/discovery_*.md` | B |
| `app/preview/modules/bundle_sections.py`, `prompts/bundle_*.md`, 기존 `players/players_contract/availability/outlook/synthesis`, `modules/__init__.py` | C → **인계 후 A** |
| `frontend/src/features/match-preview/**`, router/index | D |
| `app/preview/{contracts,provider,retry,models,store,artifacts,runner,pipeline,sections,registry,version_manifest,approvals,inspection,section_preview,presentation,jobs}.py`, `app/api/v1/preview_admin.py`, `app/main.py`, `app/core/config.py`, `requirements.txt`, `pyproject.toml`, `docs/implementation/match-preview/section-interface-manifest.md`, `tests/preview/conftest.py` | A |
| `tests/preview/test_bundle_runtime.py`, `test_bundle_integration.py`, 기존 provider/retry/pipeline/approval 테스트 | A |

B/C/D는 서로의 파일과 A의 파일을 고치지 않는다. 인계는 정확한 파일·함수·버전·증거·
`EDITING STOPPED`를 포함해야 하고, A는 그 인계를 확인한 뒤에만 통합한다.
