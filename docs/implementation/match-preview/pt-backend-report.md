# PT-BACKEND A 구현 보고 (수집만 실행·조회·요청 중복 경계)

**목표.** 기존 프리뷰 탭이 기간 수집 결과를 먼저 보여 주고, 사용자가 확인한 뒤 두 경기를 직접 생성하게 하는 흐름에서, 백엔드가 맡는 부분(후보·기간/대상 해석·수집만 실행·부작용 없는 실행 조회·bundle 요청 중복 경계)을 구현한다.

**작업 기준.** integration `07e6cdc0f9c174b08337fcded81fb6f90f03bc42`에서 만든 자식 워크트리 `/Users/woolee/orca/workspaces/benchmark/preview-test-backend`, branch `lebind12/preview-test-backend`. 착수 시 `git status --porcelain` 공백(clean)을 확인했다.

**모델.** 이 세션의 DSH 세션 로그(`~/.dsh/sessions/--Users-woolee-orca-workspaces-benchmark-preview-test-backend--/24e5d40e-……/session.v4.jsonl.zstd`)에 기록된 30건의 호출 레코드가 모두 `"model":"deepseek-ai/deepseek-v4.1-flash-1017"`, `"reasoningEffort":"high"`다. 프로필 `dsh-tui`의 hive 제공자 모델 ID와 같다. 다른 백엔드·모델로 대체하지 않았고 호출 실패는 없었다.

**적용한 poteto-mode 원칙과 그 원칙이 바꾼 결정.** `Boundary Discipline`이 검증 위치를 라우터/서비스 경계 한 곳(`build_plan`, `start_preview_test_run`)으로 모으고 실행기 내부는 재검증하지 않게 했다. `Laziness Protocol`과 `Subtract Before You Add`가 새 표·새 마이그레이션·새 작업 엔진을 만들지 않고 기존 `management_run`·`preview_runs.label`·`pg_try_advisory_lock` 패턴만 쓰게 했다. `Model the Domain`이 수집 상태를 새 필드가 아니라 기존 run payload 필드(`status`·`items[]`·`log_statistics`·`counts_kind`)로 표현하게 했다. `Test Behavior, Not Implementation`이 실제 핸들러·실제 실행기를 호출하는 검사를 만들게 했다.

## 추가한 HTTP 계약

전부 `/api/v1/admin/management` 아래이며 **ADMIN 전용**이다(라우터의 `manager_user` 위에 `require_admin` 추가). 기존 일반 관리 API의 STREAMER 정책은 건드리지 않았다.

| 경로 | 응답 |
|---|---|
| `GET /preview-test/candidates` | `as_of`, `timezone="Asia/Seoul"`, `candidates[]`, `reason` |
| `GET /preview-test/plan?fixture_ids=&fixture_ids=` | `fixture_ids`, `fixture_from`, `fixture_to`, `target_ids`, `targets[]`, `can_collect`, `blocking_reasons`, `scope_notes` |
| `POST /preview-test/runs` | 기존 management run payload(`generate_after_collection=false` 고정) |
| `GET /preview-test/runs` | `{active, items, limit}`. `active`는 진행 중 **한 건 또는 null**, `items`는 **종료 실행만**(같은 실행이 양쪽에 중복되지 않음) |
| `GET /preview-test/runs/{run_id}` | run payload 한 건 |

`candidates[]`는 `fixture_id`, `kickoff_at`(시간대 포함), `home_name`, `away_name`, `league_name`, `season`, `priority`다. 정렬은 킥오프→추천 순위→외부 경기 ID다. 기존 `eligible_rows`·`priority`를 그대로 쓰므로 홈 추천 정책은 바뀌지 않는다.

`targets[]`는 `id`, `league_name`, `season`, `include_details`다. 기간은 **당일 KST 00:00부터 두 경기 중 마지막 킥오프까지**, 양 끝 포함이다.

