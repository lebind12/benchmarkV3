# PA-IMPL API·저장소 일관성 이행 보고

작성 시각. 2026-11-18 KST  
작업트리. `/Users/woolee/orca/workspaces/benchmark/preview-api-migration` (`lebind12/preview-api-migration`)  
기준 커밋. `0751683ff6fe4eb63249a20b57a6392327bf35e3`  
실행 에이전트·모델. `antigravity / gemini-4-hydrogen-high` (Hydrogen PA-IMPL 사용자 예외 배정, 하위 워커 0회, 제품 Vertex/Gemini 설정 미변경)

## 1. 적용한 `poteto-mode` 원칙과 핵심 결정

- `principle-fix-root-causes` 및 `principle-model-the-domain`. 공개 추천(`/api/v1/home/recommendations`)이 구 `HomePreviewPublication`/`HomePreviewVersion` 테이블을 읽고, 공개 문서(`/api/v1/home/fixtures/{id}/document`)가 `preview_dev`를 읽으며 필수 섹션 누락(`section_players`)을 `complete=True`로 투영하던 근본 불일치를 제거했다. 두 공개 경로 모두 `app/services/home_preview_document.py`의 동일한 선택·완전성 투영을 사용한다.
- `principle-boundary-discipline`. 새 저장소에 대해 허용되지 않은 구 MP-10 엔드포인트(`/runs/{run_id}/resume`, `/module-reruns`, `/synthesis-runs`)를 `app/api/v1/preview_admin.py`에서 먼저 차단하고, 공개 문서 후보 조회(`_read_runs`)에서도 `mp10-*`·모의·카탈로그·단일 모듈 실행을 제외했다. `app/preview/section_preview.py` 등 소유 범위 밖 파일은 수정하지 않았다.
- `principle-prove-it-works`. 없는 시각(`generated_at`, `as_of`)을 지어내지 않는다. `generated_at`은 킥오프 이전 저장본에만 `saved_at`을 쓰고(킥오프 이후는 `None`), `as_of`는 저장시각(`saved_at`)이 아니라 실제로 표시되는 섹션들이 참조한 원천 자료 기준시각(`InformationBundle.as_of` → `collected_at`, `sources`의 `observed_at`/`observedAt`/`retrieved_at`/`collected_at`, `structured.odds[].observedAt`/`observed_at`, `PreviewResult.payload`의 `data_as_of`/`as_of`/`observed_at`/`collected_at`의 `max`)만 사용하며 근거가 없으면 `None`으로 남긴다.

## 2. 변경 내용

| 영역 | 파일 | 변경 요약 |
|---|---|---|
| 공개 문서 선택·완전성·추천 요약 | `app/services/home_preview_document.py` | `project_document`에서 표시된 섹션 기준 필수 섹션(`section_players`, `section_ai_forecast`) 누락 시 `complete=False` 부여(1557474 3섹션 사례 교정). `_is_eligible_document_run` 및 `_read_runs`에서 `mp10-*`, `mock`, `fixture_catalog`, `module` 제외 및 역사 `mp11-bundle-pipeline-*`, `section`, `test-cfg`, 단위 대역 유지. 공유 투영 함수 `recommendation_preview_status`에서 `generated_at`/`saved_at`/`as_of`를 분리하고 `_data_as_of`로 선택된 표시 섹션들의 실제 자료 기준시각만 집계(근거 없으면 `None`). |
| 공개 추천 스키마 | `frontend/src/lib/api/homeRecommendationsSchema.ts` | `homeRecommendationsSchema`에서 `served !== null`일 때 `as_of === null`을 금지하던 `superRefine` 조건을 제거해 자료 기준 미기록(`as_of: null`) 응답을 허용(단 `served: null`일 때의 `as_of: null` 제약 및 JSON 스키마 동등성 유지). |
| 공개 추천 서비스·라우트 | `app/services/home_preview.py`, `app/api/v1/home_preview.py` | `/api/v1/home/recommendations`가 `StoredDb` (`preview_db.get_db`)를 주입받아 `home_preview_document.recommendation_preview_status`로 `preview` 요약(`state`, `served`, `generated_at`, `as_of`)을 계산하고 저장소 장애 시 503 `home_preview_storage_unavailable`을 반환. |
| 구 실행 엔드포인트 가드 | `app/api/v1/preview_admin.py` | `_require_legacy_whole_preview_run`으로 bundle/section 실행의 `/runs/{run_id}/resume`, `/module-reruns`, `/synthesis-runs` 진입을 409로 거부하고 `/bundle-runs`·`/section-runs` 안내. 구 MP-10(`mp10-*`) 호환 경로 유지. |
| 관리자 UI·홈 반영 상태 | `frontend/src/components/management/PreviewPanel.vue`, `frontend/src/components/management/PreviewTestPanel.vue` | `openStoredRun` 실행 전환 시 이전 `runData`·`composition`·홈 반영 상태를 즉시 비우고 늦은 응답을 폐기. 같은 프리뷰 탭에 읽기 전용 `홈 반영 상태`(`GET /api/v1/home/fixtures/{id}/document`, `/api/v1/home/recommendations`)에서 `homeDoc.sections`와 열린 실행/활성 구성본을 `(workflow_id, section_result_id)` 단위로 대조(`일치`·`누락`·`다른 버전`·`추가 반영`·`확인 불가`·`대조 미확인`), `complete`와 열린 결과 일치 여부를 분리 표시하며 `as_of: null`은 `자료 기준 미기록`으로 표시. `PreviewTestPanel` `openDocument`에 `fixtureId`·`kickoffAt` 전달 추가. |
| 홈 부분 문서 안내 | `frontend/src/components/home-preview/HomeRecommendedSection.vue` | `complete=false`인 저장 문서 표시 시 `stored-document-partial` 안내를 함께 노출해 선수 섹션 등 필수 섹션 누락을 완전 표시로 가리지 않음. |
| 단위 테스트 | `tests/unit/test_home_preview_document.py`, `tests/unit/test_preview_api_storage_migration.py`, `frontend/tests/unit/home-preview/publication.spec.ts`, `frontend/src/components/management/PreviewPanel.test.ts`, `frontend/src/components/management/PreviewTestPanel.test.ts`, `frontend/src/components/home-preview/HomeRecommendedSection.test.ts` | 1557474 3섹션 부분 완전성, 추천/문서 일관성, `generated_at`/`as_of` 구분 및 다중 실행 `as_of` 집계·`None` 보존, `homeRecommendationsSchema` `as_of: null` 허용, 503 분리, MP-10 제외·역사 bundle 보존, legacy 409 가드, 실행 전환 비움, `(workflow_id, section_result_id)` 누락/다른 버전/구성본/조회실패 대조 UI 검증 추가. |

