# NS-03 · NS-04 선수·부상 섹션 통합 완료 보고서 (C 통합)

- **작성 시각**: 2026-11-16
- **작업 브랜치 / 작업트리**: `lebind12/player-section-integration` (`/Users/woolee/orca/workspaces/benchmark/player-section-integration`)
- **Orca 태스크 / 세션**: `task_c5545c784c81` (`dispatch_id=ctx_1c942801c317`, `orca_session_id:7913fa2d-2b33-46d0-b3cc-0aeb4dd1d679`, 모델 `Gemini 4 Hydrogen (High)`)

---

## 1. 병합 기준 커밋 및 통합 커밋

| 구분 | 기준 커밋 / 병합 커밋 | 비고 |
|---|---|---|
| A 저장 계층 (NS-01) | `5b6088d` (`merge(ns-03)`: `2277841`, `9e67d6f`) | `0006_player_section_storage` 포함. `preview_dev` 기존 0006 마이그레이션 유지·재실행 없음 |
| B 생성·처리·UI (NS-02) | `755ee65` → `9f042cd` (`14911e3`), 최종 테스트/보고 `bbc0c9c` (`ccbffb3`) | 두 브랜치 이력 보존, B 파일(`PreviewRunsView.logout.test.ts`, `ns-02-generation-report.md`) 미수정 |
| C 통합 코드·테스트 | **`231d613`** (`231d6136aca04c5aa711bd406f98b4f392279395`) | 백엔드 8파일·프론트엔드 7파일·테스트 5파일 (총 20파일) |

---

## 2. 적용 스킬 및 원칙 (`.agents/skills/poteto-mode/SKILL.md`)

- `.agents/skills/poteto-mode/SKILL.md`를 동일 세션에서 먼저 전문 읽기 완료 후 재사용.
- 적용 원칙 요약:
  - 기존 A/B 커밋 이력과 B의 제품 코드·테스트를 덮어쓰지 않고 통합 계층만 연결.
  - 거짓 완료·묵시적 대체 금지: 새 계약 결과가 정본 DB에 없을 때 `PreviewResult.payload`로 대체하지 않고 명시적 `storage_mismatch`를 표면화.
  - 기존 워크플로우/승인 보존: `section_players`·`section_availability`만 새 계약·구현 버전으로 분리해 `section_odds` 등 타 섹션 승인 해시를 흔들지 않음.
  - 실행한 검증 결과만 보고하고, 미실행인 실제 AI 호출·실제 ADMIN 브라우저 클릭·사용자 섹션 승인은 미검증으로 구분.

---

## 3. 통합 구현 요약

### 3.1 워크플로우 버전 분리 (`registry.py`, `bundle_sections.py`, `bundle_pipeline.py`)

`SECTION_RESULT_CONTRACT_VERSION="mp04-section-result-1"`(공통)과 `IMPLEMENTATION_VERSION="mp11-bundle-sections-7"`(타 섹션)을 유지한 채, 선수·부상 섹션만 아래처럼 분리했다.

| `workflow_id` | `output_contract_version` | `runner.section_workflow_version(...)` | 비고 |
|---|---|---|---|
| `section_players` | `ns01-watch-players-1` | `section_players@75313897ac9b749e` | `PLAYER_SECTION_IMPLEMENTATION_VERSION="mp11-bundle-sections-8"` 적용 |
| `section_availability` | `ns01-injury-players-1` | `section_availability@81c30e5bb989e7fe` | `PLAYER_SECTION_IMPLEMENTATION_VERSION="mp11-bundle-sections-8"` 적용 |
| `section_outlook` | `section_outlook-output-1` | `section_outlook@0145de693ebdef28` | 기존 승인 해시 보존 |
| `section_odds` | `mp11-odds-output-1` | `section_odds@49923b1c5dcb467a` | 기존 승인 해시 보존 (`section_odds@49923b1c5dcb467a` 불변) |
| `section_ai_forecast` | `mp11-ai-forecast-output-1` | `section_ai_forecast@c186f27356d4bb80` | 기존 승인 해시 보존 |

### 3.2 생성 → 정본 3표 동일 트랜잭션 저장 및 후작성 차단 (`bundle_pipeline.py`)

- `_save_draft`에서 `store.save_section_result(...)` 직후 `section_players` / `section_availability`에 대해 `player_section_store.save_player_section(...)`을 **같은 미커밋 세션/트랜잭션**에서 실행한다.
- 정본 저장 실패 시 `session.rollback()`으로 `PreviewResult`·`PreviewSectionResult`·정본 3표가 함께 롤백된다.
- 새 계약 결과(`ns01-watch-players-1` / `ns01-injury-players-1`)에는 `rewrite_body` 사후 재작성을 수행하지 않는다.
- `PreviewWatchPlayerSection`의 `home_etc`/`away_etc`는 `NULL`을 유지하며, `PreviewInjuryPlayerSection` 스키마(`etc` 컬럼 없음)와 일치한다.

