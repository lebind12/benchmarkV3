# NS-ENV 실제 DB 최소 권한 적용안 (사전 설계 · 미실행)

- 작성 시각: 2026-11-16 (KST)
- 상태: **적용 전 계획안** (이 배정에서는 `CREATE ROLE`, `GRANT`, 비밀번호 생성, 마이그레이션, 서버 기동, DB 쓰기를 실행하지 않음)
- 대상 기준 커밋: 공통 계약 수정 커밋 `568f2b6ec2c1b219d164e3efb6a7cf0d44145cc9` (`568f2b6`, `app/preview/player_section_contracts.py` + `tests/preview/test_player_section_contracts.py`)
- 전제 원칙:
  - 기존 운영 역할(현재 `~/.config/match-preview/preview-dev.env`의 `DATABASE_URL` 계정)의 권한 축소·비밀번호 변경 금지.
  - 기존 `public` 테이블 구조·제약·트리거·RLS·행 데이터 무변경.
  - 런처(`scripts/run_benchmark_dev.sh`)는 단일 `DATABASE_URL`을 사용하며 `LOCAL_DEV_AUTH_ENABLED=true`로 로그인 시 `public.app_user.last_login_at` 갱신을 우회하고 `preview_dev.preview_admin_sessions`에만 기록한다.

---

## 1. 현재 소유자·권한 실측 요약 (읽기 전용 메타데이터 확인)

`pg_roles` · `pg_namespace` · `pg_tables` · `information_schema.tables` 조회 결과(비밀값·프로젝트 식별자 마스킹):

- 기존 `preview_dev*` 역할 5종: `preview_dev_app`, `preview_dev_identity_ro`, `preview_dev_fixture_ro`, `preview_dev_names_ro`, `preview_dev_stats_ro`.
- `preview_dev` 스키마 소유자: `<broad_owner>` (현재 `DATABASE_URL` 역할, `preview_dev_app`의 멤버임).
- `preview_dev` 기존 16개 표의 소유자 분포:
  - `preview_dev_app` 소유 (14개): `checkpoint_blobs`, `checkpoint_migrations`, `checkpoint_writes`, `checkpoints`, `preview_artifacts`, `preview_attempts`, `preview_module_executions`, `preview_pipeline_runs`, `preview_results`, `preview_runs`, `preview_section_approvals`, `preview_section_results`, `preview_source_snapshots`, `preview_write_audit` (`preview_dev_app`에 `REFERENCES` 권한 포함 R/W 보유).
  - `<broad_owner>` 소유 (2개): `preview_admin_sessions`, `schema_migrations` (`preview_dev_app`에 `SELECT/INSERT/UPDATE/DELETE`는 있으나 `REFERENCES`는 `False`).
- 현재 차단 요인:
  - `DATABASE_URL` (`<broad_owner>`): `public` 28개 표 전체 `SELECT/INSERT/UPDATE/DELETE` + `CREATE` + `rolcreatedb`/`rolcreaterole`/`rolbypassrls=True`.
  - `PREVIEW_DEV_DATABASE_URL` (`preview_dev_app`): `preview_dev` 16개 표 R/W + `USAGE/CREATE`는 충족하나 `public` `SELECT` 표가 `0개`.

---

## 2. 역할 전략 비교: 기존 `preview_dev_app` 확장 vs 전용 `preview_dev_runtime` 신설

`scripts/run_benchmark_dev.sh` (`app/db.py`, `app/preview/db.py`)는 단일 `DATABASE_URL`로 `public` 읽기 + `preview_dev` 읽고 쓰기를 함께 수행한다. 다음 두 안 중 하나를 후속 적용 배정에서 선택한다.

