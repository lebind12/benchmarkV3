# MP-04 구현 보고: LangGraph 섹션 워크플로우 실행과 공통 예산·시도 기록

**목표.** 관리자가 경기 프리뷰 **섹션 하나**를 골라 실행하고, 저장된 실행 ID로 그 섹션의
본문·근거·노드 진단을 다시 여는 흐름을 실제로 돌게 만든다. 실행은 실제 LangGraph
`StateGraph`이고, 모델·API 호출은 하나의 예산·재시도·시도 기록 경로를 지난다. 승인은
그 워크플로우가 실제로 만든 섹션 본문 결과에만 연결된다.

**한 줄 결론.** 실행 구조·예산·기록·승인 연결은 완성해 검증했다. 다만 **실제 조사·생성
구현은 아직 등록되지 않았으므로(MP-05~07 소유) 지금 돌릴 수 있는 것은 명시적 모의
시연뿐**이고, 실제 모델 호출(live)은 자격 증명이 이 앱 설정에 연결되지 않아 한 번도
하지 않았다. live 성공은 주장하지 않는다.

## 실행 모델

| 항목 | 값 | 확인 방법 |
|---|---|---|
| 제공자 / 모델 | hive / `deepseek-ai/deepseek-v4.1-flash-1017` | `~/.dsh/profiles/dsh-tui/cordis.patch.yml`의 `providers.hive.models[].id` |
| 추론 강도 | max (유지, 변경 없음) | 같은 파일의 `providers.hive.reasoning: max` |
| 프로필 | dsh-tui | 세션 환경 `DSH_PROFILE=dsh-tui`, `DSH_PROFILE_DIR=~/.dsh/profiles/dsh-tui` |
| 작업 디렉터리 | `/Users/woolee/benchmark` | CWD |
| 작업 ID / Dispatch | task_3f117c87a4ea / ctx_f98b3ad466cc | 배정 프리앰블 |
| HEAD (착수) | `b6174b2` | `git log` |
| 모델·강도 변경 | 없음. 하위 워커 생성 없음 | 이 작업은 단독 수행 |

## 범위와 경계

| 항목 | 이번 작업 | 근거 |
|---|---|---|
| 쓰기 대상 | `preview_dev` 새 표 `preview_section_results` + 기존 실행 표 | `alembic/versions/0004_section_results.py`, `scripts/preview_dev_migrate.py` |
| 기존 `public` 영역 | 읽기만(경기·부상·순위). DDL·DML 없음 | `preview_dev_status.py` `result: PASS`, `update public.app_user: denied` |
| 공용 Alembic head | 실행하지 않음 | `0004.upgrade()`가 공용 체인 실행 시 `RuntimeError` |
| 운영 배포·환경 변수 | 변경 없음 | Koyeb은 읽기만(`deployments get`) |
| 외부 모델 호출 | **0회** | live 자격 증명 미연결. 아래 "실제 모델 호출" 절 |
| 외부 API 호출 | 0회 | MP-03 실행기 연결은 모의 수집 경로만 |
| 기존 809건 삭제 | 건드리지 않음 | 선별 스테이징만 |
| Plans.md·AGENTS.md·CLAUDE.md | 수정하지 않음 | 조정자 소유 |

## 실행 구조

`app/preview/runner.py`의 `build_section_workflow`가 **LangGraph `StateGraph`**를 컴파일한다.
자체 범용 실행기를 새로 만들지 않았다. 노드는 네 단계로 고정된다.

```
START → prepare_data → research → compose_body → finalize → END
```

| 노드 | 역할 | 사용자 승인 단위? |
|---|---|---|
| `prepare_data` | 공유 자료 준비(D0 등) | **아니오** |
| `research` | 섹션 조사 모듈들(1개 이상) | 아니오 |
| `compose_body` | 독자용 본문·근거 조립 | 아니오 |
| `finalize` | 본문 유무 확정, 품질 확정 | 아니오 |
| **섹션 워크플로우 전체** | 본문·근거를 가진 **섹션 결과** | **예** |

- 섹션과 모듈은 1:1이 아니다. `section_synthesis`는 R1+R2+R3+S1을 구성 모듈로 갖는다.
- 실행 하나는 `preview_runs` 행 하나와 같은 `run_id`를 쓴다. 노드마다
  `preview_module_executions`·`preview_results`가 붙고, 본문은
  `preview_section_results`에 저장된다.