## 3. 검증 명령별 실제 결과 (최종 편집 이후)

- `PYTHONPATH=. /Users/woolee/benchmark/.venv/bin/pytest tests/unit/test_home_preview_document.py tests/unit/test_preview_api_storage_migration.py -q`
  - 결과. `24 passed, 1 warning in 0.86s` (종료 코드 0, 합성 대역 및 FastAPI `TestClient` 단위 검증)
- `cd frontend && npx vitest run tests/unit/home-preview/publication.spec.ts src/components/management/PreviewPanel.test.ts`
  - 결과. `PreviewPanel.test.ts` `29 passed` (전부 통과; 기준선 `0751683` 2번 테스트의 기존 미처리 rejection 1건 `TypeError: Cannot read properties of undefined (reading 'ok')` at `src/lib/api/preview.ts:103:22` 잔존). `publication.spec.ts` `12 passed | 2 failed` (`recommendation response` 5건 전체 통과 및 `as_of: null` 검증 통과; 실패 2건은 본 브랜치 `docs/spec/schemas/`에 `home-preview-analysis.schema.json`과 `home-preview-analysis.vertex.schema.json`이 없는 기준선 `ENOENT` 실패).
- `cd frontend && npx vue-tsc -p tsconfig.app.json --noEmit`
  - 결과. 종료 코드 0 (타입 오류 없음)

## 4. 미검증 항목·제외 범위 (PA-IMPL)

- 운영 DB / 실서버(`localhost:8000` 또는 배포) 기동 및 실측 HTTP GET 검증 미실시(지시에 따라 금지).
- 실제 API-Football 수집, Gemini/LLM 모델 호출, DB 스키마 마이그레이션, 섹션 승인 API/행 변경 미실시(후속 PA-LIVE 범위).
- 통합 DB 테스트(`tests/preview/test_player_section_integration.py` 등)는 로컬/운영 DB 미연결 조건에 따라 미실행.
- 사전 설치 상태. 새 워크트리에 gitignored `frontend/node_modules`가 없어 `cd frontend && npm ci --offline`으로 의존성을 설치했고, `npm run build` 산출물은 gitignored `frontend/dist/`에 생성됐다.

## 5. 실서버 전환(PA-LIVE)에 필요한 항목

1. 코드 전환. `lebind12/preview-api-migration` 커밋을 대상 서버 실행 브랜치에 반영하고, 프론트엔드 빌드 정적 자산을 다시 배포한다.
2. 백엔드 재기동. 새 `app/api/v1/home_preview.py`(`/recommendations`의 `StoredDb` 주입 포함)와 `app/api/v1/preview_admin.py` 가드가 반영되도록 API 서버를 재기동한다.
3. DB 권한 확인. API 프로세스의 `preview_db.get_db` 연결이 `preview_dev.preview_runs`, `preview_section_results`, `preview_section_approvals`, `preview_compositions`, `preview_results` 및 3개 canonical 선수 테이블 읽기 권한을 갖는지 확인한다.
4. 무변경 실측 확인(1557474). `GET /api/v1/home/recommendations`에서 1557474의 `preview.state`가 `unavailable`이 아니라 `partial` (`served="current"`, 또는 미승인 시 `unavailable`)로, `GET /api/v1/home/fixtures/1557474/document`에서 `complete=false`로 일치하는지 확인한다.
5. `section_players` 확보 및 승인 여부는 운영자가 관리자 프리뷰 탭에서 수집·생성·승인 절차로 결정한다.
