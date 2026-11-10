# MP-08 구현 보고: 운영 지표와 원인 추적

**목표.** 관리자가 **저장된 기록만으로** 프리뷰 완료율·모듈 성공률·자료 확보율·API 보완·
429·재시도·처리 시간·사용량을 확인하고, 이상한 지표에서 해당 실행의 시도 원문까지
내려가 원인을 찾는다. 조회는 외부 모델·API를 호출하지 않는다.

**가장 작은 변경.** MP-02가 저장 구조에 이미 남기는 행(`preview_runs`,
`preview_module_executions`, `preview_attempts`, `preview_results`,
`preview_source_snapshots`)만 읽어 집계를 계산한다. 새 테이블·마이그레이션·계약 필드
변경은 없다. `contracts.py`의 `MetricsQuery`/`MetricsResult`는 **그대로** 쓰고, 화면이
필요로 하는 분해 정보(분모 범위·표본 수·내려갈 실행·사용량 누락 수)는 소유 파일
`app/preview/metrics.py`가 `MetricsResult`를 확장해 표현한다(`to_contract()`가 계약
형태를 그대로 돌려준다).

## 실행 모델

| 항목 | 값 | 확인 방법 |
|---|---|---|
| 제공자 / 모델 | hive / `deepseek-ai/deepseek-v4.1-flash-1017` | 세션 로그 `~/.dsh/sessions/--Users-woolee-benchmark--/56ff7493….jsonl.zstd`의 `provider`·`model` 필드 |
| 추론 강도 | `max` (유지, 변경 없음) | 같은 세션 로그의 `reasoningEffort` |
| 프로필 | `dsh-tui` | `DSH_PROFILE=dsh-tui`, `DSH_SESSION_ID=56ff7493-770a-417a-86fa-4f5f046e96c9` |
| 작업 디렉터리 | `/Users/woolee/benchmark` | 세션 레코드 `cwd` |
| 작업 ID / Dispatch | task_316277a498e9 / ctx_af4bb6ef676a | 배정 프리앰블 |
| 커밋 기준 HEAD | `b6174b2` | `git rev-parse --short HEAD` |

프롬프트의 문구로 모델을 대체하지 않고 세션 로그 필드로 확인했다. 모델·추론 강도·
프로필을 변경하지 않았고, 하위 워커를 만들지 않았다.

## 소유 파일

| 파일 | 역할 |
|---|---|
| `app/preview/metrics.py` | 집계 본체. `query_metrics(MetricsQuery) → MetricsReport`. 조회 전용 |
| `app/api/v1/preview_metrics.py` | 관리자 전용 읽기 라우터. `GET /api/v1/admin/preview/metrics` |
| `frontend/src/features/match-preview/metrics.ts` | 지표 자료형·질의 문자열·표기 도우미 |
| `frontend/src/features/match-preview/PreviewMetricsView.vue` | 지표 표·차트·처리 시간·사용량·내려가기 |
| `tests/preview/test_metrics.py` | 수용 테스트 13건 |
| `tests/preview/fixtures/metrics_events.json` | 지표 집계용 합성 저장 이벤트 |
| `frontend/src/features/match-preview/PreviewMetricsView.test.ts` | 화면 테스트 10건 |
| `docs/implementation/match-preview/evidence/30..34-mp08-*` | 실행 증거 |

**수정하지 않은 것:** `app/main.py`, `app/preview/contracts.py`·`store.py`·`models.py`·
`registry.py`·`inspection.py`, `app/api/v1/preview_admin.py`, `alembic/`, `tests/preview/conftest.py`,
프론트 `types.ts`·`api.ts`·`router/index.ts`·`RunInspector.vue`. 모두 MP-04 소유다.

## 집계 정의

모든 비율은 **분자·분모·표본 수·분모 범위(scope)** 를 함께 내보낸다. 없는 값은 0으로
채우지 않는다.

