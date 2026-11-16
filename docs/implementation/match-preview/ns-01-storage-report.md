# NS-01 선수 섹션 저장 구현 보고서

## 목표와 해결 문제

이 작업의 목표는 `section_players`(주목 선수)와 `section_availability`(부상/결장) 섹션 결과를 JSON 본문 하나가 아니라 `preview_dev`의 고정 4슬롯 테이블과 실행·슬롯 소유 AI 한글명 후보 테이블에 원자적으로 저장·재조회·실행 취소(undo)하는 것이다.

기존 `preview_section_results`만으로는 슬롯별 `player_id`, `original_name`, `name_ko`, `body`, `name_source`, `unresolved_reason`, `translation_candidate_id`를 정규화해 보관하거나 미검수 AI 번역 후보를 실행 단위로 추적·정리할 수 없었다. 이를 해결하기 위해 기존 `public` 스키마를 전혀 변경하지 않으면서 `preview_dev` 전용 ORM 모델 3개, 0006 마이그레이션, 후보·섹션 저장소 모듈, 기존 `store.py`의 실행 소유 undo 및 참조 충돌 차단을 최소 범위로 구현했다.

## 적용한 Poteto 원칙과 바꾼 결정

이번 작업에서 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md`와 아래 하위 원칙을 읽고 적용했다.

- **`principle-model-the-domain`**: 주목 선수(`WatchPlayerSectionInput`)와 부상·결장(`InjuryPlayerSectionInput`)의 저장·재조회 흐름을 `if/elif`로 중복 구현하지 않고 `_SectionStorageSpec` 매핑으로 통합했다. `home_etc`/`away_etc` 유무와 부상 전용 필드(`status`, `injury`, `importance`) 차이만 스펙 데이터로 분리했다.
- **`principle-make-operations-idempotent`**: `save_watch_player_section`과 `save_injury_player_section`은 동일 `section_result_id` 재호출 시 저장된 행과 후보를 정규화 딕셔너리(`canonical_dict()`)로 비교해 동일하면 기존 레코드를 그대로 반환하고, 값이 다르면 `WriteConflict`로 중단한다. `0006_player_section_storage.py` DDL도 `IF NOT EXISTS`로 반복 실행 시 안전하다.
- **`principle-boundary-discipline`**: 부모 `PreviewRun`의 취소 여부·`fixture_id`·팀 ID, 부모 `PreviewSectionResult`의 `run_id`·`workflow_id`·`output_contract_version` 일치, 후보 ID 타 슬롯/타 결과 재사용 여부를 저장 경계에서 한 번에 검증하고 내부 저장 로직은 트랜잭션을 `commit()`하지 않고 호출자 트랜잭션(`flush()`)만 사용한다.
- **`principle-sequence-verifiable-units`**: 0006 마이그레이션·ORM 등록 검증, 후보·섹션 저장소, `store.py` undo 연결, 통합 저장 테스트를 단계별로 분리해 각 단위를 로컬 PostgreSQL 테스트 DB에서 검증한 뒤 다음 단계로 넘겼다.
- **`principle-test-behavior-not-implementation`**: 내부 private 헬퍼 호출이 아니라 저장·재조회, 롤백 원자성, 멱등 재저장, 충돌 거부(`WriteConflict`/`RunNotFound`), 실행 취소와 참조 차단, 기존 `mp04-section-result-1` 보존을 실제 PostgreSQL 트랜잭션 결과로 검증했다.
- **`principle-prove-it-works` / `unslop` / `technical-writing` / `no-comments`**: 실제 Docker PostgreSQL 테스트 DB(`preview_mp01_test`)에서 `pytest`와 `scripts/preview_dev_migrate.py` 적용·멱등성을 직접 확인한 결과만 근거로 기록했다.

## 공통 계약 동기화 상태

- 시작 기준 커밋: `3f80cc2853631ed54e77d1f94255afb943b9f765`
- 공통 계약 수정 cherry-pick 적용 커밋: `79ddbb7` (원본 커밋 `568f2b6ec2c1b219d164e3efb6a7cf0d44145cc9`: 0 기반 `attempt_ordinal`, 문자열 `evidence` ID 보존, `deterministic_candidate_id` 기반 안정적 후보 UUID)
- 공통 파일(`app/preview/player_section_contracts.py`, `tests/preview/test_player_section_contracts.py`)은 A에서 임의 수정하지 않았고 충돌 없이 cherry-pick 후 저장 경로와 직접 연동 검사를 추가 확인했다.

## 변경 파일

- 신규 `app/preview/player_section_models.py`: `PreviewPlayerNameCandidate`, `PreviewWatchPlayerSection`, `PreviewInjuryPlayerSection` ORM 모델 (`preview_dev` 스키마 전용, `public` FK 없음).
- 수정 `app/preview/models.py`: 신규 3개 ORM 모델을 `Base.metadata`에 등록·재노출.
- 신규 `alembic/versions/0006_player_section_storage.py`: `preview_dev`에 3개 테이블과 인덱스/`UNIQUE(section_result_id, slot_key)`를 멱등 DDL로 추가. 공용 Alembic 체인 실행 시 `RuntimeError`로 거부.
- 수정 `scripts/preview_dev_migrate.py`: `MIGRATION_PATHS`에 `0006_player_section_storage.py` 등록.
- 신규 `app/preview/player_name_candidates.py`: 실행·결과·슬롯 단위 AI 번역 후보 저장 및 `unresolved_reason` 조인 조회 API.
- 신규 `app/preview/player_section_store.py`: `WatchPlayerSectionInput`/`InjuryPlayerSectionInput` 저장·재조회 API.
- 수정 `app/preview/store.py`: `undo_report`, `cancel_run`, `_cancel_conflict`에 새 3개 테이블 개수·FK 안전 삭제 순서·감사(`run_cancelled`)·활성 승인/타 실행 구성본(`section_composition`) 참조 충돌 차단 연결.
- 수정 `tests/preview/test_migration_schema.py`: `0006_player_section_storage` DDL-ORM 일치, 멱등성, `preview_dev_migrate.py` 등록 및 Alembic 차단 검증 추가.
- 신규 `tests/preview/test_player_section_storage.py`: 저장·재조회, 롤백 원자성, 미확인 선수·빈 자리·pending 후보, 멱등 재저장 및 충돌, 실행별 undo 및 활성 승인/타 실행 구성본 참조 충돌, 기존 `mp04-section-result-1` 보존 검사.

## C 인계용 저장 API 계약

### 1. `app/preview/player_section_store.py`

호출자는 반드시 같은 DB 트랜잭션 안에서 `store.save_section_result(...)`로 부모 `PreviewSectionResult`를 먼저 생성(`flush`)한 뒤 아래 함수를 호출하고, 마지막에 직접 `session.commit()`한다. 아래 함수들은 내부에서 `commit()`하지 않는다.

- `save_watch_player_section(session: Session, section_input: WatchPlayerSectionInput, *, actor_id: int = 0, now: datetime | None = None) -> WatchPlayerSectionRecord`
- `save_injury_player_section(session: Session, section_input: InjuryPlayerSectionInput, *, actor_id: int = 0, now: datetime | None = None) -> InjuryPlayerSectionRecord`
- `save_player_section(session: Session, section_input: WatchPlayerSectionInput | InjuryPlayerSectionInput, *, actor_id: int = 0, now: datetime | None = None) -> WatchPlayerSectionRecord | InjuryPlayerSectionRecord`
  - 입력의 `candidates`를 먼저 `preview_player_name_candidates`에 저장·flush한 뒤 섹션 행을 저장·flush하고 `preview_write_audit`에 기록한다.
  - 동일 `section_result_id` + 동일 `canonical_dict()` 재저장은 기존 레코드를 반환(멱등)한다.
  - 예외: 부모 `PreviewRun`/`PreviewSectionResult` 부재 시 `RunNotFound`, 값 불일치·실행 취소 상태·소유 `run_id`/`fixture_id`/팀 ID/`workflow_id`/`output_contract_version` 불일치·타 결과/슬롯 후보 ID 충돌 시 `WriteConflict`, 계약 위반 시 `ContractError`.
- `get_watch_player_section(session: Session, section_result_id: uuid.UUID, *, run_id: uuid.UUID | None = None) -> WatchPlayerSectionRecord | None`
- `get_injury_player_section(session: Session, section_result_id: uuid.UUID, *, run_id: uuid.UUID | None = None) -> InjuryPlayerSectionRecord | None`
- `get_player_section(session: Session, section_result_id: uuid.UUID, *, workflow_id: PlayerSectionWorkflowId | str | None = None, run_id: uuid.UUID | None = None) -> WatchPlayerSectionRecord | InjuryPlayerSectionRecord | None`
  - `run_id`를 생략하면 구성본·공개 조회용으로 결과 ID 기준 재조회가 가능하고, `run_id`를 넘기면 해당 실행 소유 결과만 반환한다.

### 2. `app/preview/player_name_candidates.py`

모든 조회 함수는 원래 섹션 슬롯의 `unresolved_reason`을 연결한 `PlayerNameCandidateRecord` 튜플 또는 단건을 반환한다.

- `get_candidate(session: Session, candidate_id: uuid.UUID, *, run_id: uuid.UUID | None = None) -> PlayerNameCandidateRecord | None`
- `list_candidates_for_section_result(session: Session, section_result_id: uuid.UUID, *, run_id: uuid.UUID | None = None) -> tuple[PlayerNameCandidateRecord, ...]`
- `list_candidates_for_run(session: Session, run_id: uuid.UUID, *, review_status: CandidateReviewStatus | str | None = None) -> tuple[PlayerNameCandidateRecord, ...]`
- `list_pending_candidates(session: Session, *, run_id: uuid.UUID | None = None, fixture_id: int | None = None, workflow_id: PlayerSectionWorkflowId | str | None = None, limit: int = 100) -> tuple[PlayerNameCandidateRecord, ...]`

### 3. `app/preview/store.py` undo 계약 변경

- `undo_report(session, run_id)["would_remove"]`와 `cancel_run(session, run_id, ...)["removed"]`에 `preview_watch_player_sections`, `preview_injury_player_sections`, `preview_player_name_candidates` 건수가 포함된다.
- `cancel_run` 삭제 순서: `preview_watch_player_sections`·`preview_injury_player_sections` -> `preview_player_name_candidates` -> `preview_artifacts` 등 -> `preview_section_results` -> `preview_results` -> `preview_module_executions`.
- `_cancel_conflict`는 활성 `PreviewSectionApproval`(`active=True`) 또는 타 실행 `section_composition` 아티팩트(`run_id != row.id`)가 해당 실행의 `section_result_id`를 참조할 때 `WriteConflict`로 중단한다.

## 검증 명령과 결과

로컬 Docker PostgreSQL 테스트 DB(`match-preview-pg-mp01`, `127.0.0.1:55432/preview_mp01_test`, `_dbguard` 통과 대상)에서만 실행했다. 공유 운영 DB에는 연결·마이그레이션하지 않았다.

1. `/Users/woolee/benchmark/.venv/bin/python -m pytest tests/preview/test_player_section_storage.py tests/preview/test_migration_schema.py tests/preview/test_player_section_contracts.py tests/preview/test_run_store.py tests/preview/test_inspection_api.py -q`
   - 결과: `54 passed, 1 warning in 11.27s`
2. `PREVIEW_DEV_DATABASE_URL="postgresql://preview:preview_local_dev@127.0.0.1:55432/preview_mp01_test" /Users/woolee/benchmark/.venv/bin/python scripts/preview_dev_migrate.py --dry-run` 및 본 실행 2회
   - 결과: `--dry-run`에서 `0006_player_section_storage: pending`(`40 statements pending`), 1차 실행에서 `0006_player_section_storage: applied`, 2차 실행에서 `0006_player_section_storage: already applied` 확인.

## 미해결 사항 및 후속 인계

- 제한 DB 연결 권한(public SELECT + preview_dev 쓰기) 준비 및 공유 `preview_dev` 대상 `scripts/preview_dev_migrate.py` 실제 적용은 C 준비·NS-03 범위로 남아 있다.
- 프론트 `5173` / 백엔드 `38000` 기동 및 실로그인·실호출 확인은 제한 DB 권한 미충족 지침에 따라 이 작업에서 수행하지 않았다.