### 3.3 정본 DB 재조회·불일치 표면화·공개 문서 투영 (`player_section_read.py`, `preview_admin.py`, `home_preview_document.py`, `section_preview.py`, `section_structured.py`)

- `player_section_read.py`(`read_canonical_player_section`, `is_new_player_section_contract`, `section_expects_canonical_storage`) 신설:
  - 새 계약(`ns01-watch-players-1`, `ns01-injury-players-1`)은 관리자 검사(`GET /runs/{run_id}`, `GET /runs/{run_id}/section-results`), 리더 뷰(`section_preview.py`), 홈 공개 문서(`home_preview_document.py`) 모두에서 정본 3표(`PreviewWatchPlayerSection`, `PreviewInjuryPlayerSection`, `PreviewTranslationCandidate`)를 재조회한다.
  - 정본 행이 DB에서 검증될 때만 `persisted=True` / `storage_status="persisted"`를 반환한다.
  - `unavailable`이 아닌 새 계약 결과인데 정본 행이 없으면 레거시 `PreviewResult.payload`로 대체하지 않고 `persisted=False`, `storage_mismatch=True`, `storage_status="storage_mismatch"`를 명시 반환한다.
  - 구 계약 결과는 기존 `PreviewResult.payload` 읽기 경로와 `persisted=False`, `storage_mismatch=False`를 유지한다.
- 공개/카드 투영:
  - 홈 공개 문서(`home_preview_document.py`)와 리더 뷰(`section_preview.py`)에서 내부 ID(`player_id`, `team_id`)를 제거하고, `external_player_id`·`photo_url`·`team_side`(`home`/`away`)·`slot_key`·`unresolved`를 유지한다.
  - 빈 슬롯(`NULL`)은 공개 카드 목록에서 제외한다.

### 3.4 프론트엔드 관리자/카드 연결 (`frontend/src/features/match-preview/*`, `frontend/src/lib/api/previewView.ts`)

- `types.ts`: `SectionResultView`, `PlayerSectionProcessingViewData`, `SectionStructuredPlayerRow`, `SectionStructuredInjuryRow`, `PlayerSectionSlotDraftView`에 `persisted`, `storage_status`, `storage_mismatch`, `storage_error`, `team_side`, `slot_key`, `unresolved`, `photo_url`, `translation_candidate_id`, `candidate_review_status` 추가.
- `PlayerSectionProcessingView.vue`: `persisted || storage_mismatch`일 때 임시 안내 배너(`#ns02-pending-note`)를 숨기고, `storage_mismatch` 시 `'저장 불일치'` 상태 배지 및 `#ns02-storage-mismatch` 경고 배너 표시, 슬롯별 `photo_url`·`candidate_review_status` 표시.
- `RunInspector.vue`, `SectionRunView.vue`: `storage_mismatch` 시 `[data-testid="section-storage-mismatch"]` 경고 배너 표시. 또한 `vue-tsc -b` 빌드 중 발견된 `RunInspector.vue` line 124의 `row.section_id` 타입/키 불일치를 `row.workflow_id`로 수정.
- `sectionStructured.ts`, `previewView.ts`: `team_side` fallback(`home`/`away`)·`slot_key`·`unresolved`·`photo_url`을 카드 뷰 모델(`MatchPreviewBody.vue`)로 전달(내부 ID 없음).

---

## 4. 검증 결과 (직접 실행·관측 기준)

### 4.1 백엔드 자동 테스트 (`preview_mp01_test` 합성 DB)

1. 통합·계약·저장·파이프라인·승인·검사 12개 파일 (`task-1064`, 마지막 Python 편집 이후 실행):
   ```sh
   PYTHONPATH=. /Users/woolee/benchmark/.venv/bin/pytest \
     tests/preview/test_player_section_contracts.py \
     tests/preview/test_player_section_storage.py \
     tests/preview/test_player_section_processing.py \
     tests/preview/test_player_section_integration.py \
     tests/preview/test_workflow_version.py \
     tests/preview/test_section_approvals.py \
     tests/preview/test_inspection_api.py \
     tests/unit/test_home_preview_document.py \
     tests/preview/test_bundle_sections.py \
     tests/preview/test_bundle_pipeline.py \
     tests/preview/test_bundle_review_fixes.py \
     tests/preview/test_bundle_integration.py -q
   ```
   - 결과: **`173 passed, 2 skipped, 1 warning in 50.41s`** (exit 0).
   - `2 skipped` 사유: `test_bundle_pipeline.py` 및 `test_bundle_integration.py`의 선택적 원래 `DATABASE_URL` / `team_translation` 환경 검사.
   - `tests/preview/test_player_section_integration.py` 신규 5건 포함:
     - `test_bundle_pipeline_saves_canonical_tables_and_rereads_every_surface`
     - `test_regeneration_persists_canonical_rows_without_mutating_parent_run`
     - `test_save_player_section_failure_rolls_back_section_result_atomically`
     - `test_missing_canonical_row_surfaces_explicit_storage_mismatch_without_legacy_fallback`
     - `test_legacy_contract_still_reads_legacy_payload_and_workflow_versions_isolated`
