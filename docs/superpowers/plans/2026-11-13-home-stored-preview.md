# 홈 최신 저장 프리뷰 Implementation Plan

> **For agentic workers:** 프로젝트 AGENTS.md의 DeepSeek 구현·별도 DeepSeek 독립 검토·검증 범위 정책이 스킬 기본 실행법보다 우선한다. 작업 전 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 읽고 적용한다. Plans.md는 GPT 조정자만 수정한다.

**Goal:** 홈 추천 경기 선택에 따라 최신 저장 문서를 표시하고, 문서가 없으면 기존 6시간 안내를 표시한다.

**Architecture:** 기존 공개 prematch 조회를 새 preview_dev 저장 결과와 연결한다. 선택한 문서의 본문·구조화 결과를 일치시켜 기존 MatchPreviewBody로 표시한다. 별도 생성 엔진·공개용 관리자 인증 해제·수동 게시 기능은 만들지 않는다.

**Tech Stack:** FastAPI, SQLAlchemy, 기존 PostgreSQL preview_dev, Vue 3, TypeScript, Zod, pytest, Vitest.

**Spec:** `docs/superpowers/specs/2026-11-13-home-stored-preview-design.md` (사용자 승인).

**사용자 추가 확인 기준:** [첫 진입·스크롤·없음/6시간 미생성·실경기·디자인](2026-11-13-home-stored-preview-acceptance.md). 2026-11-13 00:28 KST 지시를 현재 구현과 실제 확인 범위에 반영한다.

## Global Constraints

- GPT는 계획·조사·수용만, 제품/테스트/스크립트 구현과 독립 검토는 실제 DeepSeek만 수행한다.
- 공통 작업트리의 기존 변경을 보존한다. 광범위 되돌리기·커밋·포맷 변경 금지. 제품 커밋은 조정자가 변경 범위 확인 후 별도로 처리한다.
- GET은 저장 조회 전용. 새 모델/검색/스크래핑/배당조회/생성/승인 POST/운영배포 금지.
- 기존 경기·계정은 읽기 전용, DB 쓰기·마이그레이션 없이 우선 구현. 필요 시 실행하지 말고 이유와 최소 범위를 보고한다.
- 공개 가능 여부는 기존 워크플로우 승인 정책을 보존한다. 승인 없는 실제 저장본을 승인됐다고 간주하지 않는다. 승인 부재가 실제 홈 확인을 막으면 그 사실을 보고한다.
- 새 품질 점수·최소 글 길이·완전성 문턱을 추가하지 않는다. 문서 없음과 읽기 실패를 구분한다.

## Review Focus

현재 요구의 다섯 경계만 확인한다: 외부 경기 ID와 선택 문서 일치, 문서 저장시각 기준 최신 선택/본문 없는 실행 건너뛰기, 구성본의 타 실행 선택 섹션까지 동일 본문·점수·사진 유지, 공개 승인/모의 결과 제외, 홈 GET 무호출·무쓰기 및 오류/없음 구분. 이 항목의 대표 검사는 HP-IMPL이 맡고 독립 검토는 유효한 실행 근거를 재사용한다.

## HP-IMPL — 저장 조회부터 홈 렌더까지 한 연결 단위

담당: DeepSeek 구현 워커 1명. 선행: 승인 설계. 읽기/편집 소유권:

- `app/services/home_preview.py`, 필요시 새 `app/services/home_preview_document.py`: 경기별 최신 공개 가능 문서 선택·독자 투영. 추천 정책은 유지하되 추천의 프리뷰 상태와 실제 조회를 일치시킨다.
- `app/api/v1/home_preview.py`: 기존 `/api/v1/home/fixtures/{external_id}/prematch`의 공개 저장 조회 연결. 관리자 API는 읽기 참고만 한다.
- `frontend/src/components/home-preview/HomeRecommendedSection.vue`, `frontend/src/lib/api/homePreview.ts`, `homePreviewResponse.ts`, 필요시 새 `homePreviewDocument.ts`: 응답 검증·본문 표시·기존 안내 분기. `MatchPreviewBody.vue`, body.css와 관리자 기능은 수정하지 않는다.
- `frontend/src/styles/home-preview.css`: 사용자 추가 요구의 기존 흐림→선명 효과를 홈에서 연결하는 데 필요한 변경만 허용. 공통 본문 디자인/관리자 스타일을 변경하지 않는다.
- 기존 `previewView.ts`/`sectionStructured.ts`는 우선 재사용한다. 입력형을 공용 부분으로 좁히는 것이 꼭 필요하면 조정자에게 구체적 파일/최소 변경을 보고한 뒤 소유권을 확인받는다.
- 새 직접 검사 `tests/unit/test_home_preview_document.py`, `frontend/tests/unit/home-preview/storedDocument.spec.ts` 및 직접 영향받는 기존 `publication.spec.ts`, `recommendations.spec.ts`. 무관한 검사 확대 금지.
- 결과 보고서 `docs/implementation/match-preview/home-stored-preview-report.md`만 문서 편집 가능. Plans.md/공통 설계는 편집하지 않는다.

