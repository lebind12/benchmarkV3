# 검색 대체 근거·선택 구성본 — SF-02 한정 독립 검토

작성: SF-02 독립 검토 워커(읽기 전용), 2026-11-11 KST.
실행 모델: `deepseek-ai/deepseek-v4.1-flash-1017` (해당 세션 기준, 추론 강도 Max).
세션 ID는 시작 화면에서 확인했다. 이 문서는 **검토 기록**이며 승인 근거가 아니다.

- 범위: 이번 변경 5항목만. 옛 경로·옛 clock·전체 보안 확대는 심사하지 않았다.
- 금지 준수: 코드·테스트·설정 편집 0, `pytest`/`vitest` 0, 새 재현 스크립트 파일 0,
  모델 호출 0, 외부 HTTP 0, DB 쓰기 0, 서버 기동 0, 커밋 0.
- 재현에 쓴 것: **이미 있는 pure function·저장 자료 읽기**. 모델 호출 없음.
  실행한 것은 `./.venv/bin/python` 히어독에서의 함수 호출뿐이며 DB·네트워크·파일 쓰기가 없다.
- 구현자 `term_377ba85e`와 분리된 세션이며, 직접 수정하지 않는다.
  최소 수정 문장만 제시하고 수정 배정은 root가 한다.

## 검토 대상 해시

| 파일 | sha256 (앞 16자) | 줄 |
|---|---|---|
| `app/preview/discovery.py` | `6cbe440a5ecb71e2` | 910 |
| `app/preview/information_bundle.py` | `1e89823a254b67f8` | 1926 |
| `app/preview/retrieval.py` | `c011919a9cc30645` | 1807 |
| `app/preview/bundle_pipeline.py` | `c3cd29649f05100a` | 2078 |
| `app/preview/modules/bundle_sections.py` | `c1da313d285e9447` | 2681 |
| `app/preview/section_preview.py` | `e46f29e2f1d81ef8` | 406 |
| `app/preview/store.py` | `2337bf534773bb09` | 1770 |
| `app/api/v1/preview_admin.py` | `98876fd87051181a` | 1886 |
| `app/preview/send_ledger.py` | `9298f6fa12fb313a` | 391 |
| `app/preview/retry.py` | `4fa49b570b0f9a5f` | 674 |
| `scripts/preview_bundle_live_once.py` | `1678a5052a698a39` | 394 |
| `frontend/src/features/match-preview/types.ts` | `54bdf313b571d8d5` | 835 |
| `frontend/src/features/match-preview/api.ts` | `83df9096941b028e` | 236 |
| `frontend/src/features/match-preview/MatchPreview.vue` | `c6e1b17080238272` | 610 |
| `frontend/src/features/match-preview/SectionRegenerationPanel.vue` | `2fdd9aaef041f4da` | 555 |
| `docs/implementation/match-preview/section-interface-manifest.md` | `e866d5cb6cd31ce3` | 664 |

버전 상수 실제 값(주장과 일치): `INFORMATION_BUNDLE_VERSION="mp11-information-bundle-4"`
(`information_bundle.py:112`), `BUNDLE_PIPELINE_VERSION="mp11-bundle-pipeline-3"`
(`bundle_pipeline.py:75`), `IMPLEMENTATION_VERSION="mp11-bundle-sections-5"`
(`modules/bundle_sections.py:85`), 조사 프롬프트 `discovery_people/v2`·
`discovery_outlook/v2`(`discovery.py:76-77`). 4/3/5·v2 표기는 사실이다.

---

## 1) 조사 요약 → 작성 입력 연결 — **차단 1건**

### 1-a. 요약을 만드는 쪽은 요구대로다

- `parse_research_summary`(`discovery.py:598`)는 `text`가 빈 항목을 만들지 않고,
  `sources`를 http/https로 정규화하며, `unverified`를 숨기지 않는다.
- `discover_candidates`가 `material_type="search_ai_summary"`로 보존한다
  (`discovery.py:850-870`). 라벨은 `검색을 사용한 AI 조사 요약(기사 원문 아님)`
  (`information_bundle.py:141`). 기사 스니펫으로 부르지 않는다 — 요구 충족.
- 조사에만 `tools=[{"google_search": {}}]`가 붙고(`discovery.py:788`), 작성·최종
  요청에는 없다. 실측: `build_generation_config()` =
  `{'temperature': 0.2, 'max_output_tokens': 40000, 'response_mime_type': 'application/json'}`
  — `tools` 키 없음. 요구 충족.
- `grounding_chunks/supports`가 0이어도 요약을 반려하는 코드는 없다. 옛
  `core_evidence_satisfied`(`modules/synthesis.py`, `validation.py`)는 **옛 S1 경로**에만
  있고 새 묶음 경로의 게이트로 쓰이지 않는다. `bundle_sections.py`에 그 이름은 없다.
  → “예전 source-only 게이트 재반려”는 새 경로에 **없다**. 요구 충족.
- 메타 0·수집 0에서 대체 작동 여부: 섹션 게이트가 `not search.rows`를 조건에서 빼는
  형태로 이미 고쳐져 있다 —
  `bundle_sections.py:1399`(선수), `:1709`(부상), `:1967`(전망 섹션),
  최종 전망 `:2375`(`upstream_has_rows` 포함). 요약 줄이 **payload에 있으면** 호출된다.

### 1-b. 차단: 조사 요약이 저장 묶음의 `search_findings`에 실제로 들어가지 않는다

`retrieval.collect_with_bodies`가 묶음을 만들 때 `discovery_groups`만 넘기고
`search_findings`를 넘기지 않는다.

- `retrieval.py:1555-1571` — `InformationBundle(... discovery_groups=tuple(discovery_groups) ...)`
  에 `search_findings=` 인자가 **없다**.
