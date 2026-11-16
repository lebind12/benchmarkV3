# NS-ENV C 공통 계약 구현 및 환경 권한 확인 보고

- 작성 시각: 2026-11-16 (KST)
- 담당/모델: C 준비·통합 (`antigravity` / `Gemini 4 Hydrogen (High)`, 사용자 예외 적용)
- 작업트리: `/Users/woolee/orca/workspaces/benchmark/player-section-integration`
- 브랜치: `lebind12/player-section-integration`

## 1. Poteto 적용 기록

- 읽은 스킬: `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 및 연계 원칙 스킬(`principle-prove-it-works`, `principle-boundary-discipline`, `principle-type-system-discipline`, `principle-test-behavior-not-implementation`, `principle-laziness-protocol`, `unslop`, `technical-writing`)을 사전 읽기 기록으로 확인해 유지·적용했다.
- 판단에 미친 영향:
  1. 빈 자리(`None`)와 채워진 미확인 자리(`player_id=None`)가 섞이지 않도록 저장 슬롯(`WatchPlayerSlot`/`InjuryPlayerSlot`)과 B 처리 초안(`PendingWatchSlotDraft`/`PendingInjurySlotDraft`)을 분리해 경계에서 불가능한 조합을 차단했다.
  2. 제한 역할 DB가 검증되지 않은 상태에서 광권한 `DATABASE_URL`로 fallback해 `38002`/`5175` 서버를 띄우지 않고, 읽기 전용 메타데이터 권한 근거와 차단 사유만 정확히 분리 보고했다.

## 2. 공통 계약 커밋 및 A/B 분기 기준

- **A/B 분기 기준 커밋 SHA:** `3f80cc2853631ed54e77d1f94255afb943b9f765` (`3f80cc2`)
- 공통 파일 편집 종료 여부: **종료 완료** (`3f80cc2` 커밋 이후 `app/preview/player_section_contracts.py`와 계약 문서는 추가 수정 없이 고정됨).
- 포함 파일:
  - `docs/superpowers/plans/2026-11-16-player-section-contract.md` (원본 최신 계약 복사본)
  - `docs/superpowers/plans/2026-11-16-player-section-common-task.md` (원본 배정서 복사본)
  - `app/preview/player_section_contracts.py`
  - `tests/preview/test_player_section_contracts.py`

### 2.1 `app/preview/player_section_contracts.py` 주요 계약과 A/B/C 연결

- **버전·테이블 상수**
  - `PREVIEW_DEV_SCHEMA = "preview_dev"`
  - `WATCH_PLAYERS_TABLE = "preview_watch_player_sections"`, `INJURY_PLAYERS_TABLE = "preview_injury_player_sections"`, `PLAYER_NAME_CANDIDATES_TABLE = "preview_player_name_candidates"`
  - `WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION = "ns01-watch-players-1"`, `INJURY_PLAYERS_OUTPUT_CONTRACT_VERSION = "ns01-injury-players-1"` (`app.preview.contracts.SECTION_RESULT_CONTRACT_VERSION = "mp04-section-result-1"` 유지)
  - `MAX_SLOTS_PER_TEAM = 2`, `MAX_CONTENT_REGENERATIONS = 1`, `MAX_MODULE_ATTEMPTS = 3`, `FIXED_SLOT_KEYS = ("home1", "home2", "away1", "away2")`
- **열거형·경계 검증**
  - `PlayerSectionWorkflowId`, `SlotKey`, `TeamSide`, `NameSource` (`db_ko`/`ai_candidate`), `CandidateSource` (`ai_translation`), `CandidateReviewStatus` (`pending`/`approved`/`edited`/`rejected`), `SlotResolutionStatus` (`resolved`/`unresolved`/`empty`), `RegenerationReason`, `UnplacedReason`
  - `require_positive_int` / `optional_positive_int` (`bool` 거부), `require_uuid`, `require_non_empty_text`, `optional_non_empty_text` (빈 문자열 거부), `require_aware_datetime`, `normalize_evidence`, `output_contract_version_for`, `team_id_for_slot`
- **A(저장·마이그레이션·undo) 연결 타입**
  - `WatchPlayerSlot`, `InjuryPlayerSlot`: `to_columns(slot_key)` / `from_columns(slot_key, mapping)` 포함. 부분 NULL 슬롯, `player_id=None` 시 `unresolved_reason` 누락, `db_ko`에 후보 연결, `injury`/`importance` 동시 누락 차단.
  - `PlayerNameCandidateInput`, `PlayerNameCandidateRecord`
  - `WatchPlayerSectionInput`, `WatchPlayerSectionRecord`, `InjuryPlayerSectionInput`, `InjuryPlayerSectionRecord`: `home_etc`/`away_etc` non-`None` 거부, 1번 슬롯 비우고 2번 슬롯 채우기 거부, 중복 `player_id` 거부, 후보 소유권(`run_id`/`section_result_id`/`workflow_id`/`fixture_id`/`team_id`/이름) 검증, 멱등/충돌 비교용 `canonical_dict()`.
- **B(프롬프트·응답 처리·검사 UI) 연결 타입**
  - `PendingWatchSlotDraft`, `PendingInjurySlotDraft`, `UnplacedPlayerDiagnostic`, `PlayerSectionAttemptTrace`, `PlayerSectionProcessingResult`
  - 저장 전('저장 예정 값', `persisted=False`) 검사 진단과 1회 재생성/최대 3회 시도/후보 미배치 이유를 표현하며, C `_save_draft`에서 `materialize_storage_input(section_result_id=..., run_id=...)`로 저장 입력 계약 변환.
- **C(투영) 연결 타입**
  - `SlotReadProjection`, `project_slot(...)`: 미확인(`player_id=None`) 또는 빈 슬롯에 `external_player_id`/`photo_url` 투영 차단.

## 3. 직접 단위 검사 결과

1. 순수 단위 계약 검사 (DB 픽스처 없음):
   - 명령: `/Users/woolee/benchmark/.venv/bin/python -m pytest tests/preview/test_player_section_contracts.py -q`
   - 결과: `10 passed, 1 warning in 0.04s`
   - 검증 범위: 정상/미확인/빈 자리 및 컬럼 왕복, 부상 `unknown` 상태 보존 및 `materialize_storage_input`, `bool`/부분 NULL/`home_etc`/슬롯 갭/중복 선수/후보 소유 불일치/예산 초과/미확인 사진 투영 거부.
2. 런처 회귀 확인:
   - 명령: `/Users/woolee/benchmark/.venv/bin/python -m pytest tests/unit/test_benchmark_preview_runtime.py -q`
   - 결과: `10 passed, 2 failed` (`test_launcher_does_not_overwrite_database_url_from_a_fixture_dsn` 통과; 2건은 테스트 셸에 `DATABASE_URL` 미주입으로 인한 `MissingDatabaseUrl` 예상 실패).

## 4. 환경 및 DB 권한 확인 결과 (읽기 전용 메타데이터 조회)

비밀값·DSN 원문·호스트·계정 식별자는 저장소 밖 설정에서만 읽고 출력하지 않았다. `psycopg` 연결은 `read_only=True`로 `pg_roles`·`pg_namespace`·`has_table_privilege`·`information_schema.tables`만 조회했다.

### 4.1 설정 파일 키 및 권한 실측 (`~/.config/match-preview/`)

- `model-live.env` 키: `PREVIEW_MODEL_PROVIDER`, `PREVIEW_MODEL_PROJECT`, `PREVIEW_MODEL_LOCATION`, `PREVIEW_MODEL_NAME`, `PREVIEW_MODEL_CREDENTIALS_JSON`, `PREVIEW_MODEL_LIVE_ENABLED`
- `preview-dev.env` 플래그: `PREVIEW_ALLOW_NONLOCAL_DB=1`, `LOCAL_DEV_AUTH_ENABLED=None`, `AUTH_COOKIE_NAME=None`

| DSN 키 | 역할 성격 | `public` CREATE | `public` SELECT 가능 표 (총 28표 중) | `public` 쓰기 권한 | `preview_dev` USAGE/CREATE 및 R/W |
|---|---|---:|---|---:|---|
| `DATABASE_URL` | 기존 광권한 계정 (`rolcreatedb`/`rolcreaterole`/`rolbypassrls=True`) | True | 28개 전부 | 28개 전부 | True (기존 16표 R/W) |
| `PREVIEW_DEV_DATABASE_URL` | `preview_dev_app` | False | 0개 (`[]`) | 0 | True (기존 16표 R/W) |
| `PREVIEW_IDENTITY_DATABASE_URL` | `preview_dev_identity_ro` | False | 1개 (`app_user`) | 0 | False |
| `PREVIEW_FIXTURES_DATABASE_URL` | `preview_dev_fixture_ro` | False | 5개 (`fixture`, `injury`, `league`, `standings`, `team`) | 0 | False |
| `PREVIEW_NAMES_DATABASE_URL` | `preview_dev_names_ro` | False | 0개 (`[]`) | 0 | False |
| `PREVIEW_STATS_DATABASE_URL` | `preview_dev_stats_ro` | False | 0개 (`[]`) | 0 | False |

- `preview_dev` 스키마 내 기존 표(16개): `checkpoint_blobs`, `checkpoint_migrations`, `checkpoint_writes`, `checkpoints`, `preview_admin_sessions`, `preview_artifacts`, `preview_attempts`, `preview_module_executions`, `preview_pipeline_runs`, `preview_results`, `preview_runs`, `preview_section_approvals`, `preview_section_results`, `preview_source_snapshots`, `preview_write_audit`, `schema_migrations` (`preview_watch_player_sections`, `preview_injury_player_sections`, `preview_player_name_candidates` 미생성 상태).

### 4.2 런처 vs 마이그레이션 도구 키 불일치

- `scripts/run_benchmark_dev.sh`는 단일 `DATABASE_URL`만 필수로 요구하고 `PREVIEW_DEV_DATABASE_URL`, `PREVIEW_IDENTITY_DATABASE_URL`, `PREVIEW_FIXTURES_DATABASE_URL`, `PREVIEW_NAMES_DATABASE_URL`, `PREVIEW_STATS_DATABASE_URL`, `BENCHMARK_READ_DATABASE_URL`을 모두 `unset`한다 (`app/db.py`, `app/preview/db.py`도 `DATABASE_URL` 단일 연결 사용).
- 반면 `scripts/preview_dev_migrate.py`는 `PREVIEW_DEV_DATABASE_URL`만, `scripts/preview_dev_status.py`는 `PREVIEW_DEV_DATABASE_URL` + `PREVIEW_IDENTITY_DATABASE_URL`을 읽는다.
- 참고: A의 `0006_*` 마이그레이션 실행 시에는 `PREVIEW_DEV_DATABASE_URL`(`preview_dev_app`)이 이미 `preview_dev` `USAGE+CREATE`와 0 `public` 권한을 만족한다. 다만 앱 런타임 전체가 단일 `DATABASE_URL`로 `public` 조회 + `preview_dev` 쓰기를 함께 수행해야 하므로, 런타임용 제한 역할이 별도로 필요하다.

### 4.3 실제 연동 차단 사유 및 C 서버 기동 보류

- **차단 사유:** 현재 `preview-dev.env`에는 `public` 쓰기·DDL 권한 없이 필요한 `public` 표(`app_user`, `fixture`, `league`, `league_translation`, `league_sync_target`, `team`, `team_translation`, `player`, `player_translation`, `injury` 등) `SELECT`와 `preview_dev` R/W(`USAGE`, `CREATE`, `SELECT/INSERT/UPDATE/DELETE`)를 함께 만족하는 제한 연결이 없다.
- **최소 필요 연결 조건:** 운영 권한자가 `preview_dev_app`(또는 별도 단일 개발 역할)에 필요한 `public` 표 `SELECT`만 부여하고 `public` 쓰기/CREATE 및 `bypassrls`/`createdb`/`createrole`이 없는 제한 DSN을 제공해야 한다. 해당 DSN을 별도 자격 파일(`PREVIEW_CREDENTIALS_FILE=/path/to/restricted.env` 내 `DATABASE_URL`)로 넘기면 기존 `scripts/run_benchmark_dev.sh`는 광권한 fallback이나 BI-01 계약 수정 없이 그대로 사용할 수 있다.
- **C 서버 (`5175`/`38002`) 기동 여부:** **미기동** (광권한 `DATABASE_URL`로의 우회 기동 금지 준수). 포트 확인 결과 `*:8000`(`second-brain-api-1`)만 리스닝 중이며 `5173~5175`, `38000~38002`는 모두 미사용 상태다.
- **제한 연결 확보 후 C / A / B 포트·환경 실행 계획:**
  - `A`: `BENCHMARK_PORT=38000`, `AUTH_COOKIE_NAME=benchmark_refresh_a`, `CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`, `BENCHMARK_BACKEND_URL=http://127.0.0.1:38000`, Vite `--port 5173`
  - `B`: `BENCHMARK_PORT=38001`, `AUTH_COOKIE_NAME=benchmark_refresh_b`, `CORS_ALLOW_ORIGINS=http://localhost:5174,http://127.0.0.1:5174`, `BENCHMARK_BACKEND_URL=http://127.0.0.1:38001`, Vite `--port 5174`
  - `C`: `BENCHMARK_PORT=38002`, `AUTH_COOKIE_NAME=benchmark_refresh_c_prep`, `CORS_ALLOW_ORIGINS=http://localhost:5175,http://127.0.0.1:5175`, `BENCHMARK_BACKEND_URL=http://127.0.0.1:38002`, Vite `--port 5175` (모두 `PREVIEW_CREDENTIALS_FILE`로 제한 연결 자격 파일 지정)

## 5. 보호 대상 확인

- 원본 `/Users/woolee/benchmark` 및 양쪽 `Plans.md` 무변경 유지.
- `8000` `second-brain-api-1` 및 자연어 검색(`AX-REPLAN-*`) 무간섭.
