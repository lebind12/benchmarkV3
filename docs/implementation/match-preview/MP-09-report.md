# MP-09 S1 종합·독자용 프리뷰 보고

작성: 2026-11-11 KST. 작성자: DeepSeek 구현 워커(`deepseek-ai/deepseek-v4.1-flash-1017`, hive/dsh-tui, 추론 강도 사용자 설정 유지).
상태: **코드 구현 + 기록 입력 검증 완료. 실제 live S1 호출·사용자 승인·전체 파이프라인(MP-10)은 미완료.**

이 보고는 MP-09 범위만 다룬다. 사용자 승인, live S1 성공, 전체 프리뷰 완성, 공개 홈 연결은 이 보고로 완료되지 않는다.

## 0. 한 줄 요약

선택된 R1/R2/R3 저장 결과 버전과 그 결과가 참조하는 D0 스냅샷만으로 **정상 1회** S1 모델 요청을 보내고, 검증을 통과한 판단만 **독자용 프리뷰**(본문·근거·AI 예측 표시)로 투영해 관리자 경로에서 열 수 있게 했다. 진단은 별도 경로로 분리했다. 이번 검증은 기록된 구조화 입력 + `RecordedTransport`이며 외부 유료 호출은 0회다.

## 1. 인터페이스 요약 (다른 작업이 붙을 지점)

### 백엔드 계약 (기존 계약을 그대로 씀, 새 범용 프레임워크 없음)

| 함수·경로 | 입력 → 출력 | 비고 |
|---|---|---|
| `validation.validate_evidence(fixture, results, snapshots, module_ids, selected_result_ids)` | 선택 결과 + 참조 스냅샷 → `ValidatedEvidence` | 외부 호출 0 |
| `modules.synthesis.synthesize_preview(evidence, context, transport, budget, ...)` | 검증 결과 → `S1Result`(ModuleResult + PreviewDocument + 독자 payload) | 모델 요청 정상 1회 |
| `presentation.to_preview_document(...)` | 허용된 독자 필드 → `PreviewDocument`(기존 계약) | 지어낸 값 없음 |
| `presentation.reader_payload(reader, generated_at, data_as_of)` | → 독자용 dict(허용 목록) | 진단·ID 없음 |
| `GET /api/v1/admin/preview/runs/{run_id}/preview` | → 독자용 투영만 | **ADMIN 전용**, 401/403 |
| `GET /api/v1/admin/preview/runs/{run_id}/preview/diagnostics` | → 공백 사유·제외 주장·선택 입력 버전 | 관리자 전용, 독자와 **다른 경로** |
| `POST /api/v1/admin/preview/section-runs` | `workflow_id=section_synthesis`, `selected_result_ids[]` | 서버가 결과를 임의로 고르지 않음 |

기존 `SectionResult`/`run_section_workflow`/`ModuleResult` 계약을 사용한다. 공유 파일 수정은
`runner.run_section_workflow(selected_result_ids=…)` 1개 인자 추가, `registry`의 S1·`section_synthesis`
등록 상태, `version_manifest`의 S1 준비/조립 버전 연결, `sections.build_implementations`의 분기,
`preview_admin`의 라우트 2개와 요청 필드 1개다.

### 프론트엔드

- `MatchPreview.vue`: 독자용 화면. 없는 보조 항목은 **카드 자체를 만들지 않는다**.
- `GroundingSources.vue`: 검색 URL과 API 저장 자료를 다른 종류로 표시.
- `MatchPreviewRoute.vue` + 라우트 `/admin/preview/:runId`(관리자 경로, 공개 홈 아님).
- `SectionRunView.vue`: 종합 섹션 결과에서 "독자용 프리뷰 열기" 버튼.
- 진단은 화면의 접힌 영역에서 **별도 API**로 열고, 처음 DOM에는 넣지 않는다.

## 2. 실제 파일

신규:

- `app/preview/validation.py` — V0 검증(경기 일치·사실 참조·선택 ID 대조)
- `app/preview/modules/synthesis.py` — S1 실행·출력 검증·저장 payload·노드 어댑터
- `app/preview/presentation.py` — 독자용 투영(허용 목록)·본문 조립·내부 값 정리
- `app/preview/section_preview.py` — 저장 결과 → 독자용/진단 조회 어댑터
- `app/preview/prompts/synthesis.md` — S1 프롬프트(검색 도구 없음)
- `tests/preview/test_synthesis.py`, `test_presentation.py`, `fixtures/synthesis_inputs.json`
- `frontend/src/features/match-preview/MatchPreview.vue`, `GroundingSources.vue`,
  `MatchPreviewRoute.vue`, `MatchPreview.test.ts`
- `docs/implementation/match-preview/evidence/mp09/reader-preview.json`

수정(최소 공유 지점):

- `app/preview/runner.py` — `selected_result_ids` 전달
- `app/preview/registry.py` — S1 `implemented=True`, `section_synthesis` 구현 상태
- `app/preview/version_manifest.py` — S1 준비/조립 구현 버전(실제 상수)
- `app/preview/modules/__init__.py` — S1 `mp09-s1-1` / `mp09-s1-prompt-1`
- `app/preview/sections.py` — `section_synthesis` 팩토리 분기
- `app/api/v1/preview_admin.py` — 라우트 2개, `selected_result_ids` 필드
- `frontend/src/features/match-preview/{types.ts,api.ts,SectionRunView.vue}`, `src/router/index.ts`
- 기존 검사 3개 파일: S1 미구현 전제를 실제 상태로 갱신(`test_inspection_api`, `test_form_module`,
  `test_section_approvals`)

버전 축(실제 후보 값, 빈 자리표시자 아님):

```
section_synthesis@05712cb1f5effca1
  D0          prompt=""                 impl="mp09-selected-inputs-1"
  R1          prompt="mp05-form-prompt-2" impl="mp05-form-2"
  R2          prompt="mp06-r2-prompt-2"   impl="mp06-r2-2"
  R3          prompt="r3-outlook-1"       impl="mp07-r3-1"
  S1          prompt="mp09-s1-prompt-1"   impl="mp09-s1-1"
  compose_body prompt=""                  impl="mp09-compose-1"
```

## 3. 사용자 기준 반영 (사실 vs AI 판단)

| 기준 | 구현 위치 | 검사 |
|---|---|---|
| API/검색으로 확인한 사실에만 근거 참조 요구 | `validation._resolves`, `_claim_reason` | `test_fact_citation_must_exist` |
| 주목 선수 선정·관전 포인트·예상 스코어는 판단(외부 증명 불요) | `validate_synthesis` 판단 분기 | `test_ai_score_judgment_allowed_without_outcome_proof`, `test_hot_player_selection_needs_no_external_pick_source` |
| 'AI 해석'으로 새 수치·부상 사건 통과 금지 | `_unsupported_pieces` → `_drop_sentences` | `test_new_stat_in_judgment_is_dropped` |
| 매체 예상은 그 매체가 실제로 말했다는 URL 필요 | `_validated_outlook` | `test_media_forecast_requires_actual_media_proof` |
| 제공자 알고리즘 예측은 출처 종류 유지 | `source_kind=api_prediction` + `source_note` | `test_api_prediction_keeps_algorithmic_source_kind` |
| API-only 사실·검색0·배당 미제공·부상 발생일 미확인도 프리뷰 가능 | `core_evidence_satisfied` = 경기 + 참조 있는 사실 | `test_api_only_facts_still_produce_a_brief` |
| 날짜·선수·부상 맥락·배당을 지어내지 않음 | 프롬프트 지시 + 문장 필터 + `None` 처리 | 위 검사들 |
| 지원 안 하는 보조 항목은 생략(빈 카드 금지) | `presentation.reader_payload` 키 생략 | `test_missing_optional_section_is_omitted`, `test_missing_optional_section_makes_no_empty_card` |
| 진단은 관리자만 | 라우트 2개 분리, 허용 목록 투영 | `test_diagnostics_absent_from_preview_payload`, API 경계 검사 |
| AI 예측 표시·기준 시각·출처 유지 | `attribution`·`data_as_of`·`sources` | `test_ai_forecast_attribution_and_source_times_are_kept` |
| 내부 ID·토큰 미노출 | `_strip_internal`, `_reader_sources` 라벨 매핑 | `test_reader_sources_hide_internal_provider_identifiers`, `test_real_provider_names_survive_cleanup` |