- `InformationBundle`은 frozen dataclass이고 `__post_init__`이 없다
  (`information_bundle.py:968-1000`). 그래서 `discovery_groups`에 담긴 요약이
  `search_findings`로 파생되지 않는다.
- 접어 주는 함수는 `search_findings_from_groups`(`information_bundle.py:1264`) 하나뿐이고,
  그 유일한 호출부는 `bundle_from_collection`(`information_bundle.py:1818`)의
  **`if discovery_groups:` 분기 안**이다. 그런데 저장 경로
  `store.save_information_bundle_with_bodies`는 `bundle_from_collection`을
  `discovery_groups` 인자 없이 부른다(`store.py:1549-1555`). 게다가 이 분기는
  `payload is not None`(이미 `InformationBundle`인 경우)에서만 닿는다.
- 작성기는 `payload["search_findings"]`만 읽는다(`bundle_sections.py:525`).
  `discovery_groups`를 읽는 코드는 `bundle_sections.py`에 **없다**.

재현(모델·DB·HTTP·파일 쓰기 없음, 순수 함수만):

```
DiscoveryGroup.from_dict(group).search_findings          -> 1
search_findings_from_groups([dg])                        -> 1
InformationBundle(..., discovery_groups=(dg,)).search_findings -> 0   # 생성자 경로
collect_with_bodies(..., discovery_groups=(dg,)).bundle.search_findings -> 0
bundle_from_collection(collection=<그 묶음>, db_snapshot=None)          -> 0  # 저장 경로와 같은 호출
bundle_from_collection(..., discovery_groups=(dg,))                     -> 1  # 인자를 주면 살아남
_search_material(stored_payload, "section_players")      -> rows=0
_search_material({**stored_payload, "search_findings":[finding]}, "section_players") -> rows=1
```

즉 **본문 0·메타 0인 실행에서 조사 요약만 있는 경우**, 저장 묶음에는 요약이
`discovery_groups` 안에만 남고 작성 입력에는 0줄이 전달된다. 그러면
`bundle_sections.py:1399/1709/1967`의 `not search.rows` 조건이 참이 되어 세 섹션이
“자료 없음”으로 호출 없이 끝나고, 최종 전망도 `usable_sources`·`has_db`·`upstream`이
모두 비어 `bundle_pipeline.py:1063`에서 건너뛴다. 사용자 확정(“메타데이터 없어도 AI
요약 사용”)과 정면으로 어긋나는 **현재 요구 위반**이다.

기존 증거로도 확인된다. `evidence/ps05-live/live-20261111T074645Z-270baa93-….json`의
묶음 키에 `search_findings`가 없고, 세 실행 파일 모두 `search_findings` 0건이다.
그 실행에서 `section_availability`·`section_outlook`이 “수집 본문 없음”으로 미호출
종료된 것도 같은 원인과 일치한다.

**최소 수정(한 곳).** `retrieval.py:1555`의 `InformationBundle(...)` 생성에
`search_findings=search_findings_from_groups(discovery_groups),` 한 줄을 더한다
(`information_bundle`의 기존 함수 재사용, 새 규칙 없음). 검증은 위 재현을 그대로
다시 돌려 `collect_with_bodies(...).bundle.search_findings == 1`과
`_search_material(...)` rows ≥ 1을 확인하면 된다.

부수 확인(같은 원인, 별도 수정 불필요): 묶음 버전이 4로 올라갔는데
`section-interface-manifest.md:31`은 아직 `mp11-information-bundle-3`을 적고 있다.
계약 문서 표기 불일치다.

---

## 2) `selected_result_ids` → 구성본 → 마지막 AI 입력 — **차단 1건**

요구의 절반은 충족한다.

- API가 선택 ID를 받는다: `preview_admin.py:159`, `:1499`.
- 결과 ID마다 **자기 실행**에서 조회한다: `store.get_section_result_any_run`
  (`store.py:628`), 사용처 `bundle_pipeline.py:1572`.
- 다른 경기 거부: `bundle_pipeline.py`의
  `expected_fixture_id is not None and fixture_id != expected_fixture_id` → `refused[]`
  (`resolve_selected_results`, `:1553`). 중복 섹션·없는 결과도 거부한다.
- 구성본 저장/조회: `save_composition`(`bundle_pipeline.py:1644`),
  `store.save_composition`/`load_composition`(`store.py:1613`/`:1661`),
  API `POST/GET /runs/{run_id}/composition`(`preview_admin.py:1256`/`:1318`).
- 과거 행 보존: `save_module_result`가 `_next_version`으로 **새 행**을 만들고 이전 행을
  지우지 않는다(`store.py:422`). `_next_section_version`도 같은 방식이다. 요구 충족.

### 2-a. 차단: 저장 구성본이 “마지막 AI 실제 입력”으로 이어지지 않는다

`composition_upstream`(`bundle_pipeline.py:1694`)은 저장 구성본을 최종 AI `upstream`
모양으로 바꾸는 함수지만, **저장소 전체에서 호출부가 없다.**
`grep -rn composition_upstream` 결과는 정의 1곳과 계약 문서 1곳뿐이다.
`load_composition` 호출부도 `section_preview.build_selected_inputs_view`(진단 표시)와
`GET /composition`(조회)뿐이며, 실행 경로에서 쓰이지 않는다.

실제 재생성 경로 `run_section_regeneration`은 구성본을 읽지 않고
`upstream_result_ids`를 **직접** 해석한다(`bundle_pipeline.py:1980-2004`). 이 경로는
관리자가 그 요청에 ID를 실어 보낼 때만 동작한다. 그래서 “저장한 구성본을 근거로 마지막
AI만 다시 실행”하는 요구는 **저장된 구성본과 실행이 연결되지 않은 상태**다. 계약 문서
`section-interface-manifest.md:50`이 적은
`bundle_pipeline.composition_upstream → build_bundle_section(upstream=...)` 연결은
문서에만 있고 코드 호출은 없다.

