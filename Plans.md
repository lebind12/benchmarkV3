# benchmark Plans.md

축구 정보 사이트 + 방송용 페이지. AGENTS.md 가 도메인 SSOT, 이 파일은 작업 정본.

작성일: 2026-05-13

---

## Phase 0: 인프라

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| 0.1 | Supabase 프로젝트 (benchmark-v3 linked) | DATABASE_URL .env 채움. GH Secrets 미등록 | - | cc:WIP |
| 0.2 | Koyeb 프로젝트 (benchmark-v3 app 생성) | KOYEB_TOKEN GH Secrets 미등록 | - | cc:WIP |
| 0.3 | Upstash Redis (benchmark-v3-cache) | REST URL/TOKEN .env 미입력 | - | cc:WIP |
| 0.4 | FastAPI 골격 (uvicorn 부팅 가능) | `uvicorn app.main:app` 실행 시 `/health` 200 | - | cc:완료 [92b0af8] |
| 0.5 | alembic 셋업 + 첫 마이그레이션 | `alembic upgrade head` 적용 (13 테이블 prod 적용 완료) | 0.4 | cc:완료 [92b0af8] |
| 0.6 | pytest 셋업 (unit / integration marker 분리) | `pytest -m unit` 동작 + 격리 schema conftest | 0.4 | cc:완료 [a57a188] |
| 0.7 | pydantic-settings + Settings 클래스 | env 로드 동작 | 0.4 | cc:완료 [92b0af8] |
| 0.8 | docker-compose (선택, 로컬 dev DB) | MVP 미포함 결정 (remote Supabase test schema 사용) | - | blocked (MVP 외) |

## Phase 1: DB 스키마

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| 1.1 | `league` 테이블 + venue + team + player + fixture + fixture_detail + standings + team_season + *_translation + app_user (13 테이블, 단일 마이그레이션) | 단위 74/74 + 통합 28/28 통과. prod 적용 완료 | 0.5 | cc:완료 [92b0af8] |
| 1.2~1.7 | (1.1 단일 마이그레이션에 포함) | - | 1.1 | cc:완료 [92b0af8] |
| 1.8 | Supabase RLS 정책 결정 및 적용 | RLS on/off 결정 문서화. 적용 시 정책 SQL | 1.1 | cc:TODO |
| 1.9 | `league.is_active` 컬럼 follow-up (동적 league 관리) | 별도 마이그레이션 0002 + 모델 갱신 + 테스트 | 1.1 | cc:완료 [9e7d157] |
| 1.10 | `transfer` / `injury` / `news_article` 3 테이블 추가 (마이그레이션 0003) | 모델 + 마이그레이션 + 테스트 | 1.1 | cc:완료 [7115dad] |
| 1.11 | `h2h_fixture` 테이블 추가 (마이그레이션 0004) | 모델 + 마이그레이션 + 테스트 | 1.1 | cc:완료 [7115dad] |

## Phase 2: 시드 데이터

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| 2.1 | 리그 5개 한글표기 결정 (이 세션, 수동) | `seeds/league_translation*.csv` 생성 + DB import 검증 | - | cc:WIP [local-seeds] |
| 2.2 | 팀 한글표기 결정 (이 세션, EPL 20 + UCL/UEL/카라바오/FA컵 본선 클럽) | `seeds/team_translation_*.csv` 생성 + DB import 검증 | 2.1 | cc:WIP [local-seeds] |
| 2.3 | `_Player__202605131748.csv` → `player_translation` import 스크립트 | import script + import 결과 row count 검증 | 1.6 | cc:WIP [local-seeds] |
| 2.4 | league/team seed import 스크립트 | import script + dry-run/row count 검증 | 1.6, 2.1, 2.2 | cc:WIP [local-seeds] |
| 2.5 | 시드 결과 무결성 점검 (중복/결측/외부 ID 유효성) | 점검 스크립트 통과 | 2.3, 2.4 | cc:TODO |

## Phase 3: 인증

기획 정본: `docs/spec/auth-access-plan.md` (2026-06-06 작성). 구현 상태는 아래 task 기준으로 관리한다.

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| 3.1 | 비밀번호 해시 헬퍼 | 단위 테스트 통과 | 1.7 | cc:완료 [local-signup-mvp] |
| 3.2 | JWT 발급 / 검증 (access 짧은 만료) | 단위 테스트 (만료, 변조, role) | 1.7 | cc:TODO |
| 3.3 | Refresh token rotation (Upstash 저장, blacklist) | 단위 + 통합 테스트 | 3.2, 0.3 | cc:TODO |
| 3.4 | Role 검사 FastAPI Dependency (USER/STREAMER/ADMIN) | 권한 검사 단위 테스트 | 3.2 | cc:TODO |
| 3.5 | `/auth/signup`, `/auth/login`, `/auth/refresh`, `/auth/logout` | 통합 테스트 (정상/오류 케이스). signup/login MVP 완료, JWT/refresh/logout 후속 | 3.1-3.4 | cc:WIP [local-auth-mvp] |