- 체크포인터는 **선택 주입**이다(`checkpointer=`). 넘기지 않으면 상태를 저장하지 않으므로
  MP-04는 재개를 지원한다고 주장하지 않는다(MP-10 소유).
- LangGraph 내부 객체는 API 응답에 나가지 않는다. 응답은 저장 행을 검사 모양으로 바꾼
  `app/preview/inspection.py`의 dict뿐이다.

### 등록되지 않은 단계의 처리

`WorkflowImplementations`에서 빠진 구현은 **본문을 만들어 채우지 않는다**. 실행은
`unavailable_reason`을 남기고 `quality=insufficient`로 저장된다. 응답의
`section_run_availability`가 `implemented`·`missing_implementations`·`demo_only`·
`real_generation_available`·`modes`를 따로 내보내, "실행은 되지만 실제 생성은 아니다"를
값으로 구분한다.

## 공통 예산·재시도 (`app/preview/retry.py`)

계획 §5 값을 파일 한 곳에 두고 그대로 쓴다(파일을 다시 확인해 아래 값을 확정).

| 항목 | 값 |
|---|---|
| 전체 프리뷰 모델 요청 예산 | 재시도·출력 수정 포함 **8** |
| 정상 경로 모델 호출 | 조사 3 + 종합 1 = **4** (재시도 여유 4) |
| D0 외부 API 요청 예산 | 재시도 포함 **24** |
| 논리 호출 최대 시도 | 최초 포함 **3** |
| 모델 / API 동시 요청 | 각 **2** (`ConcurrencyGate`) |
| 모델 응답 대기 / API 요청 상한 | **300초 / 30초** |
| 전체 실행 기한 | 접수 후 **1,800초**(대기 포함) |
| 대기 | 유효한 Retry-After 우선, 없으면 1초부터 지수 증가, 무작위 지연 포함 **60초 상한** |

지키는 규칙:

- **재시도·예산 소유자는 하나다.** `google-genai`의 SDK 재시도를
  `HttpRetryOptions(attempts=1)`로 끈다. LangGraph 노드 재시도도 켜지 않는다. 그래서
  실제 호출 수와 `preview_attempts` 행 수가 같다.
- **아직 시작하지 않은 필수 단계의 첫 호출 몫을 남긴다.** 앞 단계 재시도가 뒤 단계의
  첫 호출을 굶기지 않는다(`RunBudget.reserved_model_requests`).
- **401·403은 눈먼 재시도를 하지 않는다.** 429는 대기 후 재시도하며 **실패·성공 두 시도가
  모두** 남는다.
- **기한은 대기까지 포함한다.** 남은 기한보다 긴 대기가 필요하면 재시도하지 않는다.
- **모르는 값은 모른다.** 사용량 미제공은 `null`(0 아님), 응답 보존 전 중단은
  `unknown`(성공 아님).

## 제공자 어댑터 (`app/preview/provider.py`)

| 함수/클래스 | 계약 |
|---|---|
| `execute_request(RequestSpec, ExecutionContext, *, transport, budget, session, …)` | 요청 하나를 예산·기한·시도 규칙 안에서 보낸다. 시도마다 `preview_attempts` 행 + 원문 아티팩트 2개(요청·응답) |
| `request_model(logical_call_id, contents, context, *, transport, budget, …)` | 모듈이 모델을 부르는 **유일한** 통로 |
| `replay_result(session, *, source_result_id, transform, …)` | 저장 원문으로 변환만 다시 한다. **외부 호출 0회** |
| `GoogleGenAIHttpTransport` | Vertex AI 실호출. 설정 없으면 `ConfigurationUnavailable` |
| `HttpApiTransport(send_func=…)` | 축구 API. `HttpResponse.headers`의 Retry-After를 읽는다 |
| `RecordedTransport(script=[…])` | 모의. 기록은 `mode=mock` |
| `ReplayTransport(stored=…)` | 저장 응답 재생. 기록은 `mode=replay` |
| `model_configuration_status(transport)` | 설정됨/없음과 사유만 낸다(값 아님) |

시도 기록은 `attempt_ordinal` 0이 최초, 1 이상이 재시도다. 각 시도는
`logical_call_id`·`request_artifact_id`·`response_artifact_id`·`usage`·`wait_ms`·
`http_status`·`error_class`로 이어진다. 그래서 화면에서 "논리 호출 → 각 시도 → 원문 →
변환 → 다음 입력"이 끊기지 않는다.