2. 공개 문서 단위 테스트 재확인:
   ```sh
   PYTHONPATH=. /Users/woolee/benchmark/.venv/bin/pytest tests/unit/test_home_preview_document.py
   ```
   - 결과: **`16 passed in 0.27s`** (exit 0).

### 4.2 프론트엔드 타입 검사 · Vitest · Vite 빌드 (마지막 프론트엔드 편집 이후 실행)

```sh
cd frontend && npm run type-check && npx vitest run \
  src/features/match-preview/PlayerSectionProcessingView.test.ts \
  src/features/match-preview/PlayerSectionStorage.test.ts \
  src/features/match-preview/SectionRunView.test.ts \
  src/features/match-preview/SectionRegenerationPanel.test.ts \
  src/features/match-preview/AdminPreviewRouting.test.ts \
  src/features/match-preview/MatchPreview.test.ts \
  src/components/home-preview/ \
  src/lib/api/ && npm run build
```
- `npm run type-check` (`vue-tsc --noEmit`): **exit 0** (오류 0건)
- Vitest 대상 8개 파일: **`Test Files 8 passed (8)`, `Tests 52 passed (52)`**
  - 신규 `PlayerSectionStorage.test.ts` (4건) 포함: 정본 저장 배지/임시 배너 숨김, `storage_mismatch` 배지·배너(`RunInspector`·`SectionRunView`), `MatchPreviewBody` 홈/원정 카드 및 `photo_url`/플레이스홀더·상태 라벨(`출전 불투명`) 투영 확인
- `npm run build` (`vue-tsc -b && vite build`): **exit 0 (`✓ built in 3.97s`)**

### 4.3 C 서버 기동 및 비변경 HTTP 확인 (`38002` / `5175`)

- A(`38000`/`5173`), B(`38001`/`5174`), Docker `8000` 미접촉.
- C 백엔드 터미널(`term_d8731431-0309-4b85-af6e-50227cb9e2f5`)만 기존 restricted env(`PREVIEW_CREDENTIALS_FILE="$HOME/.config/match-preview/preview-dev-restricted.env"`, `BENCHMARK_PORT=38002`, `AUTH_COOKIE_NAME=benchmark_refresh_c_prep`, `LOCAL_DEV_AUTH_ENABLED=true`, `CORS_ALLOW_ORIGINS="http://localhost:5175,http://127.0.0.1:5175"`)로 재기동 (`PID 11760`).
- HTTP 확인 결과:
  - `GET http://127.0.0.1:38002/health` → `200` (`{"status":"ok"}`)
  - `GET http://127.0.0.1:38002/api/v1/home/fixtures` → `200` (`{"items":[],"filters_applied":{"period":"day","league_id":null}}`)
  - `GET http://127.0.0.1:38002/api/v1/auth/me` → `401`
  - `GET http://127.0.0.1:38002/api/v1/admin/preview/runs` → `401`
  - `GET http://127.0.0.1:5175/`, `/admin/sections`, `/admin/runs` → `200` (Vite SPA HTML, `RunInspector.vue` HMR 반영 확인)

---

## 5. 미실행·미검증 범위 (완료로 간주하지 않음)

- **실제 AI 모델 호출(Vertex/live 생성) → `preview_dev` 정본 3표 저장 → 관리자 검사/홈 카드 실물 확인**: 미실행.
- **실제 ADMIN 브라우저 세션 로그인 후 `/admin/sections`·`/admin/runs` UI 조작 및 승인**: 미실행 (root 브라우저 세션 보호).
- **사용자 섹션 워크플로우 승인**: 미완료 (자동 테스트 통과는 사용자 승인이 아님).

---

## 6. 후속 수정: 최초 LIVE 선수·부상 섹션 실행 404 해소 (`task_4ae0d636296d` / `ctx_c02c30ff73dd`)

### 6.1 원인 및 최소 수정

