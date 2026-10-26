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

## 스트리머 관리 및 AX (2026-10-24)

상세 범위·화면·API 후보: `plan.md`. FE mock → endpoint-request → BE spec/test → 구현 → FE 통합 순서. 단일 checkout에서 구현과 브랜치 변경은 순차 수행한다. 이번 단계는 기획만 진행하며 신규 기능이 구현됐다는 상태를 부여하지 않는다.

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| AX-0 | 실제 코드 대조·화면/응답 초안·정책 변경 기록 | `plan.md`의 코드 근거/재사용·수정·신규/미정 경계와 결정 기록, 기존 관련 unit 42 PASS. 기능 구현 전 상태 명시 | - | cc:완료 [local-audit-20261024] |
| AX-UI-0 | 디자인 개선 전 현재 페이지 기능 목록 대조 | 실제 라우트 기준 코드 연결/기존 미연결/미구현/추가 후보를 구분, `plan.md` §9 작성. 브라우저·데이터 검증과 구분 | AX-0 | cc:완료 [local-page-inventory-20261024] |
| AX-UI-1 | 메인 추천 경기·AI 프리뷰 중심 디자인 범위 확정 | 기존 구현의 재사용 범위를 확인하고 메인은 오늘 추천 경기·로고 등장·좌우 전환·인라인 프리뷰 중심으로 재구성. 일정 탐색은 경기 탭 활용. 관련 페이지는 필요한 최소 범위, 새 추천 영역은 단일 순위 결정 후 구성 | AX-UI-0 | cc:TODO |
| AX-1 | 관리·인증 FE mock 및 API 요구 | STREAMER/ADMIN 로그인·재접속, 공유 대상 편집·NULL 해제, 선택/취소/복원/이력, 번역 충돌의 정상·빈·오류 화면과 endpoint-request | AX-0 | cc:TODO |
| AX-2 | 공통 인증·역할 BE 및 FE 연동 | JWT/refresh/me/logout, DB 사용자 확인, mock 권한 제거, USER/미인증 직접 요청 차단, STREAMER/ADMIN 관리·방송 접근 통합 검증 | AX-1 | cc:TODO |
| AX-3 | 대상·활성·2시즌·최초 수집·호출 안전성 | 등록/실행/조회 기간 일치, active 정합, 과거 시즌 초기 적재, 상세 실패 보존, 공통 호출 한도·중복 방지, 보관 정리 코드·실행 연결·dry-run·격리 실제 정리/참조 검증과 운영 적용 여부 분리. Supabase CLI 이력 기준선 정리 | AX-1, AX-2 | cc:TODO |
| AX-4 | 수집 실행·복구·이력 BE/FE 통합 | 선택·실패 재실행·협력 취소, commit/미처리 구분, DB 실행 원장·heartbeat·재접속, 중단 상태·재실행, 7일 종료 로그 화면 연결 | AX-3 | cc:TODO |
| AX-5 | 번역 검수 BE/FE 통합 | 4종 검색/수정/검수·version 409·감사 이력, filler/import 경쟁과 사람이 비운 값 보호, 전체 서비스 번역 재조회 경로 검증 | AX-1, AX-2, AX-3 | cc:TODO |
| AX-6 | 워커 실제 실행 연결 정합화 | daily-sync/번역/뉴스 실행 코드를 주기 연결과 구분, async 실행 어댑터·중복 방지 검증. 일정 변경 UI와 미요청 수동 워커 API는 제외 | AX-3, AX-5 | cc:TODO |
| AX-7 | 오늘 추천 경기 캐러셀·AI 프리뷰 FE mock과 추천 규칙 | 단일 순위·동률·날짜 이동 규칙 확정 후 로고 페이드인·좌우 전환·메인 인라인 프리뷰 구성. 빅6 EPL/UCL 8강 이후와 비빅6 UCL 4강/결승·UEL 결승 포함. 부상·최근 5경기·AI 예측·외부 전망/배당·출처·부분 실패 화면과 endpoint-request. 일정 탐색은 경기 탭, 종료는 별도 오늘 결과 | AX-0, AX-UI-1 | cc:TODO |
| AX-PRE-1 | 프리뷰 근거·부상·외부 전망·배당 수집/저장 설계와 검증 | AX-7 FE 요구 기준 기존 DB/생성 어댑터 활용, 공급자/실응답/경기 coverage·출처 사용 범위 확인, 최근 5경기·출전 변수·사이트별 전망·북메이커/시장/as-of snapshot·생성 근거. 전체 API 한도·6시간 정책·예산 유지. API-Football 신규 모델 전 MCP 실응답 확인 경로 확보 | AX-3, AX-7 | cc:TODO |
| AX-8 | 동적 리그·추천·저장 프리뷰 BE/FE 통합 | 새 리그 일반/방송 범위, 핵심 빅6/중요 토너먼트 경기 선정·프리뷰 fixture 동기화, 근거·자료/생성 시각, AI 예측/외부 전망/배당 구분, 재사용·생성 예산·누락/실패 처리. 사실 창작/미래 통계 혼입/공개 GET 외부 호출/polling 차단 검증 | AX-3, AX-7, AX-PRE-1 | cc:TODO |
| AX-9 | 실제 데이터 coverage·검색 지표/정답 정의 | 읽기 전용 리그×시즌×영역 조사, NULL/0·소속·집계 grain·JSON 필드, 실제 범위 기반 질문·기준 SQL. 운영 데이터를 변경하지 않음 | AX-0 | cc:TODO |
| AX-10 | 자연어 검색 FE mock/API 요구 | 목록/순위/비교·조건 재질문·0건/미수집/미지원/실패·링크·시각·제한 화면과 endpoint-request. 정해진 예시로 질문 제한하지 않음 | AX-9 | cc:TODO |
| AX-10-MOCK | 검색창 중심 선행 화면 목업 | `/search` 입력·예시 순위/목록/비교·조건 수정·확인 질문·오류 상태와 API 초안. `docs/features/ax-search-mock.md` 참조. 실제 coverage·지표 정의·상세 링크·검색 연동은 AX-9/10 후속이며 AX-10 완료와 구분 | AX-0 | cc:완료 [local-search-mock-20261025] |
| AX-SEARCH-CONTEXT | 자연어 검색 컨텍스트·사례 조사·상세 계획 분리 | `docs/ax/natural-language-search/`에 현재 상태·출처 있는 6개 사례·스택 점검·상세 plan.md·미정/DoD/의존성 정리, 상위 문서 연결. 운영 DB 조사·BE 구현과 구분 | AX-0, AX-10-MOCK | cc:완료 [local-search-context-20261025] |
| AX-SEARCH-DECISION | 검색 모델·로그인·DB 재사용·사전 우선 결정 반영 | Vertex AI `gemini-4-argon`·로그인 필수·기존 DB 사용을 결정 기록/AGENTS/검색 계획에 연결, 용어 사전 설계 초안 작성. 실제 호출·인증·사전 적재와 구분 | AX-SEARCH-CONTEXT | cc:완료 [local-search-decision-20261025] |
| AX-SEARCH-STACK | 검색 기술 비교군 점검 | `stack-comparison.md`에 Core/템플릿·SQLGlot/pglast/sqlparse·사전/이름 검색·Vertex SDK/REST 비교, 로컬 설치와 DB 미접속 컴파일 확인, 미검증 범위 기록. 후보 설치/최종 채택과 구분 | AX-SEARCH-DECISION | cc:완료 [local-search-stack-20261025] |
| AX-SEARCH-STACK-SELECT | 검색 구현 기술 확정 | SQLAlchemy Core·Pydantic·SQLGlot·Google Gen AI SDK·JSON 사전/DB 별칭·pg_trgm을 결정 기록/컨텍스트/상세 계획에 반영. 실제 설치·DB/모델 검증·연동은 후속 | AX-SEARCH-STACK | cc:완료 [local-search-stack-selection-20261025] |
| AX-SEARCH-DICT-RULES | 검색 사전 상세 규칙 초안 작성 | `dictionary-rules.md`에 정규화·엔티티/별칭·지표/집계/NULL·범위/소속·재질문·변경/버전·평가·미정 항목 작성. 규칙 초안과 AX-9 실데이터/사전 검증 완료 구분 | AX-SEARCH-STACK-SELECT | cc:완료 [local-search-dictionary-rules-20261025] |
| AX-SEARCH-LOOKUP-PLAN | 사전·이름 조회 실행 계획 구체화 | `entity-resolution.md`에 Retriever/서버 도구/Planner 책임, 원천·입출력·정확/유사 검색·관계/선택·bounded 호출·Bundle·LOOKUP-1~7·평가 작성. 사용자 정정 보존. 실제 도구/모델/DB 검증과 구분 | AX-SEARCH-STACK-SELECT | cc:완료 [local-search-lookup-plan-20261025] |
| AX-11 | 검색 전용 읽기 DB 경로·SQL 게이트 | 허용 view/role/AST·함수·시즌·비용검사, 실행 timeout·전용 pool·동시성·응답 byte·금액 제한. 운영 DB 버전/권한 확인, 고비용·민감정보·변경 SQL 차단 | AX-2, AX-3, AX-10 | cc:TODO |
| AX-12 | 자연어 해석·SQL 결과 및 FE 통합 | 조건/집계/순위/비교 기준답안 일치, 모호함 확인·지원한계·coverage, 검색 결과와 상세 링크·기준시각·부하 제한 검증 | AX-9, AX-10, AX-11 | cc:TODO |
| AX-13 | 통합 리뷰·상태 정리 | AX 관리/홈/검색 DoD의 코드·격리 통합·FE 증거, 관련 문서/상태 정합. 배포는 명시 요청 시 별도 작업 | AX-4, AX-5, AX-6, AX-8, AX-12 | cc:TODO |