| 지표 ID | 분모(scope) | 분자 |
|---|---|---|
| `preview_completion_rate` | 종료된 전체 프리뷰 실행 (`preview_runs`) | `status=succeeded` + `quality=ready` |
| `preview_draft_rate` | 같음 | `quality=insufficient` 초안 |
| `preview_failure_rate` | 같음 | `status=failed`. 실패 코드별 분해 포함 |
| `preview_in_flight_count` | 분모 없음(건수) | `queued/running/retry_wait`. 완료율 분모에서 제외 |
| `module_execution_success_rate` | 종료된 프리뷰 내부 논리적 모듈 실행 (`preview_module_executions`) | `status=succeeded` |
| `evidence_coverage_rate` | 같음 | 저장된 스냅샷을 참조하는 **채택** 근거가 있는 실행 |
| `api_supplementation_rate` | `SEARCH_NOT_FOUND`가 기록된 종료 모듈 실행 | 그중 API 스냅샷 근거를 채택한 실행 |
| `module_only_success_rate` | 종료된 **모듈 단독** 실행 기록 (`module_runs`) | 성공 |
| `attempt_429_rate` | 저장된 실제 요청 시도 (`preview_and_module_attempts`) | `http_status=429`. 제공자별 분해 |
| `retry_attempt_rate` | 같음 | `attempt_ordinal > 0` |
| `retried_logical_call_rate` | 논리 호출 수 | 2회 이상 시도한 논리 호출. 최종 성공/실패 분해 |
| `usage_reported_rate` | 실제 시도 수 | 제공자가 사용량을 돌려준 시도 |

핵심 분리:

| 축 | 처리 |
|---|---|
| 논리적 실행 vs 실제 시도 | 모듈 성공률 분모는 모듈 실행이다. 429 재시도는 분모를 늘리지 않는다. 429·재시도 지표만 시도를 분모로 쓴다 |
| 실행 성공 vs 근거 확보 | 형식이 유효한 200 응답이라도 채택 근거가 없으면 자료 확보율에서 빠진다 |
| 오류 빈도 vs 최종 결과 | 429 뒤 성공해도 그 시도는 `attempt_429_rate`에 남는다 |
| 운영 vs 개발·모의·재생 | 기본 조회는 `environment=prod`·`mode=live`만. 다른 축은 명시 필터가 있을 때만 나타나고 걸러낸 건수를 `excluded`에 드러낸다 |
| 전체 프리뷰 vs 다른 작업 | `fixture_catalog`는 완료율 분모에서 빠지고(`excluded.fixture_catalog_runs`로 노출), `module` 단독 실행은 별도 scope로만 표시 |
| 결과 버전 | 같은 모듈 실행에 버전이 여러 개여도 실행은 1건으로 센다(최신 결과 기준) |
| 중복 수신 | 같은 `(run_id, logical_call_id, attempt_ordinal)`은 한 번만 센다. 버린 건수를 `excluded.duplicate_events_dropped`로 표시 |
| 없는 값 | 표본 없음 → `available=false`·`numerator=null`·사유 문장. 사용량 미제공 → `null`+누락 건수. 비용 → 항상 `null`(“미확인”) |

처리 시간·사용량은 비율이 아니므로 지표 행에 섞지 않고 `timings`·`usage`로 따로
내보내며 표본 수를 함께 적는다(중앙값·95백분위). 진행 중 실행의 경과 시간은 완료율과
섞지 않고 `preview_in_flight_count`로만 보여준다.

## API

`GET /api/v1/admin/preview/metrics` — `require_preview_admin` 적용(비인증 401, 비ADMIN
403). 조회 전용이며 실행 생성·취소 경로가 없다.