## Phase 4: 워커 - daily-sync

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| 4.1 | API-Football 클라이언트 (httpx + semaphore 6 + exp backoff retry) | 단위 테스트 (mock 응답) | 0.7 | cc:WIP [local-unit] |
| 4.2 | Upstash 분산 락 (SET NX + TTL) | 단일 인스턴스 MVP 정책 재확인 후 필요 시 구현 | 0.3 | blocked (MVP 외 후보) |
| 4.3 | 리그 메타 upsert (5 리그) | 통합 테스트 (test schema) | 1.1, 4.1 | cc:WIP [local-unit] |
| 4.4 | fixture 적재 (5 리그, 최신 2시즌) | 통합 테스트 | 1.4, 4.1 | cc:WIP [local-unit] |
| 4.5 | fixture 상세 적재 | 통합 테스트 | 1.5, 4.4 | cc:WIP [local-unit] |
| 4.6 | team / player 메타 upsert | 통합 테스트 | 1.2, 1.3, 4.4 | cc:WIP [local-unit] |
| 4.7 | 컵 대회 빈 슬롯 채움 로직 (라운드 추첨 후) | 통합 테스트 | 4.4 | cc:WIP [local-unit] |
| 4.8 | cron 스케줄러 (KST 00/06/12/18) | 스케줄 검증 단위 테스트 + 실행 진입점 | 4.3-4.7 | cc:WIP [local-unit] |

## Phase 5: 워커 - translation-filler

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| 5.1 | name_ko IS NULL 감지 + few-shot 프롬프트 + 1분 폴링 (단일 구현) | 단위 14/14 + 통합 7/7 PASS | 1.1, 2.3 | cc:완료 [256501c] |

## Phase 5.5: 워커 - news-fetcher

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| 5.5.1 | RSS 파싱 | 단위 테스트 | 1.10 | cc:WIP [local-unit] |
| 5.5.2 | EPL 키워드 매칭 (DB 의 team.name + code) | 단위 테스트 | 1.10, 5.5.1 | cc:WIP [local-unit] |
| 5.5.3 | 1시간 폴링 + INSERT ON CONFLICT DO NOTHING + tags JSONB | 통합 테스트 (mock RSS) | 5.5.2 | cc:WIP [local-unit] |

## Phase 5.6: 워커 - news-translator

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| 5.6.1 | title_ko/summary_ko IS NULL 큐 조회 | 단위 테스트 | 1.10 | cc:WIP [local-unit] |
| 5.6.2 | gpt-3.5-turbo 의역 클라이언트 (temp 0.3, JSON 강제) | 단위 테스트 | 5.6.1 | cc:WIP [local-unit] |
| 5.6.3 | 1분 폴링 + 배치 50 + semaphore 5 | 통합 테스트 (mock OpenAI) | 5.6.2 | cc:WIP [local-unit] |

## Phase 6: (제거) live-poll 워커는 워커가 아니라 API endpoint 로 처리

방송용 페이지 라이브 데이터는 워커가 아니라 스트리머 호출 시점에 동작하는 API endpoint + Upstash 캐시 패턴으로 처리한다. Phase 8 의 일반 endpoint 로 흡수됨.

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| (구) 6.x | live-poll 워커 | (삭제됨 — Phase 8 의 라이브 endpoint task 로 이관) | - | deleted |

## Phase 7: 자동화 인프라 (에이전트 워크플로)

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| 7.1 | `docs/spec/agent-workflow.md` 작성 (상태 머신 + 게이트) | 본 세션에서 생성 | - | cc:완료 [df6672e] |
| 7.2 | `.codex/agents/be-{test,dev,reviewer}.toml` 3개 에이전트 명세 | 본 세션에서 생성 + 팀 스폰 동작 확인 | 7.1 | cc:완료 [df6672e] |
| 7.3 | `.codex/schemas/endpoint-flow.schema.json` (상태 파일 JSON Schema) | schema validation 통과 | 7.1 | cc:완료 [local] |
| 7.4 | `scripts/endpoint-flow.sh` (상태 전환 CLI) | 단위 테스트 통과 | 7.3 | cc:완료 [local] |
| 7.5 | GH Actions: `.github/workflows/be-ep-pr.yml` (be-ep-* PR 검증) | CI 잡 성공 | 7.4 | cc:TODO |
| 7.6 | GH Actions: `.github/workflows/backend-pr.yml` (backend ← be-ep-* PR) | CI 잡 성공 | 7.5 | cc:TODO |
| 7.7 | GH Actions: `.github/workflows/main-deploy.yml` (main push → 마이그레이션 → Koyeb) | dry-run 성공 | 7.6 | cc:TODO |
| 7.8 | 테스트 schema 자동 생성/삭제 fixture (`tests/conftest.py`) | 통합 테스트가 격리 스키마에서 실행됨 (28/28 통과 검증) | 0.6 | cc:완료 [a57a188] |
| 7.9 | reviewer agent invocation 자동화 (PR comment 또는 CI 잡) | PR 에 reviewer verdict 자동 게시 | 7.2, 7.5 | cc:TODO |

## Phase 8: API endpoint 구현 (프론트엔드 follow)

FE 가 작성한 endpoint 목록 단위로 라이프사이클 자동화 적용.

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| 8.1 | FE endpoint 목록 수신 인터페이스 (mock + endpoint spec 파일 위치 약속) | 디렉토리 구조 + 양식 문서 | 7.1 | cc:완료 [local-p0-status] |
| 8.2 | endpoint 별 라이프사이클 1건 (시범) | 1 endpoint 가 `MERGED` 까지 완주 | 7.1-7.9, 8.1 | cc:완료 [local-broadcast-overlay-endpoint] |
| 8.3 | 이후 endpoint 들은 8.2 시범을 패턴 삼아 진행 | FE 진행에 따라 채워짐 | 8.2 | cc:WIP |

