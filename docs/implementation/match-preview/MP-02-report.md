# MP-02 구현 보고: 지속 실행 기록과 단독 검사 화면

**목표.** 사용자가 개발 도중에 각 호출의 자료 흐름을 직접 확인할 수 있어야 한다. 마지막
프리뷰 한 장을 기다리는 대신, 실행 하나를 열어 요청·원문 응답·정규화 변환·다음 입력과
결과 버전을 바로 본다. 이 보고서는 그 검사 경로를 실제로 지속 저장되는 기록 위에 올린
범위를 다룬다.

**가장 작은 변경.** 계약(`contracts.py`)을 먼저 고정하고, 그 계약으로 `preview_dev`에
실행·모듈 실행·시도·자료 스냅샷·결과 버전·원문 아티팩트를 저장한다. 관리자 화면은 그
저장 행만 읽는다. 외부 호출이 없는 **녹화된 모의 실행** 하나를 명시적 버튼으로 만들 수
있게 해서, 조사 모듈이 없어도 검사 경로를 지금 눈으로 확인한다.

## 실행 모델

| 항목 | 값 |
|---|---|
| 제공자 / 모델 | hive / `deepseek-ai/deepseek-v4.1-flash-1017` |
| 추론 강도 | max (유지, 변경 없음) |
| 프로필 | dsh-tui |
| 작업 디렉터리 | `/Users/woolee/benchmark` |
| 작업 ID / Dispatch | task_c0757368e934 / ctx_18bbef40f307 |
| 커밋 기준 HEAD (착수) | `3f154a6` |
| 커밋 기준 HEAD (보고 작성) | `03e5cc6` |

세션 메타데이터에서 확인한 값이며, 프롬프트에 적힌 문구로 대체하지 않았다. 모델·추론
강도·프로필을 변경하지 않았고, 다른 모델로 대체 실행하지 않았다.

## 범위와 경계

| 항목 | 이번 작업 | 근거 |
|---|---|---|
| 쓰기 대상 | `preview_dev` 스키마 새 테이블만 | `alembic/versions/0002_preview_runs.py`, `scripts/preview_dev_migrate.py` |
| 기존 `public` 영역 | 읽기만. DDL·DML 없음 | `scripts/preview_dev_status.py` (write to public.app_user denied) |
| 운영 배포·환경 변수 | 변경 없음 | Koyeb·Supabase 설정 접근하지 않음 |
| 외부 모델·API 호출 | 0회 (mock 파이프라인만) | `app/preview/demo_pipeline.py`, 실행 라벨 `mock` |
| 유료 Vertex 호출 | 없음 | 인증·모델 미확정, 이번 범위 아님 |
| 공용 Alembic head | 실행하지 않음 | `0002_preview_runs.upgrade()`가 공용 체인 실행 시 실패 |
| 기존 809건 삭제 | 건드리지 않음 | 선별 스테이징만 (아래 커밋 참조) |
| Plans.md·정책·설계 문서 | 수정하지 않음 | 조정자 소유 |

## 공통 계약 (후속 MP-03/04/08 인계용)

`app/preview/contracts.py` 한 파일에 고정했다. 필드를 바꾸려면 의존 작업과 이유를 먼저
보고해야 한다.

| 버전 | 값 |
|---|---|
| `CONTRACT_VERSION` | `mp02-1` |
| `PROVIDER_CONTRACT_VERSION` | `mp02-provider-1` |
| `MODULE_INPUT_VERSION` | `mp02-module-input-1` |
| `PREVIEW_DOCUMENT_VERSION` | `mp02-preview-1` |
| `INSPECTOR_VERSION` | `mp02-inspector-1` |
| `REGISTRY_VERSION` | `mp02-registry-1` |

`contract_versions()`가 같은 값을 딕셔너리로 돌려주고, 실행 행(`preview_runs.contract_versions`)에
그대로 저장된다. 그래서 나중에 계약이 바뀌어도 옛 실행이 어떤 계약으로 만들어졌는지 남는다.

### 고정한 계약