`blocking_reasons[]`는 `{code, message}`이고 code는 `target_not_found`, `target_inactive`, `target_league_inactive`, `fixture_not_scheduled`, `kickoff_unknown`, `fixture_started`다. 구조적 위반(개수·중복·없는 경기 ID)만 422이고, 지금 수집할 수 없는 사유는 `can_collect=false`로 돌려준다.

## 기존 경로에 추가한 필드(기본값으로 기존 동작 보존)

`POST /runs/preview-test` 본문에 `generate_after_collection: bool = True`를 추가했다. `false`일 때만 ADMIN을 추가로 요구한다(자동 생성은 실제 모델을 부르므로). `true`(기본)의 권한·의미는 그대로다. `POST /preview/bundle-runs` 본문에 선택 `request_id: UUID`를 추가했다. 없으면 기존 동작 그대로다.

## 수집만 실행의 생성 0회 보장

`PreviewTestScope.generate_after_collection`(기본 `True`)이 실행 payload에 저장되고 실행기·종료 훅에서 복원된다. `_wants_home_preview(settings, test_scope)` 한 곳이 판정하며, 정상 종료·부분 실패·상위 예외 세 경로가 모두 이 함수를 쓴다. `false`면 전역 `HOME_PREVIEW_ENABLED`가 켜져 있어도 훅을 부르지 않고 `home_preview` 키도 만들지 않는다(없는 결과를 "생성 실패"로 읽히게 하지 않기 위해서다). 옛 저장 값에 이 키가 없으면 `True`로 복원해 이미 접수된 실행의 의미를 바꾸지 않는다.

## 요청 중복 경계

- **저장 구조.** 새 표를 만들지 않았다. 실행 `label`에 `request=<uuid>` 표기를 넣고, `label`은 실행 행과 같은 트랜잭션에 저장된다. 그래서 "실행은 저장됐는데 요청 장부는 없는" 창이 없다.
- **재전달.** 같은 `request_id`면 저장된 실행을 찾아 `bundle-runs` 응답 모양으로 되살린다. 모델 전송 0회이고 응답 문구로 재전달임을 알린다.
- **충돌.** 같은 `request_id`를 다른 경기에 쓰면 409다.
- **동시 진입.** `pg_try_advisory_lock`(namespace 730002)로 같은 요청을 직렬화한다. 잠금을 못 잡으면 기다리지 않고 409다. 잠금은 생성 전체를 감싼다.

## 실행 항목별 결과

| 항목 | 결과 |
|---|---|
| 후보 조회(정렬·제외·부족 사유) | 구현, 검사 통과 |
| 기간/대상 해석(당일 KST 00:00~마지막 킥오프) | 구현, 검사 통과 |
| 수집만 실행(생성 0회, 세 경로) | 구현, 검사 통과 |
| 부작용 없는 실행 목록·단건 조회 | 구현, 합성 테스트 DB에서 삭제·복구 없음 확인 |
| bundle `request_id` 중복(모델 1회 전송) | 구현, 핸들러 직접 호출 검사 통과 |
| 기존 제한 자격·DB 대상·키·JWT 조사 | 값 비공개로 확인(아래) |
| launcher | `scripts/run_preview_test_collection.sh` 추가 |

## 기존 자격·DB 대상·키·JWT 사전 조사 (값 비공개)

파일 존재와 권한만 확인했고 값은 읽어 출력하지 않았다.

| 파일 | 권한 | 확인한 키 이름 |
|---|---|---|
| `~/.config/match-preview/preview-dev-restricted.env` | `-rw-------` (600) | `API_FOOTBALL_KEY`, `DATABASE_URL`, `JWT_SECRET_KEY`, `LOCAL_DEV_AUTH_ENABLED`, `PREVIEW_ALLOW_NONLOCAL_DB`, `PREVIEW_DEV_DATABASE_URL` |
| `~/.config/match-preview/preview-dev.env` | 600 | 위와 같고 `PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB`, `PREVIEW_FIXTURES_DATABASE_URL`, `PREVIEW_IDENTITY_DATABASE_URL`, `PREVIEW_NAMES_DATABASE_URL`, `PREVIEW_STATS_DATABASE_URL` 추가 |
| `~/.config/match-preview/model-live.env` | 600 | `PREVIEW_MODEL_CREDENTIALS_JSON`, `PREVIEW_MODEL_LIVE_ENABLED`, `PREVIEW_MODEL_LOCATION`, `PREVIEW_MODEL_NAME`, `PREVIEW_MODEL_PROJECT`, `PREVIEW_MODEL_PROVIDER` |

