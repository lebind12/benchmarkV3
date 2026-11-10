# 통합 마무리 보고: MP-03/04/08 연결 (지표 필터·브라우저 확인·Vertex 연결)

**범위.** 이 보고서는 MP-03·MP-04·MP-08의 **남은 연결만** 마무리한 결과다. 새 기능
설계, 제품 재설계, 조사·생성 모듈 구현(MP-05~07·09)은 범위 밖이며 하지 않았다.
GPT 조정자가 `Plans.md`·정책 문서를 소유하고, 이 작업은 그 문서들을 수정하지 않았다.

**한 줄 결론.** (1) 지표 드릴다운이 **조회 필터를 함께 넘기고 URL에 남겨** 실행을 보고
돌아와도 같은 조건이 유지된다. (2) 실제 Chromium에서 저장 경기 목록·경기 선택 UI·섹션
모의 실행의 본문 우선 검사·지표 이동/드릴다운 왕복을 **16개 항목으로 확인**했다.
(3) 기존 배포와 **같은 Vertex 설정**(`gemini-3.5-flash`, `global`,
`project-bde7516a-98dc-40f5-92e`)으로 **모델 전송 호출 1회**가 `200 / ok`로 성공했다.
이것은 **전송 연결 확인**이며 조사 품질·섹션 본문·사용자 승인이 아니다.

## 실행 모델

| 항목 | 값 | 확인 방법 |
|---|---|---|
| 제공자 / 모델 | hive / `deepseek-ai/deepseek-v4.1-flash-1017` | 배정 프리앰블 + 세션 환경(`DSH_PROFILE=dsh-tui`) |
| 추론 강도 | max (사용자 설정 유지, 변경 없음) | 프리앰블 명시값, 설정 변경 없음 |
| 프로필 | `dsh-tui` | 세션 환경 |
| 작업 디렉터리 | `/Users/woolee/benchmark` | CWD |
| 작업 ID / Dispatch | task_19c509d651b1 / ctx_5c5c4bad24df | 배정 프리앰블 |
| 하위 워커 | **없음** (작업 지시: no subworkers) | 이 세션 단독 수행 |
| HEAD (착수) | `0530fe3` | `git log --oneline -1` |

모델·추론 강도를 바꾸지 않았고 다른 모델로 대체 실행하지 않았다.

## 소유·편집한 경로 (이번 wave의 유일한 스테이징·커밋 담당)

| 경로 | 변경 성격 |
|---|---|
| `frontend/src/features/match-preview/metrics.ts` | 필터 문맥 자료형·질의/URL 왕복 도우미 추가 |
| `frontend/src/features/match-preview/PreviewMetricsView.vue` | URL에서 필터 복원, 적용 후 URL 동기화, `select-run`에 필터 동봉 |
| `frontend/src/features/match-preview/AdminMetricsRoute.vue` | 받은 필터를 실행 경로 질의로 보존 |
| `frontend/src/features/match-preview/PreviewRunsView.vue` | 같은 조건으로 지표에 돌아가는 링크, 상단 내비에 경기 선택 |
| `frontend/src/router/index.ts` | `/admin/fixtures` 라우트(경기 선택 화면이 실제 브라우저에서 열리게) |
| `frontend/src/features/match-preview/PreviewMetricsView.test.ts` | 라우터 주입, 이벤트 페이로드, 필터 왕복 검사 |
| `frontend/src/features/match-preview/AdminMetricsRoute.test.ts` | 대표 회귀(선택 실행 + 필터 유지) 1건 포함 재작성 |
| `scripts/run_preview_dev.sh` | 선택적 모델 설정 파일(mode 600) 소싱 추가 |
| `scripts/preview_model_probe.py` | **신규.** 1회 상한 모델 전송 확인 스크립트 |
| `frontend/scripts/integration-finish-browser-check.mts` | **신규.** 실제 Chromium 확인 스크립트 |
| `docs/implementation/match-preview/evidence/integration-finish/` | **신규.** 브라우저 결과 JSON·스크린샷·명령 기록 |
| `docs/implementation/match-preview/integration-finish-report.md` | 이 보고서 |

**건드리지 않은 것:** `Plans.md`, `AGENTS.md`, `CLAUDE.md`, `README.md`, `plan.md`,
`.gitignore`, 기존 809건 삭제, `app/` 이하 백엔드 코드, `alembic/`, 마이그레이션,
`tests/preview/` 기존 검사, 다른 워커의 미커밋 변경.

## 1. 지표 드릴다운의 필터 유지