- **재현 결함**: `/admin/sections`(`SectionRunView.vue`)에서 기준 실행 없이(`base_run_id=None`) 경기 선택 → `section_players` 또는 `section_availability` → `live` 실행 시 `preview_admin.create_section_run`이 `base_run_id=payload.base_run_id or uuid.uuid4()`로 `run_section_regeneration`을 호출해 `404 base run not found`가 발생.
- **`app/preview/bundle_pipeline.py`**:
  - `INITIAL_PLAYER_SECTIONS = ("section_players", "section_availability")` 정의.
  - `build_single_section_bundle_graph`, `_finalize_single_section_node`, `run_section_initial` 추가: 기존 LangGraph 노드(`D0` → `discovery_people` → `collection` → `_section_node` → `_save_draft` → `finalize`)만 재사용해 선택한 섹션 1개와 필요한 인물 조사·수집만 실행하고 `player_section_store.save_player_section`까지 동일 트랜잭션으로 저장한다(타 섹션·`discovery_outlook`·전체 일괄 생성·옛 runner fallback 우회 없음).
- **`app/api/v1/preview_admin.py` (`create_section_run`)**:
  - `payload.base_run_id is None`인 최초 실행과 `payload.base_run_id is not None`인 기존 재생성을 명확히 분리(가짜 `uuid.uuid4()` 제거).
  - `base_run_id is None`일 때 `source_mode="reuse"`·`base_result_id`/`composition_id` 지정·`INITIAL_PLAYER_SECTIONS` 외 타 섹션(`section_outlook`, `section_odds`, `section_ai_forecast`)·경기 식별자 누락은 `422`로 거부.
  - 기존 `base_run_id` 재생성(`source_mode=reuse/refresh`, `selected_result_ids`, `composition_id`, 없는 `base_run_id` 404) 경로는 그대로 보존.

### 6.2 경계 검증 결과 (`preview_mp01_test` 합성 환경)

- 1차 확인(`task-1271`): `35 passed, 1 failed, 1 skipped in 18.46s` — 신규 테스트 `test_player_section_integration.py`에서 `/runs/{run_id}` 응답의 `detail_json["section_results"][0]["persisted"]` 키를 잘못 참조해 `KeyError` 1건 발생(`/runs/{run_id}`는 `player_section_processing[workflow_id]["persisted"]`, `/runs/{run_id}/section-results`는 `section_results[0]["persisted"]` 계약 유지).
- 테스트 단언을 실제 API 계약 두 경로 모두(`detail_json["player_section_processing"][workflow_id]["persisted"]` 및 `sr_json["section_results"][0]["persisted"]`) 검증하도록 보완 후 재실행:
  - `PYTHONPATH=. /Users/woolee/benchmark/.venv/bin/pytest tests/preview/test_player_section_integration.py tests/preview/test_bundle_integration.py -v` (`task-1279`): **`36 passed, 1 skipped, 1 warning in 17.34s`**
  - `PYTHONPATH=. /Users/woolee/benchmark/.venv/bin/pytest tests/preview/test_form_module.py -k test_live_run_requires_fixture_identity -v`: **`1 passed, 20 deselected, 1 warning in 0.95s`**
- 단위 모델 스텁 기반 검증이며 실제 AI 모델 호출·브라우저·`preview_dev` 실저장은 아직 미실행.

## 7. 정본 조회 문자열·매핑 evidence 보존 수정 (`task_edc631d3664b`)

### 7.1 원인 및 수정 (`app/preview/player_section_read.py`)
- 기존 실호출 실행 `86a2408c-5696-4d93-8140-ca9ac26a2af9` (`fixture_id=1557474`, `section_players`)의 정본 테이블에 문자열 `evidence` (`['people-summary-1', 'people-span-1']`, `['people-summary-1', 'people-span-2']`)가 저장돼 있었으나, `app/preview/player_section_read.py`의 `_slot_processing_dict`와 `read_canonical_player_section`이 `[item.value for item in projection.evidence]`를 가정해 `GET /api/v1/admin/preview/runs/{run_id}`에서 500 `AttributeError`가 발생했다.
- `_serialize_evidence(items)` 헬퍼를 추가해 공통 계약 `EvidenceItem`(`str | Mapping`)과 선택적 `.value` 객체를 모두 손실 없이 직렬화하도록 수정하고 두 호출부를 교체했다.