## Phase 9: 프론트엔드 인프라

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| 9.1 | Vue 3 + Vite MPA 골격 (다중 entry: main, broadcast) | `npm run dev` 가 두 entry 부팅. broadcast 는 #00B140 배경 | - | cc:완료 [533766f] |
| 9.2 | Tailwind + shadcn-vue 셋업 | shadcn-vue CLI 동작 + Button 컴포넌트 추가 | 9.1 | cc:완료 [06716c3] L125 |
| 9.3 | Pinia + Vue Router (페이지별 인스턴스) | entry 별 store 작동 | 9.1 | cc:TODO |
| 9.4 | MSW 셋업 (`VITE_USE_MOCK` 토글) | 토글로 mock/실 API 분기 | 9.1 | cc:TODO |
| 9.5 | openapi-typescript + `npm run gen:api` | BE OpenAPI → TS 타입 생성 | 9.1 | cc:TODO |
| 9.6 | zod 런타임 검증 헬퍼 (응답 schema 검증) | 단위 테스트 통과 | 9.5 | cc:TODO |
| 9.7 | Playwright 셋업 (L1/L2/L3 분리 실행 가능) | `npm run test:e2e` / `test:e2e:integration` 동작 | 9.1, 9.4 | cc:TODO |
| 9.8 | Vercel 배포 셋업 (vercel.json + env) | 첫 push 로 preview URL 생성 | 9.1 | cc:TODO |
| 9.9 | 방송용 페이지 entry + 크로마키 (`#00B140`) 레이아웃 | 방송용 라우트가 녹색 배경으로 렌더 | 9.1, 9.3 | cc:완료 [local-broadcast-match-overlay-mock-r2] |
| 9.10 | 인증 흐름 (JWT 저장 / refresh / role 가드) — BE Phase 3 완료 후 통합 | signup/login UI + USER mock auth 저장 완료. 로그아웃/JWT 저장 후속 | 3.5, 9.3 | cc:WIP [local-auth-mvp] |
| 9.11 | i18n 미도입 결정 명시 + 한글 폰트 토큰화 | 결정 문서 + Tailwind theme 한글 폰트 | 9.2 | cc:TODO |

## Phase 10: FE 자동화 (에이전트 워크플로 — FE 측)

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| 10.1 | `docs/features/README.md` (요구사항 템플릿) | 본 세션에서 생성 | - | cc:완료 [df6672e] |
| 10.2 | `docs/spec/fe-workflow.md` (상태 머신 + 게이트) | 본 세션에서 생성 | - | cc:완료 [df6672e] |
| 10.3 | `.codex/agents/fe-{planner,dev,reviewer}.toml` 3개 명세 | 본 세션에서 생성 + 팀 스폰 동작 확인 | 10.2 | cc:완료 [df6672e] |
| 10.4 | `.codex/schemas/feature-flow.schema.json` (FE state JSON Schema) | schema validation 통과 | 10.2 | cc:완료 [local] |
| 10.5 | `scripts/feature-flow.sh` (상태 전환 CLI) | 단위 테스트 통과 | 10.4 | cc:완료 [local] |
| 10.6 | `frontend/endpoint-requests/` 양식 + 자동 추출 스크립트 (mock JSON + planner spec → request.json) | 시범 feature 에서 자동 추출 성공 | 10.5, 7.4 | cc:TODO |
| 10.7 | GH Actions: `.github/workflows/fe-feat-pr.yml` (lint/type/vitest/Playwright L2/번들) | CI 잡 성공 | 9.1, 9.7 | cc:TODO |
| 10.8 | GH Actions: `.github/workflows/fe-integration-pr.yml` (L1+L2+L3 on Vercel preview, prod BE) | CI 잡 성공 | 10.7, 9.8 | cc:TODO |
| 10.9 | GH Actions: `.github/workflows/fe-prod-smoke.yml` (Vercel prod 배포 후 L4 1회) | smoke 잡 성공 | 9.8 | cc:TODO |
| 10.10 | Vercel PR preview 연동 확인 (PR 마다 URL 자동 게시) | 동작 확인 | 9.8 | cc:TODO |

## Phase 11: FE 기능 구현 (page-led)

페이지 또는 작은 기능 그룹 단위로 진행. 메인이 `docs/features/<id>.md` 작성 후 FE 팀 트리거.

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| 11.1 | 기능/페이지 카탈로그 확정 (메인에서 수동 작성) | `docs/features/_catalog.md` 또는 README 의 인덱스 | 10.1 | cc:TODO |
| 11.2 | URL 규칙 / 사이트맵 설계 (`docs/spec/url-convention.md`) | 규칙 문서 + 페이지별 URL 매핑 | 11.1 | cc:TODO |
| 11.3 | 시범 feature 1건 — Mock 라이프사이클 완주 | FE Mock 머지 + endpoint-request 자동 생성 | 9.1-9.11, 10.1-10.10, 11.2 | cc:TODO |
| 11.4 | 시범 feature 1건 — Integration 라이프사이클 완주 (BE 의존 endpoint MERGED 후) | L3 통과, Integration 머지 | 11.3, 8.2 | cc:TODO |
| 11.5 | 이후 feature 들은 11.3-11.4 패턴 반복 | 카탈로그 진척률 100% | 11.4 | cc:TODO |
| 11.6 | 방송용 중계화면 포함 페이지 디자인 (`broadcast-match-program`) | 요구사항/spec/devplan 작성 후 사용자 레이아웃 방향 확정 | 9.9, broadcast-match-overlay mock | cc:WIP |

