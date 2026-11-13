# 시험 엔드포인트 독립 확인 (PC-LIVE)

작성: DeepSeek 검토 워커(읽기 전용), 2026-11-13 05:26 KST. 모델 `deepseek-ai/deepseek-v4.1-flash-1017`, 사용자 설정 max.
스킬: `.agents/skills/poteto-mode/SKILL.md` 전문은 이 세션에서 읽었고 현재 해시 `70faeea64f157a019b349137f3e8163c5df9a0ec5a2412e4b4e75e50d760b936`(24986 bytes)로 미변경을 확인해 재사용했다. 적용 원칙은 `principle-prove-it-works`·`principle-boundary-discipline`·`principle-test-behavior-not-implementation`이다.

**확인 리비전.** 제시된 SHA256 일곱 개가 현재 파일과 모두 일치했다: `management.py` `7fbe1772…e910`, `management_runs.py` `683fa931…6d41`, `daily_sync/runner.py` `39a8df62…798d`, `collection_test_scope.py` `5af19812…f1c`, `home_preview_collection.py` `5ad2b2c8…423e`, `test_management_preview_test.py` `28603f83…2e`, `test_home_preview_collection.py` `5cbabe88…7c3`.

**실행.** `.venv/bin/python -m pytest tests/unit/test_management_preview_test.py tests/unit/test_home_preview_collection.py -q` → **34 passed (0.57s)**. 이전 22와 합산하지 않는다. 합성 대역 통과이며 실제 API·DB·모델 성공 근거가 아니다.

## 요구별 판정

### 1. 실제 요청 경계 — 부분 충족 (요구 위반 1건)

**충족하는 부분.** 라우트는 기존 관리 라우터(`prefix=/api/v1/admin/management`, `dependencies=[Depends(manager_user)]`)에 추가됐고 핸들러도 `user: Manager`를 받는다(`app/api/v1/management.py:182-200`). `test_route_uses_the_existing_manager_dependency`가 라우터 의존성과 핸들러 인자를 확인한다. 새 인증 경로는 없다.

요청 검증(`PreviewTestRunCreate`, `:60-86`)은 `extra="forbid"`로 미지 필드를 거부하고, 시간대 없는 기간·기간 역전·`target_ids` 중복·경기 ID 2개 아님·중복·비양수를 422로 막는다. `mode`는 계약에 없어 refresh 고정이다. `start_preview_test_run`(`management_runs.py:426-460`)이 같은 조건을 서비스 경계에서 다시 확인한 뒤 기존 `start_run`에 넘기므로 대상/시즌 검증·활성 여부·동시 실행 409가 기존 그대로 적용된다(`:302-344`, `:372-376`).

**요구 위반.** 계획과 설계는 "선택한 대상/시즌/기간에 **속하지 않는** 경기 입력은 수집과 모델 호출 전에 거부한다"고 요구했지만, 두 경기 ID는 그 검사를 받지 않는다. `start_preview_test_run`의 검증은 개수·중복·시간대·기간 역전뿐이고(`:445-452`), `preview_fixture_ids`를 `target_ids`·시즌·기간과 대조하는 코드가 없다(`preview_fixture_ids` 사용처는 라우터 검증·범위 생성·`collect_candidates` 필터 3곳뿐). 즉 **기간 밖 경기 ID나 다른 리그·시즌 경기 ID도 접수된다.**

**사용자 영향.** 기간 종료가 11-22 00:00이고 두 대상 경기 킥오프가 정확히 그 시각이므로, 현재 값은 양 끝 포함 판정으로 우연히 통과한다. 그러나 기간을 잘못 적거나 ID를 잘못 적으면 요청이 거부되지 않고, 수집은 정상 수행된 뒤 생성 단계에서 조용히 후보 0건이 되어 `no_candidates`로 끝난다. 사용자는 "요청이 틀렸다"는 즉시 피드백 대신 성공한 수집과 빈 프리뷰 결과를 받는다. 기간을 좁게 주면 같은 손실이 실제로 재현 가능하다.

**수집 후 일정/상태 변경 시 제외 사유도 기록되지 않는다.** `collect_candidates`는 조건에 맞지 않는 지정 경기를 사유 없이 걸러내고(`home_preview_collection.py:99-114`), 지목된 두 ID 중 하나라도 탈락하면 `rows`가 비어 `reason: no_candidates`만 남는다(`:299-301`). 설계가 요구한 "경기별 명확한 제외 사유"가 없다. 어느 경기가 왜 빠졌는지(NS 아님·킥오프 지남·기간 밖·DB 미수집)를 구분할 수 없다.