## 실제 모델 호출: 확인한 사실과 하지 않은 것

**확인한 것(비밀값 미출력, 키 이름과 비밀이 아닌 값만).** `koyeb deployments get
6b6fbe4f-…`의 `definition.env`에서 다음을 읽었다.

| 키 | 값 |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | `project-bde7516a-98dc-40f5-92e` |
| `GOOGLE_CLOUD_LOCATION` | `global` |
| `VERTEX_AI_MODEL` | `gemini-3.5-flash` |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | secret 참조(값 미출력) |

**하지 않은 것.** 이 앱에는 위 값이 연결되지 않았다. `PREVIEW_MODEL_*` 환경이 비어 있고
서비스 계정 JSON도 로컬에 없다. 그래서 `GoogleGenAIHttpTransport.configuration_problem()`이
"서비스 계정 자격 증명이 없어 실제 모델을 호출할 수 없습니다"를 돌려주고, 실행기는
요청을 **보내지 않고** `configuration_error`로 실패한다. **live 성공은 0건**이며, 이
보고서 어디에도 live 성공으로 읽힐 표현을 쓰지 않았다.

**남은 연결(정확히).** 배포에 이미 있는 `GOOGLE_APPLICATION_CREDENTIALS_JSON` 값을
`PREVIEW_MODEL_CREDENTIALS_JSON`으로, `GOOGLE_CLOUD_PROJECT`를 `PREVIEW_MODEL_PROJECT`로,
`GOOGLE_CLOUD_LOCATION`을 `PREVIEW_MODEL_LOCATION`으로, `VERTEX_AI_MODEL`을
`PREVIEW_MODEL_NAME`으로 넘기고 `PREVIEW_MODEL_LIVE_ENABLED=1`을 명시하면 live 경로가
열린다. 자격 증명은 0600 파일이나 프로세스 환경으로만 넣고 저장소·보고서·로그에 적지
않는다. 이 연결과 유료 호출 예산 승인은 조정자 결정 사항이라 내가 임의로 열지 않았다.

**모델 선택에 대해.** `gemini-3.5-flash`는 **배포에 설정된 값**으로 보고한다. 그 모델이
지금 호출 가능한지, 혹은 사용자가 승인한 대체 모델인지의 증거는 아니다. 그래서 코드는
모델 이름을 하드코딩하지 않고 설정에서 받는다.

## 저장 구조

| 표 | 이번 작업 | 내용 |
|---|---|---|
| `preview_dev.preview_section_results` | **신규(0004)** | 섹션 본문·근거·버전·실행 방식·구성 링크·관리자 진단 |
| 기존 7개 실행 표 | 변경 없음 | 실행·모듈 실행·시도·스냅샷·결과·원문·감사 |
| `preview_section_approvals` | 변경 없음 | 승인 행(append-only) |

`preview_section_results`의 핵심 열: `run_id`, `workflow_id`, `workflow_version`, `version`
(`(run_id, workflow_id, version)` 유일), `title`, `body`, `sources`, `mode`, `environment`,
`quality`, `module_execution_ids`, `result_ids`, `diagnostics`, `unavailable_reason`,
`output_contract_version`, `contract_version`, `supersedes_section_result_id`.

- 본문이 비어 있는데 `unavailable_reason`도 없으면 저장을 거부한다(빈 본문을 성공으로
  남기지 않는다).
- 모의·재생 결과도 저장하지만 `mode`를 그대로 남긴다. 승인 경로가 이 값을 확인한다.
- 실행 취소(`cancel_run`)·`undo_report`가 이 표도 함께 센다. 다른 실행이 남긴 결과가
  있으면 기존과 같은 충돌 규칙이 적용된다.

## 승인 연결

`app/preview/approvals.py`의 `approve_section_version`이 이제 실제로 승인 행을 만든다.
거부 조건을 좁게 유지했다.

| 조건 | 결과 |
|---|---|
| 실행이 없음 / 취소됨 | 422 거부 |
| 섹션 결과 ID 없음 | 422 거부("본문을 연 뒤에 승인하세요") |
| 다른 실행의 섹션 결과 | 422 거부 |
| 다른 워크플로우의 섹션 결과 | 422 거부 |
| 본문이 없거나 `unavailable` | 422 거부 |
| `mode=mock`(모의 시연) | 422 거부 — **모의는 승인 근거가 아니다** |
| 위 조건을 모두 통과 | 승인 행 생성 + `preview_write_audit` 기록 |