---

## Notes

- 본 Plans.md 는 백엔드 자동화 + 시드 + 인프라 중심. 프론트엔드 개발 방법론은 별도 기획 후 추가
- DoD 의 `[tdd:skip:<reason>]` 태그 는 Harness 규약 (현재 사용 안 함)
- Status 마커: `cc:TODO`, `cc:WIP`, `cc:완료 [hash]`, `blocked`
- 본 파일은 v2 포맷 (Task / 내용 / DoD / Depends / Status)

## 방송 화면 개선 (2026-09-10)

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| UCL-UI-1 | 챔피언스리그 포메이션 양옆 장식선 제거, 선수 UI/헤더 1.3배 확대, EPL 스탯 UI·기능 공유, 스탯 글씨 1.3배(항목·탭·리그명 1.6배), 팀 로고 1.5배, 스탯 리그명 좌우 팀 영문 약칭 표시, 오른쪽 팀 타이머 토글 | UCL 색상 유지, 단위 테스트 45개 통과 및 빌드 확인. 최종 화면은 사용자 직접 확인(Playwright 중단 요청) | - | cc:완료 [local-ucl-broadcast-ui] |
| BCAST-UI-2 | 유로파 포메이션 양옆 리본 제거, 6개 리그의 스탯 UI·기능·영문 약칭 공통화, 포메이션/스탯 글씨·선수·스탯 로고 크기를 현재 UCL 기준으로 통일 | 리그 색상 유지, 공통 스탯/방송 단위 테스트 69개 및 빌드 통과. Playwright 미실행, 화면은 사용자 확인 | UCL-UI-1 | cc:완료 [local-all-league-broadcast-ui] |
| BCAST-UI-3 | 모든 리그 하단 이벤트 팝업의 글씨 1.3배 확대(득점·교체·경고·VAR·스탯) | 공통 글씨 배율 적용 및 빌드 통과. Playwright 미실행 | BCAST-UI-2 | cc:완료 [local-event-popup-type-scale] |
| PLAYER-KO-20260910 | 미번역 선수 869명의 한국어 이름·짧은 이름과 출처를 `seeds/player_translation_pending_20260910.csv`에 기록하고 DB 반영 | NULL 행 868건 갱신, 누락 행 1건 생성. 두 번역 컬럼의 잔여 NULL 0건, 기존 비NULL 필드 21,764개 보존 확인 | - | cc:완료 [player-translation-pending-20260910] |

## 메인 추천·프리뷰 목업 — 2026-10-25

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| HOME-PREVIEW-0 | 추천 순서·진행 중·날짜 이동 결정 | plan.md §5.2.1과 결정 기록에 사용자 확정 반영 | - | cc:완료 [local-decision] |
| HOME-PREVIEW-1 | 메인 FE 평가용 목업 | 개발 전용 /home/mock, 진행 중 우선/예정 정렬·전환·로고 등장·인라인 프리뷰·누락/실패/이전본·다음 날짜·오늘 결과·모바일/다크/감소 모션 검증, BE/운영 호출 없음 | HOME-PREVIEW-0 | cc:완료 [local-mock; unit 5/E2E 10/build PASS; 사용자 평가 대기] |
| HOME-PREVIEW-EVAL | 사용자 목업 평가 | 디자인·흐름 피드백 후 실제 홈 전환·endpoint-request 범위 확정 | HOME-PREVIEW-1 | cc:TODO |

## 메인 프리뷰 구조화 JSON — 2026-10-25

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| HOME-JSON-1 | DB/웹/AI 책임·JSON 계약 및 FE 목업 | 사실/외부/분석 분리, 샘플 JSON·AI response schema·Vertex 요청 예제·FE strict validation·본문 JSON 렌더링·누락/편집·잘못된 응답 차단·endpoint-request·검증 기록 | HOME-PREVIEW-1 | cc:완료 [JSON 목업; unit 12/E2E 11/build PASS; BE 미구현] |
| HOME-JSON-2 | 근거 수집·JSON 생성·DB 저장/조회 BE 명세/구현 | 상위 묶음. 실제 실행/완료 판정은 PRE-01~09·11~12로 세분화. 기존 Markdown 호환, source/사실/시점 검증·Supabase/ORM·격리 검증 | HOME-JSON-1 | cc:WIP [로컬 BE 구현·검증; PRE-12 인수/리뷰 대기] |
| HOME-JSON-3 | 저장 JSON 실 연동 검증 | 상위 묶음. 실제 실행/완료 판정은 PRE-10·12. 현재 / 라우트·DB 저장본·동일 fixture·누락/이전본·출처 검증 | HOME-JSON-2 | cc:WIP [실 / 연동·격리 L3 통과; PRE-12 대기] |

## 메인 구조화 JSON 프리뷰 구현 계획 — PRE 실행 정본 (2026-10-25)

