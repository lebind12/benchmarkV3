# NS-ENV 제한 런타임 DB 역할 적용 및 C 서버(5175/38002) 준비 보고

- 작성 시각: 2026-11-16 (KST)
- 담당/모델: C 준비 (`antigravity` / `Gemini 4 Hydrogen (High)`, 사용자 예외 적용)
- 적용 기준: [ns-env-db-minimal-privilege-plan.md](ns-env-db-minimal-privilege-plan.md) **안 A** (`preview_dev_runtime` 전용 런타임 역할)
- 공통 계약 기준: `568f2b6ec2c1b219d164e3efb6a7cf0d44145cc9` (`568f2b6`, 무변경 유지)

## 1. Poteto 적용 기록

- [SKILL.md](file:///Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md)의 유효한 읽기 기록을 동일 세션에서 재사용했다.
- 적용 원칙:
  - **Boundary Discipline:** Postgres에서 비소유자(`DATABASE_URL`)가 `preview_dev_app` 소유 14표에 `GRANT`하면 오류 없이 경고만 남기고 무권한이 될 수 있음을 실측으로 확인하고, `preview_dev_app` 자격(`PREVIEW_DEV_DATABASE_URL`)으로 소유 표 14개와 `preview_dev` 한정 `ALTER DEFAULT PRIVILEGES`를 분리 부여했다.
  - **Prove It Works:** 콤마 일괄 조회 대신 `pg_tables` 전체(`public` 28표·`preview_dev` 16표)를 순회하며 권한별(`SELECT`/`INSERT`/`UPDATE`/`DELETE`/`TRUNCATE`/`REFERENCES`/`TRIGGER`) 개별 `has_table_privilege` 검사와 실제 `preview_dev_runtime` 읽기 스모크·Vite(`5175`)→Uvicorn(`38002`) 프록시 `/api/v1/home/*` 응답을 확인했다.

## 2. 적용한 역할 · 제한 자격 파일 및 권한 검사 결과

- **신규 DB 역할:** `preview_dev_runtime` (`LOGIN`, `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, `NOBYPASSRLS`, `NOREPLICATION`, 기존 역할 멤버십 `[]` — 없음)
- **제한 자격 파일 경로:** `~/.config/match-preview/preview-dev-restricted.env` (파일 권한 `0600`, 내용·비밀값·계정 식별자 미출력; 기존 `~/.config/match-preview/preview-dev.env` 및 `~/.config/match-preview/model-live.env`는 덮어쓰지 않음)
  - `DATABASE_URL`: `preview_dev_runtime` 제한 연결만 지정
  - `PREVIEW_DEV_DATABASE_URL`: 기존 `preview_dev_app` 유지 (`scripts/preview_dev_migrate.py` 전용, `scripts/run_benchmark_dev.sh` 실행 시 자동 `unset`)
  - `PREVIEW_ALLOW_NONLOCAL_DB=1`, `LOCAL_DEV_AUTH_ENABLED=true`, 기존 로컬 `JWT_SECRET_KEY` 및 `API_FOOTBALL_KEY` 재사용

### 전·후 검사 요약 및 기존 영역 무변경 근거

- **적용 전 확인:** 동일 호스트·포트·DB 대상 확인, `preview_dev_runtime` 기존 미존재(`False`), `~/.config/match-preview/preview-dev-restricted.env` 기존 미존재(`False`), `public` 17표·`preview_dev` 16표 RLS 모두 `False`, `PUBLIC` 역할의 17표 테이블 권한 없음(`[]`).
- **적용 후 `preview_dev_runtime` 직접 접속(`read_only=True`) 개별 권한 검사:**
  - `pg_roles` 속성: `(rolcanlogin=True, rolsuper=False, rolcreatedb=False, rolcreaterole=False, rolbypassrls=False, rolreplication=False, memberships=[])`
  - 스키마 권한: `public (USAGE=True, CREATE=False)`, `preview_dev (USAGE=True, CREATE=False)`
  - `public` 28개 표 개별 검사:
    - `SELECT=True` (정확히 17표 일치): `app_user`, `fixture`, `fixture_detail`, `league`, `league_translation`, `league_sync_target`, `team`, `team_translation`, `team_color`, `player`, `player_translation`, `player_season_stat`, `coach`, `coach_translation`, `team_coach`, `injury`, `standings`
    - `SELECT=False` (11표): `alembic_version`, `api_football_league_catalog`, `broadcast_momentum_state`, `h2h_fixture`, `management_run`, `news_article`, `team_season`, `transfer`, `translation_audit`, `venue`, `worker_sync_log`
    - `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `REFERENCES`, `TRIGGER`: **28개 표 전체 `False`** (`[]`)
  - `preview_dev` 16개 표 개별 검사:
    - 런타임·체크포인트 15표(`checkpoint_blobs`, `checkpoint_migrations`, `checkpoint_writes`, `checkpoints`, `preview_admin_sessions`, `preview_artifacts`, `preview_attempts`, `preview_module_executions`, `preview_pipeline_runs`, `preview_results`, `preview_runs`, `preview_section_approvals`, `preview_section_results`, `preview_source_snapshots`, `preview_write_audit`): `SELECT=True, INSERT=True, UPDATE=True, DELETE=True`
    - `preview_dev.schema_migrations`: `SELECT=False, INSERT=False, UPDATE=False, DELETE=False` (런타임 미부여)
  - `preview_dev` 한정 기본 권한(`pg_default_acl` on `preview_dev`): `('preview_dev_app', 'r', '{preview_dev_runtime=arwd/preview_dev_app}')`, `('preview_dev_app', 'S', '{preview_dev_runtime=rwU/preview_dev_app}')`
  - 실 읽기 스모크: `public` 17표 및 `preview_dev.preview_runs`, `preview_section_results`, `preview_admin_sessions` `SELECT 1 ... LIMIT 1` 모두 통과 (`public` 행 수정·쓰기 시험 미실행).

## 3. 코드 커밋 및 작업트리 상태

- 런처 수정 커밋: `3006d16a6643c1374fe5cbd9231c7705ac7a6ce4` (`3006d16`)
  - 수정 파일: `scripts/run_benchmark_dev.sh` (`BENCHMARK_PYTHON="${BENCHMARK_PYTHON:-.venv/bin/python}"` 지원 1건 추가; `pytest tests/unit/test_benchmark_preview_runtime.py -k test_launcher -q` → `1 passed, 11 deselected in 0.01s`)
- 워크트리 로컬 링크(미추적·`.gitignore` 무시): `frontend/node_modules` → `/Users/woolee/benchmark/frontend/node_modules` (`git status --short` clean 유지)
- 보호 대상: `568f2b6` 공통 파일, 원본 `/Users/woolee/benchmark`, 양쪽 `Plans.md`, A/B 워크트리, `8000` `second-brain-api-1` 모두 무변경·무간섭.

## 4. C 서버(5175/38002) 기동 및 동작 확인

- **기동 리비전:** `3006d16a6643c1374fe5cbd9231c7705ac7a6ce4`
- **C 백엔드 (`http://127.0.0.1:38002`):**
  - Orca 터미널: `term_d8731431-0309-4b85-af6e-50227cb9e2f5` (`tabId=a8948e67-ae45-4fc0-89fa-e9be3f1df2fe`, shell PID `74709`, uvicorn PID `75834`)
  - 적용 환경: `PREVIEW_CREDENTIALS_FILE=$HOME/.config/match-preview/preview-dev-restricted.env`, `BENCHMARK_PORT=38002`, `AUTH_COOKIE_NAME=benchmark_refresh_c_prep`, `LOCAL_DEV_AUTH_ENABLED=true`, `CORS_ALLOW_ORIGINS=http://localhost:5175,http://127.0.0.1:5175` (`WORKER_SCHEDULER_ENABLED=false`, `HOME_PREVIEW_ENABLED=false`)
- **C 프론트 (`http://127.0.0.1:5175/`):**
  - Orca 터미널: `term_5b562799-00b1-4534-a376-7372c0ab1f37` (`tabId=fdb6deab-85d6-414e-a22b-9f9cb3f3a3ff`, shell PID `74763`, vite PID `75968`)
  - 적용 환경: `BENCHMARK_BACKEND_URL=http://127.0.0.1:38002`, `--port 5175`
- **포트 격리 (`lsof`):** `*:8000` (Docker `second-brain-api-1`), `127.0.0.1:38002` (Python/uvicorn), `127.0.0.1:5175` (Node/vite)만 리스닝 중 (`5173`, `5174`, `38000`, `38001` 미점유).
- **검증 결과 (서버 가용성 vs 신규 기능 연동 구분):**
  - `GET http://127.0.0.1:38002/health` → `200 OK` (`{"status":"ok"}`)
  - `GET http://127.0.0.1:5175/` → `200 OK` (Vite HTML)
  - `OPTIONS http://127.0.0.1:38002/api/v1/auth/me` (`Origin: http://127.0.0.1:5175`) → `200 OK` (`access-control-allow-origin: http://127.0.0.1:5175`, `access-control-allow-credentials: true`)
  - `GET http://127.0.0.1:5175/api/v1/auth/me` (프록시) → `401 Unauthorized` (`{"detail":"로그인이 필요합니다."}`)
  - `GET http://127.0.0.1:5175/api/v1/home/fixtures` 및 `/api/v1/home/injuries` (프록시 + `preview_dev_runtime` `public` 읽기) → 각 `200 OK`
- **미실행/후속 확인 사항:**
  - **로그인 · 개발 쓰기 · 신규 3표 연동:** 평문 ADMIN 계정이 작업 환경에 없어 실 로그인·세션 생성·개발 쓰기/취소 및 A의 `0006_*` 마이그레이션/AI 모델 호출은 실행하지 않았다(사용자 로그인 또는 후속 NS-03 통합 단계에서 확인). 현재 C 서버는 제한 DB 연결과 기존 앱·프록시 가동만 준비된 상태다.

## 5. A/B 작업트리 기동 시 필요한 환경 키 및 독립 쿠키 안내

- 공통 필수 환경:
  - `PREVIEW_CREDENTIALS_FILE="$HOME/.config/match-preview/preview-dev-restricted.env"`
  - `BENCHMARK_PYTHON="/Users/woolee/benchmark/.venv/bin/python"` (또는 각 워크트리 `.venv`)
  - `LOCAL_DEV_AUTH_ENABLED=true`
  - **마이그레이션 전용 (`scripts/preview_dev_migrate.py`):** `PREVIEW_DEV_DATABASE_URL` (`preview_dev_app`)만 사용하며 `run_benchmark_dev.sh`는 실행 시 `PREVIEW_DEV_DATABASE_URL`을 `unset`하고 `DATABASE_URL`(`preview_dev_runtime`)만 사용한다.
- 포트 및 쿠키 격리:
  - **A (`5173`/`38000`):** `BENCHMARK_PORT=38000`, `AUTH_COOKIE_NAME=benchmark_refresh_a`, `CORS_ALLOW_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"`, `BENCHMARK_BACKEND_URL="http://127.0.0.1:38000"`, Vite `--port 5173`
  - **B (`5174`/`38001`):** `BENCHMARK_PORT=38001`, `AUTH_COOKIE_NAME=benchmark_refresh_b`, `CORS_ALLOW_ORIGINS="http://localhost:5174,http://127.0.0.1:5174"`, `BENCHMARK_BACKEND_URL="http://127.0.0.1:38001"`, Vite `--port 5174`
  - **C (`5175`/`38002` 현재 준비 환경):** `BENCHMARK_PORT=38002`, `AUTH_COOKIE_NAME=benchmark_refresh_c_prep`, `CORS_ALLOW_ORIGINS="http://localhost:5175,http://127.0.0.1:5175"`, `BENCHMARK_BACKEND_URL="http://127.0.0.1:38002"`, Vite `--port 5175`