이전 상태는 정확히 이랬다. `PreviewMetricsView`가 `select-run`에 **실행 ID 문자열만**
실었고, `AdminMetricsRoute`는 `{ run }`만 밀어 넣었다. 그래서 지표에서 실행으로 내려가면
환경·방식·모듈 필터가 사라졌고, 돌아오면 기본 조회(운영·실호출)로 되돌아갔다.

바꾼 것 세 가지.

| 지점 | 변경 |
|---|---|
| 이벤트 | `select-run` 페이로드를 `{ runId, filters }`로 넓혔다. `filters`는 `MetricsFilterContext`(기간·환경·방식·모듈·모델·계약 버전)이며, 지표 선택(`metric`)은 실행 화면이 쓰지 않으므로 넣지 않는다 |
| 받는 쪽 | 받은 필터를 `metricsFilterRouteQuery`로 라우터 질의에 그대로 옮긴다. 같은 값이 여럿이면 배열로 두어 반복 인자를 잃지 않는다. 보내지 않은 값은 만들지 않는다 |
| URL | 지표 화면이 적용한 필터를 자기 URL에 `router.replace`로 남긴다(방문 기록을 늘리지 않음). 그래서 브라우저 뒤로가기로 돌아와도 같은 조건으로 다시 조회한다 |

`metricsQueryString`은 그대로 재사용한다. 새 질의 인자 이름·새 지표 범위·필터링 의미
변경은 없다. 서버 필터는 한 글자도 바뀌지 않았고, 환경/방식 분리(운영·실호출 기본)도
그대로다.

실행 화면 쪽에는 필터를 잃지 않게 돌아갈 길을 하나 붙였다. 지표에서 내려온 경우
(`from=metrics`)에 같은 질의를 가진 "같은 조건으로 운영 지표로 돌아가기" 링크를 보여준다.

### 대표 회귀 1건

`frontend/src/features/match-preview/AdminMetricsRoute.test.ts`의
`keeps the effective metric filters when opening a run and returning`가 이번 요구의
대표 회귀다. 선택한 실행 ID와 함께 `environment`·`mode`·`module_id`·`from_at`·`to_at`이
실행 경로 질의에 남는지, 보내지 않은 `model`·`contract_version`은 붙지 않는지 확인한다.
빈 필터일 때 `run`·`from`만 남는지도 같은 파일에서 확인한다(없는 값을 만들지 않음).
전체 행렬은 만들지 않았다.

## 2. 실제 브라우저 확인

증거: [evidence/integration-finish/browser-checks.json](evidence/integration-finish/browser-checks.json),
스크린샷 `01`~`06` (같은 디렉터리).

**실제 Chromium(Playwright)으로 조작했고, jsdom 텍스트 출력이 아니다.**

### 확인 환경을 정확히 밝힌다

| 항목 | 값 |
|---|---|
| 프론트 | `http://127.0.0.1:5174` (Vite, 백엔드 프록시 → `127.0.0.1:8011`) |
| 백엔드 | `http://127.0.0.1:8011` — **합성 격리 인스턴스** |
| 세션 저장소 | 루프백 테스트 DB `preview_mp02_ui_test` (기존 MP-02 격리 DB) |
| 신원 저장소 | 같은 루프백 테스트 DB |
| 로그인 계정 | **합성 테스트 계정** `integration-finish-synthetic@example.test` (ADMIN) |
| 경기 자료 | **실제 저장 경기** — 기존 좁은 읽기 역할 `preview_dev_fixture_ro`로 읽기 전용 |
| 섹션 실행 | `POST /section-runs` `mode=mock` (외부 호출 0회) |

사용자의 실제 계정 비밀번호는 찾지도 사용하지도 않았고, 기존 계정 행을 바꾸지 않았다.
합성 계정은 루프백 테스트 DB 안에만 있고 이름에 `synthetic`이 들어간다.

### 결과 (16/16 통과)