| 질의 인자 | 의미 |
|---|---|
| `from_at`, `to_at` | 집계 기간(포함/미포함). 없으면 최근 7일. `from_at >= to_at`은 422 |
| `environment` (반복) | `dev`/`test`/`prod`. 비우면 `prod` |
| `mode` (반복) | `live`/`replay`/`mock`. 비우면 `live` |
| `module_id`, `model`, `contract_version` (반복) | 그 축의 기록이 있는 실행/모듈만 분모에 넣는다 |
| `metric` (반복) | 원하는 지표만. 모르는 값은 422 |

응답은 `window`(기간·기본값 여부), `filters`(적용값·기본값 여부), `rows`(지표별
분자·분모·표본·ratio·scope·`detail_run_ids`·분해), `timings`, `usage`, `runs`(내려갈
실행·모듈 실행·시도), `excluded`, `notes`, `empty`, `read_only: true`다.

## 화면

`PreviewMetricsView.vue`는 MP-01의 Hallmark 토큰(`frontend/src/styles/app.css`)만 쓴다.
새 팔레트·폰트·라이브러리를 도입하지 않았고 차트는 CSS 막대다(외부 차트 의존성 없음).

| 영역 | 내용 |
|---|---|
| 필터 | 기간·환경·실행 방식·모듈·모델·계약 버전. 비우면 운영·실호출 |
| 기간·필터 요약 | 기간(기본/지정), 일수, 적용 환경·방식, 기본값 적용 표시 |
| 제외 안내 | 환경/방식으로 걸러낸 건수, 목록 수집 제외 건수, 중복 수신 처리 |
| 지표 표 | 값·분자/분모·표본·분모 범위. 표본 없는 행은 `표본 없음`으로 흐리게 |
| 비율 차트 | 비율 지표만. 표본 없는 지표는 막대를 그리지 않는다(0%로 그리지 않음) |
| 처리 시간 | 전체 실행·시도 소요의 중앙값·95백분위·표본 수, 대기 합계 |
| 사용량 | 입력/출력 토큰·검색 사용량·비용. 미제공은 “미확인”, 누락 건수 표시 |
| 내려가기 | `detail_run_ids`로 걸러진 실행 목록 → 실행 열기 → 모듈별 시도(429 실패 시도 포함) |

빈 상태는 “이 기간에 집계할 실행 기록이 없습니다 — 0%가 아니라 표본이 없다는
뜻입니다”로, 오류 상태는 서버 메시지를 그대로 보여준다.

## MP-04 통합 요청 (공유 파일, 내가 편집하지 않음)

이미 `app/main.py`에 등록이 들어와 동작을 확인했다. 남은 것은 프론트 경로·내비게이션이다.

| # | 파일 | 필요한 변경 |
|---|---|---|
| 1 | `app/main.py` | `from app.api.v1 import auth, preview_admin, preview_metrics` + `app.include_router(preview_metrics.router)` — **적용됨 확인**(`create_app()` 라우트에 `/api/v1/admin/preview/metrics` 존재) |
| 2 | `frontend/src/router/index.ts` | `{ path: '/admin/metrics', name: 'preview-metrics', component: () => import('@/features/match-preview/PreviewMetricsView.vue') }` — **미적용** |
| 3 | 내비게이션 | 실행 목록 헤더에서 `preview-metrics`로 가는 링크. `PreviewMetricsView`는 실행 열기를 `select-run(runId)` 이벤트로만 넘기므로, 받는 쪽에서 실행 검사로 연결(예: `/admin/runs` + 선택 실행) |

계약 변경은 필요 없다. `MetricsQuery`/`MetricsResult`는 고정 그대로 쓰고, 화면용
자료형은 소유 파일 `metrics.ts`에 독립 정의했다.

### `select-run` 인계 계약 (MP-04가 그대로 연결할 값)