승인 행에는 워크플로우 버전, 구성 모듈/프롬프트/구현/계약 버전 집합, 확인한 실행·섹션
결과 ID, 승인자·시각, 검토 메모가 남는다. 같은 섹션의 기존 활성 승인은 지우지 않고
`active`만 내린 뒤 새 행이 `supersedes_approval_id`로 가리킨다.

**이번에 고친 결함(중요).** `section_approval_status`가 `release_version`의 반환값을
`(구성, 버전)` 순서로 잘못 풀어, 승인 직후에도 항상 `superseded`로 보였다. 실제로는
`(버전, 구성)` 순서다. 고치기 전에는 승인해도 화면이 "재확인 필요"로 남았다.

## API

모든 경로는 `require_preview_admin`을 통과한다(비인증 401, 비ADMIN 403).

| 메서드 | 경로 | 성격 |
|---|---|---|
| GET | `/sections` | 섹션별 실행 가능성(`modes`, `demo_only`, `missing_implementations`) |
| POST | `/section-runs` | 섹션 워크플로우 실행 → `run_id`. 지금은 `mock`만 열림 |
| GET | `/runs/{run_id}/section-results` | 저장된 섹션 본문 결과 |
| POST | `/results/{result_id}/replays` | 저장 응답 재생(외부 호출 0회) |
| GET | `/fixtures` | 저장된 경기 목록(수집 없음). 읽기 연결 없으면 사유 노출 |
| POST | `/fixtures/import` | 관리자 명시 수집. 지금은 모의 실행기(`external_calls=0`) |
| GET | `/registry` | 모듈·섹션 등록부 + `section_availability` |
| POST | `/sections/{workflow_id}/approvals` | 실제 섹션 결과에 대한 승인 |
| GET | `/metrics` | MP-08 지표(이번에 `main.py`에 라우터 등록) |

`mode=live` 요청은 422로 거부된다. 실제 조사 구현이 등록되지 않은 상태에서 live 실행을
성공으로 꾸미지 않기 위해서다.

## 검사 화면

| 파일 | 이번 변경 |
|---|---|
| `RunInspector.vue` | **섹션 본문·근거를 모듈 목록보다 먼저** 보여준다. 버전 전환, 모의 라벨, 저장 응답 재생 버튼, 승인은 `approvable` 결과만 |
| `panels/AttemptPanel.vue` | **신규.** 논리 호출·시도 순번·결과·HTTP·대기·사용량. 429→재시도 두 시도가 함께 보인다 |
| `AdminMetricsRoute.vue` | **신규.** MP-08 지표 화면의 `select-run`을 실행 검사로 연결(MP-08 파일 미수정) |
| `types.ts`, `api.ts` | 섹션 결과·실행·재생·지표 연결 타입/호출 추가 |
| `PreviewRunsView.vue` | 관리자 상단 내비(실행 목록/운영 지표), `?run=`으로 검사 화면 바로 열기 |
| `router/index.ts` | `/admin/metrics` 라우트 추가 |

노드별 요청·원문·변환·다음 입력은 `<details>` 접이식 **진단**으로 남는다(승인 단위 아님).
사용을 줄이지 않고 자리만 옮겼다.

### 상속된 dirty 공유 파일 조정

착수 시 `inspection.py`·`RunInspector.vue`·`types.ts`에 MP02(종료된 터미널)가 남긴 미커밋
변경이 있었다. 그 변경은 "승인 단위는 섹션"이라는 정책에 맞는 방향이었지만, 짝이 되는
테스트 fixture가 갱신되지 않아 `row.module_ids.join`이 `undefined`에서 터졌다. 나는 그
변경을 **버리지 않고** 받아들여, fixture에 `display_name`·`module_ids`·`implemented`·
`unrunnable_reason`을 채우고 섹션 결과 표시를 그 위에 얹었다. 덮어쓰지 않았다.

## 수용 기준별 증거