| 계약 | 요지 |
|---|---|
| `FixtureIdentity` | `fixture_id`, `league_id`, `season`, `home_team_id`, `away_team_id`, `kickoff_at`. 경기명은 표시용 |
| `FixtureCatalogQuery` | `league_id`, `date`, `timezone`. 아직 한 경기 식별자를 요구하지 않음 |
| `ExecutionContext` | `run_id`, `operation_kind`, `environment`, `mode`, `actor_id`, `config_version`, `limits`, `module_execution_id` |
| `SourceSnapshot` | `snapshot_id`, 범위, `source_kind`, provider, 수집·갱신 시각, 아티팩트 참조, 검증 상태 |
| `EvidenceClaim` | 종류(사실/외부 전망/API 예측/AI 해석), 채택·제외·상충, 참조 스냅샷 |
| `ModuleInput` | 경기, 스냅샷·선택 결과 참조, `input_hash`, 프롬프트·계약·구현 버전, 실제 전달값 |
| `ModuleResult` | 결과 버전, 실행 상태, 품질 상태, claims, coverage, diagnostics |
| `ModuleRegistration` | 모듈 ID·표시 이름·선행 관계·버전·검사 패널·구현 여부·실행 방식 범위 |
| `RequestSpec` / `ProviderResponse` | 제공자·논리 호출·모델·파라미터·`secret_refs`(이름만) / 상태·원문 참조·오류·사용량 |
| `AttemptTrace` | 시도 순번, 요청·응답 참조, 시작·종료·대기, 오류 분류, 사용량, 불명확 결과 |
| `PreviewDocument` | 독자용 필드만. 내부 진단·시도·비밀값 없음 |
| `ValidatedResearch` | 선택 결과·스냅샷, 채택·제외 claims, 핵심 근거 충족 여부 |
| `RunSummary` / `RunDetail` / `MetricsQuery` / `MetricsResult` | 관리자 조회 계약 |

세 축을 끝까지 분리했다.

- `environment`: dev / test / prod
- `mode`: live / replay / mock (실행 방식)
- `source_kind`: api / search (자료 출처)

운영(`prod`) 환경은 `live` 외 실행을 저장 단계에서 거부한다(`store.store_run`). 모의·재생
기록을 운영 성공률에 섞지 않기 위한 것이다.

## 저장 구조 (`preview_dev` 신규 테이블)

| 테이블 | 역할 |
|---|---|
| `preview_runs` | 실행 한 건. 방식·환경·상태·품질·배우·설정 버전·경기 표시·쓰기 범위·취소 표시 |
| `preview_module_executions` | 모듈 실행. 입력·전달값·시도 수·재시도 수·상태 |
| `preview_attempts` | 실제 시도 한 건. 논리 호출 + 순번, 제공자·모델·모드, 결과·HTTP·오류·사용량 |
| `preview_source_snapshots` | 자료 수집 한 건. `source_kind`, 수집·갱신 시각, 검증 상태 |
| `preview_results` | 결과 **버전**. `(module_execution_id, version)` 유일, 이전 버전 미덮어쓰기 |
| `preview_artifacts` | 비밀값 제거 원문·변환 결과. 요약·해시·기간 분리 보관 |
| `preview_write_audit` | 쓰기·취소 감사. 값이 아니라 동작·대상만 |

마이그레이션 이력은 기존 규칙대로 `preview_dev.schema_migrations(version, applied_at)`에
남긴다. `0002_preview_runs`가 추가되었다.

## 공통 저장 함수

| 함수 | 동작 |
|---|---|
| `store_run` | 실행 생성. 운영 환경 + 비-live 조합은 거부 |
| `start_module_execution` | 모듈 실행 생성. 입력과 `input_hash`를 함께 저장 |
| `append_attempt` | 시도 추가. 같은 `logical_call_id`의 다음 순번이 재시도 |
| `save_module_result` | 결과를 **새 버전**으로 저장. `supersedes_result_id`로 이전 버전 연결 |
| `update_module_delivery` | 다음 단계로 넘긴 값을 기록 |
| `get_run_detail` | 저장 행만 읽어 상세 구성. 외부 호출 없음 |
| `get_module_execution` | 다른 실행의 모듈 실행 ID는 `None` |
| `compare_result_versions` | 두 버전 비교. claims 추가·제거·변경, coverage 변화, `input_hash` 변경 여부 |
| `cancel_run` / `undo_report` | 범위가 한정된 취소와 사전 확인 |