## 4. 검증 명령과 결과 (이번에 실제로 실행)

```sh
# backend (기록 입력, 외부 호출 0)
.venv/bin/python -m pytest tests/preview/test_synthesis.py -q                       # 22 passed
.venv/bin/python -m pytest tests/preview/test_presentation.py -q                    # 13 passed
.venv/bin/python -m pytest tests/preview/test_synthesis.py tests/preview/test_presentation.py \
    tests/preview/test_inspection_api.py tests/preview/test_form_module.py \
    tests/preview/test_availability_module.py tests/preview/test_section_approvals.py \
    tests/preview/test_workflow_version.py tests/preview/test_module_runner.py \
    tests/preview/test_run_store.py tests/preview/test_retry_budget.py \
    tests/preview/test_provider.py -q                                               # 155 passed

# frontend
npm --prefix frontend run test:unit -- src/features/match-preview/MatchPreview.test.ts \
    src/features/match-preview/SectionRunView.test.ts                               # 10 passed
npm --prefix frontend run type-check                                                # 통과 (출력 없음)
npm --prefix frontend run build                                                     # 통과
node .agents/skills/hallmark/scripts/sloplint.mjs \
  frontend/src/features/match-preview/MatchPreview.vue \
  frontend/src/features/match-preview/GroundingSources.vue \
  frontend/src/features/match-preview/MatchPreviewRoute.vue \
  --genre modern-minimal --scope app                                                # clean 0 FAIL / 0 REFLEX / 0 WARN
```

계획 §6 MP-09 대표 검사 매핑:

| 계획 검사 | 실제 검사 |
|---|---|
| `test_synthesis_has_no_search_call` | `test_synthesis_has_no_search_call` (요청 `generation_config`에 `tools` 없음, 논리 호출 1회) |
| `test_selected_result_versions_match_input` | `test_selected_result_versions_match_input` + `test_selected_result_ids_mismatch_is_diagnosed_not_filled` + 모듈 입력 `selected_result_ids` 확인 |
| `test_added_module_claims_reach_synthesis` | `test_added_module_claims_reach_synthesis`(R9 추가 → 같은 계약으로 입력 진입) |
| `test_fact_citation_must_exist` | `test_fact_citation_must_exist` |
| `test_missing_optional_section_is_omitted` | `test_missing_optional_section_is_omitted`, `test_missing_optional_section_makes_no_empty_card` |
| `test_diagnostics_absent_from_preview_payload` | `test_diagnostics_absent_from_preview_payload`, `test_preview_endpoint_returns_reader_projection_only` |
| `test_insufficient_core_not_ready` | `test_insufficient_core_not_ready`, `test_empty_selection_is_not_ready_and_makes_no_call`, `test_invalid_fixture_is_rejected_before_the_call`, `test_section_run_without_selected_results_is_not_ready` |

증거 파일: `docs/implementation/match-preview/evidence/mp09/reader-preview.json`
(`mode=mock`, `external_calls=0`, `tools=[]`, 선택 결과 ID 3건, 독자용 키 목록, 진단 키 목록).

## 5. 독자용 예시 (기록 입력으로 만든 실제 투영)

```text
리그 3위 Manchester City가 홈에서 하위권 Fulham을 상대합니다.

관전 포인트. Manchester City가 홈에서 볼 점유를 오래 가져가는 흐름을 볼 만합니다.

주목할 선수는 이렇습니다. Erling Haaland(Manchester City)는 상대 수비가 내려서는 경기에서
먼저 지켜볼 선수입니다.

Manchester City는 왼쪽 수비 자원이 줄어 측면 대응이 달라질 수 있습니다.

외부 전망입니다. BBC Sport(2026-11-09): Manchester City가 홈에서 우세할 것으로 전망했습니다.
API-Football: 알고리즘은 홈팀 우세로 계산했습니다.

AI 예측은 홈팀 우세, 예상 스코어 2-1입니다. 상대가 하위권이고 홈 이점이 있어 홈팀 우세로 봅니다.
예상은 결과를 보장하지 않습니다.
```