덧붙여, 관리자 화면에도 이 연결을 여는 조작이 없다. `saveComposition`은
`api.ts:212`에만 정의되어 있고 어떤 `.vue`도 호출하지 않으며
(`grep -rln saveComposition frontend/src` → `api.ts` 하나),
`SectionRegenerationPanel.vue`는 `selected_result_ids`를 보내지 않는다
(`grep selected_result_ids` → 0건). 즉 지금 화면으로는 UI에서 구성본을 만들 수 없다.

**최소 수정.** 마지막 AI 단독 재실행 진입점에서 `store.load_composition`으로 저장
구성본을 읽고 `composition_upstream(session, composition)`을 `upstream`으로 넘긴다
(구성본이 없으면 지금처럼 `upstream_result_ids` 경로를 유지). 화면 연결은 별도 항목으로
분리해도 되지만, 최소 한 곳은 `selected_result_ids`를 실제로 보내야 요구가 성립한다.

---

## 3) 마지막 AI의 새 검색·추가 심사 없음·ready 형식·본문 보존 — **차단 0건**

- 검색 도구 없음: `build_generation_config()`(`bundle_sections.py:1027-1036`)에 `tools`
  키가 없다(실측 확인). 최종 프롬프트도 “이 요청에는 검색 도구가 없고, 네가 새로 출처를
  검증하지도 않는다”고 명시한다(`prompts/bundle_forecast.md:4-6`).
- 추가 source 품질 게이트 없음: 작성기는 받은 줄로만 쓰고, 기사↔DB 재대조·진입 반려
  단계가 없다. `_clean_evidence`는 **전달하지 않은 id 인용을 표시에서 빼는** 정리이며
  새 사실 심사가 아니다.
- `ready` 형식: 전망 문장과 예상 스코어가 **둘 다** 있어야 `READY`, 스코어가 없으면
  `INSUFFICIENT` + 사유(`bundle_sections.py:2528-2545`). 없는 스코어를 만들지 않는다
  (`_score_of`, 음수·비정수 거부). 요구 충족.
- 잘린 응답 보호: `_truncation_reason`이 `MAX_TOKENS`·닫히지 않은 JSON을 ready로
  올리지 않는다(`bundle_sections.py:1104-1121`).
- 진짜 본문 보존: 모델 `call.text`가 그대로 `parsed`로 가고, 후처리 예외 전에 원문은
  provider 아티팩트·장부에 남는다(§5). 실패 시에도 `unavailable_reason`과 부분 본문을
  함께 남긴다. 요구 충족.
- 선택 섹션 부족은 자동 실패가 아니다. 필수는 `section_players`·`section_ai_forecast`
  뿐이고(`section_preview.py:97`), 부상·매체·배당은 본문이 없으면 블록에서 빠지고
  사유만 관리자에게 남는다(`:145-158`). 없는 배당/스코어를 만들지 않는다. 요구 충족.

참고(차단 아님): 최종 전망 노드 게이트 `bundle_pipeline.py:1063`은 `usable_sources`
(수집 본문)와 `has_db`만 보고 **검색 자료는 세지 않는다.** §1-b를 고쳐 요약이
`search_findings`에 실제로 들어가도, 본문 0·DB 0·upstream 0이면 이 게이트에서 먼저
건너뛴다. 검색 자료가 유일한 입력인 경우를 살리려면 이 조건에
`bundle.deliverable_search_findings`를 포함해야 한다. §1-b 수정과 같은 커밋에서
처리하는 것이 자연스럽다(현재 요구 “검색 요약으로 작성”과 직결).

---

## 4) 독자 투영·API·화면 — **차단 0건, 참고 2건**

- 투영: `build_bundle_reader_view`(`section_preview.py:175`)가 옛 S1 경로보다 **먼저**
  호출된다(`preview_admin.py:963-967`). 저장 섹션 행만 읽고, `body`·`title`·`sources`를
  내보낸다. 필수 본문이 없으면 `complete=false`와 사유를 남긴다(`:221-225`).
- 내부 값 비노출: 블록 dict에 `section_id`·`version`·`workflow_version`이 들어가지만
  (`:167`), 독자 본문 문자열에는 들어가지 않고 출처도 허용 키만 남긴다
  (`_reader_sources_of`, `:120-130`). 프론트 타입도 같은 필드를 관리자 추적용으로만
  선언한다(`types.ts:759-769`). 화면은 `body`만 문단으로 렌더한다
  (`MatchPreview.vue:151-178`). 요약 유형·진단·수집 실패 설명이 독자 본문에 새지 않는다.
  요구 충족.
- 관리자 추적: `GET /information-bundle`(`preview_admin.py:1101`)으로
  `search_findings`·`section_deliveries`·출처를, `GET /section-results`,
  `GET /runs/{run_id}`(장부)로 전달·전송을 확인한다. 요구 충족.

### 4-a. 참고(현재 요구 위반 아님): 같은 섹션의 여러 버전이 독자 본문에 함께 실린다

`composition_section_blocks`는 정렬만 하고 섹션당 1개로 줄이지 않는다
(`section_preview.py:109-116`). 그래서 같은 실행에 `section_players` v1·v2가 있으면
블록이 2개 생기고 `body`가 두 본문을 이어 붙인다.

재현(순수 함수): v1·v2·forecast 3행 투입 → `blocks=3`,
`body = "v2 본문 / v1 본문 / 전망"`. 독자 화면에는 같은 섹션이 두 번 나온다.
저장된 구성본(선택 ID)이 있으면 그 집합을 1차 기준으로 쓰는 것이 자연스럽다
(§2-a 연결과 같은 수정으로 해결 가능). 이번 5항목의 “전체 표시” 요구를 깨지는 않으므로
참고로 분리한다.

