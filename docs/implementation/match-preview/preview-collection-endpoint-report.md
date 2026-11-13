# 기간 지정 프리뷰 시험 엔드포인트 인계 (구현)

작성: DeepSeek 구현 워커, 2026-11-13. 모델 `deepseek-ai/deepseek-v4.1-flash-1017`, 추론 강도 `max`.
승인 근거: `docs/superpowers/specs/2026-11-13-preview-collection-test-endpoint-design.md`(37줄 전문).

## 새 엔드포인트 요약 (실제 요청/응답 계약)

`POST /api/v1/admin/management/runs/preview-test`

기존 관리 라우터(`prefix=/api/v1/admin/management`, `dependencies=[Depends(manager_user)]`)에
추가했으므로 **인증은 기존 그대로**다. 새 인증 경로를 만들지 않았다.

요청(모든 필드 필수, `extra="forbid"`):

| 필드 | 형식 | 검증 |
|---|---|---|
| `target_ids` | int 배열(1~20) | 중복 거부 |
| `fixture_from` | ISO8601 **시간대 필수** | 시간대 없으면 422 |
| `fixture_to` | ISO8601 **시간대 필수** | `from > to` 거부 |
| `preview_fixture_ids` | int 배열 **정확히 2개** | 중복·1개·3개 거부, 양수만 |

`mode`는 받지 않고 refresh로 고정한다(계약에 없음).

이번 실제 호출 값:
`{"target_ids":[13],"fixture_from":"2026-11-21T21:30:00+09:00","fixture_to":"2026-11-22T00:00:00+09:00","preview_fixture_ids":[1557470,1557476]}`

응답: 기존 수집 실행 payload(즉시 반환). 실행 ID로
`GET /api/v1/admin/management/runs/{run_id}`를 조회하면 다음을 확인할 수 있다.

- `test_scope`: `fixture_from`·`fixture_to`·`preview_fixture_ids`·`run_id`(요청별 범위 보존)
- 기존 필드 그대로: `status`, `started_at`, `finished_at`, `items[]`, `logs[]`, `progress`
- `home_preview`: 종료 훅 결과(`collection_status`, `generated[]`(경기 ID·run_id·status),
  `failed[]`, `skipped[]`, `approval_gate`)

GET 종료 조건: `finished_at`이 채워지고 `home_preview.state`가 최종값일 때. `status`만으로
완료 처리하지 않는다(설계 35행).

## 변경 파일과 책임

| 파일 | 변경 |
|---|---|
| `app/api/v1/management.py` | `PreviewTestRunCreate` 요청 모델(경계 검증) + 새 POST 라우트 |
| `app/services/management_runs.py` | `start_preview_test_run()`, `start_run(test_scope=)`, 범위를 payload에 저장, 실행기가 측정·종료 훅에 전달 |
| `app/workers/daily_sync/runner.py` | `measure_league_sync_plan(test_scope=)`가 기간 안 경기만 `fixture_external_ids`(저장·상세 게이트)에 넣음 |
| `app/services/collection_test_scope.py` (신규) | 불변 범위 값 `PreviewTestScope`만 정의(실행 엔진 아님) |
| `app/services/home_preview_collection.py` | `collect_candidates(test_scope=)`의 두 경기 한정 6시간 예외, 시험 전용 회차 키 |
| `tests/unit/test_management_preview_test.py` (신규) | 라우트 계약·기간 저장 게이트·범위 값·회차 키 |
| `tests/unit/test_home_preview_collection.py` | 시험 범위가 생성 후보를 두 경기로 제한하는 검사 추가 |
| `docs/implementation/match-preview/preview-collection-endpoint-report.md` | 이 문서 |

읽기 전용 유지: 프론트·모델/DB 스키마·마이그레이션·Plans.md·승인 계산·`worker_runs.py`의
정기 호출 계약(기본 인자 유지, 무변경).

## 6시간 예외의 경계 (핵심)

- 예외는 **이 엔드포인트 요청의 `preview_fixture_ids` 두 경기만** 받는다.
  `collect_candidates(test_scope=...)`가 그 두 ID로 후보를 제한하고, 6시간 밖이면 후보에
  추가로 더한다. 다른 후보 조건(NS·미래 시각·승인 판정·본문 유무)은 그대로다.
- 일반 수집·정기 실행은 `test_scope=None`이므로 예외 객체 자체가 없다
  (`test_regular_path_has_no_scope_so_the_six_hour_rule_is_unchanged`가 `start_run`의
  기본 인자가 `None`임을 고정).
- **시험 회차 키가 정기 회차를 소모하지 않는다.** 시험은 `preview-test:<수집 실행 ID>`
  label을 쓰고, 정기는 기존 `generation_due_at(kickoff)`을 쓴다. 시험이 정기 슬롯을
  선점하면 이후 정기 생성이 중복으로 건너뛰어지므로 이 분리가 필요하다.

