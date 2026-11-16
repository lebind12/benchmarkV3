# NS-ENV C 공통 시작본 준비 및 환경 사전 확인 보고서

작성: Gemini 4 Hydrogen (High) (`antigravity`, Orca session `7913fa2d-2b33-46d0-b3cc-0aeb4dd1d679`, task `task_d52e77bc5e43`).
기준 문서: `docs/superpowers/plans/2026-11-16-player-section-storage.md` 및 `docs/superpowers/plans/2026-11-16-player-section-prep-task.md`.
이 보고서는 공통 시작본 보존과 기동·DB·의존성 사전 조사 결과만 담는다.
최소 공통 계약(`app/preview/player_section_contracts.py`) 구현, 서버 기동, 실제 DB 접속, 마이그레이션, AI 호출은 이 배정 범위 밖이다.

## 0. 스킬 읽기 기록과 판단 근거

### 착수 시 읽은 스킬과 적용 원칙

- `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` (전문 162줄)
- `/Users/woolee/benchmark/.agents/skills/principle-separate-before-serializing-shared-state/SKILL.md`
- `/Users/woolee/benchmark/.agents/skills/principle-sequence-verifiable-units/SKILL.md`
- `/Users/woolee/benchmark/.agents/skills/principle-prove-it-works/SKILL.md`
- `/Users/woolee/benchmark/.agents/skills/principle-laziness-protocol/SKILL.md`
- `/Users/woolee/benchmark/.agents/skills/unslop/SKILL.md`
- `/Users/woolee/benchmark/.agents/skills/technical-writing/SKILL.md`
- `/Users/woolee/.gemini/skills/orchestration/SKILL.md` 및 `orca skills get orchestration`

### 완료 시 확인한 원칙별 결정 변화

- `principle-separate-before-serializing-shared-state`: 원본 `/Users/woolee/benchmark`를 읽기 전용으로 유지하고 조정자 소유의 `Plans.md`를 원본과 복사본 모두에서 건드리지 않았다. 포트와 Origin 설정도 A(`5173/38000`), B(`5174/38001`), C 준비(`5175/38002`)가 `8000`의 `second-brain-api-1`과 겹치지 않게 분리 정리했다.
- `principle-sequence-verifiable-units`: 순수 제품 상태 스냅샷 커밋(`81db957`)을 먼저 만들고 검증한 뒤, 보고서 커밋을 별도로 분리해 A·B가 순수 기준 커밋이나 보고서 포함 브랜치 중 필요한 지점을 선택할 수 있게 했다.
- `principle-prove-it-works`: `git ls-files` 전수 대조 스크립트로 1,962개 추적 파일·65개 심볼릭 링크 일치, `Plans.md` 불변, 비밀값·의존성·산출물 미포함, `.venv/bin/python`의 `app` 해석 경로, 현재 포트 리스너를 직접 실행해 확인했다.
- `principle-laziness-protocol`: 새 래퍼 스크립트를 만들지 않고 기존 `scripts/run_benchmark_dev.sh`의 `BENCHMARK_PORT`·`CORS_ALLOW_ORIGINS`와 `frontend/vite.config.ts`의 `BENCHMARK_BACKEND_URL`을 그대로 재사용하는 실행 계획을 세웠다.
- `unslop`·`technical-writing`: 과장 표현과 불필요한 기호를 피하고 실제 파일 경로, 심볼, 수치만 기록했다.

## 1. 공통 시작본 보존 결과와 원본 대비 차이

### 기준 위치

- 작업트리 경로: `/Users/woolee/orca/workspaces/benchmark/player-section-integration`
- 브랜치: `lebind12/player-section-integration`
- 부모 기준 커밋(원본 `main` HEAD): `7cf466b` (`docs: record production preview deployment and verification`)
- 공통 시작 스냅샷 커밋: `81db9574781b4c37859c1b0a09536570497713d5` (`81db957`)
- 원본 `/Users/woolee/benchmark`: 무변경 확인(`HEAD=7cf466b`, `git status --porcelain=v1` 463줄 유지 = `421 D`, `4 M`, `38 ??` 최상위 항목).

### 보존 대상과 제외 대상