### 4-b. 참고: 진단 응답의 `composition_inputs`가 프론트 타입에 없다

서버는 `composition_inputs`를 내보내지만(`section_preview.py:338`),
`ReaderPreviewDiagnostics` 타입에 그 키가 없다(`types.ts:802-834`, `selected_inputs`만
있음). 받아도 화면에서 읽지 않는다. 표시 요구의 핵심(본문·결론 전체 표시)은 4의
본문 경로로 충족되므로 차단하지 않는다.

---

## 5) 출력 40,000·모듈별 3회·장부 내구·3xx 홉 — **차단 0건, 참고 1건**

- 출력 상한: `max_output_tokens: 40000`(`bundle_sections.py:1034`)이
  `RequestSpec.parameters["generation_config"]`로 전달된다
  (`provider.py:1252-1255`). 실측 `build_generation_config()` 값 일치. 요구 충족.
- 모듈별 3회: `RunBudget.module_send_cap`/`prior_module_usage`/`sent_by_module`
  (`retry.py:251-255`)로 **논리 호출 단위** 상한을 건다(`can_attempt`, `:412-427`).
  `charge`가 `sent_by_module`을 올린다(`:471`). 재시작 후에도
  `RunBudget.restore`가 `sent_by_module`을 복원하고(`:304-307`), `prior_module_usage`도
  함께 보존한다. 순수 함수 확인: cap 3, prior 1, 이번 실행 2회 전송 후 `module_total=3`,
  복원 후에도 3, 4번째 전송은 거부(`승인된 실제 전송 상한(3회…)`). 요구 충족.
- 장부 내구: `journal_send`가 **전송 전 예약**과 응답 결과를 각각 독립 트랜잭션으로
  커밋하고(`send_ledger.py:129-268`), 실행 행이 미커밋이면 redacted 원문을 `detail`에
  담아 잃지 않는다(`:212-242`). 장부를 못 쓰면 전송을 시작하지 않는다(`:262-266`).
  `reconcile_budget_from_journal`이 재시작 시 **둘 중 큰 값**을 채택한다(`:313-345`).
  `unresolved_sends`는 결과 없는 예약을 성공/실패로 단정하지 않는다(`:348-376`).
  요구 충족.
- 3xx 홉: 두 클라이언트 모두 자동 추종을 끄고 매 홉을 게이트로 차단한다.
  stdlib는 3xx를 `HTTPError`로 올리는 경로까지 분기해 실제로 따라간다
  (`retrieval.py:305-335`), Scrapling도 동일(`:449-455`). `on_hop`이 전송 **직전**
  `charge_transport`로 차감하고(`:1257-1274`), 홉은 `attempts_per_call`과 분리돼 있다
  (`retry.py:493-500`). `redirect_loop`·`redirect_without_location`·
  `too_many_redirects`(5홉)를 구분한다. 요구 충족.

### 5-a. 참고(현재 5항목 위반 아님): 시험 run 집합이 스크립트에 고정돼 있다

`scripts/preview_bundle_live_once.py:182-185`는 `PRIOR_RUNS`를
`0d938572…`·`216d11ca…` 두 개로 **하드코딩**한다. 실제 증거 3개 실행의 모듈별 전송 합계는
`discovery_outlook 3 / discovery_people 3 / section_ai_forecast 3 / section_players 3 /
section_availability 1`이다. 즉 세 번째 실행(`270baa93…`)의 사용량이 `PRIOR_RUNS`에
없어, 그 스크립트를 다시 쓰면 이미 3회에 닿은 모듈의 이전 사용량을 세지 않는다.
계획 SF-03의 “이번 변경 시험의 run 집합을 명시” 요구는 실행 전에 `PRIOR_RUNS`를 이번
시험 집합으로 갱신하면 충족된다. 이번 5항목의 직접 변경 회귀는 아니므로 참고로 둔다.

---

## 요약

| 항목 | 판정 | 근거 |
|---|---|---|
| 1 조사 요약 → 작성 입력 | **차단 1** | 저장 묶음 `search_findings` 0 (`retrieval.py:1555`, `store.py:1549`) |
| 2 선택 ID → 구성본 → 마지막 AI | **차단 1** | `composition_upstream` 호출부 0, 화면 전송 0 |
| 3 마지막 AI 무검색·ready·본문 보존 | 통과 | `bundle_sections.py:1027`, `:2520`, `:1104` |
| 4 독자 투영·내부값 비노출 | 통과(참고 2) | `section_preview.py:175`, `types.ts:759` |
| 5 40k·3회·장부·3xx | 통과(참고 1) | `bundle_sections.py:1034`, `retry.py:412`, `send_ledger.py:129`, `retrieval.py:305` |

차단 2건은 모두 “실제 전달 입력”이 비는 문제이며, 각각 **한 줄·한 연결**로 고칠 수 있다.
그 밖의 항목은 이미 요구를 충족한다. 참고 4건(1-b 문서 버전 표기, 3 최종 게이트 검색
미포함, 4-a 버전 중복, 5-a run 집합)은 현재 수용 기준의 직접 위반이 아니므로 후속
후보로 분리한다.

## 재현 근거 요약(모두 부작용 없음)

1. `search_findings` 접힘: §1-b의 6줄 재현(생성자 0 / `bundle_from_collection` 0 /
   인자 주면 1 / `_search_material` 0 → 1).
2. `composition_upstream` 미사용: `grep -rn composition_upstream` → 정의 1 + 문서 1.
3. 독자 버전 중복: `composition_section_blocks`에 v1·v2·forecast 투입 → blocks 3,
   `body`에 두 선수 본문 연결.
4. 모듈별 3회 내구: `RunBudget` cap 3·prior 1·2회 전송 → 복원 후 `module_total=3`,
   4번째 거부.