### 7.2 기존 실실행 `86a2408c-5696-4d93-8140-ca9ac26a2af9` 읽기 전용 점검 (`preview_dev`)
- 조건: `SET TRANSACTION READ ONLY` + `rollback()`, `preview-dev-restricted.env` 사용, 신규 AI 호출 및 DB 쓰기·변경·undo 없음.
- 실행 요약: `operation_kind='section'`, `status='succeeded'`, `quality='ready'`, `fixture_id=1557474`, `home_team_id=13`, `away_team_id=4`.
- 테이블 건수: `section_results=1` (`id='32cc83da-55ca-46fb-bd48-0d56c63a1621'`, `workflow_id='section_players'`, `workflow_version='section_players@75313897ac9b749e'`, `output_contract_version='ns01-watch-players-1'`, `quality='ready'`, `version=1`), `watch_sections=1`, `injury_sections=0`, `candidates=0`.
- 슬롯 저장 상태 (`home_etc=None`, `away_etc=None`, 전 슬롯 `name_source='db_ko'`, `candidate_id=None`):
  - `home1`: `player_id=533`, `external_id=1100`, `'엘링 홀란드'`, `evidence=['people-summary-1', 'people-span-1']`
  - `home2`: `player_id=541`, `external_id=156477`, `'라얀 셰르키'`, `evidence=['people-summary-1', 'people-span-1']`
  - `away1`: `player_id=124`, `external_id=1455`, `'알렉산더 츄카 이워비'`, `evidence=['people-summary-1', 'people-span-2']`
  - `away2`: `player_id=144`, `external_id=278133`, `'오스카 보브'`, `evidence=['people-summary-1', 'people-span-2']`
- 수정 후 읽기 전용 `preview_admin.get_run(UUID('86a2408c-5696-4d93-8140-ca9ac26a2af9'), ...)` 호출 확인: `persisted=True`, `storage_status='persisted'`, `storage_mismatch=False`, `home1_name='엘링 홀란드'`, `home1_ext=1100`, `home1_photo='https://media.api-sports.io/football/players/1100.png'`, `home1_evidence=['people-summary-1', 'people-span-1']`, `away1_evidence=['people-summary-1', 'people-span-2']`, `structured_count=0`, `structured_0_evidence=None`.

### 7.3 로컬 합성 테스트 (`preview_mp01_test`)
- `tests/preview/test_player_section_integration.py`에 `test_canonical_read_preserves_string_and_mapping_evidence` 추가 (문자열 및 `str | Mapping` 혼합 `evidence` 저장 후 `GET /api/v1/admin/preview/runs/{run_id}` 및 `GET /api/v1/admin/preview/runs/{run_id}/section-results?include_structured=true` 보존 검증).
- 실행 명령: `PYTHONPATH=. /Users/woolee/benchmark/.venv/bin/pytest tests/preview/test_player_section_integration.py tests/preview/test_inspection_api.py tests/preview/test_player_section_storage.py -q`
- 결과: `33 passed, 1 warning in 12.69s`.

---

## 8. 진단 투영·상태·안내 문구·미승인 카드 미리보기 연결 (`task_3235d0814e16`)

### 8.1 확인된 원인 및 수정 사항

1. **실행 0회 / 채택 시도 없음 오표시 (`PlayerSectionProcessingView`)**:
   - **원인**: `bundle_pipeline._save_draft`는 `ModuleResult.to_dict()` 래퍼(`{"run_id", "module_id", "status", "payload": {"structured": {"processing": ...}}}`) 형태로 `preview_results.payload`를 저장하지만, `app/api/v1/preview_admin.py`의 `_extract_player_section_processing`이 바깥 dict만 확인해 `raw_processing=None`을 반환했다. 그 결과 정본 재조회에서 `module_attempt_count=0`, `adopted_attempt_ordinal=None`, `attempts=[]`로 초기화됐고, `PlayerSectionProcessingView.vue`도 `ok || persisted`일 때 `adopted_attempt_ordinal == null`을 `'채택 시도 없음 (실패)'`로 고정 표시했다.
   - **수정**:
     - `app/api/v1/preview_admin.py` `_extract_player_section_processing`: 바깥 `payload`와 `payload.get("payload")`를 모두 탐색하도록 보완해 `get_run`과 `get_section_results` 모두 저장된 `module_attempt_count`, `adopted_attempt_ordinal`, `attempts`를 그대로 복원한다.
     - `frontend/src/features/match-preview/PlayerSectionProcessingView.vue`: `ok || persisted`이면서 추적만 비어 있을 때 `'채택 시도 추적 미기록 (저장·성공)'` / `'추적 미기록 (저장·성공)'`으로 표시해 실패와 구분한다.