| 항목 | 값 |
|---|---|
| 이벤트 이름 | `select-run` (Vue `emit('select-run', runId: string)`) |
| 페이로드 | 실행 ID 문자열 하나(`preview_runs.id`의 UUID 문자열). 배열·객체 아님 |
| 발생 시점 | 관리자가 “내려갈 실행” 목록에서 실행 한 건을 누를 때. 지표 조회·필터 변경 시에는 발생하지 않는다 |
| 함께 전달되는 것 | 없음. 현재 필터를 이벤트 인자로 싣지 않는다 |
| 받는 쪽에서 필요한 조회 | 실행 상세는 기존 경로 그대로다: `GET /api/v1/admin/preview/runs/{run_id}` (`previewRunsApi.detail`). 지표 응답의 `runs[].modules[].attempts[].attempt_id`가 그 실행에 속하므로 같은 실행 상세에서 시도 원문을 찾을 수 있다 |
| 필터 유지 기대 | 이동은 화면 전환이므로 필터를 쿼리 문자열로 넘기려면 받는 쪽에서 `PreviewMetricsView`의 필터 상태를 URL 쿼리로 승격해야 한다. 지금은 **이벤트에 필터를 싣지 않으므로** 받는 쪽이 이동만 처리하면 된다(뒤로 오면 기본 조회) |

지표 응답에서 실행으로 내려갈 때 쓸 수 있는 값은 두 가지다.

- `rows[].detail_run_ids`: 그 지표의 분자에 해당하는 실행 ID(표의 “실행 N건” 버튼)
- `runs[]`: 조회 필터가 적용된 실행·모듈 실행·시도 트리(내려가기 목록과 시도 표가 이 값을 그대로 쓴다)

지표 조회 조건을 그대로 다시 쓰려면 같은 질의 인자를 넘기면 된다
(`metricsQueryString({ fromAt, toAt, environments, modes, moduleIds, models, contractVersions, metrics })`
가 만든 쿼리 문자열을 `/api/v1/admin/preview/metrics`에 붙인다).

## 수용 기준별 증거

| 계획 §6 MP-08 수용 기준 | 테스트 | 증거 |
|---|---|---|
| `test_attempt_and_execution_denominators` | 실행 성공 2/2, 429 1/3, 근거 확보 1/2, 추가 재시도 1 | [evidence/30](evidence/30-mp08-backend.txt) |
| `test_mock_replay_dev_excluded_from_prod` | 운영 기본 조회에 dev 모의가 없고 3건 제외가 드러남 | evidence/30 |
| `test_catalog_and_module_runs_not_preview_runs` | 목록 수집 제외, 모듈 단독은 별도 scope | evidence/30 |
| `test_duplicate_event_not_counted_twice` | 같은 키 중복은 1회만 집계 | evidence/30 |
| `test_missing_usage_not_zero` | 사용량 누락 2건, 검색 사용량·비용 `null` | evidence/30 |
| `test_metric_drilldown_keeps_filters` | 지표→실행→시도(429 포함) 연결, 필터 유지 | evidence/30 |
| 표본 없음은 0%가 아님 | `test_empty_window_reports_no_sample_not_zero` | evidence/30 |
| 잘못된 기간 거부 | `test_invalid_window_is_rejected` | evidence/30 |
| 관리자 경계 | `test_metrics_endpoint_is_admin_only` (401/403) | evidence/30 |
| 조회가 외부 호출을 하지 않음 | `test_metrics_endpoint_reads_only_and_has_no_provider_calls` (소켓 connect 차단) | evidence/30 |
| 필터·지표 선택·기본값 | `test_metrics_endpoint_filters_by_metric_and_module`, `test_metrics_endpoint_defaults_to_prod_live` | evidence/30 |
| 화면 표·차트·빈 상태·이벤트 | 10건 | [evidence/31](evidence/31-mp08-frontend.txt) |

### 실행 명령과 결과

| 명령 | 결과 |
|---|---|
| `.venv/bin/python -m pytest tests/preview/test_metrics.py -q` | `13 passed` (exit 0) |
| `npm --prefix frontend run test:unit -- src/features/match-preview/PreviewMetricsView.test.ts` | `1 file, 10 tests passed` (exit 0) |
| `npm --prefix frontend run type-check` | 통과(출력 없음, exit 0) |
| `npx vue-tsc --noEmit -p <MP-08 파일만 포함한 임시 tsconfig>` | 통과(exit 0) |