5. 출력 상한 전달: `build_generation_config()` 실측 dict, `RequestSpec` `parameters.
   generation_config` 경로 확인.
6. 기존 저장 자료: `evidence/ps05-live/live-*.json` 3개에서 `search_findings` 0건,
   실행별 attempts 모듈 분포.

---

# 수정 확인 (SF-02 재확인 1회) — 2026-11-11 KST

구현자 `ctx_76f3426824fa`의 최종 편집 종료 보고 후 **한 번만** 확인했다. 전면 재검토는 하지
않았고, 위 문서의 차단 2건 + 직접 연결된 참고 3건만 봤다. 읽기 전용이며 편집·실행 확대는 없다.
이번에도 `pytest`/`vitest`·새 재현 파일·모델·외부 HTTP·DB 쓰기·서버·커밋은 **0회**다.
재현은 기존 pure function·기존 저장 자료 읽기뿐이다(모델 호출 없음).

## 이번 확인 대상 해시

| 파일 | sha256 (앞 16자) | 줄 |
|---|---|---|
| `app/preview/retrieval.py` | `146e98d599eddabc` | 1812 |
| `app/preview/bundle_pipeline.py` | `0f9e1e31d3855e83` | 2178 |
| `app/preview/section_preview.py` | `c57f46eac71d5353` | 462 |
| `app/api/v1/preview_admin.py` | `97f3840d1f10c990` | 1893 |
| `app/preview/information_bundle.py` | `43f33e39c6aadc89` | 1955 |
| `app/preview/modules/bundle_sections.py` | `387534129304f577` | 2690 |
| `scripts/preview_bundle_live_once.py` | `ec87fd7911d871be` | 423 |
| `frontend/.../CompositionPanel.vue` | `e20dd24449dc3a7f` | 348 |
| `frontend/.../SectionRunView.vue` | `033e76cd6fb4f9c5` | 652 |
| `frontend/.../types.ts` | `4f49c5ced709fdce` | 847 |

## 각 변경 확인

### (1) `search_findings` 접힘 — **해결**

`retrieval.py:1567`이 `search_findings=search_findings_from_groups(tuple(discovery_groups))`로
묶음 최상위에 접는다. 재현(순수 함수): 조사 요약 1건 → `collect_with_bodies(...).bundle.
search_findings = 1`, `deliverable_search_findings = 1`, `_search_material` 행
(`section_players`/`section_availability`/`section_ai_forecast` = 1,
`section_outlook`은 그룹 범위 밖이라 0 — 정상).
저장 경로 왕복도 확인했다: `store.save_information_bundle_with_bodies`가 쓰는
`bundle_from_collection(collection, db_snapshot)` 호출을 그대로 재현해 1차 저장 1건,
2차 재저장 1건, `to_dict`/`from_dict` 왕복 1건. 이전 차단(생성자 0 / 재구성 0)은 사라졌다.
`SearchFinding.deliverable`이 저장 전 계산값이므로 `deliverable` 키 없는 조사 산출도 전달된다.

### (2) 최종 전망 게이트 — **해결**

`bundle_pipeline.py:1091-1092`가 `has_search = bool(bundle.deliverable_search_findings)`를
조건에 포함한다. 재현: 본문 0·DB 0·upstream 0, 요약만 있는 묶음에서 게이트가 **건너뛰지
않는다**(`skip=False`). 비전달 유형(`model_note`)만 있을 때는 여전히 건너뛴다(정상).

### (3) 구성본 → 마지막 AI — **해결(백엔드)**

`run_section_regeneration`이 `store.load_composition(session, base_run_id)`(`:2034`)로 저장
구성본을 읽고, `composition_id`가 저장 값과 다르면 `SectionRegenerationRefused`(`:2038-2041`),
구성본이 없는데 `composition_id`를 주면 거부(`:2043-2047`)한다. 통과 시
`composition_upstream(session, {"items": ...})`(`:2069`)로 `upstream`을 만든다.
API는 `composition_id`를 그대로 넘기고(`preview_admin.py:792`), 거부는 422로 매핑된다
(`:794-798`). `selected_result_ids`보다 구성본이 우선이고(`:2049`), 없을 때만 기존 경로다
(`:2076`). 화면도 생겼다: `CompositionPanel.vue`가 라디오로 섹션당 1개를 고르고(기본 최신,
`seedSelection`), `saveComposition`(`:125`) → `regenerateSection({workflow_id:'section_ai_forecast',
source_mode:'reuse', base_run_id, composition_id})`(`:161-166`) 순으로 보낸다.
`SectionRunView.vue:465`에 마운트된다.

### (4) 독자 중복 제거 — **해결**

`section_preview._select_rows`(`:132`)가 섹션당 1행만 고른다. 재현: v1·v2 동시 저장 +
구성본 없음 → v2 하나만(이전 3블록 → 현재 2블록), 구성본이 v1을 고르면 v1 하나만.
`build_bundle_reader_view`(`:240-250`)가 이 실행의 저장 구성본을 읽어 선택을 우선하고,
없을 때만 최신 1개로 폴백한다. 독자 본문 중복은 사라졌다.

### (5) 시험 집합별 모듈 3회 — **해결(전체 실행 경로)**

`bundle_pipeline.py:80-100`에 `TRIAL_TAG_PREFIX`/`trial_tag`/`trial_set_of`가 있고,
`run_bundle_pipeline(trial_set_id=...)`(`:1425`)이 실행 label에 태그를 붙인다(`:1456`,
`_with_trial_tag`는 멱등). `scripts/preview_bundle_live_once.py:188`이
`PREVIEW_TRIAL_SET_ID`(기본 `sf-b4-search-fallback`)로 집합을 정하고, `:208-215`가 label
태그로 그 집합의 실행만 찾아 `:223-244`에서 장부(`send_charged`, `counted` + `MODEL`)를
모아 모듈별 선행 사용량을 센다. 옛 3개 run은 지우지 않고 집합 근거에서만 빠진다(`SEED_RUN_IDS`
빈 값, 주석 `:184-185`). 순수 함수 확인: `trial_tag`/`trial_set_of` 왕복 일치, 태그 없음 →
`None`, 타 집합 구분, 이중 부착 없음.

