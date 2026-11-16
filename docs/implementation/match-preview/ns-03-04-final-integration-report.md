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