사용자가 요청한 것은 구현 계획 수립이다. 상세 설계·추천 정책·한계·회귀 기준은 `plan.md` §14와 §5.2.1을 따른다. 표의 `완료`는 해당 산출물만 의미하며, 문서/FE 목업 완료를 BE·실 연동·운영 완료로 확대하지 않는다. 아래 최신 실행 결과가 과거 미착수 기록보다 우선한다.

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| PRE-00 | 현재 코드 대조·구현 계획 수립 | 기존 JSON/DB/생성/인증/스케줄러·migration 현황 대조, plan.md §14 및 본 표 작성, 미정 계약/실응답/운영 경계 명시. 문서 자체 점검 | HOME-JSON-1 | cc:완료 [계획 문서만; 구현 미착수] |
| PRE-01 | FE 부족 상태·조회/추천 계약 보완 | 생성 전/실패/이전 유효본 envelope·null 생성 시각/공개 reason·컵 폼 기준, 동적 추천 목록/정렬/날짜·상태 시각 요구를 mock/Zod/JSON/endpoint-request로 작성·검증. 기존 디자인 유지 | PRE-00 | cc:완료 [FE 계약/목업; unit 23/E2E 13/build PASS; BE 미구현] |
| PRE-02 | DB coverage·웹/배당 소스·provider 검증 | 읽기 전용 coverage, 공식/매체/외부 전망 소스 매칭·사용 범위·시각, 부상/배당 MCP 실응답 확인 경로/누락 기록, Vertex 검색/structured output 계약·usage fixture. 탐색 범위/자료 유효기간/검색·비용 상한 명세. 사용자에게 소스 조사 전가 안 함 | PRE-01 | cc:WIP [공식 API 실응답·DB/Vertex 확인; MCP 미연결·웹 실원문 coverage 대기] |
| PRE-03 | BE 명세·Pydantic·테스트 선행·spec review | endpoint-request 기준 GET/저장/생성 경계·오류/권한·상태·시간/사실 검증 명세와 testplan·실패 테스트. JSON Schema/Zod/Pydantic 공통 fixture·drift 검증 계획. 기존 방송 호환·독립 spec review | PRE-01, PRE-02 | cc:WIP [명세/Pydantic/공통 fixture·테스트 구현; 독립 spec review 대기] |
| PRE-04 | snapshot·프리뷰·publication 저장 기반 | 실제 baseline 대조 후 Supabase CLI migration/ORM/문서 동기화, 근거/불변 버전/현재 제공본/실행 책임 확정, unique/FK/인덱스·원자 전환·2시즌 보관 정리. 격리 migration·기존 데이터/참조 보존 검증 | PRE-03 | cc:완료 [로컬 migration/ORM·원자 저장·FK/unique·보관 정리 검증; 운영 미적용] |
| PRE-05 | DB 사실 조립·추천 정책 서비스 | 기존 경기/번역/최근 경기 재사용, snapshot+킥오프 cutoff·FT/AET/PEN·표본/NULL·source provenance, 활성/허용 시즌·진행 중 우선/확정 순서·동률·KST fallback·중복 제거·모든 중요 경기 접근성 테스트 | PRE-04 | cc:완료 [로컬 DB 사실·추천 정책 및 경계 테스트] |
| PRE-06 | 웹 근거·부상·외부 전망·배당 어댑터 | 검증한 원본만 정규화·저장, source registry/grounding·발표/확인 시각·같은 경기·확정/불확실·시장/북메이커, unverified/missing/error 및 상충 보도. URL/시간/크기 제한·출처 지시 격리. 고정 원본+소량 실응답 contract 검증 | PRE-02, PRE-04 | cc:WIP [API 우선/원문 검증 어댑터 구현; 실제 웹·상충 보도 인수 대기] |
| PRE-07 | schema 강제 AI analysis 생성 | 검증된 근거만 입력·새 JSON 경로, MIME/provider schema+strict Pydantic·근거/필드/시점·원본 사실 대조, 거절/잘림/빈/오류/환각 출처·숫자 테스트. 기존 방송 Markdown 회귀 통과 | PRE-03, PRE-05, PRE-06 | cc:완료 [schema 강제·서버 검증·실제 Vertex JSON 성공; 로컬 검증] |
| PRE-08 | 생성 pipeline·publication·내부 실행 | DB→웹→JSON→합성/검증→원자 저장, fingerprint/생성 버전·중복/소유권·제한된 재시도·deadline/예산·중단/복구. 실패 시 이전본 보존, 자료만 있는 부분/미제공 처리, 예정만 생성·킥오프 경계. 내부 CLI/작업으로 검증, 미요청 수동 API 추가 안 함 | PRE-05, PRE-06, PRE-07 | cc:완료 [로컬 pipeline/CLI·4슬롯·재시도·원자 publication·실패 보존 검증] |
| PRE-09 | 공개 저장본·추천 GET 구현 | 보완한 FE 계약대로 DB 조회만 제공. 정상/일부/이전본/생성본 없음/없는 fixture/DB 장애, is_mock=false·진단 비노출·외부 호출 0. 추천 전환용 fixture identity·동적 활성 리그/날짜·오늘 결과 통합 테스트 | PRE-03, PRE-04, PRE-05, PRE-08 | cc:완료 [DB 전용 공개 GET·조회 외부 호출 0 검증] |
| PRE-10 | 실제 메인 FE 연동 | 실제 / 라우트에 평가 디자인·저장 JSON GET/Zod 적용, /home/mock 평가 도구 분리, 빠른 연속 전환/늦은 응답 경합·부분/실패/이전본·출처/시각·mobile/dark/reduced motion. L1/L2/build+격리 API L3 | PRE-09 | cc:완료 [실 / 연동·unit 24/E2E 16/build·격리 L3 1 PASS] |
| PRE-11 | 6시간 갱신의 실제 실행 연결 | 정기 daily-sync와 관리 수동 실행의 종료 경로 대조·공통 후처리, enable 설정·커밋된 성공 snapshot·중복/부분 실패·재기동·예산 이월 검증. 공개 조회/서버 import 생성 0·진행 중 신규 생성 0·전체 API 한도 유지. 운영 설정/재시작 없음 | PRE-08, PRE-09 | cc:WIP [현재 커밋 기반 공통 후처리·enable OFF·테스트; 관리 세션 통합 대조 대기] |
| PRE-12 | 전체 인수·독립 리뷰·운영 인계 | 핵심 추천 유형별 근거→JSON→DB→메인, 정상/실제 미제공 coverage·모든 negative case, migration·unit/격리 integration·FE L1~L3/build·스케줄/비용/회귀·독립 review. 외부/DB 환경 부족 skip은 완료 아님. 운영 적용/배포는 별도 기록 | PRE-10, PRE-11 | cc:WIP [로컬 핵심 흐름 통과; 독립 리뷰·실제 웹 coverage·전체 유형 인수 대기] |