## 새로 확인된 현재 요구 직접 회귀 (차단 1건)

### A. 재생성·마지막 AI 실행 경로가 시험 집합 3회 상한 밖에서 전송한다 — **차단**

`run_section_regeneration`은 `budget = RunBudget.for_run(budget_limits, now=moment)`
(`bundle_pipeline.py:1949`)만 만들고 `module_send_cap`·`prior_module_usage`를 **설정하지
않는다**(소스 검사: 두 이름 모두 부재). `RunBudget.can_attempt`(`retry.py`)는
`if self.module_send_cap is not None:`일 때만 상한을 걸므로, 이 경로는 모듈별 3회를
적용받지 않는다. 전체 실행(`run_bundle_pipeline`)만 상한을 받는다(`:1463-1464`).

이번 변경으로 `CompositionPanel` 버튼이 **정상 UI 경로에서** 이 재생성을 호출하게 됐으므로,
이것은 “모듈별 실제 전송 상한 3회를 전송 전에 적용”이라는 이번 계약의 **직접 회귀**다.
사용자가 마지막 AI 실행을 반복하면 `section_ai_forecast`가 3회를 넘겨도 막히지 않는다.
(전체 실행 경로의 상한 자체는 정상임을 §5에서 이미 확인했다.)

최소 수정: `run_section_regeneration`에서 `RunBudget.for_run` 직후
`budget.module_send_cap = <승인 상한>`과 `budget.prior_module_usage = <시험 집합 장부 집계>`를
설정한다(전체 실행과 같은 값·같은 장부 출처). 재생성 실행도 `trial_set_of(base_run_id
label)`로 태그를 물려받으므로(`:1941-1944`) 장부 집계는 이미 가능하다.

## 참고(차단 아님, 이번 요구의 직접 위반 아님)

- **B. 구성본+결론을 한 화면에서 보는 경로가 없다.** 재생성은 **새 실행**에 전망 1건만
  저장하고(`:2124-2131`, `save_composition` 호출 없음), 독자 투영은 **그 실행의** 구성본만
  읽는다(`section_preview.py:240`). 재현: 새 실행 행 1건(전망) 투입 → 블록 1개, 구성본 없음.
  기준 실행 투입 → 선택 항목 + **옛** 전망. 즉 “선택 구성본 + 새 최종 결론 전체 표시”는
  화면·API 어느 한 경로에서도 동시에 만족되지 않는다. 이번 5항목의 직접 회귀는 아니며
  (구성본 표시 자체는 (4)로 동작), 표시 요구를 닫으려면 재생성 실행에도 구성본(또는
  부모 실행 링크)을 남기고 투영이 그것을 읽어야 한다.
- **C. 600자 초과 요약이 저장 단계에서 실행 전체를 중단시킨다.** `(1)`로 요약이 묶음에
  실제로 들어오면서, `validate_information_bundle`의 기존 상한
  `MAX_SEARCH_FINDING_CHARS=600`(`information_bundle.py:178`, 검사 `:1469`)이
  `save_information_bundle`(`store.py:1403`)에서 `BundleBuildError`를 낸다. 재현: 요약
  600자 → 저장 통과, 601자·900자 → `BundleBuildError`. 수집 노드는 이 예외를
  `bundle=None`으로 삼키고 진행하므로(`bundle_pipeline.py:912-920`) **모든 섹션이
  “묶음 없음”으로 비게 된다.** 조사 프롬프트는 “1~3문장”만 권하고 길이 상한을 지시하지
  않으며, 파싱·저장 어디에도 절단이 없다(`parse_research_summary`·`SearchFinding.from_dict`
  모두 무절단). 요약이 여러 개면 각각 600자까지는 통과하므로 항상 실패하지는 않는다.
  이번 요구(“메타데이터 없어도 AI 요약 사용”)의 직접 회귀는 아니고, 600자 상한은 기존
  계약이다. 다만 (1)로 처음 실제 도달 가능해진 경로이므로, 저장 시 절단+진단 기록 또는
  상한 상향 중 하나를 후속으로 정하는 편이 좋다.

## 수정 확인 판정

| 확인 항목 | 판정 | 근거 |
|---|---|---|
| (1) 요약 → 묶음 → 작성 입력 | 해결 | `retrieval.py:1567`, 저장 왕복 1건 |
| (2) 전망 게이트 검색 포함 | 해결 | `bundle_pipeline.py:1091` |
| (3) 구성본 → 마지막 AI + 422 + 화면 | 해결 | `:2034-2071`, `CompositionPanel.vue:125,161` |
| (4) 독자 중복 제거·선택 우선 | 해결 | `section_preview.py:132,240` |
| (5) 시험 집합 3회 | 전체 실행 해결 / **재생성 미적용** | `:80-100`, `:1456`; 재생성은 `:1949` |
| A 재생성 상한 누락 | **차단 1** | `:1949` + `retry.can_attempt` |
| B 구성본+결론 동시 표시 | 참고 | `:2124`, `section_preview.py:240` |
| C 600자 초과 요약 저장 중단 | 참고 | `information_bundle.py:1469`, `store.py:1403` |

차단 3건 중 2건(§1-b, §2-a)과 참고 2건(§3 게이트, §4-a 중복)은 실제로 닫혔다.
새 차단 A는 이번 변경이 연 정상 UI 경로에서 기존 상한을 우회하므로 직접 회귀다.
B·C는 현재 수용 기준을 깨지 않으므로 후속 후보로 분리한다.