`type-check`는 처음 실행했을 때 **내 파일이 아닌** `FixtureSelector.vue`(MP-03 소유,
미커밋)의 `provider_calls` 오류로 실패했다. 같은 오류가 0건임을 MP-08 범위 검사로
확인했고, MP-03 쪽 수정 후 전체 `type-check`도 통과했다.

## 실제 vs 모의 구분

| 항목 | 사실 |
|---|---|
| 지표 자료 | `tests/preview/fixtures/metrics_events.json`의 **합성 저장 행**. 실제 제공자 호출 결과가 아니다 |
| 지표 계산 | 실제 `query_metrics` 코드가 실제 PostgreSQL 테스트 DB(`preview_mp01_test`)에서 계산한 결과다 |
| 외부 모델·API 호출 | 0회. 조회 경로가 소켓 연결을 열지 않는 것을 테스트로 확인 |
| 운영 실호출 지표 | **측정하지 않았다.** 실제 live 실행 기록이 아직 없다. 위 수치는 합성 자료의 계산 예시이며 실제 호출 성공률로 인용하면 안 된다 |
| 화면 | Vitest 컴포넌트 테스트로 확인. 실제 브라우저 조작·스크린샷은 하지 않았다(라우터 등록이 MP-04 대기) |

### 화면 예시 지표 (합성 자료)

[evidence/33](evidence/33-mp08-metrics-example.txt)에 재현 스크립트와 출력을 남겼다.
같은 조건을 실제 라우터로 호출한 응답이 [evidence/35](evidence/35-mp08-api-response.json)이고,
그 응답으로 화면을 렌더한 텍스트가 [evidence/36](evidence/36-mp08-view-render.txt)이다.
운영·실호출 기본 조회 결과:

| 지표 | 분자/분모 | 표본 | 비고 |
|---|---|---|---|
| `module_execution_success_rate` | 2 / 2 | 2 | 429→200 재시도가 분모를 늘리지 않음 |
| `attempt_429_rate` | 1 / 3 | 3 | 429 뒤 성공해도 남음 |
| `evidence_coverage_rate` | 1 / 2 | 2 | 200이지만 근거 없는 모듈은 빠짐 |
| `retry_attempt_rate` | 1 / 3 | 3 | 최초 2 + 재시도 1 |
| `retried_logical_call_rate` | 1 / 2 | 2 | 복구 1 / 실패 0 |
| `preview_completion_rate` | 1 / 1 | 1 | 진행 중 1건은 분모 제외 |
| `module_only_success_rate` | 표본 없음 | 0 | 기본 조회 범위에 모듈 단독 실행 없음 |
| 사용량 | 입력 1000 · 출력 250 · 검색 미확인 · 비용 미확인 | 시도 1/3 보고 | 누락 2건 |

`excluded`: 환경 기준 3건(dev 모의 프리뷰·목록 수집·모듈 단독), 실행 방식 기준 0건.

## 보이는 지표 예시 (실제 라우터 응답 + 렌더)

| 확인 항목 | 결과 | 증거 |
|---|---|---|
| 관리자 로그인 → `GET /api/v1/admin/preview/metrics` | `200`, 지표 12행, 내려갈 실행 2건, `read_only: true` | [evidence/35](evidence/35-mp08-api-response.json) |
| 비인증 상태의 같은 경로 | `401` | evidence/35 생성 로그에 함께 기록 |
| 응답으로 화면 렌더 | 지표 표 12행 + 막대 10개 + 처리 시간·사용량 | [evidence/36](evidence/36-mp08-view-render.txt) |

렌더에서 확인되는 것(발췌):