2. **모듈 실행 상태 `running` 잔존 및 R4(0명)·R2(빈 패널) 표시**:
   - **원인 (쓰기 측 보고 대상)**: `app/preview/bundle_pipeline.py:467-560`의 `_save_draft`가 `store.start_module_execution` + `store.save_module_result`만 호출하고 `store.update_module_delivery(..., status=..., quality=...)`를 호출하지 않아, 기존 `preview_dev` DB의 `preview_module_executions` 행(`R4`, `R2`)이 `status='running'`, `quality='pending'`, `finished_at=None`으로 남았다(상류 쓰기 측 보완 후보로 보고).
   - **원인 (읽기/UI 투영)**: `RunInspector.vue`가 `bundle_pipeline`의 `SectionDraft`(`structured` + `player_section_processing`)를 기존 R4(`PlayersPanel.vue`)·R2(`AvailabilityPanel.vue`) 패널이 기대하는 legacy 필드로 투영하지 않고 그대로 넘겼다.
   - **수정**:
     - `app/preview/store.py` `_module_view`: DB 행을 변경하지 않고, `row.status == "running"`이면서 최신 `PreviewResult`가 종료 상태(`succeeded`/`failed`)이면 읽기 응답에서 `status`, `quality`, `finished_at`을 최신 결과 기준으로 투영한다.
     - `frontend/src/features/match-preview/bundlePanelAdapters.ts` 추가 및 `RunInspector.vue` 연결: `adaptPlayersPanelResult`·`adaptAvailabilityPanelResult`로 `bundle_pipeline` R4/R2 실행을 기존 패널 계약으로 투영한다(기존 legacy R4/R2 payload는 그대로 통과).
3. **구 버전 하드코딩 `availability_note` 교정**:
   - **원인**: `app/preview/inspection.py` `build_run_inspection`이 `"D0·R1·R2·R3·S1의 실제 조사 구현은 아직 등록되지 않았습니다..."`를 무조건 반환했다.
   - **수정**: `_build_availability_note(registry, run_mode)`를 추가해 `describe_registry()`의 `implemented` / `unavailable` 모듈·섹션 목록과 `run_mode`를 반영하도록 교체했다.
4. **미승인 상태 실제 사진 카드(`MatchPreviewBody`) 명시적 관리자 미리보기 연결**:
   - **기존 경로 점검**: `MatchPreviewBody.vue`는 `/admin`(`PreviewPanel.vue`)에서만 쓰였고, `/admin/runs`(`RunInspector.vue`)와 `/admin/sections`(`SectionRunView.vue`)는 `/runs/{id}`만 읽어 `structured`(`photo_url`)가 빠지거나, `SectionRunView.vue`의 `openReaderPreview`가 존재하지 않는 `'preview-reader'` 라우트(`section_synthesis` 전용)를 가리켰다.
   - **수정**:
     - `app/api/v1/preview_admin.py` `_attach_player_section_processing`: `/runs/{id}` 응답의 정본 선수/부상 섹션 행에도 `structured`·`available`·`persisted`·`storage_status`를 함께 부착해 `photo_url`과 `team_side`가 바로 전달되게 했다.
     - `RunInspector.vue` 및 `SectionRunView.vue`: 섹션 결과(`sectionResults`)와 `section-results`(지원 시 보강 병합)를 이용해 `toMatchPreviewView`로 `MatchPreviewBody`를 조립하는 접힘형 블록(`data-testid="unapproved-card-preview"`, `"미승인 관리자 카드 미리보기 · 실제 카드(MatchPreviewBody) 확인 (공개·홈 미반영)"`)을 연결했다. 기본 홈/공개 승인 상태는 변경하지 않는다.

### 8.2 검증 결과 (`preview_dev` 읽기 전용 실실행 2건 + 합성 단위 테스트)

- **운영 `preview_dev` 읽기 전용 `preview_admin._detail_or_404` 확인** (`SET TRANSACTION READ ONLY` + `rollback()`, DB 행 무변경, 모델 재호출 없음):
  - `86a2408c-5696-4d93-8140-ca9ac26a2af9` (`section_players`):
    - `inspector_modules`: `[{'id': 'R4', 'status': 'succeeded', 'quality': 'ready', 'attempt_count': 1, 'mod_proc_attempts': 1}]`
    - `player_section_processing`: `persisted=True`, `storage_status='persisted'`, `storage_mismatch=False`, `module_attempt_count=1`, `adopted_attempt_ordinal=0`, `attempts_len=1`, `parsed_valid=[True]`
    - `sr_structured`: `persisted=True`, `available=True`, `count=4` (엘링 홀란드 1100, 라얀 셰르키 156477, 알렉산더 츄카 이워비 1455, 오스카 보브 278133 모두 `photo_url` 포함)
    - `availability_note`: `"실제 실행 구현이 등록된 모듈: R1·R2·R3·R4·S1·mock_demo. 단독 미등록/자료 준비 단계(D0) 외 섹션 워크플로우에서 실행할 수 있습니다. 실제 생성 섹션 결과만 승인 근거로 사용하며, 모의 결과는 승인 근거로 쓰지 않습니다."`
  - `d2764e8d-5aa8-44ca-beb4-97faa91a8929` (`section_availability`):
    - `inspector_modules`: `[{'id': 'R2', 'status': 'succeeded', 'quality': 'ready', 'attempt_count': 1, 'mod_proc_attempts': 1}]`
    - `player_section_processing`: `persisted=True`, `storage_status='persisted'`, `storage_mismatch=False`, `module_attempt_count=1`, `adopted_attempt_ordinal=0`, `attempts_len=1`, `parsed_valid=[True]`
    - `sr_structured`: `persisted=True`, `available=True`, `count=4` (앙투안 세메뇨 19281, 마크 게히 67971, 톰 케어니 19025, 조슈아 킹 389315 모두 `photo_url` 포함)