## 관리 기능 우선 개발 (2026-10-24)

상세 실행계획: `plan.md` §11. FE 입력: `docs/features/streamer-management.md`. 각 기능 묶음은 FE mock → endpoint-request → BE spec/test/구현 → FE 실 API 연동 순서로 진행한다. 아래는 최초 계획을 기준으로 하며, 2026-10-25 사용자 승인 후 관리 화면·BE·실 API 연결을 로컬 검증했다. commit/push/merge 및 운영 적용과 구분한다. 상세 증거는 `docs/features/streamer-management.verification.md`를 따른다.

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| MGMT-0 | 관리 우선 개발계획·FE 입력 작성 | 범위·작업/의존성·API/DB 후보·검증·배포 제외, `plan.md` §11과 feature 요구사항·작업표 정합 | AX-0 | cc:완료 [local-management-plan] |
| MGMT-1 | 인증·관리 공통 셸 FE mock/API 요구 | 로그인/권한/만료/재접속·공통 안내·네 탭의 spec/devplan/testplan·mock·L1/L2와 인증 endpoint-request | MGMT-0 | cc:완료 [local-ui-and-contract] |
| MGMT-2 | 공통 인증 BE 및 FE 연동 | JWT/refresh/me/logout·DB 사용자/role·prefix·mock 우회 제거·공통 API client, STREAMER/ADMIN 허용·USER/미인증 거부·방송/MPA 회귀·세션 L3 | MGMT-1 | cc:WIP [integrated; 기존 DB 0017/미배포/merge 전] |
| MGMT-3 | 수집 대상 FE mock/API 요구 | 카탈로그·허용/지원 시즌·기존 설정 복원·NULL 해제·활성/제외·선택·경합/오류 화면과 endpoint-request | MGMT-2 | cc:완료 [local-ui-and-contract] |
| MGMT-4 | 수집 대상 BE/정책 및 FE 연동 | CRUD 재사용·명시 NULL 수정·시즌/active 정합·카탈로그 호출 제어·지원 제약 표시, Supabase CLI 기준선/ORM 동기화·격리 검증·실 연동 | MGMT-3 | cc:WIP [integrated; 기존 DB 0017/미배포/merge 전] |
| MGMT-5 | 실행·취소·복구·이력 FE mock/API 요구 | 선택/initial-refresh·단계·부분 저장·취소 요청/완료·중단/재접속·재실행·이력 mock과 endpoint-request | MGMT-4 | cc:완료 [local-ui-and-contract] |
| MGMT-6 | 실행 DB/워커·취소/복구 및 FE 연동 | queued부터 DB 저장·target/단계 snapshot·heartbeat/소유권·중복/멱등·초기 전체/갱신·취소/재실행·이력. 상세 실패 보존·전체 한도, 격리/부하/실 UI 검증 | MGMT-5 | cc:WIP [integrated; 기존 DB 0017/미배포/merge 전] |
| MGMT-7 | 번역 검수 FE mock/API 요구 | 4종 검색·원문/두 한글 필드·검수/누락·이력·409 최신값 비교/입력 보존 mock과 endpoint-request | MGMT-6 | cc:완료 [local-ui-and-contract] |
| MGMT-8 | 번역 버전·감사·보호 BE 및 FE 연동 | 조건부 갱신/이력 원자성·두 사용자/filler/import 경쟁·인간 NULL/기존값 보호·일반/방송 재조회·격리 통합/L3 | MGMT-7 | cc:WIP [integrated; 기존 DB 0017/미배포/merge 전] |
| MGMT-9 | 관리 운영 정합·보관 정리 | daily-sync/translation-filler 실제 주기·async 실행/중복·빈 큐, 최신 2시즌 정리 코드/실행 연결/dry-run/격리 삭제·공유 원본/번역 보존. 뉴스 연결은 조사 상태 기록 | MGMT-6, MGMT-8 | cc:WIP [수집/보관/보호 코드 검증; 다른 워커 운영 연결 제외] |
| MGMT-10 | 관리 전체 인수·리뷰 | 역할별 E2E·대상→선택 수집→취소/재실행→복원/이력→번역 충돌/보호, unit/격리 integration·FE type/build·L2/L3·리뷰·문서 증거. 운영 적용/배포 상태 별도 | MGMT-9 | cc:WIP [로컬 L3 검증; 독립 리뷰/운영 인수 전] |
| MGMT-11 | 선수·감독 번역 조건 검색 및 관리 로고 | FE 조건/로고 mock→API 계약→DB 소속 EXISTS/종속 팀 API→실 연동. 이름·상태·리그·팀 AND, 이적/다중시즌 중복 제거, 잘못된 조합/초기화·모바일·키보드·이미지 실패 fallback. 격리 PG 10/FE unit 34/목업 E2E 15/실 API E2E 6/build/Ruff 통과. 상세 근거 `docs/features/player-translation-filters.md` | MGMT-4, MGMT-8 | cc:완료 [로컬 구현·검증; migration/운영 DB 변경/배포 없음] |
| MGMT-12 | 카탈로그 한글·별칭 추천 검색과 동명 대회 구분 | FE 목업/응답→실제 카탈로그 확인→기존 GET 확장/연동. 추천·자동완성·국가/종류/주요 대회·ID 상세·페이지·시즌 편집, 사람 번역 우선·늦은 응답/오류·모바일. 격리 PG 15/관련 FE unit 36/목업 E2E 16/실 API E2E 7/build/Ruff 통과. 상세 `docs/features/catalog-discovery.md` | MGMT-4, MGMT-11 | cc:완료 [로컬 구현·검증; migration/운영 쓰기/배포 없음] |
| MGMT-13 | 국가·지역 검색 추천 및 한국어 우선 정렬 | 기존 선택 컴포넌트 재사용·국가 한글/원문/한국 별칭·키보드/해제/빈 상태·모바일. 한국어 국가 우선 및 대회 DB 페이지 처리 전 우선 정렬. PG 16/FE unit 37/목업 E2E 17/실 API E2E 7/build/Ruff 통과, 팀 로고 회귀 확인 | MGMT-12 | cc:완료 [로컬 구현·검증; DB/배포 변경 없음] |
| MGMT-14 | 수집 원문 로그 분석·분류 및 페이지 이탈 추적 보완 | 실제 기존/현재 원문 조사→FE 단계/원인·응답→조회 시 분류/legacy 통계→실 API. 원문/카운터 보존·미분류·정보 요약 중복 오류 방지·접근 제한/락 건너뜀 구분. 복귀 작업 ID 유지 및 뉴스 이탈→복귀→완료 이력 검증. Python unit37/PG18/FE unit39/목업 E2E18/실 API E2E9/build/Ruff. 상세 `docs/features/sync-log-classification.md` | MGMT-6, MGMT-12 | cc:완료 [로컬 구현·검증; migration/배포 없음] |
| MGMT-15 | 비어 있지 않은 종류별 로그 접기/펼치기 | 기본 접힘·같은 종류 내부 누적/건수·폴링 중 열린 상태 유지·새 종류 추가/제거·시간순·오류/경고 강조·개별 한국어 설명/원문 유지. FE unit44/목업 E2E18/기존 실 API E2E9/build 통과 | MGMT-14 | cc:완료 [FE만 변경; 백엔드 재시작/배포 없음] |
| MGMT-16 | 관리 변경 분리·로컬 main 통합 및 운영 DB 검증 | 홈/검색 코드 제외한 스테이징 검증본에서 BE371/FE200/목업18/실 API9/build/Ruff 통과. 운영 Supabase0017·컬럼/RLS/보호 트리거/인덱스/조회 점검 일치, 추가 DDL 불필요. 사용자 로컬 병합 승인, 원격 push·앱 배포 보류 | MGMT-15 | cc:완료 [로컬 병합 인수 검증; 운영 DB 읽기 전용 점검] |
| MGMT-17 | 병합 전 관리 목업 제거 | 사용자 승인에 따라 개발 탭/평가 경로·샘플 API 제거, 실제 management 컴포넌트·API 타입 독립화, 테스트 fixture만 tests로 이동. 분리본 FE unit200/실 API E2E10/build 통과, 범위 밖 파일 보존 | MGMT-16 | cc:완료 [목업 제거 후 로컬 main 병합 인수] |