의존 흐름: `PRE-01 → 02 → 03 → 04 → (05,06) → 07 → 08 → 09 → (10,11) → 12`. 괄호는 논리 의존 관계이며 단일 checkout에서 동시 브랜치 편집을 허용하는 뜻이 아니다. 실제 작업은 한 task branch에서 소유 범위를 보존하고 FE/BE 역할을 순차 인계한다.

- 다음 실행 출발점: **PRE-01**. 이 계획 수립 턴에서는 workflow 상태 전이·브랜치/커밋·원격 push/merge·운영 DB/외부 API·배포를 수행하지 않는다.
- HOME-JSON-2는 PRE BE 작업의 상위 묶음, HOME-JSON-3는 FE 실 연동/인수 상위 묶음이다. AX-7/AX-PRE-1/AX-8의 홈 관련 범위를 구체화하며 AX-8의 모든 일반/방송 동적 리그 확장 완료까지 주장하지 않는다.
- 현재 checkout의 관리/검색/홈 미커밋 변경과 실제 작업 소유·migration baseline을 보존·정리한 뒤 lifecycle을 시작한다. 기존 변경을 임의 stash/reset하지 않는다.

### PRE 착수 승인·브랜치/예산 후속 기록 — 2026-10-25

- 사용자가 계획 저장 후 개발 진행을 요청했다. 생성 시점·처리 횟수·시즌/토큰 비용 가정은 `plan.md` §14.11에 저장했다. 브랜치 계획은 §14.12를 따른다.
- 현재 `fe-feat-streamer-management-mock`에 관리·검색·홈의 미커밋 변경이 있어 브랜치 전환·구현 수정은 아직 하지 않았다. 작업 소유/보존과 clean 상태 확보를 선행하며 임의 stash/reset/전체 일괄 커밋을 하지 않는다.
- 로컬 통합 `feat/home-preview-json` → `fe-feat-home-preview-contract` → `be-ep-home-prematch` → `be-ep-home-recommendations` → `fe-feat-integration-home-preview` → `be-feat-home-preview-refresh` 순서. 각 단계 결과를 로컬 통합 브랜치에 반영하며 실제 시작 커밋은 정리 후 기록한다.
- PRE-01의 기능 구현·테스트는 미착수 상태다. 계획/브랜치 정책 저장을 구현 완료나 배포 승인으로 처리하지 않는다.

### 현재 세션 분리 기록

- 홈 프리뷰 세션의 전용 파일과 공용 파일의 홈 관련 부분만 복원했다. 관리·검색·선수 번역 및 공통 인증/환경 변경은 포함하지 않았다.
- 작업 브랜치: `fe-feat-home-preview-contract`, 로컬 통합 기준 브랜치: `feat/home-preview-json`. 두 브랜치의 기준은 `e3e8f40a8e045174d06544116a933cc03507c33a`이다.
- 공통 인증/관리 코드가 이 브랜치에 없으므로 관련 재사용 계획은 후속 의존성 검토가 필요하다. 원래 브랜치의 미커밋 상태는 별도 stash로 보존한다.

## 전용 worktree 분리 완료 — 최신 사용자 지시

현재 작업 경로는 `/Users/woolee/benchmark-main`, 통합 브랜치는 `feat/home-preview-json`이다. 이전의 공유 checkout/브랜치 분리 기록은 당시 기록이며 운영 방식은 `docs/decisions/2026-10-25-parallel-worktrees.md`로 대체한다. 관리·AX 변경은 포함하지 않았다. PRE-01은 미착수이며 다음 작업이다. 공통 인증/관리 코드는 현재 출발 커밋에 없으므로 후속 의존성 검토가 필요하다.


### PRE-01 실행 결과 — 2026-10-25