- **백엔드 표적 검사 (`preview_mp01_test`)**:
  - `PYTHONPATH=. /Users/woolee/benchmark/.venv/bin/pytest tests/preview/test_inspection_api.py tests/preview/test_player_section_integration.py -q`: **`27 passed, 1 warning in 11.23s`**
- **프론트엔드 타입·단위 검사**:
  - `npm --prefix frontend run type-check && npm --prefix frontend run test:unit -- src/features/match-preview/BundlePanelAdapters.test.ts src/features/match-preview/PlayerSectionProcessingView.test.ts src/features/match-preview/SectionRunView.test.ts src/features/match-preview/panels/AvailabilityPanel.test.ts src/features/match-preview/PlayerSectionStorage.test.ts`: **`type-check` 오류 0건, `Test Files 5 passed (5)`, `Tests 24 passed (24)`**
  - 비고: 기존 `RunInspector.test.ts` 및 `R4PanelAndBody.test.ts`는 이전 커밋(`b2ac969`)의 `authenticatedFetch` 도입 이후 `setAccessToken`이 설정되지 않아 기존 상태에서도 실패하며 본 작업에서 수정하지 않았다(신규 R4/R2·카드 미리보기 검증은 `BundlePanelAdapters.test.ts`에서 `setAccessToken('test-token')`으로 수행).

## 9. 제한 role 기반 합성 DB 저장·조회·undo 검증 및 최종 5173/38000 기동 증거

### 9-1. 제한 연결(`preview_dev_runtime`) 권한 확인
- **사용 환경 파일**: `$HOME/.config/match-preview/preview-dev-restricted.env` (`SET TRANSACTION READ ONLY` 세션에서 역할·권한 조회, 접속 비밀값 미기록).
- **역할 및 권한**:
  - `role`: `('preview_dev_runtime', 'preview_dev_runtime', 'postgres', 'public')`
  - `flags`: `{'rolsuper': False, 'rolbypassrls': False, 'rolcreaterole': False, 'rolcreatedb': False}`
  - `public` 테이블(`app_user`, `fixture`, `player`, `team`): 모두 `can_select=True, can_insert=False, can_update=False, can_delete=False`.
  - `preview_dev` 테이블(`preview_runs`, `preview_section_results`, `preview_watch_player_sections`, `preview_injury_player_sections`, `preview_player_name_candidates`, `preview_write_audit`): 모두 `can_select=True, can_insert=True, can_delete=True`.

### 9-2. 합성 실행(`ea7a7bce-3596-4055-b6a9-7b5301a19b9a`) 저장·정본 조회·undo 검증
- **증거 성격 명시**: 본 항목은 제한 DB 역할의 `preview_dev` 쓰기·조회·소유 범위 undo 동작을 검증한 **합성 DB 증거**이며, 실제 AI 번역·모델 호출 증거가 아니다.
- **기존 실실행 사전 상태(`BEFORE_LIVE_RUNS`)**:
  - `86a2408c-5696-4d93-8140-ca9ac26a2af9`: `status='succeeded', cancelled_at=None, sr=1, watch=1, injury=0`
  - `d2764e8d-5aa8-44ca-beb4-97faa91a8929`: `status='succeeded', cancelled_at=None, sr=1, watch=0, injury=1`