- 지표 표가 `2 / 2`, `1 / 3`, `1 / 2`, `1 / 1`처럼 **분자/분모와 표본 수**를 함께 보여준다.
- `module_only_success_rate`는 `표본 없음`·`—`로 표시되고 **막대가 없다**(0%로 그리지 않음).
- `preview_in_flight_count`는 `1건`·`건수 표시(분모 없음)`으로, 비율처럼 꾸미지 않는다.
- 사용량에서 검색 사용량·비용은 `미확인`이고, 시도 1/3만 사용량이 보고됐다.
- 기간 안에서 환경 기준 3건을 제외했다는 문장이 화면에 남는다.

이 렌더는 jsdom 텍스트 출력이며 스크린샷이 아니다. 실제 브라우저 조작은 프론트 라우트
등록(MP-04) 이후에 가능하다.

### 실호출이 아니라는 표시

위 예시의 모든 수치는 `tests/preview/fixtures/metrics_events.json`의 **합성 저장 행**에서
나온 값이다. 실제 제공자 호출은 0회다. 따라서 `attempt_429_rate 1/3`은 “이 합성 자료가
그렇게 계산된다”는 증거이며, 실제 계정의 429 발생률 측정치가 아니다.

## 커밋

### 커밋 1 — `7ef8821` `feat(preview): MP-08 stored-event operational metrics`

내 소유 파일 13개를 `git add`로 선별 스테이징하고 커밋했다. **그런데 이 커밋에는 내
파일 외에 MP-03이 같은 순간 스테이징해 둔 14개 파일도 함께 들어갔다.** 사실과 원인을
그대로 적는다.

| 구분 | 파일 |
|---|---|
| 내 것 (13) | `app/preview/metrics.py`, `app/api/v1/preview_metrics.py`, `frontend/.../metrics.ts`, `PreviewMetricsView.vue`, `PreviewMetricsView.test.ts`, `tests/preview/test_metrics.py`, `tests/preview/fixtures/metrics_events.json`, `MP-08-report.md`, `evidence/30..34-mp08-*` |
| MP-03 것 (14) | `app/preview/data.py`, `app/preview/sources/{__init__,api_football,fixtures}.py`, `tests/preview/test_data.py`, `tests/preview/test_api_football.py`, `tests/preview/fixtures/api_football.json`, `frontend/.../FixtureSelector.{vue,test.ts}`, `frontend/.../fixtures.ts`, `frontend/.../panels/DataPanel.{vue,test.ts}`, `MP-03-report.md`, `evidence/mp03/d0_mock_run.json` |

- **원인.** 이 저장소는 여러 워커가 같은 작업 트리와 **하나의 git 인덱스**를 공유한다.
  내가 `git diff --cached --name-only`로 스테이징 목록을 확인한 시점에는 내 13개만
  있었는데, 그 확인과 `git commit` 사이에 MP-03 워커가 자기 파일을 `git add`했고,
  `git commit`은 인덱스 **전체**를 커밋하므로 그것까지 함께 들어갔다.
- **손실 없음.** MP-03 파일은 커밋된 내용과 작업 트리 내용이 동일함을
  `git diff HEAD -- <MP-03 경로들>`(출력 없음)로 확인했다. 덮어쓰거나 지운 파일은 없고,
  MP-03의 이후 편집도 그대로 디스크에 있다.
- **되돌리지 않았다.** `reset`·`checkout`·`--amend`로 공유 브랜치 이력을 다시 쓰면
  이미 이 HEAD 위에서 작업 중인 다른 워커(MP-03/04)의 기준이 흔들린다. 혼합 커밋은
  기록만 정확히 남기고, 이력 정리는 조정자가 판단할 일로 남긴다.
- 앞으로의 방법: 다른 워커가 스테이징한 항목을 건드리지 않으려면
  `git commit -- <경로들>`(`--only` 의미)로 경로를 지정해 커밋해야 한다. 이 보고서
  수정 커밋부터 그 방식을 썼다.

### 커밋 2 — `0a81676` `docs(preview): record MP-08 commit scope and the shared-index incident`