| 구분 | 수량 | 처리 내역 |
|---|---:|---|
| `7cf466b` 미수정 제품 추적 파일 | 881 | 그대로 유지 (`app/`, `frontend/`, `alembic/versions/0001..0005`, `tests/preview/`, `tests/unit/` 8개, `scripts/preview_*`, `scripts/run_*.sh`, `.env.example`, `pyproject.toml`, `requirements.txt`, `AGENTS.md`, `CLAUDE.md` 등) |
| 원본 추적 삭제(`D`) | 421 | `git rm`으로 동일하게 삭제 보존 (`alembic/versions/` 구 마이그레이션 18개, `assets/` 87개, 구 `docs/` 123개, 구 `scripts/` 37개, `seeds/` 49개, `supabase/` 4개, 구 `tests/` 93개, `.claude-plugin/`·`.claude/settings.json`·`.koyebignore`·CSV·`output/pdf/` 10개) |
| 원본 추적 수정(`M`) | 4 중 3 | `.gitignore`, `README.md`, `plan.md` 반영. `Plans.md`는 지침에 따라 원본·복사본 모두 수정하지 않고 `7cf466b` 상태 유지 |
| 선택 보존 미추적 파일 | 1,077 | `.agents/skills/`(744개, `.agents/skills/.claude/` 제외), `.claude/skills/`(65개 상대 심볼릭 링크), `skills-lock.json`(1개), `docs/planning/`(230개), `docs/decisions/`(미추적 2개), `docs/superpowers/plans/`(3개), `docs/implementation/match-preview/evidence/`(미추적 7개 하위 폴더 32개) |
| 제외 대상(비밀·의존성·산출물·로그) | — | `.env`(원본에도 없음), `~/.config/match-preview/*.env`, `**/.env.local`, `*.preview-dev.env`, `.venv/`, 루트 `node_modules/`, `frontend/node_modules/`, `frontend/dist/`, `frontend/.vercel/`, `frontend/playwright-report/`, `frontend/test-results/`, `frontend/tsconfig.*.tsbuildinfo`, `__pycache__/`, `.pytest_cache/`, `out/`(3,167개), `docs/benchmarks/`(34개), `.playwright-mcp/`(10개), `.hallmark/`, `.claude/sessions/`, `.claude/state/`, `.agents/skills/.claude/`, `.DS_Store` |

### 시작본 대조 검증 결과

- `81db957` 추적 파일 총수: `1,962`개 (`1,306 - 421 + 1,077`).
- `Plans.md` 제외 전 추적 파일(`1,896`개 정규 파일 + `65`개 심볼릭 링크)이 `/Users/woolee/benchmark`와 바이트·링크 대상 기준 불일치 0건, 누락 0건.
- `Plans.md`는 `7cf466b:Plans.md`와 바이트 일치(`True`).
- 금지 경로(`.env`, `*.preview-dev.env`, `node_modules`, `.venv`, `__pycache__`, `.DS_Store`, `.playwright-mcp`, `.claude/sessions`, `.claude/state`, `out/`, `dist/`) 포함 0건, 키 패턴(`AIza...`, `PRIVATE KEY`, `sk-...`) 검출 0건.

## 2. 기동 명령·설정 키와 A/B/C 실행 계획

### 소스에서 확인한 기동 명령과 설정 키