메인 전용 worktree `feat/home-preview-json`에서 FE 계약/목업을 보완했다. `docs/features/home-preview-contract.md`가 상세 계약이다. publication/refresh 분리, null 본문·생성 시각, facts-only, 갱신 실패 이전본, 공개 reason enum, FT/AET/PEN, 추천 목록/정렬/KST/기준 시각과 endpoint-request를 검증했다. 생성 구조 JSON Schema와 Zod의 drift 검사 포함. 단위 23개, E2E 13개, production build PASS. E2E는 API 요청 0건을 확인했다. DB/Redis/API-Football/Vertex를 호출하지 않았다. PRE-02가 다음 작업이며 PRE-03 BE spec/test/review 및 실제 구현은 아직 시작하지 않았다. 앞의 미착수 표기는 분리 당시 기록이다.

### PRE-02~11 로컬 구현 기록 — 2026-10-25

메인 전용 경로/브랜치에서만 구현했다. 공식 API endpoint를 먼저 확인하고 부상·배당·자체 전망을 근거로 수집했으며, 실제 Vertex JSON 저장과 공개 DB GET·메인 표시를 검증했다. 최신 상태는 위 PRE 표와 `docs/features/home-preview-implementation.md`를 따른다. 문서의 과거 ‘다음 PRE-01/02’는 당시 기록이다. 독립 승인/운영 인수/배포 완료는 주장하지 않는다. 다른 세션의 관리·AX·인증 변경은 가져오지 않았다.

### 주요 결장자·매체 전망·팀명 배당 후속 — 2026-10-25

중복 제거, DB 출전 근거 조립, 기존 analysis의 key_absences 선별과 서버 검증, 팀당 2명/전체 펼치기 UI, API 전망 유무와 독립적인 기사 검색·원문 의견 병합, 팀명 배당을 메인 전용 worktree에서 구현했다. 실제 1557442에서 주요 3명/전체 12명 및 외부 Sports Mole 전망 1건 저장을 확인했다. PRE-06의 실제 웹 성공 사례를 추가했으며 모든 유형/상충 보도 인수와 독립 리뷰는 계속 남아 있다. 기본 생성 호출은 검색+분석 2회이며 자동 생성 활성화/배포는 하지 않았다.

### 주요 선수·사진·접힌 기록 후속 — 2026-10-25

| Task | 내용 | DoD | Depends | Status |
|---|---|---|---|---|
| HOME-PLAYER-POINTS | 선수·확인된 연속 기록 관전 포인트, 인지도 보조 결장자, 홈/원정 고정 2×2와 우측 얼굴, 접힌 선정 이유·기록 | DB 기록/누락 경계·ID/근거/팀당 2명·번역/사진·fallback·모바일 배치/상세 토글·실제 JSON 저장→공개 GET→메인 확인 | PRE-05~10 | cc:완료 [로컬 구현; BE100/FE27/E2E17/L3 4/build PASS; PRE-12 독립 인수 별도] |

현재 요구와 검증 기록은 docs/features/home-preview-players.md가 정본이다. 기존 유명세 비사용 정책은 최신 사용자 지시로 순위 보조 허용으로 바뀌었다. 운영 활성화·배포·원격 반영은 하지 않았다.

선수별 선정 이유의 LLM 응답 포함을 후속 확정했다. 신규 모델 응답 필수 reason 및 저장/조회/접힌 상세의 실제 문자열 일치까지 검증한다. 과거 저장본에는 임의의 LLM 이유를 덧붙이지 않는다. 최신 구현/검증 정본은 home-preview-players.md, 생성 버전은 home-preview-1.1-prompt-6이다. 운영/최종 독립 인수는 여전히 PRE-12 별도다.

최신 후속: 선정 이유를 확인된 시즌·최근 표본·연속 기록·팀 폼을 연결하는 3~5문장으로 확장했다. 숫자와 항목별 표본 수를 분리한다. 로컬 교정 검증의 별도 개발 모델 1회는 snapshot metadata에 명시하며 worker 슬롯/기존 버전을 변경하지 않았다. 운영 자동 생성 호출 수와 OFF 설정은 유지한다. 세부·검증은 home-preview-players.md의 복합 이유 절을 따른다.


### 2026-10-25 메인 후속 — 원인 연구·매체 3곳·상세 이동

최신 계약·정책은 `docs/features/home-preview-research.md`를 따른다. 선택 결장자만 최대 팀당 2명 원인/발생 시점을 후속 검색하며 일반 GET은 DB 전용이다. 기본 최대 모델 호출은 검색1+분석1+선택 원인1=3회(4슬롯 최대12회)로 변경했다. 외부 전망은 서로 다른 웹 매체3곳 목표/API 자체 전망 제외, 부족하면 partial이다. 실제 현재 맨유–본머스 웹0건/원인 미확인과 구현 완료를 구분한다. 선택 경기 상세 이동 버튼을 연결했다. PRE-12의 독립 리뷰·실제 coverage 인수·운영 적용은 아직 남아 있다.