| 비교 항목 | 안 A: 전용 런타임 역할 신설 (`preview_dev_runtime`, **권장**) | 안 B: 기존 `preview_dev_app`에 `public SELECT` 추가 |
|---|---|---|
| 역할 구성 | 마이그레이션(`preview_dev_migrate.py`)은 기존 `preview_dev_app` 유지, 앱 런타임(`DATABASE_URL`)은 신규 `preview_dev_runtime` 사용 | 기존 `preview_dev_app` 하나를 `PREVIEW_DEV_DATABASE_URL`과 제한 런타임 `DATABASE_URL`에 공용 |
| `preview_dev` DDL 분리 | 런타임 역할에 `CREATE ON SCHEMA preview_dev` **미부여**(실수 DDL 차단) | `preview_dev_app`이 `preview_dev` `USAGE+CREATE`와 14표 소유권을 함께 보유 |
| 기존 역할 영향 | 기존 `preview_dev_*` 5개 역할 권한 **무변경** | `preview_dev_app`의 기존 무-`public` 정책 변경 |
| 신규 자격·비밀 필요 | 새 로그인 비밀번호 + pooler DSN 1건 발급 필요 | **새 역할·비밀번호 불필요**(기존 `PREVIEW_DEV_DATABASE_URL` 자격 재사용) |
| 신규 `0006_*` 표 R/W 처리 | `ALTER DEFAULT PRIVILEGES FOR ROLE preview_dev_app IN SCHEMA preview_dev` 또는 `0006` 직후 `GRANT` 1회 필요 | `preview_dev_app`이 `0006` 직접 생성·소유하므로 자동 R/W |

- **판단 근거:** 보안/역할 경계를 깔끔히 유지하고 기존 `preview_dev_*` 5개 역할을 건드리지 않으려면 **안 A (`preview_dev_runtime`)**가 가장 안전하다. 다만 Supabase 대시보드/운영자 절차상 신규 pooler 계정 발급 비용을 줄여야 할 때는 **안 B (`preview_dev_app`에 최소 `public SELECT`만 부여)**도 AGENTS.md("하나의 제한 역할이 public SELECT와 preview_dev 쓰기를 지원해도 요구를 충족")에 부합한다.

---

## 3. 실제 `public` 읽기 필요 테이블 목록 및 코드 호출 근거

전체 `public` 28개 표 중 아래 **호출 근거가 확인된 표에만 `SELECT`**를 부여한다(`INSERT`/`UPDATE`/`DELETE`/`TRUNCATE`/`REFERENCES`/`TRIGGER` 및 `CREATE ON SCHEMA public` 전면 금지).

| `public` 테이블 | 분류 | 실제 호출 모듈 근거 | 용도 |
|---|---|---|---|
| `app_user` | 필수 (인증/권한) | `app/auth/identity.py`, `app/auth/benchmark_sessions.py`, `app/preview/access.py`, `app/api/v1/auth.py`, `app/services/auth.py` | 관리자 로그인 검증·세션 사용자 조회(`LOCAL_DEV_AUTH_ENABLED=true`로 무변경) |
| `fixture` | 필수 (경기) | `app/preview/sources/fixtures.py`, `app/services/home_preview.py`, `app/services/home_preview_players.py`, `app/services/home_preview_injuries.py`, `app/services/management_runs.py` | 경기 목록·일정·팀/리그 식별자 확인 |
| `fixture_detail` | 필수 (경기/선수) | `app/services/home_preview_players.py`, `app/services/home_preview_injuries.py` | 경기 상세·라인업/결장 컨텍스트 조회 |
| `league` | 필수 (리그) | `app/preview/sources/fixtures.py`, `app/services/home_preview.py`, `app/services/admin.py` | 리그 기본 정보 및 시즌 조회 |
| `league_translation` | 필수 (리그명) | `app/services/home_preview.py`, `app/services/home_preview_players.py`, `app/services/admin.py` | 리그 한글명 조회 |
| `league_sync_target` | 필수 (대상 리그) | `app/api/v1/admin.py`, `app/services/admin.py`, `app/services/home_preview.py`, `app/services/home_preview_injuries.py`, `app/services/management_runs.py` | 노출/동기화 활성 리그 필터링 |
| `team` | 필수 (팀) | `app/preview/sources/fixtures.py`, `app/preview/localized_names.py`, `app/services/home_preview.py`, `app/services/broadcast_program.py` | 내부 `team.id` ↔ 외부 `team.external_id` 확인 |
| `team_translation` | 필수 (팀 한글명) | `app/preview/localized_names.py`, `app/services/home_preview.py`, `app/services/broadcast.py` | 팀 한글명 우선 해석 |
| `team_color` | 선택 (홈 프리뷰) | `app/services/broadcast_program.py` | 홈 프리뷰 팀 컬러 메타데이터 조회 |
| `player` | 필수 (선수) | `app/preview/localized_names.py`, `app/services/home_preview.py`, `app/services/home_preview_players.py`, `app/services/home_preview_injuries.py` | 내부 `player.id`·외부 `external_id` 검증 |
| `player_translation` | 필수 (선수 한글명) | `app/preview/localized_names.py`, `app/services/home_preview.py`, `app/services/home_preview_players.py`, `app/services/broadcast.py` | DB 확인 선수 한글명 최우선 조회 (`db_ko`) |
| `player_season_stat` | 필수 (선수 통계) | `app/preview/sources/player_stats.py`, `app/services/home_preview_players.py`, `app/services/home_preview_injuries.py` | 주목/부상 선수 시즌 스탯 사실 수집 |
| `coach`, `coach_translation`, `team_coach` | 필수 (감독 이름) | `app/preview/localized_names.py`, `app/services/broadcast.py` | 경기 감독 한글명 해석기 |
| `injury` | 필수 (부상 사실) | `app/preview/sources/fixtures.py` | 부상/결장 API 사실 조회 |
| `standings` | 필수 (순위) | `app/preview/sources/fixtures.py` | 프리뷰 전망/순위 조회 |
| `api_football_league_catalog`, `management_run`, `worker_sync_log` | 선택 (관리자 상태) | `app/api/v1/management.py`, `app/services/admin.py`, `app/services/management_runs.py` | 관리자 동기화/관리 상태 읽기 전용 화면 사용 시 포함 |