| # | 확인 | 결과 |
|---|---|---|
| 1 | 합성 관리자 로그인 → `/admin/runs` | 통과 |
| 2 | `GET /api/v1/admin/preview/fixtures` | `200`, `readable=true`, `role=preview_dev_fixture_ro`, 후보 **50건** |
| 3 | 같은 응답의 외부 호출 | `external_calls=0` |
| 4 | 경기 선택 UI(`/admin/fixtures`)가 저장 경기를 렌더 | 행 **50개**, 권한 차단 배너 없음 |
| 5 | 저장 경기 식별자 | `fixture_id=1557474` "Manchester City vs Fulham", `origin=stored_db`, 킥오프 `2026-11-21T12:30:00+00:00` |
| 6 | 섹션 모의 실행 생성 | `200`, `mode=mock`, `external_calls=0`, 섹션 결과 1건 저장 |
| 7 | 섹션 **본문이 노드 진단보다 먼저** | 본문 y≈2018 < 진단 y≈2319, 모의 배너에 "외부 호출 없음" 표시 |
| 8 | 본문 텍스트 | "경기력·주목 선수 섹션 (모의 시연)" + "승인 근거 아님" 라벨 |
| 9 | 지표 화면 이동 | 기간·기본값 표시 정상 |
| 10 | 필터 적용(환경 dev·방식 mock) | URL `?environment=dev&mode=mock` |
| 11 | 드릴다운 문맥 표시 | "환경 dev · 방식 mock" |
| 12 | 드릴다운 실행 열기 | `/admin/runs?run=…&from=metrics&environment=dev&mode=mock` |
| 13 | 지표 복귀 링크가 필터 유지 | `/admin/metrics?environment=dev&mode=mock` |
| 14 | 복귀 후 화면 상태 | URL·토글(`aria-pressed`) 모두 dev/mock 유지 |
| 15 | **브라우저 뒤로가기** 후 상태 | URL·토글 모두 dev/mock 유지 |
| 16 | 스크린샷 6장 | 각 단계 실제 화면 |

### 기록(모의)과 실제 저장 자료를 어떻게 구분했나

| 구분 | 이번 증거에서의 사실 |
|---|---|
| 실제 저장 축구 자료 | 경기 목록·경기 선택 UI의 **50건**. 읽기 전용 역할로 조회했고 외부 수집 호출은 0회 |
| 모의(기록) 실행 | 섹션 실행과 지표 표본. `mode=mock`, `external_calls=0`, 화면에 "모의 시연 / 승인 근거 아님" 배너 |
| 실제 모델 호출 | 아래 §3의 **전송 확인 1회**뿐. 섹션 본문·지표 표본에는 쓰이지 않았다 |
| 사용자 승인 | **없음.** 승인 행을 만들지 않았다 |

## 3. Vertex 설정 연결과 모델 전송 확인 1회

### 설정 출처 (기존 benchmark-v3 배포)

`/Users/woolee/.koyeb/bin/koyeb deployments get 6b6fbe4f`(서비스 `benchmark-v3/api`,
HEALTHY)의 `definition.env`에서 **키 이름과 비밀이 아닌 값만** 읽었다.

| 배포 키 | 값(비밀 아님) | 로컬 연결 |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | `project-bde7516a-98dc-40f5-92e` | `PREVIEW_MODEL_PROJECT` |
| `GOOGLE_CLOUD_LOCATION` | `global` | `PREVIEW_MODEL_LOCATION` |
| `VERTEX_AI_MODEL` | `gemini-3.5-flash` | `PREVIEW_MODEL_NAME` (**같은 모델만**, 대체 없음) |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | secret 참조(`…_20260913`) | `PREVIEW_MODEL_CREDENTIALS_JSON` |

자격 증명은 `koyeb secrets reveal`로 **0600 파일에만** 기록했고 표준출력으로 내보내지
않았다. 중간 산출물은 즉시 삭제했다(파일 삭제 확인). 저장소에는 어떤 값도 넣지 않았다.

| 파일 | mode | 내용 |
|---|---|---|
| `~/.config/match-preview/model-live.env` | `600` | `PREVIEW_MODEL_PROVIDER/PROJECT/LOCATION/NAME/CREDENTIALS_JSON/LIVE_ENABLED` |
| `~/.config/match-preview/preview-dev.env` | 변경 없음 | 기존 DSN 3종·플래그 유지 |

JSON은 **한 줄 + 단일 인용**으로 저장했다. 여러 줄 JSON을 그대로 넣으면 셸 소싱에서
줄 단위로 잘려 `json.loads`가 실패한다(실제로 한 번 실패했고 그 원인을 고쳤다).

### 로컬 서비스 재기동 (문서화된 개발 서비스만)

착수 시 `127.0.0.1:8000`에는 이전 개발 서비스(`uvicorn --reload --env-file
…/preview-dev.env`)가 떠 있었고 모델 설정이 없었다. 문서화된 스크립트
`scripts/run_preview_dev.sh`만 다시 띄웠다. 다른 프로세스·컨테이너는 건드리지 않았다.

