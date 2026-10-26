# 관리 기능 로컬 main 통합 인수 — 2026-10-26

사용자 승인: 관리 기능을 먼저 main에 병합하고, 홈/검색 워크트리 통합 후 배포한다. 이어서 배포 전 운영 DB 적용 상태 확인과 검증도 요청했다. 이번 작업은 로컬 통합이며 원격 push·배포·서비스 재시작·운영 환경변수 변경을 하지 않는다.

## 분리한 범위

관리 네 탭, JWT/refresh·서버 권한, 공유 수집 대상·최초/갱신·취소/영속 이력, 번역 보호/충돌/감사 및 선수·감독 조건 검색, 카탈로그 추천/한국어 우선 정렬, 원문 분석·종류별 접기/펼치기를 포함한다. 0017 ORM/DDL/Supabase SQL bridge·관련 정책/명세/테스트를 함께 포함한다.

공용 헤더·라우터에서는 관리/인증 변경만 스테이징하고 SearchMockView 및 HomePreviewMockView 연결은 제외했다. 홈·검색 구현과 별도 CSV/과거 하네스 상태 파일은 원래 작업 디렉터리에 보존한다. plan.md와 Plans.md에는 공통 요구·설계 및 관리 범위만 반영하며 후속 홈/검색 구현 완료 상태는 포함하지 않는다.

최초 분리는 작업 파일을 덮어쓰지 않고 Git 스테이지만 분리했으며, 이후 사용자가 승인한 관리 목업 제거·컴포넌트 경로 정리만 원본에 반영했다. 홈/검색 등 범위 밖 36개 파일의 hash는 최초 기록과 일치한다. 별도 Git worktree를 생성하지 않았다. `/private/tmp/benchmark-management-merge-20261026/candidate-clean`은 Git index에서 추출한 검증용 일반 디렉터리다. 원본 working file hash를 대조해 분리 중 변경이 없음을 확인했다. 최종 검증 뒤에는 검증 기록/운영 DB 결과와 계획 행만 갱신했다. backend/DDL은 371개 테스트를 통과한 후보와 동일한 Git tree임을 대조했다.

## 분리 후보의 실제 검증

- Backend: 전체 단위 테스트 및 관리 PostgreSQL 통합 테스트 **371 PASS**, 47.43초. DB는 전용 로컬 55439에서 테스트마다 격리 schema를 사용한다.
- Frontend: 전체 unit **200 PASS / 29 files**, TypeScript + Vite build PASS.
- Playwright: 정리 전 관리 mock **18 PASS**. 사용자가 해당 평가 UI 제거를 승인해 평가 전용 E2E/설정을 제거했다. 최종 실제 Vue → 분리 후보 FastAPI → 테스트 Postgres **10 PASS**(개발 모드에서도 목업 탭/경로 없음 포함). 후보의 테스트 주소만 임시 변경해 기존 실행 서버와 분리했다. API-Football/Upstash는 fixture이며 운영 수집/유료 호출을 실행하지 않는다.
- 신규/변경 Python 파일 Ruff PASS, Git diff 공백 검사 PASS.
- 기본 production bundle에서 `/api/_mock/management`, `sample-1006`, `SearchMockView`, `HomePreviewMockView` 참조 0건. 평가용 mock/별도 홈·검색이 기본 번들에 포함되지 않음을 확인했다.

이 기록은 주 에이전트의 코드 검토·자동 검증 및 사용자의 로컬 main 병합 승인 근거다. 과거 FE 목업의 독립 APPROVE를 이번 backend 변경의 독립 리뷰로 확대하지 않는다. 원격 PR/배포 완료를 의미하지 않는다.

## 운영 DB 적용·검증

운영으로 사용하는 기존 연결 Supabase를 **READ ONLY 트랜잭션**으로 확인했다. 실행 증거는 `streamer-management-production-db-verification.json`이다. 운영 사용자/권한/비밀번호/축구 데이터는 수정하지 않았다.

- Alembic 이력은 이미 `0017_streamer_management`이며 이번 관리 migration과 일치한다. 기존 적용을 반복 실행하지 않았다.
- 필수 테이블/컬럼 누락 0, management_run/translation_audit RLS 활성, 4개 번역 보호 trigger, human_modified/version 보호 함수와 필수 인덱스 존재를 확인했다.
- 당시 active run 0, 실행자/감사 수정자 고아 참조 0.
- 한글/별칭 조회: 아시안컵 7건, 동아시아 2건, EPL 1건. EPL 범위 선수 847명/감독 46명 조회 및 리그/팀 선택지 조회 통과.
- 따라서 이번 관리 범위에는 추가 운영 DDL 적용이 필요 없다. 쓰기/회전 토큰/충돌·취소 테스트는 운영 public 대신 격리 테스트 DB와 fixture에서 수행했다.
- 나머지 홈/검색 워크트리의 DB 변경은 그 코드까지 합친 뒤 스키마/이력/적용 순서를 다시 대조해야 한다. 이번 DB 검증을 그 작업의 적용 완료로 확대하지 않는다.

## 로컬 main 반영 방식

현재 checkout에 남은 홈/검색 미커밋 원본을 보존하기 위해 브랜치를 전환하지 않는다. 검증된 관리 커밋을 만든 뒤 main이 그 조상임을 확인하고 로컬 ref를 fast-forward한다. 기존 main을 덮어쓰는 force update나 원격 push는 수행하지 않는다. main과 관리 브랜치의 commit/tree 일치를 확인하며 실제 SHA는 Git 이력 및 사용자 보고에 남긴다.

## 사용자 승인에 따른 관리 목업 정리

- 개발용 `/admin/mock` 경로, 헤더 탭, AdminMockView, 샘플 API client·MSW browser/handlers와 시나리오/초기화 도구를 제거했다. 운영 빌드에서만 숨기는 방식이 아니라 src에서 제거했다.
- 실제 사용 컴포넌트와 스타일은 `frontend/src/components/management/`, `frontend/src/styles/management.css`로 정리했다. API 인터페이스는 실제 응답 타입으로 독립 정의해 평가 client에 대한 타입 의존도 제거했다.
- 테스트 데이터/상태 helper만 `frontend/tests/fixtures/management/`로 이동했다. 그 helper를 사용하는 단위 테스트는 유지하고, 네트워크 client 테스트는 실제 management API 경로를 검사하도록 변경했다. 별도 FastAPI/Postgres fixture 서버는 tests/support에만 남는다.
- 목업 제거 후 분리본 frontend unit 200 PASS, 실제 API E2E 10 PASS, TypeScript/Vite build PASS. 정리 전 운영 DB audit와 backend 371 PASS 근거는 backend tree가 같으므로 그대로 유효하다.
- 홈·검색 작업의 미커밋 원본과 해당 워크트리는 변경하지 않았다. 관리 목업 제거 전에 외부 임시 검증 디렉터리에도 원본을 보관했다.
