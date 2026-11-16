# NS-03 선행 단계: A 저장 구현 병합 및 `preview_dev` 0006 적용 보고

- 작성 시각: 2026-11-16 (KST)
- 담당/모델: C (`antigravity` / `Gemini 4 Hydrogen (High)`, 사용자 예외 적용)
- 브랜치/작업트리: `lebind12/player-section-integration` (`/Users/woolee/orca/workspaces/benchmark/player-section-integration`)

## 1. Poteto 적용 기록

- [SKILL.md](file:///Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md)의 유효한 읽기 기록을 동일 세션에서 재사용했다.
- 적용 원칙:
  - **Sequence Work into Verifiable Units:** A 병합(`2277841`) → `preview_dev_migrate.py --dry-run` → `applied` → `already applied` → `preview_dev_runtime` 개별 권한 검증 → 기존 `term_d8731431` 확인 후 백엔드(`38002`)만 짧게 재기동하는 순서로 단계별 검증을 마쳤다.
  - **Boundary Discipline:** `0006_player_section_storage`는 `preview_dev_app` (`PREVIEW_DEV_DATABASE_URL`)으로만 적용하고, `preview_dev_runtime`에는 `ALTER DEFAULT PRIVILEGES FOR ROLE preview_dev_app IN SCHEMA preview_dev`로 부여된 신규 3표 DML만 확인하며 런타임 `CREATE`나 `schema_migrations` 권한은 추가하지 않았다.

## 2. A 최종 구현 병합

- **병합 대상:** A 최종 수용 커밋 `5b6088dad22320949f590d4147ac01d58488d875` (`5b6088d`)
- **부모 커밋:** `9a052035dbb4c2116c15fb2d2d72b5a23bf2a6d7` (`integration`), `5b6088dad22320949f590d4147ac01d58488d875` (`player-section-storage`)
- **병합 커밋 SHA:** `2277841976912d3587b1f2657f2e77cf4fd9613b` (`2277841`, `merge --no-ff`, 충돌 0건)
- **공통 파일 일치 확인:** `git diff 568f2b6 79ddbb7 -- app/preview/player_section_contracts.py tests/preview/test_player_section_contracts.py` 출력 없음(동일 내용 유지).
- **반영 파일 (10개, B 파일·`_save_draft` 무수정):**
  - `alembic/versions/0006_player_section_storage.py`
  - `app/preview/models.py`, `app/preview/player_name_candidates.py`, `app/preview/player_section_models.py`, `app/preview/player_section_store.py`, `app/preview/store.py`
  - `scripts/preview_dev_migrate.py`
  - `docs/implementation/match-preview/ns-01-storage-report.md`
  - `tests/preview/test_migration_schema.py`, `tests/preview/test_player_section_storage.py`
- **기존 로컬 검사 재사용:** A 수용 단위(`test_player_section_storage.py`, `test_migration_schema.py`, `test_player_section_contracts.py`, `test_run_store.py`, `test_inspection_api.py` 54 PASS) 근거를 재사용했으며 불필요한 중복 실행은 하지 않았다.

## 3. `preview_dev` 0006 마이그레이션 및 신규 3표 권한 검증

자격은 `~/.config/match-preview/preview-dev-restricted.env`에서 읽었다(`PREVIEW_DEV_DATABASE_URL`=`preview_dev_app`로 마이그레이션, `DATABASE_URL`=`preview_dev_runtime`으로 읽기 전용 검증).

1. **적용 전 확인 (`preview_dev_app`):**
   - `schema_migrations` 이력: `['0001_preview_dev_admin_sessions', '0002_preview_runs', '0003_preview_approvals', '0004_section_results', '0005_pipeline_runs']`
   - 신규 3표(`preview_player_name_candidates`, `preview_watch_player_sections`, `preview_injury_player_sections`) 존재 여부: 모두 `False`
2. **`--dry-run` 확인:**
   - 명령: `/Users/woolee/benchmark/.venv/bin/python scripts/preview_dev_migrate.py --credentials-file "$HOME/.config/match-preview/preview-dev-restricted.env" --dry-run`
   - 결과: `0002..0005 already applied`, `0006_player_section_storage: pending`, `dry run: 11 statements pending` (예상 11문 외 변경·과거 재적용 없음)
3. **명시 적용 및 멱등 재실행:**
   - 1차 실행: `0006_player_section_storage: applied`, `checkpoints: ready in preview_dev`
   - 2차 실행: `0006_player_section_storage: already applied`
   - `preview_dev.schema_migrations`: `['0001_preview_dev_admin_sessions', '0002_preview_runs', '0003_preview_approvals', '0004_section_results', '0005_pipeline_runs', '0006_player_section_storage']`
4. **신규 3표 스키마 · 소유자 · `preview_dev_runtime` 개별 권한 (`read_only=True`):**
   - `preview_dev` 스키마 전용 생성 확인(`public` 3표 모두 `False`).
   - `preview_player_name_candidates`: 소유자 `preview_dev_app`, 컬럼 13개(`id`, `run_id`, `section_result_id`, `workflow_id`, `slot_key`, `fixture_id`, `team_id`, `player_id`, ..., `source`, `review_status`, `created_at`), `preview_dev_runtime` `SELECT/INSERT/UPDATE/DELETE=True` (default ACL 자동 승계, 추가 GRANT 불필요).
   - `preview_watch_player_sections`: 소유자 `preview_dev_app`, 컬럼 41개(`section_result_id`..`home_etc`, `away_etc`, `created_at`), `preview_dev_runtime` `SELECT/INSERT/UPDATE/DELETE=True`.
   - `preview_injury_player_sections`: 소유자 `preview_dev_app`, 컬럼 51개(`section_result_id`..`away2_injury`, `away2_importance`, `created_at`), `preview_dev_runtime` `SELECT/INSERT/UPDATE/DELETE=True`.
   - 유지 확인: `preview_dev.schema_migrations` (`SELECT/INSERT/UPDATE/DELETE=False`), `preview_dev`/`public` `CREATE=False`, `public` 28표 중 허용 17표만 `SELECT=True` 및 28/28 쓰기·DDL 권한 0건.

## 4. C 백엔드(38002) 짧은 재기동 및 프록시 확인

- **기동 리비전:** `2277841976912d3587b1f2657f2e77cf4fd9613b` (`2277841` — A 병합본)
- **Orca 터미널 및 프로세스:**
  - C 백엔드 (`http://127.0.0.1:38002`): 기존 `term_d8731431-0309-4b85-af6e-50227cb9e2f5` (`worktreePath=/Users/woolee/orca/workspaces/benchmark/player-section-integration`, `PID 75834`) 확인 후 SIGINT 종료 → 동일 터미널·환경(`PREVIEW_CREDENTIALS_FILE=$HOME/.config/match-preview/preview-dev-restricted.env`, `BENCHMARK_PYTHON=/Users/woolee/benchmark/.venv/bin/python`, `AUTH_COOKIE_NAME=benchmark_refresh_c_prep`, `LOCAL_DEV_AUTH_ENABLED=true`, `CORS_ALLOW_ORIGINS=http://localhost:5175,http://127.0.0.1:5175`)으로 **PID `79982`** 재기동.
  - C 프론트 (`http://127.0.0.1:5175/`): `term_5b562799-00b1-4534-a376-7372c0ab1f37` (vite PID `75968`) 무중단 유지.
  - Docker `*:8000` (`PID 3541`) 및 A/B 포트(`5173`/`5174`/`38000`/`38001`) 무간섭·미점유.
- **응답 검증:**
  - `GET http://127.0.0.1:38002/health` → `200 OK` (`{"status":"ok"}`)
  - `GET http://127.0.0.1:5175/` → `200 OK` (Vite HTML)
  - `GET http://127.0.0.1:5175/api/v1/home/fixtures`, `/injuries`, `/standings`, `/recommendations` → 각 `200 OK`
  - `GET http://127.0.0.1:5175/api/v1/auth/me` → `401 Unauthorized`
- **코드 편집 종료 여부:** C의 이번 배정 코드 편집 종료(clean 유지).

## 5. 미완료 후속 범위 구분

- B 구현 인계 후 최종 병합(`NS-03` 본통합), `_save_draft`·조회/투영·카드 UI 연결, 실제 ADMIN 로그인 세션 기반 `save_player_section` 실연동/해당 실행 undo 검증, 실제 AI 호출 및 사용자 승인 흐름은 후속 배정 범위로 남겨두었다.