- 백엔드 (`scripts/run_benchmark_dev.sh`):
  - 실행 명령: `.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${BENCHMARK_PORT:-8000}"`
  - 자격 파일: `PREVIEW_CREDENTIALS_FILE`(기본 `~/.config/match-preview/preview-dev.env`, mode `600` 존재 확인)과 선택 `PREVIEW_MODEL_CREDENTIALS_FILE`(기본 `~/.config/match-preview/model-live.env`, mode `600` 존재 확인). 내용은 읽거나 출력하지 않았다.
  - 필수 환경 키: `DATABASE_URL`, `PREVIEW_ALLOW_NONLOCAL_DB`, `JWT_SECRET_KEY`.
  - 로컬 프로필 기본값: `LOCAL_DEV_AUTH_ENABLED=true`, `AUTH_COOKIE_NAME=benchmark_refresh_local`, `AUTH_COOKIE_SECURE=false`, `AUTH_COOKIE_SAMESITE=lax`, `CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`, `WORKER_SCHEDULER_ENABLED=false`, `HOME_PREVIEW_ENABLED=false`.
  - 런처가 명시적으로 `unset`하는 구 키: `PREVIEW_DATABASE_URL`, `PREVIEW_DEV_DATABASE_URL`, `PREVIEW_IDENTITY_DATABASE_URL`, `PREVIEW_FIXTURES_DATABASE_URL`, `PREVIEW_NAMES_DATABASE_URL`, `PREVIEW_STATS_DATABASE_URL`, `BENCHMARK_READ_DATABASE_URL`.
  - 참고: `app/core/config.py`의 `model_post_init`은 작업 디렉터리 `.env`에 `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `VERTEX_AI_MODEL`, `GOOGLE_APPLICATION_CREDENTIALS_JSON`이 있으면 프로세스 환경보다 우선 읽는다.
- 프론트엔드 (`frontend/package.json`, `frontend/vite.config.ts`):
  - 실행 명령: `npm run dev` (`vite`).
  - `vite.config.ts` 설정: `host: '127.0.0.1'`, `port: 5173` 고정, `strictPort: true`, `envDir: resolve(__dirname, '..')`, `envPrefix: ['VITE_']`, `/api` 프록시 대상 `process.env.BENCHMARK_BACKEND_URL ?? 'http://127.0.0.1:8000'`, `changeOrigin: false`, `timeout: 0`, `proxyTimeout: 0`.
  - 주의: `vite.config.ts`의 `server.port`가 `5173`으로 고정되어 있으므로 B(`5174`)와 C 준비(`5175`)는 CLI 인자 `-- --port 5174` / `-- --port 5175`를 전달해야 한다. `strictPort: true`는 유지되어 포트 충돌 시 조용히 다른 포트로 옮기지 않는다.

### 현재 포트 상태와 A/B/C 실행 계획

`lsof -nP -iTCP:5173,5174,5175,38000,38001,38002,8000 -sTCP:LISTEN` 실행 결과 `*:8000`만 `com.docke` PID `3541`(`second-brain-api-1`)이 점유 중이며, `5173`, `5174`, `5175`, `38000`, `38001`, `38002` 리스너는 0건이었다.

| 환경 | 프론트 포트 | 백엔드 포트 | 백엔드 실행 env (`scripts/run_benchmark_dev.sh`) | 프론트 실행 env (`frontend/`) |
|---|---:|---:|---|---|
| A (storage) | 5173 | 38000 | `BENCHMARK_PORT=38000 CORS_ALLOW_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"` | `BENCHMARK_BACKEND_URL=http://127.0.0.1:38000 npm run dev -- --port 5173` |
| B (generation) | 5174 | 38001 | `BENCHMARK_PORT=38001 CORS_ALLOW_ORIGINS="http://localhost:5174,http://127.0.0.1:5174"` | `BENCHMARK_BACKEND_URL=http://127.0.0.1:38001 npm run dev -- --port 5174` |
| C 준비 (integration) | 5175 | 38002 | `BENCHMARK_PORT=38002 CORS_ALLOW_ORIGINS="http://localhost:5175,http://127.0.0.1:5175"` | `BENCHMARK_BACKEND_URL=http://127.0.0.1:38002 npm run dev -- --port 5175` |
| C 최종 인계 | 5173 | 38000 | A 종료·포트 인계 후 `BENCHMARK_PORT=38000` 전환 | `BENCHMARK_BACKEND_URL=http://127.0.0.1:38000 npm run dev -- --port 5173` |

### 환경 공유 방법

- 비밀값: 저장소 밖 0600 파일(`~/.config/match-preview/preview-dev.env`, `~/.config/match-preview/model-live.env`)을 A·B·C가 그대로 공유해 사용한다. 워크트리에 복사하지 않는다.
- 의존성 디렉터리: `.venv/`와 `frontend/node_modules/`는 `.gitignore` 제외 대상이므로 각 워크트리에 `/Users/woolee/benchmark/.venv`와 `/Users/woolee/benchmark/frontend/node_modules` 심볼릭 링크를 연결하거나 필요 시 독립 설치한다.
- Refresh 쿠키 충돌 방지: 브라우저는 쿠키를 포트 구분 없이 호스트(`127.0.0.1`) 단위로 공유한다. A·B·C가 동시에 로그인해 refresh 회전을 실행하면 같은 `benchmark_refresh_local` 쿠키가 덮어써져 다른 포트 세션이 `401`로 만료될 수 있다. 동시 브라우저 확인 시 `AUTH_COOKIE_NAME`을 환경별로 구분(`benchmark_refresh_a`, `benchmark_refresh_b`, `benchmark_refresh_c`)하는 편이 안전하다.

## 3. DB 대상·권한 도구와 무변경 ADMIN 인증 준비 상태

### 기존 설정과 도구 현황

- 연결·대상 검증 모듈: `app/core/config.py`, `app/preview/config.py`, `app/core/db_target.py`, `app/db.py`, `app/preview/db.py`.
- 프로비저닝·마이그레이션·상태 점검 스크립트: `scripts/preview_dev_provision.py`, `scripts/preview_dev_migrate.py`, `scripts/preview_dev_status.py`.
- 테스트 격리 가드: `tests/preview/_dbguard.py`, `tests/preview/conftest.py`.

### 소스에서 확인한 중요 사실과 미구현·불일치 지점