| Task | 내용 | DoD | Depends | Status |
|---|---|---|---|---|
| HOME-RESEARCH-DETAIL | 선택 부상 원인/발생 시점 웹 검증, 독립 매체3곳 목표 및 API 구분, 선택 경기 상세 이동 | 선택2명/팀·미확인/상충/날짜 정밀도·기존 facts 불변·매체 count·링크 전환/이동 검증; 최신 계약 home-preview-research.md | HOME-PLAYER-POINTS, PRE-06~10 | cc:완료 [로컬 구현 BE107/FE29/E2E17/L3 4/build; 실제3곳 coverage/PRE-12 인수 별도] |


### 2026-10-25 실제4경기 시험·재시도 정책안

실제 신규 게시2/기존본 유지2. 원인과 단계별 재시도 설계는 `docs/features/home-preview-retry-policy.md`를 따른다. 부모 source index 보완은 구현/관련30테스트 PASS. HTTP 오류 상세 진단·단계 checkpoint·실패 단계만 재개·슬롯당 추가 AI 합계1회(기본3+1=4,4슬롯16) 정책은 아직 구현되지 않았다. 현행 자동 생성 OFF와 정상 슬롯 이력은 유지한다.

| Task | 내용 | DoD | Depends | Status |
|---|---|---|---|---|
| HOME-PREVIEW-RETRY | 단계별 실패 진단·checkpoint·제한 재시도 | 오류 분류/허용 metadata·재개/유효성·공유 추가1회·300초/킥오프/owner·부분 성공·회귀·미완료2경기 재시험 | HOME-RESEARCH-DETAIL | cc:완료 [로컬 재시도·checkpoint/BE125/실제4경기 및 브라우저 PASS; PRE-12 별도] |


### 2026-10-25 재시도 구현 착수

사용자 요청으로 원인180초/전망·분석90초, 실행 lease900초, 슬롯 모델4회·공유 추가1회, 비공개 불변 checkpoint 및 단계 재개를 메인 경로에 구현했다. 최신 정본은 `docs/features/home-preview-retry-policy.md`의 후속 확정 절이다. 고정 응답/격리 DB 검증 후 실제4경기 재시험 중이며, 결과가 확인되기 전 전체 성공으로 기록하지 않는다. 자동 생성/운영 배포는 OFF다.


| Task | 내용 | DoD | Depends | Status |
|---|---|---|---|---|
| HOME-CAUSE-EVIDENCE | 선수별 공식 검색·주장별 다중 근거·날짜 정밀도/사건 연결 검증 | 공식 소보슬라이/프림퐁 원문 확보·원인/발생/재발/발표일 분리·소제목/다중 문단/다중 출처·실패 구분·실제 결과 대조 | HOME-PREVIEW-RETRY | cc:WIP [실제 누락 진단/4MiB 수집 보완; 다중 근거·날짜 검증 재설계 중] |


### 2026-10-25 재시도·실제4경기 전체 검증 완료

HOME-PREVIEW-RETRY 로컬 구현 완료. 원인180초/기타90초, 실행1200초, 단계당 추가1회·전체6회 상한(정상3회,4슬롯 최악24회), checkpoint 재개/진단을 적용했다. BE125 및 실제 DB→API→브라우저4경기 PASS. 최종 저장본과 원문 누락 한계는 `docs/features/home-preview-generation-verification.md`가 정본이다. 기존 자동 생성/운영 상태와 정상 worker 슬롯 이력은 유지한다. PRE-12 독립 인수/전체 실제 웹 coverage는 별도다.


### 2026-10-25 원문 우선 검색 재시험

생성 버전prompt13. 부상 검색을 일반 Google Search→실제 URL 원문 수집→출처 ID enum JSON 추출로 분리했다. 다중 인용·소제목·발표일 정밀도·동일 사건 검증, 원문4MiB/공식 기사 링크 우선 탐색을 구현했다. 정상 최대4호출, 단계 최대3요청·슬롯 전체6요청·1200초,429는30/60초·기타10/20초 및 최대90초 대기로 보완했다. 실제4경기 최신 생성/DB→API→브라우저 오류0, 모델18/API16. BE137+추가 회귀4(기존3+신규1)/FE29/E2E17/build 통과.

외부 매체는2/2/1/1곳, 자동 발생일 확인0명으로 자료 목표 미완료다. 원인 확인은3/0/1/0명. 공식 원문 개별 검증 통과와 자동 검색 완성을 구분하며 HOME-CAUSE-EVIDENCE는WIP, PRE-12 별도다. 최신 결과 정본은 docs/features/home-preview-generation-verification.md. 정상 worker 이력/다른 세션/운영 환경은 변경하지 않았다.


### 2026-10-25 단일 호출 프롬프트 준비

| Task | 내용 | DoD | Depends | Status |
|---|---|---|---|---|
| HOME-SINGLE-PROMPT | 맨유–본머스 DB 입력을 동봉한1회 검색·분석·JSON 요청안 | 원인/발생 시점/출처를 한 응답에 보존, 실제 DB 후보·기록·시각, 읽기 전용 생성 도구·request body | HOME-CAUSE-EVIDENCE | cc:완료 [프롬프트/실험 계약/DB 입력 준비; 실제 호출·runtime 전환 미실행] |

정본 docs/features/home-preview-single-call/README.md. 후보12명·관전8명·양팀 최근5경기, 로컬 저장 API 수집본과 DB 통계 입력. 이전 LLM 결과 제외, 외부 호출/DB 쓰기0회. 검색+responseSchema 실제 호환성/출력 검증과 단일 호출 worker 구현은 별도다.