독자용 응답 키(허용 목록): `fixture, headline, body, generated_at, data_as_of, attribution,
watch_points, players_to_watch, absences_impact, external_outlook, ai_prediction, sources`.
`diagnostics, coverage, gaps, selected_result_ids, snapshot_ids, attempt, workflow_version, run_id`는 없다.

## 6. 구현 중 실제로 발견해 고친 결함

1. **예산 시계 불일치** — 고정 시각을 넘겨 테스트하면 첫 시도가 기한 초과로 거부됐다(`RuntimeError:
   recorded no attempt`). `request_model(now=…)`로 예산 판정과 시도 기록 시각을 같은 시계로 맞췄다.
2. **중첩 payload 미해제** — 저장 행은 `ModuleResult.to_dict()`라 실제 payload가 한 겹 안에 있다.
   어댑터가 두 모양을 모두 읽도록 고쳤다. 이 때문에 매체 전망과 coverage가 초기에 비어 보였다.
3. **실제 출처 이름 오삭제** — 내부 ID 정리 규칙(대소문자 무시)이 `API-Football`을 `api-…`로 오인해
   지웠다. 규칙을 소문자 claim ID로 한정하고 회귀 검사를 추가했다.
4. **내부 제공자 식별자 노출** — `vertex-google-search`가 독자용 근거 라벨로 나갔다. 사람이 읽는
   이름으로 매핑하고, 검색 스냅샷 중복 행을 만들지 않게 했다.
5. **경기 이름 유실** — 결과 payload에 팀 이름이 없으면 `경기 1557474`로만 표시됐다. 저장된 실행
   라벨을 표시용 대체로 쓰고(지어내지 않음), 없으면 경기 ID만 남긴다.

## 7. 현재 gap과 다음 사람이 할 일

- **live S1 호출 0회.** 이번 작업의 외부 호출 상한(0)에 따라 실제 모델 호출은 하지 않았다. 실제
  선택 입력으로 한정 통합 호출은 조정자가 별도 배정해야 한다. 그때까지 S1 실생성·내용 품질은 미검증이다.
- **서버 재시작 필요.** 실행 중인 `127.0.0.1:8000` 백엔드는 새 라우트를 싣지 않았다
  (`/openapi.json`에 `preview/diagnostics` 없음, 무인증 요청 404). 기존 `sh scripts/run_preview_dev.sh`로
  **백엔드 1회 재시작**이 필요하다. 내가 임의로 재시작/kill하지 않았다.
- **사용자 승인 없음.** `section_synthesis`는 `implemented=True`일 뿐 승인 상태는 `none`이다. 승인 행을
  만들지 않았다. 모의 결과는 승인 근거가 아니다.
- **MP-10 미구현.** 전체 그래프·재개·중복 방지·승인 버전 강제는 이번 범위 밖이다. 종합은 섹션 단독
  실행으로만 열린다.
- **R2/R3 live 미연결.** 그 결과가 없으면 종합은 선택 결과에 있는 것만 쓴다. 배당·매체 전망 항목이
  빠질 수 있고, 그때 프리뷰는 그 항목을 **생략**한다(빈 카드 없음).
- **선행 회귀 아님(기존 실패).** `tests/preview/test_outlook_module.py`는 이번 변경 전 HEAD(`45b442a`)에서도
  동일하게 23 failed / 2 passed다. 원인은 고정 시각과 실제 시계 혼용으로 R3 테스트가 재현되는 지점이며,
  R3 소유 파일이라 이번 범위에서 고치지 않았다. R1 사실 로직도 건드리지 않았다.
- **공개 홈·배포 없음.** `/admin/preview/:runId`는 관리자 영역 라우트이며 공개 경로가 아니다.

## 8. 편집 종료

MP-09 파일 편집을 멈춘다. 추가 지시(R1 검토 지적 수정, live 한정 통합, MP-10)는 이 작업 범위가 아니며
조정자가 새 작업으로 배정해야 한다.