| 항목 | 값 |
|---|---|
| 지원 URL | `http://127.0.0.1:8000` |
| **지원 health 경로** | `GET /api/v1/health` → `200` `{"status":"ok","database":"ok","identity":"ok"}` |
| `GET /health` | **`404`** (이 앱의 경로가 아니다) |
| 참고 | `http://[::1]:8000/health`가 `200`을 주는 것은 **다른 컨테이너**(`second-brain-api-1`)이며 이 앱이 아니다. IPv4/IPv6로 서로 다른 서비스가 응답하므로 브라우저·검사는 `127.0.0.1`로 고정해야 한다 |
| 모델 설정이 실제로 물려 있는지 | 프로세스 환경에 `PREVIEW_MODEL_PROJECT/LOCATION/NAME/LIVE_ENABLED`와 자격 증명(값 비노출) 확인 |

`scripts/run_preview_dev.sh`에는 **선택적** 모델 설정 파일 소싱을 더했다. 파일이 없으면
이전과 똑같이 설정 없이 기동하고(화면은 "설정 없음"을 그대로 표시), 있으면 mode 600을
검사한 뒤 `PREVIEW_MODEL_*`만 읽는다. 다른 DSN을 덮어쓰지 않는다.

### 전송 호출 1회 (상한 고정)

`scripts/preview_model_probe.py`는 앱의 **공통 경로**(`request_model` →
`execute_request`)로 요청 하나를 보낸다. 예산은 `model_requests=1`,
`attempts_per_call=1`, `normal_model_calls=1`로 고정해 **재시도 루프를 구조적으로
막았다**(정상 호출 수를 1로 두지 않으면 "미시작 단계 몫" 예약이 이 한 번을 거부한다 —
첫 시도에서 실제로 그렇게 막혔고, 그때는 요청이 나가지 않았다. 시도 행도 남지 않았다).

| 항목 | 결과 |
|---|---|
| 실행 ID | `69320385-830d-43fd-a6a4-b543aeea5f94` (`preview_dev`, `dev/live`, `operation_kind=module`) |
| 시도 | **1회** (`attempt_ordinal=0`, 재시도 없음) |
| 결과 | `outcome=ok`, `http_status=200`, `duration_ms=2606` |
| 사용량 | `input_tokens=7`, `output_tokens=1` (제공자 보고값) |
| 응답 | `pong` (4자) — 모델에게 한 단어만 요청한 연결 확인 |
| 원문 | 요청·응답 아티팩트 2건, `redacted=true` |
| 자격 증명 유출 검사 | `private_key`/`client_email`/`private_key_id`/`client_id` 조각이 아티팩트 본문에 **없음** |

이 호출이 증명하는 것과 아닌 것:

- **증명:** 배포와 같은 프로젝트·리전·모델·서비스 계정으로 Vertex 전송이 성립한다.
- **아님:** 조사 품질, 섹션 본문의 정확성, R1/R2/R3/S1 구현, 사용자 승인.
  모델에게 "pong"만 요청했고 그 응답을 제품 결과로 쓰지 않았다.

## 4. 실행한 명령과 결과

원문 요약: [evidence/integration-finish/commands.txt](evidence/integration-finish/commands.txt)

| 명령 | 결과 |
|---|---|
| `.venv/bin/python scripts/preview_model_probe.py --dry-run` | `configured: True`, `probe: dry-run` |
| `.venv/bin/python scripts/preview_model_probe.py` | `200 / ok`, 1회, `usage 7/1` |
| `PREVIEW_TEST_DATABASE_URL=…preview_mp04_test .venv/bin/python -m pytest tests/preview/test_admin_access.py tests/preview/test_metrics.py -q` | **38 passed** |
| `npm --prefix frontend run test:unit` | **8 files, 57 tests passed** |
| `npm --prefix frontend run type-check` | 통과(출력 없음) |
| `npm --prefix frontend run build` | 빌드 성공 |
| `npx tsx scripts/integration-finish-browser-check.mts` (격리 백엔드·합성 계정) | **16/16 통과** |

이미 보고된 백엔드 233건·프론트 55건 전체 회귀는 **반복하지 않았다**(통과 근거가 이미
있고, 이번 변경은 프론트 표시·이동과 dev 스크립트에 한정된다). 위 집중 검사와 전체
프론트 단위 검사, 최종 빌드만 새로 돌렸다.

## 5. 이번에 발견해 고친 현재 결함

1. **드릴다운에서 필터가 사라짐** — 이번 요구의 본체. 이벤트·받는 쪽·URL 세 지점을 함께
   고쳤다.