## 기간이 실제 수집을 제한하는 방식

`measure_league_sync_plan`에서 기간 필터를 적용해 **`season_plan.fixture_external_ids`**를
만든다. 이 목록이 `backfill_measured_league`의 저장 대상과 상세 수집 대상(`* 4` 단위)을
동시에 결정하므로, 표시만 거르는 방식이 아니라 **저장 게이트**다.

### 정직하게 밝히는 범위 한계

- **팀·선수·순위 보조 수집은 기간으로 제한되지 않는다.** 이들은 `/teams`·`/players`·
  `/standings`를 리그·시즌 단위로 조회하며 기존 대상 설정을 쓴다. 따라서 이번 시험이
  외부 API 요청량까지 두 경기로 줄였다고 주장하지 않는다(설계 23행과 일치).
- 기간 밖 경기의 저장·상세 수집은 일어나지 않는다. `mode`는 refresh 고정이라 전체 시즌
  수집 완료로 기록하지 않는다.

**정정(2026-11-13 05:35)**: 이 문서의 앞 판은 "시즌 정리·초기화도 하지 않는다"고 적었으나
그 서술은 **당시 코드와 일치하지 않았다.** `execute_run`은 항목이 succeeded이면
`test_scope`와 무관하게 `prune_league_seasons(...)`를 호출했고, 그 함수는 수집 리그의
오래된 시즌 행(`Fixture`/`Injury`/`PlayerSeasonStat`/`Standings`/`TeamSeason`/`TeamCoach`)을
`DELETE`한다. 즉 시험 실행도 시즌 정리를 일으킬 수 있었다. 이번에 시험 범위가 있으면 그
호출을 하지 않도록 고쳤고, 일반 수집의 정리 정책은 유지했다(요구 4).

## 검사

`.venv/bin/python -m pytest tests/unit/test_management_preview_test.py tests/unit/test_home_preview_collection.py -q`
→ **34 passed** (신규 11 + 기존 23).

**합성 검사다.** 실제 API·모델·DB·브라우저를 호출하지 않았다. 라우터·`start_preview_test_run`
·`measure_league_sync_plan`·`collect_candidates`는 실제 진입점을 호출하고 외부 연결만
대역으로 바꿨다. 이 통과를 실제 수집·실제 생성 성공으로 인용하지 않는다.

회귀 확인(각각 되돌린 뒤 34 passed 복귀 확인):

- `runner`의 기간 필터를 제거하면 `test_date_range_filters_fixture_storage_targets_not_just_display`
  가 실패한다(기간 밖 경기가 저장 대상에 남음).
- `collect_candidates`의 두 경기 제한을 제거하면
  `test_test_scope_limits_generation_to_the_two_named_fixtures`가 실패한다.
- 시험 회차 키를 정기 키로 바꾸면 회차 키 검사가 실패한다.

### 작성 중 스스로 잡은 문제

1. 기간 필터 검사가 처음에는 `PreviewTestScope.in_window`만 확인해 **실제 runner 코드를
   지나가지 않았다**. runner 필터를 지워도 통과했으므로, `measure_league_sync_plan`을 직접
   호출해 `fixture_external_ids`를 확인하도록 다시 썼다.
2. 그 과정에서 대역 클라이언트가 `client.get`(병렬 수집이 쓰는 메서드)이 아니라 `response`만
   구현했고, payload도 `{"response": [...]}` 모양이어야 함을 실제 오류로 확인해 고쳤다.
3. 기존 검사 9곳의 `collect_candidates` 대역 람다가 새 `test_scope` 인자를 받지 않아 13건이
   깨졌다. 시그니처를 맞춰 해결했다(제품 회귀 아님, 대역 시그니처 불일치).

## 실제 호출 전제 (조정자 담당, 이번에 하지 않음)

- 실제 요청은 **한 번만** 보낸다. 실패·지연 시 새 POST를 자동 재전송하지 않는다.
- 실행 서버에 이 변경이 반영돼 있어야 새 경로가 존재한다(서버 재시작·배포는 조정자).
- target 13이 활성이고 최신 두 시즌 조건을 만족해야 `start_run` 검증을 통과한다.
- 승인 상태가 `ready`여야 생성 게이트를 통과한다. 현재 승인 조회 결과에 따라
  `approval_not_ready`로 건너뛸 수 있으며, 그 경우 수집은 정상 기록되고 프리뷰는 사유와
  함께 남는다(정상 완료로 꾸미지 않음).