입력: 외부 경기 ID, 저장 실행·구성본·섹션 결과·승인 기록. 출력: 같은 경기의 최신 표시 가능 문서 또는 명시적 없음, 저장시각, 본문과 정확히 대응하는 구조화 값. 공개 응답은 본문 표시에 필요한 화이트리스트만 포함한다. 프론트가 관리자 GET들을 직접 호출해서 구성하지 않는다. 실행 진단·프롬프트·원문·비밀값을 공개 계약에 넣지 않는다.

- [ ] 현행 저장 계약을 읽고 공개 응답의 필드/버전 및 최신 선택시각을 보고서에 확정한다. 하나의 워커가 생산자와 소비자를 함께 변경하여 계약 불일치를 피한다.
- [ ] 현재 수용 기준에 직접 연결된 대표 실패 검사를 작성·실행하고, 각 새 검사 이유와 사용자 영향을 한 문장으로 남긴다. 합성 입력의 단위 검사는 실제 DB에 연결하지 않는다.
- [ ] 최신 저장 문서 선택과 공개 투영을 구현한다. 구성본 선택을 보존하고, 새 본문 없는 실행은 이전 문서를 가리지 않으며, 6시간 밖 저장본도 표시한다.
- [ ] 기존 본문 컴포넌트를 연결하고 첫 진입 자동 조회·경기 전환/조회중/없음/오류를 분리한다. 없음은 메시지 한 개만, 킥오프 전 6시간 이내 미생성은 문제 안내로 구분한다. 기존 스크롤 섹션별 흐림→선명을 홈 범위에서 유지한다. 추천 UI·공통 본문 스타일을 유지한다.
- [ ] backend 직접 검사: `.venv/bin/python -m pytest tests/unit/test_home_preview_document.py -q`. frontend 직접 검사: `npm run test:unit -- tests/unit/home-preview/storedDocument.spec.ts tests/unit/home-preview/publication.spec.ts tests/unit/home-preview/recommendations.spec.ts src/components/home-preview/MatchPreviewBody.test.ts` (cwd frontend). 환경의 실제 실행기가 다르면 동등한 기존 명령과 이유를 보고한다.
- [ ] `npx vue-tsc -b --pretty false` (cwd frontend)로 실제 프로젝트 타입 검사를 한 번 실행하고 기존 오류와 새 오류를 구분한다. 전체 빌드/전체 회귀/추가 브라우저는 요구하지 않는다.
- [ ] 완료 보고에 변경 파일·검사 명령/결과·선택 계약·읽기 정책·미해결·적용 원칙을 남기고 `EDITING STOPPED`와 편집/백그라운드 작업 종료를 명시한다. 이후 worker_done으로 인계한다.

## HP-REVIEW — 별도 DeepSeek 읽기 전용 검토

선행: HP-IMPL 인계·편집 종료. 소유권은 `docs/implementation/match-preview/home-stored-preview-review.md` 보고서만이다.

- [ ] 실제 변경과 위 다섯 경계·직접 검사 근거를 한 번 검토한다. 요구사항 위반·재현 결함·참고 개선을 구분한다.
- [ ] 수정이 필요하면 구현 워커에게 전달한다. 수정 확인은 지적 항목과 직접 영향 경로만 확인한다. 근거가 유효하면 같은 검사를 반복하지 않는다.

## HP-HOME — 조정자 실제 홈 확인 및 수용

선행: 구현 인계. 독립 검토와 병렬 가능하다.

- [ ] 현재 로컬 서버에 변경을 반영하고 공개 GET으로 실제 저장본/없음 응답을 확인한다. 서버 재기동은 편집 인계 후 정상 종료로 수행한다.
- [ ] 연결된 사용자 관점 확인 기준의 실제 홈 시나리오를 수행한다. 첫 진입, 맨체스터 저장본, 과거·미래 문서 없음, 경기 전환, 섹션별 흐림→선명, 8:2/정사각 점수/중앙/테마/좁은 폭을 확인한다. 6시간 경계 실사례가 없으면 합성 직접 검사와 실데이터 근거를 구분한다.
- [ ] 실제 승인 기록 부족으로 문서가 없으면 이를 차단 원인으로 기록하며 승인 우회·가짜 실데이터 증거를 만들지 않는다.
- [ ] 구현/검토/실제 화면의 근거를 Plans.md에 모아 수용한다. 통과 후 범위를 넓히지 않고 종료한다.

의존성: HP-IMPL → (HP-REVIEW ∥ HP-HOME) → 수용. 재확인 요청 없이 승인된 범위를 실행한다.