## 미검증으로 남긴 것(정직 표기)

- **실제 생성·실제 저장·UI 로그인은 검증하지 않았다.** 이번 확인은 정적 코드·순수 함수·기존
  저장 자료로 한정했고, 모델·DB·브라우저를 쓰지 않았다. 위 판정은 “코드가 그 요구를
  만족하는 구조인가”에 대한 확인이며, 실제 유료 실행의 성공이나 사용자 승인을 뜻하지 않는다.
- 새 유료 실행은 이 수용 뒤 root가 지시한다. 그래서 `CompositionPanel` 클릭→실 모델 전송,
  화면 로그인, 실제 `search_findings`가 DB에 저장된 결과는 **아직 관측 전**이다.
- 이 미검증을 이유로 무관한 검사(전체 회귀·브라우저·다른 경로)를 추가하지 않았다.

---

# 델타 확인 (bundle5/sections6) — 2026-11-11 KST

root 메일(`msg_68f84b4694ff`)의 지시대로 **원 지적 2건 + 연결 참고 3건 + 새 델타**만 확인했다.
새 버전이라는 이유로 전면 검토를 다시 시작하지 않았고, 새 계약이 원 수정의 직접 회귀를 만든
경우만 차단으로 적는다. 읽기 전용이며 `pytest`/`vitest`·새 재현 파일·모델·HTTP·DB 쓰기·
서버·커밋은 이번에도 **0회**다. 순수 함수·기존 저장 자료만 썼다.

## 이번 확인 대상 해시

| 파일 | sha256 (앞 16자) | 줄 |
|---|---|---|
| `app/preview/information_bundle.py` | `a995aeaf16ffc066` | 1970 |
| `app/preview/modules/bundle_sections.py` | `935f0ef5c5614b82` | 2701 |
| `app/preview/bundle_pipeline.py` | `1a3001ef1be795c0` | 2329 |
| `app/preview/section_preview.py` | `d7acaecbebd2141c` | 525 |
| `app/preview/retrieval.py` | `146e98d599eddabc` | 1812 |
| `app/preview/discovery.py` | `35845d34c7f5455d` | 950 |
| `app/api/v1/preview_admin.py` | `97f3840d1f10c990` | 1893 |
| `scripts/preview_bundle_live_once.py` | `ec87fd7911d871be` | 423 |
| `frontend/.../CompositionPanel.vue` | `e20dd24449dc3a7f` | 348 |

버전: `mp11-information-bundle-5`, `mp11-bundle-sections-6`, `mp11-bundle-pipeline-3` —
보고된 값과 일치한다. 조사 프롬프트는 `discovery_people/v2`·`discovery_outlook/v2` 그대로다.

## 원 지적 항목 재확인 (전부 유지)

- **차단 1(요약 접힘)**: `retrieval.py:1567` 그대로. 재현: 요약 1건 →
  `bundle.search_findings=1`, `deliverable=1`, 작성기 `_search_material` 행 1.
- **전망 게이트**: `bundle_pipeline.py:1091-1092` 그대로(`has_search` 포함). 요약만 있어도
  건너뛰지 않는다.
- **차단 2(구성본→마지막 AI)**: 저장 구성본 로드·`composition_upstream`·`composition_id`
  422 거부가 유지된다.
- **참고 4-a(독자 중복)**: `section_preview._select_rows` 유지. 재현: v1·v2 → v2 하나,
  선택 a1 → a1 하나.
- **작성기 계약**: `build_generation_config()` = `{'temperature':0.2,
  'max_output_tokens':40000,'response_mime_type':'application/json'}`, `tools` 키 없음.
  버전만 `mp11-bundle-sections-6`으로 올라갔고 계약 값은 그대로다.

## 이전 차단 A(재생성 상한 누락) — **해결**

`bundle_pipeline.py:2015-2019`가 재생성에도 `budget.module_send_cap = MODULE_SEND_CAP`(3,
`:1588`)과 `budget.prior_module_usage = dict(prior_usage)`를 건다. 선행 사용량은
`trial_module_usage`(`:1591`)가 이번 시험 집합 label 태그 실행의 `send_charged` 장부에서
다시 센다. 재현(순수): cap 3·prior 3 → `section_ai_forecast` 전송 거부, prior 2 → 허용.
계수 초기화 없이 같은 상한이 걸린다.

## 이전 참고 C(600자 초과 요약이 실행 중단) — **해결**

길이가 더 이상 저장 거부 사유가 아니다(`information_bundle.py:1486-1488` 주석,
검사 블록에서 길이 항목 제거). 원문은 묶음·아티팩트에 그대로 보존하고, 작성 입력에 넣을
때만 `excerpt_for_delivery`(`:1316`)로 자른다(`bundle_sections.py:557-567`은 잘린 사실을
진단에 남긴다). 재현: 900자 요약 → `ensure_valid_bundle` 통과, `excerpt_for_delivery`
→ 600자·`cut=True`, 600자 이하는 그대로.

## 이전 참고 B(구성본+새 결론 동시 표시) — **해결**

재생성이 새 실행에 구성본을 복사해 기록한다(`bundle_pipeline.py:2263-2290`,
`copied_from_composition_id`로 부모 구성본을 남긴다). 그래서 새 실행의 독자 투영이
선택 항목 + 이 실행의 새 결론을 함께 읽는다.

## 델타 신규 항목 확인

- **자료 우선순위**: 네 작성 프롬프트 모두 `### 자료 우선순위 (위에서부터)` 블록을 갖고
  “수집 본문 → 검색 자료 → DB” 순서와 “아래 계층을 근거 없이 버리지 않는다” 취지를 적는다
  (`bundle_players/availability/outlook/forecast.md` 각 1건). 요구와 일치.