### 커밋 3 — 이 보고서 갱신 + 보이는 지표 증거 ([evidence/35](evidence/35-mp08-api-response.json), [evidence/36](evidence/36-mp08-view-render.txt))

`git commit -- <경로들>`로 내 파일만 커밋했다(인덱스 전체를 쓰지 않는다). 다른 워커의
스테이징 항목은 건드리지 않았다. 커밋 해시는 조정자에게 `worker_done`으로 보고한다
(자기 커밋은 자기 보고서에 적고, 이후 재작성하지 않는다).

기존 대량 삭제(809건)·`Plans.md`·`AGENTS.md`·`CLAUDE.md`·공유 파일은 스테이징하지
않았다.

## 남은 것 / 인계

| 항목 | 상태 |
|---|---|
| 프론트 라우트 `/admin/metrics` + 내비게이션 | **MP-04 대기**. 내가 편집하지 않는 공유 파일 |
| 실제 live 실행 기록으로 지표 확인 | **미검증**. live 실행 기록이 생긴 뒤 같은 조회로 바로 확인 가능(MP-10/11) |
| 실제 브라우저 확인 | **미검증**. 라우트 등록 후 `/admin/metrics`를 열어 확인 필요 |
| 비용 환산 | **미구현(의도)**. 가격 기준·적용 시각이 확인되지 않아 `null`로 둔다 |
| 제공자 내부 검색 호출 수 | **집계하지 않음(의도)**. 저장된 사용량에 없으므로 포함했다고 주장하지 않는다 |
| 섹션 워크플로우 단위 완료율 | **미구현**. 섹션 결과 저장이 MP-09 소유이고, 저장된 섹션 실행 기록이 아직 없다. 저장 구조가 생기면 `operation_kind` 분기로 같은 방식으로 추가한다 |
| 지표 알림·자동 감시 | 범위 아님(계획에 없음). 대시보드는 요청 시 조회다 |

### 지표를 추가할 때

`app/preview/metrics.py`의 `_preview_rows`/`_preview_module_rows`/`_attempt_rows`에
`_ratio_row(...)` 한 건을 더하고, `PreviewMetricsView.vue`는 행 목록을 그대로 그리므로
화면 수정이 필요 없다. 분모가 다르면 `scope`를 새 값으로 두고 `scopeLabel()`에만
표시 이름을 더한다. 새 모듈이 등록되어도 같은 `preview_module_executions` 행을 쓰므로
자동으로 집계된다.

## 제약으로 확인한 것

- 쓰기는 로컬 전용 테스트 DB(`preview_mp01_test`)에서만 했다. 운영/개발 실 DB에는
  새 스키마·행·마이그레이션을 만들지 않았다. `preview_dev` 스키마 대상 DDL은 실행하지
  않았다(기존 앱 DB에 지표용 테이블을 추가하지 않음 — 새 테이블이 필요 없다).
- 기존 `public` 계정·경기 자료는 읽지도 쓰지도 않았다(테스트는 합성 계정 원장).
- 새 마이그레이션·공용 Alembic 실행 없음. 배포·푸시 없음.
- 자격 증명·비밀값을 출력·증거·보고서에 남기지 않았다. `~/.config/match-preview/preview-dev.env`는
  읽지 않았다(지표 구현에 필요 없었다).
- 계획이 지정한 수용 테스트에만 검사를 두었다. 보안·호환성 전수 검사나 무관한 입력
  조합 탐색은 추가하지 않았다.

## 보고

| 항목 | 값 |
|---|---|
| 완료 | 집계 모듈·읽기 라우터·화면·테스트·증거, 백엔드 13건·프론트 10건·type-check 통과 |
| 미완료 | 프론트 라우트·내비게이션(MP-04), 실제 live 기록 지표, 실제 브라우저 확인 |
| 실호출 | 0회. 어떤 수치도 실제 제공자 성공률이 아니다 |