수집 전용 launcher는 `preview-dev.env`(기존 수집 후보)를 쓰고, `DATABASE_URL` 하나만 넘긴다. 모델 키는 넘기지 않고(`PREVIEW_MODEL_LIVE_ENABLED`·`PREVIEW_MODEL_CREDENTIALS_JSON` 해제), scheduler와 자동 홈 프리뷰도 끈다. 제한 파일의 광권한 자격을 preview 38000에 넣지 않았다.

**미검증.** 실제 수집 자격으로의 연결 성공 여부는 확인하지 않았다(이번 배정에 실수집 없음). launcher의 실제 기동도 하지 않았다.

## 실행한 명령과 결과

```
$ git rev-parse HEAD
07e6cdc0f9c174b08337fcded81fb6f90f03bc42
$ git status --porcelain        # 착수 시 공백

$ PREVIEW_TEST_DATABASE_URL=...preview_mp01_test .venv/bin/python -m pytest \
    tests/unit/test_management_preview_test.py \
    tests/unit/test_home_preview_collection.py \
    tests/preview/test_preview_test_requests.py -q
81 passed          # 커밋 f9bc34c 시점 74, a62545c 시점 78, 이번 보완 후 81

$ PREVIEW_TEST_DATABASE_URL=...preview_mp01_test .venv/bin/python -m pytest \
    tests/unit tests/preview/test_preview_test_requests.py \
    tests/preview/test_admin_access.py -q
161 passed         # 커밋 a62545c 시점 158. 136은 tests/unit 전체 실행 결과다

$ sh -n scripts/run_preview_test_collection.sh
syntax ok
$ PREVIEW_TEST_COLLECTION_CREDENTIALS=/nonexistent/env sh scripts/run_preview_test_collection.sh
missing credentials file: /nonexistent/env   (exit 1)
```

합성 테스트 DB는 로컬 `127.0.0.1:55432/preview_mp01_test`이며, 실행 전 `pgrep -fl pytest`로 다른 pytest 프로세스가 없음을 확인하고 실행했다. 기존 경기·계정 운영 DB에는 연결하지 않았다.

**미검증(이번 A 배정 범위 밖).** 실제 수집 1회, 실제 AI 호출, 실DB 쓰기, 서버 재시작, 기존 마이그레이션 재실행, 브라우저 확인은 하지 않았다. `ruff`는 이 venv에 설치되어 있지 않아 실행하지 못했고, `python -m compileall`로 문법만 확인했다.

## B에 인계하는 run 응답 매핑

`management_run.payload`를 `_payload`가 변환한 값이며, `POST /preview-test/runs`·`GET /preview-test/runs`·`/runs/{id}`가 같은 모양이다.

- 수집 상태: `status`, `progress`(0~100), `stage`, `items[].status`, `items[].total_known`
- 오류: `log_statistics`(코드별 `errors`/`warnings`/`target_ids`), `logs[]`(`level`/`code`/`message`/`analysis`)
- 시각: `created_at`, `started_at`, `finished_at`, `logs[].at`(UTC ISO). **target별 갱신시각은 run 응답에 없다**(`GET /targets`의 `last_sync`에만 있다).
- 실제 대상: `items[]`의 `target_id`/`league_id`(외부 리그 ID)/`name`/`season`, `test_scope.preview_fixture_ids`
- 기간: `test_scope.fixture_from`/`fixture_to`
- **주의.** `counts_kind="processing_units"`면 `items[].saved`·`total`·`stored_rows`는 처리 단위이고 경기 건수가 아니다. `legacy_unknown`이면 대상별 수가 없다. 기간 내 실제 수집 경기 목록은 run payload에 없으므로 선택 두 경기와 같은 것으로 표시하면 안 된다.
- 생성 결과: `home_preview`는 `generate_after_collection=true`일 때만 있는 선택 키다. 부재를 생성 실패로 표시하면 안 된다.