## API

모든 경로는 `require_preview_admin`을 통과해야 하며 접두어는 `/api/v1/admin/preview`다.

| 메서드 | 경로 | 성격 |
|---|---|---|
| GET | `/runs` | 저장된 실행 목록. 외부 호출 0 |
| POST | `/runs/mock-demo` | 녹화된 모의 실행 생성. 관리자 명시 동작, 외부 호출 0 |
| GET | `/runs/{run_id}` | 실행 상세 + 검사 구조 |
| GET | `/runs/{run_id}/modules/{module_execution_id}` | 모듈 실행 하나. 다른 실행 ID는 404 |
| GET | `/runs/{run_id}/results/{module_execution_id}/versions` | 결과 버전 비교 |
| GET | `/runs/{run_id}/undo` | 취소하면 무엇이 지워지는지 |
| POST | `/runs/{run_id}/undo` | 이 실행 소유 기록 취소 |
| GET | `/runs/{run_id}/audit` | 쓰기·취소 감사 내역 |
| GET | `/registry` | 등록 모듈과 구현 여부 |
| GET | `/retention` | 보관 정책과 현재 상태 |
| POST | `/retention/expire` | 만료 처리 1회 실행(자동 스케줄러 아님) |

## 모듈 등록부 상태

`app/preview/registry.py` 한 곳에서만 등록한다. 자동 플러그인 로더는 없다.

| 모듈 | 표시 이름 | 구현 | 실행 방식 | 화면 표시 |
|---|---|---|---|---|
| `D0` | 경기·API 자료 준비 | 아니오 | live/replay | 사용할 수 없음 |
| `R1` | 경기력·주목 선수 조사 | 아니오 | live/replay | 사용할 수 없음 |
| `R2` | 부상·결장 영향 조사 | 아니오 | live/replay | 사용할 수 없음 |
| `R3` | 배당·외부 전망 조사 | 아니오 | live/replay | 사용할 수 없음 |
| `S1` | 프리뷰 종합 | 아니오 | live/replay | 사용할 수 없음 |
| `mock_demo` | 기록 시연 (모의) | 예 | **mock only** | 실행 가능 |

미구현 모듈에는 `unrunnable_reason`이 붙고 화면은 `사용할 수 없음`으로 표시한다. 모의
시연은 이름·라벨·`mode_scope` 모두 mock으로 고정되어 live 성공으로 읽히지 않는다.

## 검사 화면

`frontend/src/features/match-preview`로 옮겼다.

| 파일 | 역할 |
|---|---|
| `types.ts` | 서버 계약과 같은 이름의 자료형 |
| `api.ts` | 공통 `previewRequest` 위의 조회·생성·취소 클라이언트 |
| `PreviewRunsView.vue` | 실행 목록(모드·환경·상태·모듈·시도) + 모의 실행 생성 + 검사 열기 |
| `RunInspector.vue` | 실행 요약, 실행 방식 배너, 모듈 목록, 보관·취소 영역 |
| `ModuleResultPanel.vue` | 요청·원문 응답·정규화 변환·다음 입력 **네 탭** |
| `RunVersionCompare.vue` | 결과 버전 비교와 입력 불일치 경고 |

라우터는 `/admin/runs` → `features/match-preview/PreviewRunsView.vue`로 바꿨다. 기존
`views/PreviewRunsView.vue`와 그 로그아웃 테스트는 삭제하지 않고 이동했다(테스트 7건은
그대로 통과). MP-01 동작은 유지된다.

네 탭의 출처:

| 탭 | 보여주는 값 |
|---|---|
| 요청 | 논리 호출, 제공자·모델, 프롬프트·계약 버전, `secret_refs`(이름), 파라미터, 비밀값 제거 요청 본문 |
| 원문 응답 | 결과·HTTP 상태·오류 분류·사용량, 비밀값 제거 수신 본문, 만료 시 만료 표시 |
| 정규화 변환 | 결과 버전·상태·품질·입력 해시, 채택·제외·상충 사유가 붙은 claims, coverage, 내부 진단 |
| 다음 입력 | 전달 대상, 선택한 결과 ID와 버전(최신 여부), 실제 전달 값 |