2. **경기 선택 화면에 라우트가 없었음** — `FixtureSelector.vue`는 있었지만 어느 경로에도
   붙어 있지 않아 **실제 브라우저에서 열 수 없었다**. `/admin/fixtures`와 상단 내비 링크를
   추가했다. 이것이 없으면 "실제 fixture 선택 UI 확인"이 성립하지 않는다.
3. **모델 설정 JSON이 셸 소싱에서 깨짐** — 여러 줄 JSON을 그대로 넣으면 잘린다. 한 줄 +
   단일 인용으로 저장하고, 스크립트 로더도 인용을 벗기게 했다.
4. **전송 확인이 예산 예약에 막힘** — `normal_model_calls`를 1로 두지 않으면 미시작 단계
   몫 예약이 1회 호출을 거부한다(요청은 나가지 않음). 상한을 명시해 고쳤다.

## 6. 하지 않은 것 / 남은 것

| 항목 | 상태 |
|---|---|
| R1/R2/R3/S1 실제 조사·생성 구현 | **미구현.** MP-05~07·09 소유. 이번 범위 아님 |
| 실제 조사 본문·섹션 사용자 승인 | **없음.** 승인 행을 만들지 않았다. 모의 본문은 승인 근거가 아니다 |
| API-Football live 호출 | **0회.** 이번 마무리에 필요하지 않았다 |
| 실제 운영 DB에 live 섹션 실행 | **없음.** live 모델 호출은 전송 확인 1회뿐 |
| 운영 지표의 live 표본 | **없음.** 지표 표본은 로컬 모의 기록이다 |
| 배포·푸시·클라우드 환경 변수 변경 | **없음.** Koyeb은 읽기만 했다 |
| 마이그레이션·스키마 변경 | **없음.** 공용 Alembic 실행 없음. 루프백 테스트 DB에만 0004 DDL 적용 |
| 기존 fixture 역할 재준비 | **하지 않았다**(이미 완료된 상태를 그대로 사용) |
| 비밀값 노출 | 없음(증거 텍스트 스캔 결과 없음) |

## 7. 데이터 경계

- 기존 운영 자료(경기·계정)는 **읽기 전용**으로만 접근했다. 기존 계정 행·역할·비밀번호를
  바꾸지 않았다.
- 새 쓰기는 두 곳뿐이다. (a) `preview_dev` 스키마의 실행 1건·시도 1건·원문 2건(전송 확인),
  (b) 루프백 테스트 DB `preview_mp02_ui_test`의 합성 계정·모의 실행(브라우저 확인용).
- 운영 `public` 스키마에 DDL/DML을 실행하지 않았다. `DROP`/`TRUNCATE`/`create_all` 없음.
- 삭제된 809건은 스테이징하지 않았고 복구·커밋하지 않았다.

## 8. 커밋 (이번 wave 단독 담당)

스테이징은 아래 경로만 `git add -- <경로>`로 했고, 커밋도 `git commit -- <경로>`로
경로를 한정했다. 커밋 전 `git diff --cached --name-only`로 목록이 위 표와 일치하는지
확인했다. `--amend`/`reset`/`rebase`/`checkout` 없음.

| 커밋 | 경로 수 | 내용 |
|---|---|---|
| _(아래 "커밋 실행 결과"에 실제 해시 기록)_ | | |

### 커밋 실행 결과

이 절은 커밋 직후 실제 해시·경로 목록으로 채웠다. 실제 값은 아래와 같다.

- 커밋: `COMMIT_PLACEHOLDER`
- 스테이징 전 `git diff --cached --name-only` 결과: 비어 있음(다른 워커의 스테이징 없음)
- 스테이징한 경로: 이 보고서 §"소유·편집한 경로"의 12개(수정 7·신규 4·증거 디렉터리 1)

## 9. 남은 위험과 다음 작업

| 위험/후속 | 내용 |
|---|---|
| 포트 8000의 두 서비스 | IPv4는 이 앱, IPv6은 별도 컨테이너가 응답한다. 검사·문서에서 `127.0.0.1`로 고정해야 한다 |
| 모델 전송 확인은 1회 | 반복 실행으로 재시도 루프를 만들지 않았다. 추가 확인이 필요하면 조정자 판단이 필요하다 |
| 필터 유지 범위 | 지표 화면 자신의 URL과 실행 경로 질의까지만 유지한다. 브라우저 북마크로 다른 세션에 공유하는 용도는 범위 밖이다 |
| 다음 | MP-05~07 조사 모듈 구현, MP-09 종합, MP-10 전체 실행·재개, MP-11 전체 검증 |
