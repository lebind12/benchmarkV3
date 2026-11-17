# PA-IMPL API·저장소 일관성 이행 보고

작성 시각. 2026-11-18 KST  
작업트리. `/Users/woolee/orca/workspaces/benchmark/preview-api-migration` (`lebind12/preview-api-migration`)  
기준 커밋. `0751683ff6fe4eb63249a20b57a6392327bf35e3`  
실행 에이전트·모델. `antigravity / gemini-4-hydrogen-high` (Hydrogen PA-IMPL 사용자 예외 배정, 하위 워커 0회, 제품 Vertex/Gemini 설정 미변경)

## 1. 적용한 `poteto-mode` 원칙과 핵심 결정

- `principle-fix-root-causes` 및 `principle-model-the-domain`. 공개 추천(`/api/v1/home/recommendations`)이 구 `HomePreviewPublication`/`HomePreviewVersion` 테이블을 읽고, 공개 문서(`/api/v1/home/fixtures/{id}/document`)가 `preview_dev`를 읽으며 필수 섹션 누락(`section_players`)을 `complete=True`로 투영하던 근본 불일치를 제거했다. 두 공개 경로 모두 `app/services/home_preview_document.py`의 동일한 선택·완전성 투영을 사용한다.
- `principle-boundary-discipline`. 새 저장소에 대해 허용되지 않은 구 MP-10 엔드포인트(`/runs/{run_id}/resume`, `/module-reruns`, `/synthesis-runs`)를 `app/api/v1/preview_admin.py`에서 먼저 차단하고, 공개 문서 후보 조회(`_read_runs`)에서도 `mp10-*`·모의·카탈로그·단일 모듈 실행을 제외했다. `app/preview/section_preview.py` 등 소유 범위 밖 파일은 수정하지 않았다.
- `principle-prove-it-works`. 없는 시각(`generated_at`)을 지어내지 않고, 킥오프 이후 저장본은 `generated_at=None`, `as_of=saved_at`으로 유지하며 `home_preview.structure("recommendations", ...)` 스키마 검증을 통과하게 했다.

## 2. 변경 내용

| 영역 | 파일 | 변경 요약 |
|---|---|---|
| 공개 문서 선택·완전성·추천 요약 | `app/services/home_preview_document.py` | `project_document`에서 표시된 섹션 기준 필수 섹션(`section_players`, `section_ai_forecast`) 누락 시 `complete=False` 부여(1557474 3섹션 사례 교정). `_is_eligible_document_run` 및 `_read_runs`에서 `mp10-*`, `mock`, `fixture_catalog`, `module` 제외 및 역사 `mp11-bundle-pipeline-*`, `section`, `test-cfg`, 단위 대역 유지. 공유 투영 함수 `recommendation_preview_status` 추가. |
| 공개 추천 서비스·라우트 | `app/services/home_preview.py`, `app/api/v1/home_preview.py` | `/api/v1/home/recommendations`가 `StoredDb` (`preview_db.get_db`)를 주입받아 `home_preview_document.recommendation_preview_status`로 `preview` 요약(`state`, `served`, `generated_at`, `as_of`)을 계산하고 저장소 장애 시 503 `home_preview_storage_unavailable`을 반환. |
| 구 실행 엔드포인트 가드 | `app/api/v1/preview_admin.py` | `_require_legacy_whole_preview_run`으로 bundle/section 실행의 `/runs/{run_id}/resume`, `/module-reruns`, `/synthesis-runs` 진입을 409로 거부하고 `/bundle-runs`·`/section-runs` 안내. 구 MP-10(`mp10-*`) 호환 경로 유지. |
| 관리자 UI·홈 반영 상태 | `frontend/src/components/management/PreviewPanel.vue`, `frontend/src/components/management/PreviewTestPanel.vue` | `openStoredRun` 실행 전환 시 이전 `runData`와 홈 반영 상태를 즉시 비우고 늦은 응답을 폐기. 같은 프리뷰 탭에 읽기 전용 `홈 반영 상태`(`GET /api/v1/home/fixtures/{id}/document`, `/api/v1/home/recommendations`)와 홈 이동 링크, 선수 DB 연결/사진 `NULL` 무오류 안내 추가. `PreviewTestPanel` `openDocument`에 `fixtureId`·`kickoffAt` 전달 추가. |
| 홈 부분 문서 안내 | `frontend/src/components/home-preview/HomeRecommendedSection.vue` | `complete=false`인 저장 문서 표시 시 `stored-document-partial` 안내를 함께 노출해 선수 섹션 등 필수 섹션 누락을 완전 표시로 가리지 않음. |
| 단위 테스트 | `tests/unit/test_home_preview_document.py`, `tests/unit/test_preview_api_storage_migration.py`, `frontend/src/components/management/PreviewPanel.test.ts`, `frontend/src/components/management/PreviewTestPanel.test.ts`, `frontend/src/components/home-preview/HomeRecommendedSection.test.ts` | 1557474 3섹션 부분 완전성, 추천/문서 일관성, 킥오프 이후 `generated_at=None`, 503 분리, MP-10 제외·역사 bundle 보존, legacy 409 가드, 실행 전환 비움, 홈 반영 상태·부분 표시 UI 검증 추가. |

## 3. 검증 명령별 실제 결과 (최종 편집 이후)

- `PYTHONPATH=. /Users/woolee/benchmark/.venv/bin/pytest tests/unit/test_home_preview_document.py tests/unit/test_preview_api_storage_migration.py -q`
  - 결과. `23 passed, 1 warning in 0.92s` (종료 코드 0, 합성 대역 및 FastAPI `TestClient` 단위 검증)
- `cd frontend && npx vitest run src/components/management/PreviewTestPanel.test.ts src/components/management/PreviewPanel.test.ts src/components/home-preview/HomeRecommendedSection.test.ts`
  - 결과. 3개 파일 56개 테스트 전체 통과 (`HomeRecommendedSection.test.ts` 6 passed, `PreviewPanel.test.ts` 27 passed, `PreviewTestPanel.test.ts` 23 passed). 다만 기준선(`0751683`)부터 존재하던 `PreviewPanel.test.ts` 1번 테스트(`확인한 그 경기 하나만 생성하고, 더블클릭해도 POST는 한 번이다`)의 미처리 rejection 1건(`TypeError: Cannot read properties of undefined (reading 'ok')` at `src/lib/api/preview.ts:103:22`) 때문에 Vitest 프로세스 종료 코드는 1이다. 이번 변경으로 늘어난 오류는 0건이다.
- `cd frontend && npx vue-tsc -p tsconfig.app.json --noEmit && npm run build`
  - 결과. 종료 코드 0 (`✓ built in 5.13s`)

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