**최소 수정 범위(구현하지 않음).** `start_preview_test_run`에서 두 ID를 조회해 활성 대상·시즌·`fixture_from~fixture_to` 포함과 미래 NS 여부를 확인하고 불일치 시 422로 거부한다. 수집 후 판정은 `run_collection_generation`이 지정 ID별 탈락 사유를 `skipped`에 남기도록 한 곳을 고치면 된다. 검사는 "기간 밖 ID 요청이 접수 단계에서 거부된다"와 "수집 후 NS가 아니게 된 지정 경기의 사유가 남는다" 두 건이면 충분하다.

### 2. 기간의 실제 효력 — 충족

`measure_league_sync_plan(..., test_scope=)`가 `fixture_external_ids`를 만들기 **전에** 기간 필터를 적용한다(`runner.py:363-372`). 이 목록이 저장 대상(`:462-467`, `allowed_fixture_ids`로 응답을 다시 거름)과 상세 수집 4종(`:557-568`)을 동시에 결정하므로 표시 필터가 아니라 **저장 게이트**다. `test_date_range_filters_fixture_storage_targets_not_just_display`가 실제 `measure_league_sync_plan`을 호출해 기간 밖 ID가 목록에 없음을 확인한다. 구현자가 처음에 `in_window`만 검사하던 약한 검사를 스스로 잡아 고친 점도 보고서와 일치한다.

기간 밖 저장·상세 수집과 시즌 정리가 새로 생기지 않고, `mode`는 refresh 고정이라 전체 시즌 완료로 기록하지 않는다. 팀·선수·순위 보조 수집이 기간으로 제한되지 않는다는 한계는 설계 23행과 일치하게 보고서에 명시돼 있으며, 이를 실제 API 요청량 감소로 과장하지 않았다.

### 3. 두 경기 한정 예외 — 충족

`collect_candidates`의 기본은 `now < kickoff <= now+6h`이고(`:91-97`), `test_scope`가 있을 때만 `preview_fixture_ids`에 한해 6시간 밖 후보를 추가한다(`:98-110`). 예외 후보도 `status_short == "NS" and now < kickoff`를 다시 확인하므로 NS·미래 조건은 유지된다. 이어서 `is_preview_fixture`로 후보를 두 ID로 제한하므로(`:112-114`) 같은 시각의 다른 경기(예: 1557474)는 대상이 되지 않는다. `test_scope=None`인 일반·정기 경로에는 예외 객체 자체가 없고(`:116-117`), `test_regular_path_has_no_scope_so_the_six_hour_rule_is_unchanged`가 `start_run` 기본 인자 `None`을 고정한다.

승인 게이트(`:318-320`)와 FAILED 분류(`:423`)는 두 경기 예외와 무관하게 그대로이며, "기본 인자의 존재만"이 아니라 후보 결과를 근거로 확인했다(범위 제한·일반 경로 미적용 모두 코드 경로와 검사로 확인).

### 4. 종료 훅과 결과 — 충족

`test_scope`는 payload에 저장되고(`:399-401`), `execute_run`이 복원해(`:477-479`) 정상 종료 훅(`:626-630`)과 상위 예외 경로 훅(`:655-658`) 양쪽에 전달된다. `run_home_preview_after_sync(test_scope=)`가 `run_collection_generation`까지 이어 넘긴다(`:745-780`). 기존 생성 서비스만 호출하고 새 엔진은 없다.

원래 수집 상태 보존(`collection_status` 별도 키), 취소 시 미생성(`:283`, `:342`), 경기별 실패 격리(`:411-418`), 비예외 FAILED 분류(`:423-433`), 승인 게이트(`:318-320`)가 모두 유지된다. 각 결과에 `run_id`가 실려 추적 가능하다.

**검사 누락.** 훅이 `test_scope`를 받아 두 경기만 생성하는 것을 **종단으로** 고정하는 검사는 없다. `test_scope_restricts_preview_candidates_to_the_two_fixtures`는 `PreviewTestScope` 값 객체의 메서드만 검사하고 `collect_candidates`를 호출하지 않는다. 즉 수용 결과 4의 "한 요청의 범위가 종료 훅까지 이어져 두 경기를 처리한다"는 배선이 직접 검사로 고정되지 않았다. 코드 경로로는 확인됐으나 회귀 방지 근거가 없다.

### 5. 중복과 기존 동작 — 충족