- **합성 저장 및 정본 조회(`READ_BACK`)**:
  - 합성 `PreviewRun` `ea7a7bce-3596-4055-b6a9-7b5301a19b9a` (fixture `1557474`, `home=13`, `away=4`), `PreviewModuleExecution` 2건(`R4`, `R2`), `PreviewResult` 2건, `PreviewSectionResult` 2건을 저장했다.
  - `save_watch_player_section`으로 `home1` 확정 선수(`'엘링 홀란드'`, `player_id=533`, `DB_KO`)와 `away1` 미해결 선수(`'합성 미확인 윙어'`, `AI_CANDIDATE`, `cand_watch_id=e3ef20f1-452b-4b9e-90d6-f57f31245de7`, `review_status='pending'`)를 저장했다.
  - `save_injury_player_section`으로 `home1` 확정 선수(`'마크 게히'`, `player_id=549`, `doubtful`, `DB_KO`)와 `away1` 미해결 선수(`'합성 미확인 수비수'`, `confirmed_absence`, `AI_CANDIDATE`, `cand_inj_id=7210a9cb-051e-46ae-b8c7-a270a70664bc`, `review_status='pending'`)를 저장했다.
  - 재조회 결과 `detail_watch_persisted=True`, `detail_inj_persisted=True`와 후보 2건(`pending`) 연결을 확인했다.
- **`undo_report` 및 `cancel_run` 결과**:
  - `undo_report`: `write_scope='preview_dev'`, `undo.state='cancellable'`, `can_cancel=True`, `would_remove={'preview_watch_player_sections': 1, 'preview_injury_player_sections': 1, 'preview_player_name_candidates': 2, 'preview_artifacts': 0, 'preview_source_snapshots': 0, 'preview_attempts': 0, 'preview_results': 2, 'preview_section_results': 2, 'preview_module_executions': 2}`.
  - `cancel_run` (`cancelled_at='2026-11-16T15:26:45.690986+00:00'`): 위 소유 행을 모두 삭제하고 `kept=['preview_runs', 'preview_write_audit']`를 유지했다.
  - undo 이후(`AFTER_UNDO`): `run_status='cancelled'`, `cancelled_at_set=True`, 모든 `remaining_counts=0`, `audit_actions=['run_created', 'section_result_saved', 'section_result_saved', 'player_name_candidate_saved', 'player_section_saved', 'player_name_candidate_saved', 'player_section_saved', 'run_cancelled']`.
- **기존 실실행 보존(`AFTER_LIVE_RUNS`)**:
  - `86a2408c-5696-4d93-8140-ca9ac26a2af9` (`watch=1`, `injury=0`) 및 `d2764e8d-5aa8-44ca-beb4-97faa91a8929` (`watch=0`, `injury=1`) 모두 `status='succeeded'`, `cancelled_at=None`으로 원상 보존됐다.

### 9-3. 최종 통합 워크트리 `5173`/`38000` 지속 기동 및 격리 확인
- **실행 워크트리·코드 SHA**: `/Users/woolee/orca/workspaces/benchmark/player-section-integration` (`lebind12/player-section-integration`), 코드 기준 SHA `d823cdfc2b1de7cf15934cc96870ee6af77d9b2f`.
- **신규 5173/38000 지속 터미널 및 쿠키 분리**:
  - 백엔드 `38000`: Orca 터미널 `term_a61aadfe-bafb-4b90-90c5-fe43a9722574` (`title: C-backend-38000`, 셸 PID `35404`, uvicorn 리슨 PID `36569`), `PREVIEW_CREDENTIALS_FILE="$HOME/.config/match-preview/preview-dev-restricted.env"`, `AUTH_COOKIE_NAME=benchmark_refresh_local`, `CORS_ALLOW_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"`.
  - 프론트엔드 `5173`: Orca 터미널 `term_9796803e-c509-48ca-ac1f-dee1a9dedf1e` (`title: C-frontend-5173`, 셸 PID `35434`, vite 리슨 PID `36646`), `BENCHMARK_BACKEND_URL="http://127.0.0.1:38000"`.
- **기존 서버·세션 보존 확인**:
  - Docker `8000` (PID `3541`), B `5174`/`38001` (PID `87512`/`87452`), C root 사용자 세션 `5175`/`38002` (PID `75968`/`31182`, `term_d8731431-0309-4b85-af6e-50227cb9e2f5`, 쿠키명 `benchmark_refresh_c_prep`) 모두 유지했다.
- **HTTP 검증 결과**:
  - `http://127.0.0.1:38000/health` `200`, `http://127.0.0.1:5173/` `200`, `http://127.0.0.1:5173/api/v1/home/fixtures` `200`.
  - `http://127.0.0.1:5173/api/v1/auth/me` `401`, `http://127.0.0.1:38000/api/v1/admin/preview/runs` `401`.
  - `OPTIONS http://127.0.0.1:38000/api/v1/admin/preview/runs` (`Origin: http://localhost:5173`) `200` (`access-control-allow-origin: http://localhost:5173`, `access-control-allow-credentials: true`).
  - `http://127.0.0.1:38002/health` `200`, `http://127.0.0.1:5175/` `200`.