화면에 표시한 스타일은 MP-01에서 확정한 Hallmark 토큰(`frontend/src/styles/app.css`)을
그대로 쓴다. 새 팔레트·폰트를 도입하지 않았다.

## 수용 기준별 증거

| 계획 §6 MP-02 수용 기준 | 증거 |
|---|---|
| `test_trace_survives_restart` | [evidence/22](evidence/22-mp02-backend-focused.txt), [evidence/26](evidence/26-mp02-restart-persistence.txt) (실제 백엔드 재시작 후 같은 실행·버전·원문) |
| `test_trace_redacts_secrets` | evidence/22, [evidence/26](evidence/26-mp02-restart-persistence.txt) |
| `test_version_compare_keeps_old_result` | evidence/22, 화면 [ui-06](evidence/ui-06-inspector-next-input.png) |
| `test_read_does_not_call_provider` | evidence/22, 브라우저 외부 요청 0건 [evidence/24](evidence/24-mp02-browser.txt) |
| `test_expired_artifact_keeps_summary` | evidence/22 |
| `test_registered_module_uses_generic_inspector` | evidence/22 |
| 등록되지 않은 모듈도 공통 검사 | evidence/22 (`unregistered_module` 케이스) |
| 관리자 경계 (401/403) | evidence/22 |
| 범위 한정 undo·충돌 | evidence/22, 실제 개발 영역 [evidence/27](evidence/27-mp02-scoped-undo.txt) |
| 마이그레이션 = 모델 | evidence/22 (`test_migration_creates_the_tables_the_models_use`) |
| 프론트 네 탭·모드 표시·버전 비교 | [evidence/23](evidence/23-mp02-frontend.txt), [evidence/24](evidence/24-mp02-browser.txt) |

### 실행 명령과 결과

| 명령 | 결과 |
|---|---|
| `.venv/bin/python -m pytest tests/preview -q` | 141 passed |
| `.venv/bin/python -m pytest tests/preview/test_run_store.py tests/preview/test_inspection_api.py tests/preview/test_retention.py tests/preview/test_migration_schema.py -q` | 37 passed, exit 0 |
| `npm --prefix frontend run test:unit` | 3 files, 24 tests passed |
| `npm --prefix frontend run type-check` | 통과 (출력 없음) |
| `npm --prefix frontend run build` | 빌드 성공 |
| `npx playwright test --config=playwright.mp02.config.ts` | 3 passed (격리 환경, 실제 백엔드·DB) |
| `.venv/bin/python scripts/preview_dev_migrate.py` | `0002_preview_runs: applied` |
| `.venv/bin/python scripts/preview_dev_status.py` | `result: PASS` |

계획 §6이 요구한 backend 세 파일의 수용 테스트를 모두 포함한다. 마이그레이션 DDL↔모델
일치 검사(`test_migration_schema.py`)는 운영 개발 환경에서 "테이블은 있는데 앱이 못 쓰는"
상태를 미리 막기 위해 추가했고, 실패 시 사용자가 보는 결과는 검사 화면이 열리지 않는
것이므로 수용 기준과 직접 연결된다.

## 브라우저 확인

사용자의 실제 로그인 세션과 실제 개발 서버를 건드리지 않기 위해 격리 환경을 썼다.

| 항목 | 값 |
|---|---|
| 백엔드 | `127.0.0.1:8010` (전용 로컬 테스트 DB `preview_mp02_ui_test`) |
| 프론트 | `127.0.0.1:5273` (`VITE_BACKEND_TARGET=http://127.0.0.1:8010`) |
| 계정 | 테스트 DB에만 만든 합성 ADMIN(`mp02-ui-admin@example.test`) |
| 확인 | 모의 실행 생성 → 검사 열기 → 네 탭 → 버전 비교 → 비밀값 부재 → 외부 요청 0 |

사용자 자격 증명은 요구하지 않았고, 증거 파일·로그에 합성 비밀번호도 남기지 않았다([evidence/24](evidence/24-mp02-browser.txt), 스크린샷 ui-06·ui-07). 화면 캡처는
`model does not declare image input` 제약으로 내가 직접 판독하지 못했다. 그래서 렌더링
검증은 Playwright 단언(testid 기반 텍스트·가시성)으로 했고, 픽셀 인상은 주장하지 않는다.