시험 회차 키는 `preview-test:<수집 실행 ID>`이고(`:55-61`), 정기는 `generation_due_at(kickoff)`를 쓴다. `test_test_round_key_does_not_consume_the_regular_slot`이 두 키가 다르고 시험 실행마다 달라짐을 고정한다. 같은 시험은 `fixture_id + label` 중복 조회로 한 번만 생성한다. 기존 관리자 문서는 label이 달라 자동 중복으로 잡히지 않는다(PC-CONNECT에서 수용한 동작 재사용).

## 지적 요약

| 구분 | 건수 | 내용 |
|---|---|---|
| 현재 요구 위반 | 1 | 두 경기 ID가 대상/시즌/기간 소속 여부를 수집 전에 검증받지 않는다(§1) |
| 근거 부족 | 1 | 종료 훅→두 경기 생성 종단 검사 없음(§4) |
| 요구 위반(부수) | 1 | 수집 후 탈락한 지정 경기의 경기별 제외 사유 미기록(§1) |
| 참고 | 2 | 아래 |

**참고 (차단 아님).**

- 예외 후보 조회 창이 `now + 365일`이다(`:104`). 대상 ID로 제한되므로 누출은 없지만, 먼 미래 경기를 지정하면 예외가 적용된다. 설계가 "과거 경기용 범용 기능은 만들지 않는다"고만 정했으므로 위반은 아니나 상한을 두는 편이 의도에 가깝다.
- `in_window`는 시간대 없는 `kickoff_at`을 포함하지 않는다(`collection_test_scope.py:44-51`). 저장된 킥오프가 항상 tz-aware이므로 실제 문제는 없고, 조용히 제외되는 쪽으로 실패한다.

## 실제 호출 전 막힌 점 (root 담당, 미실행)

- 실제 API·모델·preview_dev 쓰기는 실행하지 않았다. 34 passed는 그 근거가 아니다.
- 승인 상태가 `ready`여야 생성 게이트를 통과한다. `not_ready`이면 수집만 정상 기록되고 프리뷰는 `approval_not_ready`로 남는다.
- 두 경기 킥오프가 기간 종료와 같은 11-22 00:00이라 양 끝 포함 판정에 의존한다. 실제 응답의 킥오프 표기가 다르면 `fixture_external_ids`에 들지 않을 수 있으므로 실행 기록으로 확인해야 한다.
- 위 §1 위반 때문에 **기간을 잘못 지정하면 요청이 거부되지 않고 빈 결과로 끝난다.** 실제 호출 전에 기간·ID를 다시 확인할 것을 권한다.

`EDITING STOPPED`. 백그라운드 작업 0건.

## 여섯 연결 보완의 한정 수정 확인 (2026-11-13 05:45)

한정 수정 확인이다. 위 본문의 판정은 **보완 전 리비전**에 대한 것이고, 아래는 현재 리비전에 대한 재판정이다. 최초 전체 검토를 반복하지 않았다.

**확인 리비전.** 제시된 SHA256 일곱 개가 현재 파일과 모두 일치했다: `management_runs.py` `f560511b…690d`, `home_preview_collection.py` `e58adfeb…cec1`, `pipeline.py` `dbf65a50…27c8`, `version_manifest.py` `d518c7a3…570d`, `test_management_preview_test.py` `940d41dc…341f`, `test_home_preview_collection.py` `730809e1…53f7`, `test_bundle_collection_admission.py` `4189c993…cff9`. 스킬 `poteto-mode/SKILL.md` 해시 `70faeea6…b936`도 미변경이라 기존 읽기를 재사용했다.

**실행.** 허용 명령 1회: `.venv/bin/python -m pytest tests/unit/test_management_preview_test.py tests/unit/test_home_preview_collection.py tests/unit/test_bundle_collection_admission.py tests/unit/test_home_preview_document.py -q` → **66 passed (0.60s)**. 이전 34와 합산하지 않는다. 합성 검사이며 실제 수집·모델·DB 성공 근거가 아니다.

### 1. 접수 전 소속 확인 — 해결

`start_preview_test_run`이 `start_run` **호출 전**에 `_require_preview_fixtures_in_scope`를 실행한다(`management_runs.py:454-460`, 함수 `:471-543`). 실제 저장 모델로 검사한다: `LeagueSyncTarget` → `League`로 허용 `(external_id, season_year)` 집합을 만들고(`:491-504`), `Fixture.external_id`로 경기를 읽어(`:506-511`) 각 ID에 대해 존재·리그/시즌 소속·기간 양 끝 포함·`status_short == "NS"`를 확인한다(`:513-543`). 실패는 모두 422이고 메시지에 **경기 ID와 어긋난 조건**이 들어간다(예: 킥오프 시각과 요청 기간을 함께 출력).