## 실제 수집 경기 근거(`collection_evidence`)

승인 설계는 기간 안에서 **실제로 수집된 경기 목록/건수**를 선택한 생성 대상 2개 및 처리 단위 카운터와 구별해 보여주기를 요구한다. 기존 run payload에는 그 정보가 없었으므로, 이미 계산된 계획과 백필 결과를 접어 `collection_evidence`를 남긴다.

**위치.** 시험 범위(`test_scope`)가 있는 실행의 payload에만 있다. 일반 수집 실행에는 키가 없어 기존 응답 모양이 바뀌지 않는다(검사로 고정).

| 필드 | 의미 |
|---|---|
| `scope_fixture_ids` | 사용자가 선택한 생성 대상 2개(다른 축) |
| `fixture_from`/`fixture_to` | 요청 기간(시간대 포함) |
| `planned_fixture_ids` | 계획 단계가 기간 안에서 대상으로 삼은 경기. **저장 성공 아님** |
| `stored_fixture_ids` | 백필이 **upsert하고 커밋까지 끝낸** 경기. 저장 성공 판정의 유일한 근거 |
| `detail_stored_fixture_ids` | 상세 4종 **응답을 저장한** 경기(`/injuries` 제외) |
| `unverified_fixture_ids` | 계획에 있었지만 저장이 확인되지 않은 경기. **실패로 단정하지 않음** |
| `partial` | 확인된 범위를 전체로 믿을 수 없는 상태. 백필 결과의 오류 + run 대상 실패(`items[].status`) + 실행 status(failed/partial_failed/cancelled/interrupted) + "계획은 있는데 커밋된 결과 없음"을 모두 반영 |
| `counts` | `planned`/`stored`/`detail_stored`/`unverified` 건수 |
| `notes` | 위 구분을 문장으로 남긴 설명 |

**보수적 판정 규칙(문서 명시).**

- `stored_fixture_ids`의 근거는 **커밋까지 끝난** 백필 결과뿐이다. 커밋 전에 결과를 근거에 넣으면 롤백된 경기 ID가 "저장됨"으로 남는다.
- 예외·취소로 커밋을 확인할 수 없는 범위는 `stored`가 아니라 `unverified`다. **실패로 단정하지 않는다**(미확인과 실패는 다르다).
- `detail_stored`는 상세 응답 **저장 확인**이다. 정상 빈 응답도 저장으로 세므로, 이 값이 있다고 상세 자료가 채워졌다는 뜻은 아니다.
- 근거는 정상 종료·취소·상위 예외 세 경로에서 모두 남긴다. 예외로 끝나 저장을 확인할 수 없으면 `partial=true`이고 `stored`는 비어 있다.

**구현 방식.** 새 수집기·추가 외부 호출·새 표를 만들지 않았다. `app/workers/daily_sync/runner.py`의 `SeasonBackfillResult`에 `fixture_external_ids_stored`·`detail_fixture_external_ids_stored`를 추가하고, 이미 upsert하는 루프에서 ID만 기록한다(API 호출 증가 없음). 접기는 `management_runs._collection_evidence`가 한다.

## 단건 GET 무쓰기 확인

`GET /preview-test/runs/{run_id}`는 integration `management_runs.get_run`(첫 줄에서 `_recover_orphans` 호출)을 쓰지 않는다. `preview_test.test_run` → `_test_run_rows`(SELECT) → `payload_view`(`_payload` 별칭) 경로다. 기존 `get_run`·`run_list`는 변경하지 않았다.

## 남은 일

- 통합(C)·독립 검토·실제 수집 1회·사용자 수동 생성 확인은 이번 A 범위가 아니다.
- 실 수집 자격 연결 성공과 launcher 실제 기동은 C/조정자 단계에서 확인해야 한다.
- `ruff` 미설치로 정적 검사를 실행하지 못했다.