## 실제 개발 영역 확인

사용자가 이미 로그인한 세션에서 바로 열 수 있도록, 실제 `preview_dev`에 **작업 소유로
명확히 표시된** 모의 실행을 하나 남겼다.

| 항목 | 값 |
|---|---|
| 실행 ID | `e091436e-074d-44b9-983b-1fab31acf9c6` |
| 라벨 | `MP-02 검증 실행 (작업 소유, mock) · inspect-keep` |
| 방식 / 환경 | mock / dev |
| 상태 | succeeded / pending |
| 결과 버전 | 1, 2 |
| 시도 / 아티팩트 | 1 / 3 |
| 확인 주소 | http://127.0.0.1:5173/admin/runs → `e091436e` 검사 |

두 번째 실행(`c4e95076-…`, 라벨 `undo-proof`)은 **취소 시연용**으로 만들었다가 그 실행만
취소했다. 남은 실행 행은 `cancelled` 상태로 감사 표시가 남아 있다. 다른 실행·기존 자료는
건드리지 않았다.

### 쓰기·취소 범위

| 항목 | 내용 |
|---|---|
| 쓰기 스키마 | `preview_dev`만 (`write_scope='preview_dev'`) |
| 취소 대상 | 해당 실행 ID로 만들어진 모듈 실행·시도·결과·스냅샷·아티팩트 |
| 취소 제외 | `preview_runs` 행, `preview_write_audit` 감사 행 |
| 충돌 조건 | 같은 모듈 실행에 **다른 실행**이 남긴 결과 버전이 있으면 409, 아무것도 지우지 않음 |
| 이미 취소됨 | 409 |
| 기존 경기·계정 | 처음부터 쓰지 않으므로 대상이 아님. 취소 후 `public.app_user` 8행 그대로 |

## 보관 기간

| 항목 | 값 |
|---|---|
| 원문(비밀값 제거) | 30일 |
| 구조화 실행·품질·지표 기록 | 180일 (이 단계에서는 삭제 경로 없음, 값만 고정) |
| 만료 효과 | 원문 본문만 삭제. 요약·해시·기간·실행·결과는 유지. 재생 불가 표시 |
| 자동 삭제 | 없음. `POST /retention/expire`로 명시 실행만 |

만료는 "읽기 실패"와 다른 상태(`status: expired`)로 표시한다. 화면은 만료 사유를 문장으로
보여주고, 만료 뒤에도 실행·결과·버전 비교는 그대로 열린다.

## 비밀값 처리

저장 **전에** 제거한다(조회 시 가리는 방식이 아님).

| 방식 | 예 |
|---|---|
| 키 이름 기준 | `authorization`, `api_key`, `x-goog-api-key`, `token`, `secret`, `password`, `cookie` 등 |
| 본문 문자열 | `Bearer …`, `token=…`, `apikey: …` |
| DSN | `postgresql://user:***@host` |
| 호출자 제공 값 | 저장 호출에 넘긴 실제 비밀값 치환 |

모의 요청·응답에 카나리 문자열을 넣어 실제로 지워지는지 확인했다. 실제 개발 DB의 7개
테이블을 전수 스캔해 카나리 0건, `[REDACTED]` 표시 존재를 확인했다.

## 인계 (MP-03/04/08)

| 인계 항목 | 값 |
|---|---|
| 계약 파일 | `app/preview/contracts.py` |
| 저장 함수 | `app/preview/store.py` (`store_run`, `append_attempt`, `save_module_result`, `get_run_detail`, `compare_result_versions`) |
| 원문·보관 | `app/preview/artifacts.py`, `app/preview/retention.py` |
| 검사 구조 | `app/preview/inspection.py` |
| 등록부 | `app/preview/registry.py` (등록은 이 파일 한 곳) |
| 라우터 | `app/api/v1/preview_admin.py` (통합 소유자만 편집) |
| 마이그레이션 | `alembic/versions/0002_preview_runs.py` + `scripts/preview_dev_migrate.py` |
| 프론트 공유 파일 | `frontend/src/features/match-preview/{types,api}.ts`, `RunInspector.vue`, `ModuleResultPanel.vue` |