매핑: AX-1은 MGMT-1/3/5/7, AX-2는 MGMT-2, AX-3/4는 MGMT-4/6/9, AX-5는 MGMT-8, AX-6의 관리 관련 부분은 MGMT-9로 구체화한다. 뉴스 워커 기능 개발까지 MGMT 완료에 포함하지 않는다. MGMT 완료를 AX-13(홈/검색까지 포함)의 완료로 간주하지 않는다.

### 사용자 평가 선행: 관리 네 탭 목업

사용자 최신 지시로 현재는 네 탭 전체의 FE 목업을 먼저 만들고 평가 후 BE를 진행한다. MGMT-2 이후 backend 단계는 사용자 평가 이전에 착수하지 않는다.

| Task | 내용 | DoD | Depends | Status |
|------|------|-----|---------|--------|
| MGMT-PREVIEW | 수집 대상/수집 실행/실행 이력/번역 검수 평가용 목업 | 개발 전용 `/admin/mock`, 샘플 MSW/localStorage만 사용. 대상 편집·모의 실행/취소·복원·이력·번역 충돌 조작, L1/L2/type/build·실화면 확인. BE/실데이터/배포 없음. 최신 로컬 unit 33/E2E 13/build·평가 반영 6캡처. 이전 버전 독립 review APPROVE, 최신 변경 root 자체 검증 | MGMT-0 | cc:완료 [평가 피드백 반영; 실제 연결 승인] |
| MGMT-EVAL | 사용자 목업 평가 반영 | 네 탭 평가 결과와 수정 범위 기록. 이후 API 계약 및 BE 착수 범위 확정 | MGMT-PREVIEW | cc:완료 [피드백 반영 및 BE 연결 지시] |