- 명시적 제외(`public` 미부여): `alembic_version`, `broadcast_momentum_state`, `h2h_fixture`, `news_article`, `team_season`, `transfer`, `translation_audit`, `venue` 및 모든 `public` 쓰기/DDL 권한.

---

## 4. `preview_dev` 권한 및 소유자 관계 설계

신규 3개 테이블(`preview_watch_player_sections`, `preview_injury_player_sections`, `preview_player_name_candidates`)은 `preview_runs`·`preview_section_results`(둘 다 `preview_dev_app` 소유)를 FK 참조한다.

1. **마이그레이션 실행 주체:** `scripts/preview_dev_migrate.py`는 기존 `PREVIEW_DEV_DATABASE_URL` (`preview_dev_app`)을 계속 사용한다. `preview_dev_app`은 이미 `preview_dev` `USAGE, CREATE`와 부모 표(`preview_runs`, `preview_section_results`) 소유·`REFERENCES`를 보유하므로 `<broad_owner>` 권한 없이 `0006_*` DDL 적용이 가능하다.
2. **런타임 역할의 `preview_dev` 권한:**
   - **안 A (`preview_dev_runtime`) 선택 시:**
     - `USAGE ON SCHEMA preview_dev` (단 `CREATE` 미부여).
     - `SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA preview_dev` (`<broad_owner>` 소유의 `preview_admin_sessions`/`schema_migrations` 및 `preview_dev_app` 소유의 14표 포함).
     - `USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA preview_dev`.
     - `ALTER DEFAULT PRIVILEGES FOR ROLE preview_dev_app IN SCHEMA preview_dev GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO preview_dev_runtime;` (및 시퀀스 동일 적용). 단, `<broad_owner>` 대신 `preview_dev_app`으로 마이그레이션해야 위 default privilege가 자동 승계된다.
   - **안 B (`preview_dev_app` 공용) 선택 시:**
     - 기존 16표 및 `preview_dev` `USAGE, CREATE`는 이미 충족되어 있으며, §3의 `public SELECT` 목록만 추가 부여하면 즉시 런타임 동작 조건을 만족한다.
3. **최소 SQL 템플릿 (참고용 · 이번 배정 미실행):**
   - 안 A 기준 예시(`<target_role>` = 신규 `preview_dev_runtime` 또는 안 B의 `preview_dev_app`):
     - `REVOKE ALL ON SCHEMA public FROM <target_role>;`
     - `GRANT USAGE ON SCHEMA public TO <target_role>;`
     - `GRANT SELECT ON public.app_user, public.fixture, public.fixture_detail, public.league, public.league_translation, public.league_sync_target, public.team, public.team_translation, public.team_color, public.player, public.player_translation, public.player_season_stat, public.coach, public.coach_translation, public.team_coach, public.injury, public.standings TO <target_role>;` (관리자 동기화 탭 포함 시 `api_football_league_catalog`, `management_run`, `worker_sync_log` 추가)
     - 안 A일 때만 `GRANT USAGE ON SCHEMA preview_dev`, `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA preview_dev`, `ALTER DEFAULT PRIVILEGES FOR ROLE preview_dev_app IN SCHEMA preview_dev ...` 추가.