리그 ID 공간을 섞지 않는다. `Fixture.league_id`는 내부 기본키이고 허용 집합 키는 `League.external_id`이며, 비교도 `league_external in allowed`로 한다(`:523`). 검사 대역의 모양에 기대지 않고 실제 ORM 관계를 읽는다. 작업 생성·외부 호출 전에 거부되므로 수용 결과를 충족한다.

### 2. 수집 후 범위와 경기별 사유 — 해결

`collect_candidates(test_scope=, skipped=)`가 지정 경기별 사유를 남긴다: `outside_requested_period`(상세에 실제 킥오프), `not_scheduled`(현재 상태), `kickoff_passed`, `fixture_not_found`(`home_preview_collection.py:88-191`). `_note_skipped`가 같은 경기를 중복 기록하지 않는다(`:75-85`).

생성 직전 기간 존중이 **6시간 안팎 모두** 적용된다. 6시간 창 안 후보도 `test_scope.is_preview_fixture`이면서 `in_window`가 거짓이면 `outside_requested_period`로 빠지고(`:118-135`), 6시간 밖 예외 후보도 `in_window`를 먼저 확인한다(`:136-169`). 기간 밖이면 예외로도 후보에 넣지 않으므로 다른 경기로 대체하지 않는다. 새 임의 기간 상한은 추가되지 않았다(예외 탐색 창은 기존 `now+365일`).

리뷰가 지적한 "기간 밖이면 항상 no_candidates" 서술은 정정한다. 지금은 경기별 사유가 `skipped`에 남는다. 보고서도 자기 결함을 인정했다(스스로 잡은 문제 2번: 6시간 안·기간 밖 경기가 후보에 남아 있던 실제 결함).

### 3. 명시적 시험 훅 — 해결

정상 경로 조건이 `settings.home_preview_enabled or test_scope is not None`(`:704`)이고, 상위 예외 경로도 `not preview_started and (getattr(...home_preview_enabled, False) or test_scope is not None)`(`:741-743`)로 같은 조건을 쓴다. 정기 경로는 `test_scope=None`이라 동작이 바뀌지 않고 전역 설정도 켜지 않는다. 명시 취소는 `SyncCancelled` 경로로 빠져 훅에 도달하지 않는다(기존 유지).

종단 검사 `test_management_run_with_test_scope_reaches_two_fixtures_through_the_real_hook`(`test_management_preview_test.py:269-456`)는 훅을 대체하지 않는다. 실제 `execute_run` → 실제 `run_home_preview_after_sync` → 실제 `run_collection_generation` → `collect_candidates`를 통과시키고 모델·DB 외부 경계만 대역으로 바꾼다. `home_preview_enabled = False`인 설정으로 돌려 두 지정 경기만 생성됨, `preview-test:run-top` 회차 키 연결, `collection_status == "succeeded"` 보존, `generated` 2건을 단언한다(`:444-453`). 리뷰가 지적한 근거 부족이 해소됐다.

### 4. 시험에서 시즌 정리 제외 — 해결, 최초 판정 정정

`prune_league_seasons` 호출이 `item["status"] == "succeeded" and test_scope is None` 조건으로 감싸졌다(`management_runs.py:646-649`). 일반 수집의 정리 정책은 유지된다.

**최초 보고서의 판정을 정정한다.** 앞 절들이 적은 "시험에서 시즌 정리·초기화도 하지 않는다"는 **당시 코드와 일치하지 않았다.** 그 무렵 `execute_run`은 항목이 succeeded이면 `test_scope`와 무관하게 `prune_league_seasons`를 호출했다. 구현 보고서도 같은 취지로 스스로 정정했다(80-88행). 이 검토는 그 정정이 타당함을 코드로 확인했다.

새 검사가 **빈 검사가 아니다.** 종단 검사에서 `store.get`이 실제 `_Target`을 돌려주고 항목이 succeeded로 끝나 정리 분기에 실제로 도달하며, `prune_league_seasons`를 대역으로 바꿔 `pruned == []`를 단언한다(`test_management_preview_test.py:381-386`, `:453`). target=None이라 분기에 닿지 않는 형태가 아니다.

### 5. 실제 bundle 대상 승인 판정 — 해결