### 관리 목업 평가 반영 — 2026-10-25

- MGMT-PREVIEW: 카탈로그 독립 조회/최신화/시즌 선택, 번역·미번역 두 상태, 한국어 로그 대응과 실패 로그/원인별 통계 반영.
- 검증: unit 33개/E2E 13개/빌드 통과. 5173 기존 개발 서버에서 desktop/mobile/dark 캡처 6개, pageerror/외부 API 요청/문서 가로 넘침 0. 후속 백엔드 구현은 시작하지 않음.
- MGMT-EVAL: 수정 목업 재평가 대기. 이전 독립 APPROVE는 10/24 목업 기준이며 이번 피드백 변경은 root 자체 검증 결과로 구분한다.

### 관리 실제 연결 — 2026-10-25

- 사용자 BE 착수·실제 연결 승인. `/admin` 네 탭 + JWT/refresh/서버 role + shared target/catalog + durable run/cancel/retry/history + translation CAS/audit/protection 구현.
- 검증과 실행 방법: `docs/features/streamer-management.verification.md`, `docs/features/streamer-management-api.md`.
- 기존 5173은 유지, 별도 5187/8016 및 전용 PostgreSQL 55439에서 검증. 통합 검증의 외부 축구·Upstash는 fixture다. 이후 기존 로그인 연결 문제를 수정하고 기존 Supabase DB에 0017을 반영했으며 배포·다른 서비스에는 변경 없음. 공식 워크플로의 merge/review 완료를 주장하지 않는다.