| MP-04 수용 기준 | 증거 |
|---|---|
| 429 → 대기 → 성공 두 시도가 검사 화면에 보임 | `tests/preview/test_provider.py::test_429_then_success_two_attempts`, `tests/preview/test_module_runner.py::test_retry_trace_is_visible_in_the_run_inspection`(API 응답에서 `[429, 200]`, `wait_ms=2000`, `retry_count=1`), `AttemptPanel.test.ts` |
| 예산이 중첩 재시도로 늘지 않음 | `test_retry_budget.py::test_budget_is_not_multiplied_by_nested_retry_loops`, `test_provider.py::test_google_transport_disables_sdk_retries`(`attempts=1` 확인) |
| 미시작 단계 예약 | `test_retry_budget.py::test_retry_reserves_the_first_call_of_unstarted_steps`, `::test_unstarted_steps_keep_their_reserve_until_started` |
| 401 눈먼 재시도 없음 / 기한에 대기 포함 | `::test_401_no_blind_retry`, `::test_deadline_includes_wait_time`, `::test_charge_refuses_after_deadline` |
| 원문 보존 / 사용량 unknown | `::test_raw_payload_preserved`, `::test_unknown_usage_is_null_not_zero`, `::test_unknown_outcome_is_not_a_success` |
| 저장 재생 무호출 | `::test_replay_has_zero_network_calls`(소켓 `connect` 차단 상태에서 통과), `::test_section_api_rejects_live_until_implementations_exist` |
| 섹션 결과 영속·표시 | `::test_section_run_persists_reader_facing_body_and_sources`, `::test_section_detail_exposes_body_before_diagnostics`, 실제 개발 DB `dfd9d371…` |
| 승인 근거가 실제 일치 결과일 때 연결 | `::test_approval_links_to_the_real_section_result`(모의 거부), `::test_approval_is_written_when_a_matching_non_mock_result_exists`, `::test_approval_refuses_a_section_result_from_another_run` |
| LangGraph 실제 사용 | `::test_section_run_uses_langgraph_state_graph`(`CompiledStateGraph` 인스턴스 확인) |
| 마이그레이션 = 모델 | `test_migration_schema.py::test_section_result_ddl_matches_the_model` |

### 실행 명령과 결과

원문 출력은 [evidence/37](evidence/37-mp04-execution.txt)에 그대로 남겼다.

| 명령 | 결과 |
|---|---|
| `PREVIEW_TEST_DATABASE_URL=…/preview_mp04_test .venv/bin/python -m pytest tests/preview -q` | **233 passed** |
| `npm --prefix frontend run test:unit` | **8 files, 55 tests passed** |
| `npm --prefix frontend run type-check` | 통과(출력 없음) |
| `npm --prefix frontend run build` | 빌드 성공 |
| `.venv/bin/python scripts/preview_dev_migrate.py` | `0004_section_results: applied` |
| `.venv/bin/python scripts/preview_dev_status.py` | `result: PASS` (public 쓰기·경기 읽기 거부 확인) |
| `.venv/bin/python -m app.workers.preview list-sections` / `run` / `show` | 섹션 4개 `modes=mock`, 실행 `dfd9d371…` 저장·재열람 성공 |

**전용 테스트 DB를 쓴 이유.** 기본 `preview_mp01_test`는 다른 워커가 동시에 스키마를
지우며 도는 중이라 간헐적으로 `UndefinedTable`이 났다. `preview_mp04_test`를 새로 만들어
경합을 없앴다. 이 사실은 테스트 실패를 감추기 위한 것이 아니라, 같은 증상을 반복
관찰해 원인을 분리한 결과다.

## 실제 개발 영역 확인

| 항목 | 값 |
|---|---|
| 실행 ID | `dfd9d371-83e4-4e6b-9fe0-74dbaa2b391d` |
| 워크플로우 | `section_form` (`section_form@9f0d2e9bcb33c26d`) |
| 방식 / 상태 | **mock** / succeeded, quality pending |
| 섹션 결과 | `8b4176bc-5628-4af9-95fa-2e1c78bf3358` v1 |
| 외부 호출 | 0 |
| 저장된 행 | 실행 1, 모듈 실행 3, 결과 3, 스냅샷 1, 원문 1, 섹션 결과 1 |
| 감사 | `run_created → module_started×3 → artifact_saved → snapshot_recorded → result_saved×3 → section_result_saved → run_finished` |

모의 실행이므로 이 결과는 **승인 근거가 아니다**. 승인 행은 만들지 않았다(개발 워커가
사용자 대신 승인하지 않는다).

## 429 흔적을 실제로 확인한 방법

모의 transport로 429 → Retry-After 2초 → 200을 재현하고, 그 실행을
`GET /api/v1/admin/preview/runs/{run_id}`로 조회해 다음을 확인했다.

```
attempts[0]: ordinal 0, outcome error,  http_status 429, error_class rate_limited
attempts[1]: ordinal 1, outcome ok,     http_status 200, wait_ms 2000
summary:    attempt_count 2, retry_count 1, mode mock
```