새 모듈을 붙이는 방법: `registry.py`에 `ModuleRegistration`을 추가하고 `implemented=True`로
바꾼 뒤, `store.save_module_result`로 결과를 저장한다. 검사 화면은 등록부를 읽으므로 화면
코드를 고치지 않아도 네 탭이 그대로 나온다. 전용 표현이 필요할 때만 `inspector_panel` 값을
바꿔 별도 패널을 붙인다.

## 수용한 것 / 보류한 것

**수용(이번 범위에서 끝남):** 지속 기록, 요청·원문·변환·다음 입력 네 탭, 결과 버전 보존과
비교, 비밀값 제거, 보관 기간 만료 표시, 공통 모듈 검사, 등록부, 관리자 경계, 범위 한정
undo와 충돌 처리, 감사 표시, 앱 재시작 후 동일 실행 유지, GET 무외부호출.

**보류(다음 작업):**

| 항목 | 이유 |
|---|---|
| D0/R1/R2/R3/S1 실제 실행 | MP-03~MP-09 소유. 지금은 등록만, 실행 불가로 표시 |
| 실제 모델·API 호출과 live 표시 | MP-04. Vertex 인증·모델 미확정이므로 live 성공을 주장하지 않음 |
| 프리뷰 반영 탭 | S1·V1이 생기는 MP-09 이후 |
| 지표 표·그래프 | MP-08. `MetricsQuery`/`MetricsResult` 계약만 고정 |
| LangGraph 실행·체크포인트 | 사용자 선택 문서(`docs/decisions/2026-11-10-preview-framework.md`)에 따라 후속. 이번 저장 구조는 그 위에서 재사용 가능 |
| 모듈 버전 사용자 승인 기록 | 정책에 추가됨. 승인 대상 모듈이 생기는 MP-05 이후에 붙이는 것이 자연스러움 |
| 만료 자동 처리 스케줄러 | 운영 보관 정책 확정 전 금지 |
| 180일 구조화 기록 삭제 경로 | 정책 값만 고정, 실행 시점 미확정 |

## 제약으로 확인한 것

- 운영 DB에 `DROP SCHEMA`·`TRUNCATE`·`create_all/drop_all`·fixture 초기화를 실행하지 않았다.
  파괴적 준비는 전용 로컬 테스트 DB(`preview_mp01_test`, `preview_mp02_ui_test`)에서만 했다.
- 기존 `public` 영역 쓰기 권한이 실제로 막혀 있음을 `preview_dev_status.py`로 재확인했다.
- 공용 Alembic 체인을 실행하지 않았다. `0002`의 `upgrade()`는 공용 체인 실행 시 명시적으로
  실패하므로, 실수로 실행해도 `public`에 객체가 생기거나 "적용됨"으로 남지 않는다.
- 기존 운영 계정 로그인 경로는 그대로다. 새 인증 방식·새 계정을 만들지 않았다.
- 테스트는 계획이 지정한 수용 기준과 변경 영향에만 두었다. URL 형태·DB 종류·권한 조합의
  완전 탐색은 추가하지 않았다.
- `docs/decisions/2026-11-10-preview-framework.md`(LangGraph·모듈 승인 결정)는 이번
  작업 범위 밖이며 수정하지 않았다.

## 남긴 환경

| 위치 | 상태 |
|---|---|
| 백엔드 `127.0.0.1:8000` | 실행 중, 실제 개발 DB 연결, health `database: ok / identity: ok` |
| 프론트 `127.0.0.1:5173` | 실행 중, `:8000` 프록시, 기존 로그인 유지 |
| 확인용 백엔드 `127.0.0.1:8010` | 격리 테스트 DB(`preview_mp02_ui_test`). 저장소·개발 DB와 무관 |
| 확인용 프론트 `127.0.0.1:5273` | `:8010` 프록시 |

사용자는 이미 로그인한 세션으로 http://127.0.0.1:5173/admin/runs 를 열어 `e091436e`
실행의 검사 화면을 바로 볼 수 있다. 자격 증명을 새로 요구하지 않는다.