`pipeline.bundle_workflows()`가 `information_bundle.SECTION_IDS`를 그대로 돌려준다(`pipeline.py:190-199`). 실제 값은 players·availability·outlook·odds·ai_forecast 5개다(`information_bundle.py:238-244`). 판정 로직은 `_judge()`로 한 곳에 모였고(`pipeline.py:202-228`), `admission_state`(옛 경로)와 `bundle_admission_state`(bundle)가 같은 로직을 쓴다(`:231-247`, `:250-`). 수집 경계는 `bundle_admission_state`를 쓴다(`home_preview_collection.py:523-526`).

form/synthesis를 요구하지 않고 odds/ai_forecast를 포함한다. 옛 경로 의미도 보존된다: `required_workflows()`에 form/synthesis가 남아 있고 두 집합이 다름을 `test_legacy_required_workflows_keeps_its_own_meaning`이 고정한다. 승인 없음·버전 불일치 차단은 유지되며 `test_stale_approval_still_blocks_bundle_generation`이 `ready is False`와 `stale_approval` 집합을 단언한다.

승인 함수들은 읽기 전용이다(`_judge`·`bundle_admission_state`·`admission_state` 구간에 `session.add`/`commit`/`delete` 없음). 승인 행을 만들거나 `ready`를 강제하지 않는다.

**인계 사항(차이).** 관리자 기존 `/admission` GET은 여전히 옛 경로(`admission_state`)를 본다. 그래서 관리자 화면의 "기본 전체 프리뷰" 판정과 수집 자동 생성 판정이 서로 다른 집합을 본다. 요구 5가 옛 경로 의미 보존을 지시했으므로 의도된 결과이나, **조정자가 관리자 `/admission` 값만 보고 실제 POST 가능 여부를 판단하면 오판할 수 있다.** 보고서도 이 점을 명시했다.

### 6. 같은 결과의 계약 비교 일치 — 해결

실제 bundle 저장 경로가 모듈 결과를 `SECTION_RESULT_CONTRACT_VERSION`(=`mp04-section-result-1`)으로 기록한다(`bundle_pipeline.py:452`, `:473`, `:495`, `:522`). `version_manifest.constituents_for_workflow`가 **`BUNDLE_WORKFLOW_IDS`에 속한 모듈 항목에만** 같은 축을 쓴다(`version_manifest.py:163-175`). `BUNDLE_WORKFLOW_IDS`는 정확히 그 5개 섹션이다(`:40-48`). D0와 compose는 `CONTRACT_VERSION`을 유지하고(`:141-148`, `:177-185`), 옛 워크플로우(`section_form`)도 기존 축을 유지한다.

검사가 축을 고정한다: `test_bundle_workflow_constituents_use_the_section_result_contract_axis`, `test_legacy_workflow_keeps_the_original_contract_axis`, `test_d0_and_compose_keep_the_pipeline_contract_axis`. 구현자가 odds에 모듈 항목이 없다는 잘못된 단언을 스스로 잡아 고친 점도 보고서와 일치한다(배당은 모델 모듈 없이 수집·정규화 결과를 쓴다).

승인 행을 수정하거나 `ready`를 강제하지 않았다. 같은 승인 근거와 실제 구성의 **비교 오류**를 고쳐 기존 승인 버전과 일치하게 만든 것이며, 의미 변경을 새로 승인한 것이 아니다. 실제 프롬프트/출력/구현이 달라 차이가 남으면 미승인으로 남는다(위 stale 검사).

## 이번 수정이 만든 직접 회귀

없다. 기간 저장 게이트(`runner.py`, 무변경), 두 경기 6시간 예외, 시험 회차 키, 승인 게이트, 취소, 경기별 실패 격리, FAILED 분류, 공개 문서 선택이 66건 안에서 함께 통과한다. 편집 범위도 소유권 목록과 일치한다(`management.py`·`runner.py`·`collection_test_scope.py`는 이번 창에서 변경 없음).

## 실제 확인이 남은 점 (root 담당, 미실행)

- 실제 POST·API 수집·모델 생성·`preview_dev` 새 기록은 실행하지 않았다. 66 passed는 그 근거가 아니다.
- 요구 6의 축 일치가 실제 기존 승인 5행을 `approved`로 만드는지는 실행 없이 확인하지 않았다. live evidence의 승인 상태와 대조해야 한다.
- 관리자 `/admission` GET 값과 수집 경계 `bundle_admission_state` 값이 다를 수 있다. POST 전에 후자를 기준으로 판단할 것.
- 실행 서버에 변경이 반영됐는지(재시작·배포) 미확인.

`EDITING STOPPED`. 백그라운드 작업 0건.