즉 **실패한 시도를 지우고 성공만 남기지 않는다**. 이 재현은 모의 transport이며 실제 계정의
429 발생률 측정이 아니다.

## 수용한 것 / 보류한 것

**수용(이번 범위에서 끝남):** LangGraph 섹션 실행과 실행 ID 영속, 공통 예산·재시도·기한,
시도·원문·사용량 기록, 섹션 본문 결과 저장·표시·버전, 실제 결과에 대한 승인 연결,
저장 응답 재생(무호출), 관리자 API·검사 화면 연결, 지표 화면 연결, 전용 마이그레이션,
모의 시연 경로.

**보류(다른 작업 소유 또는 사용자 결정 필요):**

| 항목 | 이유 |
|---|---|
| 실제 조사·생성 본문(R1/R2/R3/S1) | MP-05~07. 구현을 등록하면 같은 실행기가 그대로 쓴다 |
| live 모델 호출 | 자격 증명 연결 + 유료 호출 승인 필요(위 "남은 연결") |
| 실제 섹션 승인 행 | 사용자가 본문을 확인한 뒤에만 만든다. 내가 만들지 않았다 |
| LangGraph 체크포인트 재개·time travel | MP-10. MP-04는 `checkpointer=` 주입 자리만 둔다 |
| 전체 파이프라인(D0→R1/R2/R3→V0→S1→V1) | MP-10 |
| 운영 지표의 live 표본 | live 실행이 없어 미검증(MP-08 보고와 동일) |

## 다른 작업에 넘기는 통합 요구

| 대상 | 요구 |
|---|---|
| MP-05/06/07 | 조사 노드는 `NodeImplementation(module_id, implementation_version, prompt_version, mode=RunMode.LIVE, run=callable)`로 등록하고, 모델 호출은 `provider.request_model(...)`만 쓴다. 예산·시도는 자동으로 같은 `run_id`에 남는다 |
| MP-03 | `list_fixtures(reader=StoredFixtureReader.from_url(settings.fixtures_database_url))` 연결을 마쳤다. 실제 저장 경기 5건·외부 호출 0을 확인했다. `import_fixtures`의 실제 API 전송은 자격 증명 연결 뒤 |
| MP-08 | `main.py` 라우터 등록과 `/admin/metrics` 라우트·`select-run` 연결을 마쳤다. **지표가 필터를 `select-run`에 함께 내보내지 않으면 이동 시 필터를 유지할 수 없다.** 필터 유지가 필요하면 MP-08이 이벤트 payload를 넓혀야 한다(내가 MP-08 파일을 고치지 않았다) |
| MP-09 | 섹션 결과 표(`save_section_result`/`list_section_results`)와 승인 연결을 재사용한다. S1 본문도 같은 표에 `workflow_id=section_synthesis`로 저장하면 승인 경로가 그대로 열린다 |
| MP-10 | `runner.build_section_workflow(checkpointer=...)`에 `preview_dev` 범위 체크포인터를 넘기면 재개가 붙는다. 예산은 `RunBudget`을 실행 간에 넘겨 재개 시 남은 예산을 쓴다 |

## 제약으로 확인한 것

- 운영 DB에 `DROP SCHEMA`·`TRUNCATE`·`create_all/drop_all`·fixture 초기화를 실행하지 않았다.
  파괴적 준비는 전용 로컬 테스트 DB(`preview_mp04_test`)에서만 했다.
- `public` 영역 쓰기 권한이 실제로 막혀 있음을 재확인했다(`update public.app_user: denied`,
  `public.app_user rows = 8` 유지).
- 공용 Alembic 체인을 실행하지 않았다. `0004.upgrade()`는 명시적으로 실패한다.
- 새로 만든 좁은 역할 `preview_dev_fixture_ro`는 MP-03이 준비한 것을 그대로 썼다. 권한을
  넓히지 않았고, 조회기가 승인 범위 밖 표를 조인하던 문제는 MP-03이 조회를 좁혀 고쳤다.
- 비밀값은 어떤 산출물에도 넣지 않았다. 설정 객체의 `repr`에도 서비스 계정 JSON이 나오지
  않음을 검사로 고정했다(`test_live_settings_are_read_from_environment_without_printing_secrets`).
- 기존 문서 809건 삭제·대량 변경은 스테이징하지 않았다.