1. **통합 런타임 연결의 권한 분리 부재**: `scripts/run_benchmark_dev.sh`는 단일 `DATABASE_URL`을 사용하며 구 `PREVIEW_*_DATABASE_URL`을 `unset`한다. `app/preview/config.py`의 모든 DB URL property도 `DATABASE_URL` 하나를 돌려주고, `app/preview/db.py`는 `search_path=preview_dev`만 지정할 뿐 읽기 전용이나 `public` 권한 차단을 DB 역할 수준에서 강제하지 않는다. 따라서 통합 런타임에서 `public` 무변경은 DB 권한 분리가 아니라 앱 계층 규약(`preview_dev` 스키마 명시 모델, 로컬 인증 프로필 플래그)에 의존한다.
2. **과거 분리 역할 스크립트와 마이그레이션 도구의 키 불일치**: `scripts/preview_dev_provision.py`, `scripts/preview_dev_migrate.py`, `scripts/preview_dev_status.py`는 `PREVIEW_DEV_DATABASE_URL`과 `PREVIEW_IDENTITY_DATABASE_URL`을 읽는다. 반면 `run_benchmark_dev.sh`는 이 두 키를 `unset`하고 `DATABASE_URL`을 쓴다. 또한 `alembic/env.py` 17행은 존재하지 않는 `app.db.Base`를 import하므로(`Base`는 `app/models/`와 `app/preview/db.py`에 분리), `alembic` CLI 대신 `scripts/preview_dev_migrate.py`의 `MIGRATION_PATHS`를 확장해 `preview_dev` 스키마에만 적용해야 한다.
3. **기존 ADMIN 인증 경로(소스 근거)**: `LOCAL_DEV_AUTH_ENABLED=true`일 때 `app/api/v1/auth.py`와 `app/services/auth.py`는 `/api/v1/auth/signup`을 `403`으로 닫고, `/api/v1/auth/login`은 `touch_last_login=False`로 호출해 `public.app_user`를 갱신하지 않는다. Refresh 세션은 `app/auth/benchmark_sessions.py`를 통해 `preview_dev.preview_admin_sessions`에만 기록한다. `/api/v1/auth/me`와 `app/preview/access.py`의 `require_preview_admin`은 Bearer JWT의 `current_user`와 `user.role == "ADMIN"`을 검사한다(비인증 `401`, 비ADMIN `403`).
4. **미확인 사항**: 실제 DB 접속, `public.app_user` 읽기, `preview_dev` 쓰기·권한 상태(`scripts/preview_dev_status.py`), 실제 ADMIN 로그인은 이번 배정 범위에서 실행하지 않았으므로 후속 NS-ENV 서버 확인 단계에서 검증해야 한다.

## 4. 기존 검사 명령과 의존성 재사용 가능 여부

### Python 환경과 검사 명령

- `/Users/woolee/benchmark/.venv/bin/python`은 Python `3.11.4`이며 `pytest 8.3.4`가 설치되어 있다.
- 워크트리 cwd(`/Users/woolee/orca/workspaces/benchmark/player-section-integration`)에서 `/Users/woolee/benchmark/.venv/bin/python -c "import app; print(app.__file__)"` 실행 시 `.venv` site-packages에 편집 가능 설치(`.pth`)가 없어 현재 워크트리의 `app/__init__.py`를 정확히 import함을 확인했다.
- 따라서 각 워크트리는 `/Users/woolee/benchmark/.venv`를 직접 호출하거나 `.venv` 심볼릭 링크를 두어 `.venv/bin/python -m pytest ...` 명령을 재사용할 수 있다.
- 주의: `tests/preview/conftest.py`는 테스트마다 `DROP SCHEMA IF EXISTS preview_dev CASCADE`와 `DROP SCHEMA IF EXISTS public CASCADE`를 실행하며 `tests/preview/_dbguard.py`가 루프백 및 `test_*`·`*_test` DB 이름만 허용한다. 운영 DB를 가리키는 환경에서는 절대 실행하지 않는다.

### Frontend 환경과 검사 명령

- 확인된 버전: Node `v22.19.0`, npm `11.11.0`, `/Users/woolee/benchmark/frontend/node_modules/.bin/vitest` `2.1.9`, `vue-tsc` `5.7.3`.
- 스크립트(`frontend/package.json`): `npm run test:unit`, `npm run type-check`, `npm run build`, `npm run test:e2e`.
- 새 워크트리의 `frontend/node_modules`는 비어 있으므로, `/Users/woolee/benchmark/frontend/node_modules` 심볼릭 링크를 두거나 `npm ci`를 실행한 뒤 위 검사 명령을 사용한다.