- 현재 시각에서 두 경기가 6시간 밖임을 기록해야 한다(예외로만 생성됐다는 근거).
- 두 경기의 킥오프가 2026-11-22 00:00 KST이고 기간 종료와 같으므로 **양 끝 포함** 판정으로
  포함된다. 실제 응답의 킥오프 표기가 다르면 포함 여부가 달라질 수 있으므로, 실행 기록의
  `season_plan.fixture_external_ids`/저장 결과로 확인해야 한다.

## 남은 항목

- 실제 API 수집·실제 모델 생성·preview_dev 새 기록·실행 ID 재조회는 **미실행**이다.
- 실행 서버 반영 전이므로 새 경로가 배포 환경에서 동작하는지 미확인.
- 승인 `ready` 여부에 따라 자동 생성이 건너뛰질 수 있고, 그 판정은 이번에 실행하지 않았다.

`EDITING STOPPED`. 백그라운드 작업 0건.

---

# PC-LIVE 실행 전 연결 보완 (2026-11-13 05:35)

입력: `preview-collection-endpoint-review.md`(요구 위반 1·부수 1·근거 부족 1),
`preview-collection-admission-findings.md`, `preview-collection-live-evidence.md`, 조정자 추가 사실.

## 요구별 수정

### 1. 접수 전 소속 확인 (신규)

`start_preview_test_run`이 `start_run` 호출 **전에** `_require_preview_fixtures_in_scope`로
두 외부 경기 ID를 검증한다. 부적합하면 422로 거부하고 **어느 경기의 어떤 조건**인지 알린다.

검증 항목: 저장된 경기 존재 → 선택 대상의 리그/시즌 소속 → 요청 기간 양 끝 포함 →
`status_short == "NS"`.

**리그 ID 공간을 섞지 않는다.** 저장된 `Fixture.league_id`는 내부 기본키이고, 대상의 리그는
`League.external_id`(API-Football 외부 ID)다. 그래서 대상에서 외부 ID를 꺼내 비교한다
(`target_payload`가 `league_id`에 external_id를 담는 기존 규칙과 같은 축).

### 2. 수집 후 범위와 경기별 사유

- `collect_candidates(test_scope=...)`가 **지정 경기별 탈락 사유**를 남긴다:
  `outside_requested_period`(상세에 실제 킥오프), `not_scheduled`, `kickoff_passed`,
  `fixture_not_found`. 사유는 결과의 `skipped`에 보존된다.