- **URL 출처 구분**: `SearchFinding.url_provenance`(`information_bundle.py:586`)와 표기
  `SEARCH_URL_PROVENANCE_LABELS`(`:170`)가 있고, 작성 프롬프트 렌더가 도구 반환 주소가
  아닌 경우에만 라벨을 덧붙인다(`bundle_sections.py:628-634`). **요약을 버리는 게이트가
  아니라 표시 구분**이다 — 요구대로 차단 조건을 만들지 않았다.
- 참고(차단 아님): `_provenance`(`discovery.py:873-887`)는 첫 인용 주소의 **호스트**가
  `grounding_chunks` 도메인과 일치하는지만 본다. 그래서 라벨 `검색 도구가 반환한 주소`는
  “정확한 URL이 도구 반환값과 동일”을 증명하지 않는다. root 지시대로 이번에 고치지 않고
  후속 후보로만 남긴다(요약 채택을 막지 않음).

## 델타가 만든 새 직접 회귀 — **차단 1건**

### A′. 재생성이 부모 실행의 `trial-set:` 표기를 **필수**로 요구해, 관리자 UI로 만든 실행은
### 마지막 AI 재실행이 422로 막힌다

`run_section_regeneration`은 상한 계산 전에 부모 label의 태그를 읽고, **없으면 거부**한다:

```
bundle_pipeline.py:1977  regeneration_trial = trial_set_of(base_detail.summary.label)
bundle_pipeline.py:1978  if regeneration_trial is None:
bundle_pipeline.py:1979      raise SectionRegenerationRefused("부모 실행에 시험 집합 표기(trial-set:)가 없어 ...")
```

그런데 태그를 붙이는 곳은 `run_bundle_pipeline(trial_set_id=...)`(`:1425`, `:1456`) 하나뿐이고,
`trial_set_id`를 넘기는 호출자는 `scripts/preview_bundle_live_once.py:285` **한 곳**이다.
API는 이 값을 전혀 넘기지 않는다(`grep -c trial_set_id app/api/v1/preview_admin.py` → **0**,
`SectionRunRequest`에도 필드 없음). 그래서 `POST /bundle-runs`·`POST /section-runs`로 만든
실행의 label은 `정보 원문 프리뷰 · live` 같은 기본값이고 `trial_set_of(...)`가 `None`이다.

재현(순수): `trial_set_of("정보 원문 프리뷰 · live")` → `None`,
`trial_set_of("섹션 재생성 · … · trial-set:sf-b4-search-fallback")` → `sf-b4-search-fallback`.
즉 태그가 있는 실행(스크립트 실행 또는 그 자식)만 재생성할 수 있고, **화면에서 정상적으로
만든 실행은 구성본 패널의 “마지막 AI 실행”이 422로 거부된다.**

이번 변경이 `CompositionPanel`을 관리자 화면에 연결했으므로, 그 패널이 실제로 쓰는 실행이
막히는 것은 **이번 변경이 만든 직접 회귀**다. 상한을 지키려는 의도는 옳지만, 태그가 없는
실행을 **거부**하는 대신 상한 계산만 불가로 표시하고 진행하거나, 실행 생성 시 태그를
기본으로 붙이는 쪽이 요구(“모듈별 3회를 전송 전에 적용”)에 맞다.

최소 수정(둘 중 하나, 한 곳):
1. API가 실행 생성 시 `trial_set_id`를 받거나 기본 집합 표기를 붙인다
   (`preview_admin.py:1679`의 `run_bundle_pipeline` 호출, `SectionRunRequest`에 필드 추가).
2. 또는 `:1978`의 거부를 “상한 없이 보내지 않는다”가 아니라 “이 실행은 시험 집합 밖이므로
   모듈별 상한을 적용할 수 없다”는 **진단으로 남기고 진행**한다(전체 실행 상한 8회는 그대로).

## 판정

| 확인 항목 | 판정 | 근거 |
|---|---|---|
| 차단1 요약 접힘 | 유지·해결 | `retrieval.py:1567`, 재현 1행 |
| 전망 게이트 | 유지·해결 | `bundle_pipeline.py:1091` |
| 차단2 구성본→최종 AI | 유지·해결 | `:2034-2071`, 422 |
| 참고4-a 독자 중복 | 유지·해결 | `section_preview._select_rows` |
| 이전 A 재생성 상한 | **해결** | `:2015-2019`, `trial_module_usage` |
| 이전 B 구성본+결론 | **해결** | `:2263-2290` |
| 이전 C 600자 중단 | **해결** | `:1316`, `:1486-1488` |
| 델타 자료 우선순위 | 통과 | 네 프롬프트 `자료 우선순위` 블록 |
| 델타 URL 출처 구분 | 통과(표시만) | `:586`, `:170`, `bundle_sections.py:628` |
| **A′ 태그 없는 실행 재생성 422** | **차단 1** | `:1977-1982`, API `trial_set_id` 0곳 |
| 참고 URL provenance 호스트 기준 | 참고 | `discovery.py:873-887` |

## 미검증으로 남긴 것(정직 표기)

- **실제 생성·실제 저장·UI 로그인은 이번에도 검증하지 않았다.** 코드 구조·순수 함수·기존
  저장 자료로만 확인했고 모델·DB·브라우저를 쓰지 않았다. 위 판정은 “요구를 만족하는
  구조인가”이며 실제 유료 실행 성공이나 사용자 승인이 아니다.
- 새 시험 집합(`trial-set:sf-b4-search-fallback`)의 실제 전송은 **아직 0회**이고, 그 집합으로
  한 번 실행해 실제 요약이 생성되는지는 root 지시 후 확인할 일이다.
- A′ 때문에 화면에서 만든 실행으로는 그 실행 자체를 검증할 수 없다. 이 미검증을 이유로
  무관한 검사(전체 회귀·브라우저·다른 경로)를 추가하지 않았다.