---

## 5. 자격 파일 분리 및 포트별 런처 구성안

기존 `~/.config/match-preview/preview-dev.env`(광권한 `DATABASE_URL` 유지 · 다른 프로세스/8000 간섭 방지)를 덮어쓰지 않고 **별도 제한 자격 파일**을 사용한다.

- 제한 자격 파일 경로: `~/.config/match-preview/preview-dev-restricted.env` (저장소 외부, `chmod 600`)
- 필수 키:
  - `DATABASE_URL` = 제한 역할 DSN (`preview_dev_runtime` 또는 `public SELECT` 부여 후 `preview_dev_app`)
  - `PREVIEW_DEV_DATABASE_URL` = `preview_dev_app` DSN (`scripts/preview_dev_migrate.py` 용도, `run_benchmark_dev.sh` 실행 시 자동 `unset`됨)
  - `PREVIEW_ALLOW_NONLOCAL_DB=1`
  - `LOCAL_DEV_AUTH_ENABLED=true` (`public.app_user.last_login_at` 무변경 보장)
  - `JWT_SECRET_KEY` = 로컬 개발 서명 키 (운영 키 재사용 금지)
  - `API_FOOTBALL_KEY` = 기존 개발 설정값
- 실행 시 환경 주입(`scripts/run_benchmark_dev.sh` 무수정 호환):
  - 공통: `PREVIEW_CREDENTIALS_FILE=$HOME/.config/match-preview/preview-dev-restricted.env`
  - A (`5173`/`38000`), B (`5174`/`38001`), C (`5175`/`38002`)별로 `BENCHMARK_PORT`, `AUTH_COOKIE_NAME` (`benchmark_refresh_a` / `_b` / `_c_prep`), `CORS_ALLOW_ORIGINS`, `BENCHMARK_BACKEND_URL`, Vite `--port`만 분리.

---

## 6. 적용 전·후 검증 체크리스트 (실행은 후속 배정)

1. **적용 전 확인 (미실행):**
   - 대상 역할의 `pg_roles` 속성: `rolsuper=false`, `rolcreatedb=false`, `rolcreaterole=false`, `rolbypassrls=false`.
   - `preview_dev.schema_migrations` / `preview_admin_sessions`와 `preview_dev_app` 소유 14개 표 목록 확인.
2. **적용 직후 읽기 전용 메타데이터 검사 (`read_only=True`):**
   - `has_schema_privilege(<role>, 'public', 'USAGE') = true`, `'CREATE' = false`.
   - `public` 28개 표 전체에 대해 `has_table_privilege(<role>, format('public.%I', tablename), 'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') = false` (28/28 모두 `false`).
   - §3 허용 표 목록에 대해서만 `SELECT = true`.
   - `preview_dev` 전 표(`0006_*` 전 16개 / 후 19개)에 대해 `SELECT,INSERT,UPDATE,DELETE = true`.
   - 안 A 선택 시 `has_schema_privilege(<role>, 'preview_dev', 'CREATE') = false` 추가 확인.
3. **후속 실연동 동작 검사 (권한 적용 + A 마이그레이션 후):**
   - `PREVIEW_CREDENTIALS_FILE=~/.config/match-preview/preview-dev-restricted.env`로 백엔드(`38002`) + Vite(`5175`) 기동 후 `/health` · 프록시 읽기 · ADMIN 로그인(`preview_admin_sessions` 기록만 증가, `public.app_user` 무변경) 확인.
   - `public` 쓰기 시도 시 PostgreSQL `42501 insufficient_privilege` 차단 확인.

---

## 7. 이번 배정에서 의도적으로 실행하지 않은 항목

- `CREATE ROLE` / `GRANT` / `REVOKE` / 비밀번호 변경 또는 생성.
- `scripts/preview_dev_provision.py` 실행 및 `0006_*` 마이그레이션 실행.
- C 서버(`5175`/`38002`) 기동, 로그인/쓰기/undo, AI 모델 호출.
- `app/preview/player_section_contracts.py`와 `tests/preview/test_player_section_contracts.py` 외 제품 코드/A·B/원본/`Plans.md`/자연어 검색 계획 수정.