- **생성 직전에도 요청 기간을 존중한다.** 6시간 안이면서 기간 밖인 지정 경기도 후보에서
  빠지고 그 사유가 남는다. 이 부분은 새 검사가 실제 결함을 드러내 고친 것이다(아래 "스스로
  잡은 문제" 2번).
- 새 임의 기간 상한은 추가하지 않았다.

### 3. 명시적 시험 훅 (전역 플래그 우회)

두 훅 지점의 조건을 `home_preview_enabled or test_scope is not None`으로 바꿨다. 정기 경로는
`test_scope=None`이라 동작이 바뀌지 않고, 전역 설정은 켜지 않는다. 상위 예외 경로도 같은
조건을 쓰므로 시험 요청은 정상/예외 종료 모두에서 훅을 한 번 호출한다.

### 4. 시험에서 시즌 정리 제외

`prune_league_seasons` 호출에 `test_scope is None` 조건을 추가했다. 대상 객체가 실제로
존재하고 수집이 succeeded인 경우로 검사해, `target=None`이라 정리 분기에 닿지 않는 빈 검사가
되지 않게 했다(검사에서 `store.get`이 실제 `_Target`을 돌려주고 `pruned == []`를 확인).

### 5. 실제 bundle 대상 승인 판정

- `pipeline.bundle_workflows()`가 `information_bundle.SECTION_IDS`를 **같은 출처**로 돌려준다.
- `pipeline._judge()`로 공통 판정 로직을 한 곳에 모으고, `admission_state()`(옛 전체 프리뷰)
  와 `bundle_admission_state()`(bundle)가 같은 로직을 쓴다.
- 수집 경계(`home_preview_collection._admission`)가 `bundle_admission_state`를 쓴다.
  form/synthesis를 요구하지 않고 odds/ai_forecast를 포함한다. 승인 없음·버전 불일치는 계속 차단한다.
- **관리자 기존 GET/`/admission`은 여전히 옛 경로 판정(`admission_state`)이다.** 그 경로의
  의미를 보존하라는 요구에 따른 것이며, 화면의 "기본 전체 프리뷰" 판정과 수집 자동 생성 판정이
  서로 다른 집합을 본다는 뜻이다. 이 차이는 인계 사항으로 남긴다.

### 6. 같은 결과의 계약 비교 일치

- 실제 bundle 저장 경로가 `SECTION_RESULT_CONTRACT_VERSION`(`mp04-section-result-1`)으로
  모듈 결과를 기록하는 것을 코드로 확인했다(`bundle_pipeline`의 `ModuleInput`·저장 호출).
- `version_manifest.constituents_for_workflow`가 **bundle 워크플로우의 모듈 항목에만** 같은
  축을 쓴다. D0와 compose는 기존 `CONTRACT_VERSION`(`mp02-1`)을 유지하고, 옛 워크플로우
  (`section_form`)도 기존 축을 유지한다.
- 승인 행을 수정하거나 `ready`를 강제하지 않았다. 비교 축을 맞춘 결과가 기존 승인 버전과
  일치하면 그것은 새 승인이 아니라 계산 오류의 수정이다. 실제로 프롬프트/출력/구현이 달라
  의미 있는 차이가 남으면 그때는 미승인으로 남는다(검사 `test_stale_approval_still_blocks_bundle_generation`).

## 스스로 잡은 문제

1. `test_bundle_workflow_constituents_use_the_section_result_contract_axis`가 처음에
   `section_odds`까지 모듈 축을 단언해 실패했다. odds는 모델 모듈 없이 수집·정규화 결과를 쓰므로
   비교할 모듈 항목이 없다. 잘못된 단언을 고치고, 실제 모듈이 있는 4개 섹션을 확인하도록 바꿨다.
2. **제품 결함 1건을 검사가 드러냈다.** 6시간 안이면서 요청 기간 밖인 지정 경기가 후보에 남아
   있었다. 요청 기간을 모든 시험 후보에 적용하고 탈락 사유를 남기도록 고쳤다.
3. 기존 검사 대역 9곳의 `collect_candidates` 람다가 새 `skipped` 인자를 받지 않아 13건이
   깨졌다. 대역 시그니처를 맞춰 해결했다(제품 회귀 아님).

## 검사

```text
.venv/bin/python -m pytest tests/unit/test_management_preview_test.py \
  tests/unit/test_home_preview_collection.py \
  tests/unit/test_bundle_collection_admission.py \
  tests/unit/test_home_preview_document.py -q
→ 66 passed
```

구성: `test_management_preview_test.py` 17, `test_home_preview_collection.py` 24,
`test_bundle_collection_admission.py` 9, `test_home_preview_document.py` 16.

**합성 검사다.** 실제 DB·외부 API·모델·서버·브라우저·승인 POST·마이그레이션은 0건이다.
세션·클라이언트·모델 전송·경기 잠금·승인 조회를 대역으로 바꿨다.

종단 연결 검사
`test_management_run_with_test_scope_reaches_two_fixtures_through_the_real_hook`은
`execute_run` → 실제 `run_home_preview_after_sync` → 실제 `run_collection_generation` →
`collect_candidates`를 통과시킨다. 확인하는 것: 두 지정 경기만 생성, `preview-test:<수집ID>`
회차 키로 이어짐, `collection_status` 보존, `generated` 2건, 그리고 **시험 범위에서
`prune_league_seasons` 미호출**(대상 객체가 존재하고 수집이 succeeded인 경우). 훅을 대체해
호출 횟수만 세지 않는다.

## 실제 요청·종료 판정·승인 확인 방법 (조정자용)

- 요청: `POST /api/v1/admin/management/runs/preview-test` (기존 ADMIN 인증).
  본문은 이전 절의 현재 값 그대로.
- 접수 거부 확인: 기간 밖 ID나 다른 리그/시즌 ID를 넣으면 **422**와 함께 어느 경기의 어떤
  조건인지 메시지에 나온다. 수집·외부 호출은 시작되지 않는다.
- 종료 판정: `GET /api/v1/admin/management/runs/{run_id}`의 `finished_at`이 채워지고
  `home_preview`가 최종일 때. `status`만으로 완료 처리하지 않는다.
- 승인 확인: `bundle_admission_state`가 `ready`여야 생성이 시작된다. 승인 없음/버전 불일치면
  `approval_not_ready`로 건너뛰고 수집은 정상 기록된다. 관리자 `/admission` GET은 옛 경로
  판정이므로 **그 값이 ready가 아니어도 수집 경계 판정과 다를 수 있다**.

## 미확인

- 실제 POST·실제 API 수집·실제 모델 생성·preview_dev 새 기록은 실행하지 않았다.
- 질문 6의 축 일치가 실제 기존 승인 5행을 `approved`로 만들지는 실행 없이 확인하지 않았다.
  live evidence의 승인 상태와 대조는 조정자 몫이다.
- 실행 서버에 이 변경이 반영되는지(재시작·배포) 미확인.

`EDITING STOPPED`. 백그라운드 작업 0건.
