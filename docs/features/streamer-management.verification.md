# 관리 실제 화면·백엔드 연결 검증 — 2026-10-25

## 결과와 범위

평가한 네 탭 UI를 실제 `/admin`에 반영하고 `/api/v1/admin/management/*`에 연결했다. 평가용 `/admin/mock`도 유지한다. 사용자 지시로 BE에 착수했으며, 초기 검증 후 사용자의 DB 연결 제보에 따라 기존 Supabase DB를 0016→0017로 갱신했다. 기존 계정/경기 자료와 DB 주소는 보존했다. 배포·배포 환경변수 변경·운영 서비스 재시작은 하지 않았다. commit/push/merge 및 공식 독립 머지 리뷰도 수행하지 않았다.

기존 DB를 사용하는 실제 로컬 화면: http://127.0.0.1:5173/admin (기존 계정으로 로그인).

별도 fixture 통합 검증 화면: http://127.0.0.1:5187/admin (아래 테스트 계정 전용).

- 로컬 계정: `streamer@management.local` / `Bench1234` (테스트 전용 STREAMER).
- USER 차단용: `user@management.local` / 동일 비밀번호.
- Vue 5187 → FastAPI 8016 → 전용 PostgreSQL 55439. 실제 저장/조회/트랜잭션/JWT 검증을 사용한다.
- API-Football과 Upstash의 외부 경계만 fixture로 대체한다. 실제 운영 계정의 비밀번호로 로그인하거나 유료 축구 API를 호출하지 않았다. 기존 Upstash는 읽기 전용 PING/PONG과 local: prefix 연결만 확인했다. FA Cup fixture는 오류·재시도·통계 평가용 timeout을 반환한다.
- `tests/support/management_live_server.py`는 전용 로컬 DB만 허용하며 production app에서 import하지 않는다. 다른 cookie 이름과 `local:management-e2e:` prefix를 사용한다.

## 구현과 확인한 동작

- 인증: login JWT, HttpOnly refresh cookie, Upstash 명령의 원자 rotation, me/logout, DB 현재 활성·역할 확인. 관리의 익명401/USER403, STREAMER/ADMIN 허용. 브라우저 저장 역할을 바꿔도 실제 관리 권한을 얻지 못한다.
- 대상: DB 카탈로그 검색/최신화 확인·진행·결과·시각·재조회, 최신 두 실제 개최 시즌, 기존 대상 편집/upsert, 명시 null로 제한 해제, active와 league 활성 정합, 설정 제외와 자료 삭제 분리.
- 실행: scope snapshot, queued부터 DB 저장, 중복 index/advisory lock, 최초 전체 시즌/갱신 3일 필터, API/commit 경계 취소, commit 자료 보존, 재실행/재접속/중단 감지. 저장 행과 처리 단위 수를 구분한다. 수집 범위 확인 전 취소도 다시 실행할 수 있다.
- 기존 daily-sync 수동 trigger도 새 영속 실행으로 연결한다. 기본 대상 fallback으로 비활성 설정을 우회하지 못한다.
- 이력/로그: 기존 worker_sync_log 조회를 보존하고 신규 실행을 함께 제공한다. 최근 7일 최대100개 요약, 상세 로그 별도 조회, 한국어 코드 대응/원문/대상/단계/시도 횟수, 1000줄 tail을 넘어도 전체 오류/경고 카운터 보존. 과거 대상별 수는 없으면 미기록으로 표시한다.
- 번역: 네 종류 원문/한글 검색·서버 페이지 처리, 번역/미번역만 표시, 버전 충돌409와 초안 유지, 수정 이력. DB trigger와 filler queue/UPDATE가 사람이 수정한 이름 및 의도적 NULL을 보존하며 기존 import도 같은 보호를 받는다.
- 성공한 수집 리그에 한정해 최신 두 실제 개최 시즌의 시즌 자료 보관 정리. 공유 entity/번역 보존. 다른 워커 자동 등록이나 수집 주기 변경 UI는 추가하지 않았다.

## 검증 결과

- 백엔드 전체 unit **316개**, 관리 격리 Postgres integration **7개**, 합계 **323개 PASS**.
- FE 관련 unit **36개 / 5파일 PASS**.
- 평가 목업 E2E **13개 PASS**.
- 실제 API 연결 E2E **5개 PASS**. 실제 역할 위조 차단, 카탈로그 최신화, DB null 저장·새로고침, 번역 CAS/감사, 워커 적재/오류·원인 통계, 취소·재실행 선택까지 확인했다.
- `npm run build` (vue-tsc + Vite) PASS.
- 변경 백엔드 파일 Ruff PASS.
- 실제 API 화면 캡처: `out/management-live/desktop-failure.png`, `mobile-failure.png`. 모바일 문서 가로 넘침 0, E2E pageerror 0.
- 신규 0017까지 로컬 migration upgrade 성공. 기존 연결 Supabase도 0017 head 확인.

재현 명령:

```sh
DATABASE_URL=postgresql+psycopg://postgres:benchmark_test_only@127.0.0.1:55439/benchmark_test TEST_DATABASE_URL=postgresql+psycopg://postgres:benchmark_test_only@127.0.0.1:55439/benchmark_test .venv/bin/pytest tests/unit tests/integration/test_streamer_management.py -q
```

```sh
cd frontend
npm run test:unit -- tests/unit/lib/managementMock.spec.ts tests/unit/lib/managementLogPresentation.spec.ts tests/unit/components/common/AppHeader.spec.ts tests/unit/views/LoginView.spec.ts tests/unit/views/SignupView.spec.ts
./node_modules/.bin/playwright test --config playwright.management.config.ts
./node_modules/.bin/playwright test --config playwright.management-live.config.ts
npm run build
```

실제 운영에 적용하기 전 별도로 확인할 내용은 [관리 API 계약/구현 결과](streamer-management-api.md)의 migration 기준선과 인증/CORS/cookie 설정이다. 외부 API/Upstash 실 자격증명으로의 smoke 검증 및 방송 MPA 전체 인증 정합성은 이 로컬 검증 결과에 포함하지 않는다. 새 실행과 달리 기존 실행은 구조화 원인 정보가 없어 목록 원인 통계가 일부 누락될 수 있음을 표시한다.

## 기존 로그인 연결 문제 수정

5173은 기존 8000/Supabase, 5187은 테스트 8016/전용 로컬 DB였다. 기존 화면에서 정상 origin이 CORS에는 허용되지만 cookie 인증의 Origin 검사에서는 차단돼 403이 발생했다. CORS/Origin 허용 목록을 공통 함수로 통합하고, 로컬 `.env`의 누락된 JWT 키와 HTTP cookie 설정을 보완했다. DB URL과 사용자 계정/비밀번호/역할은 변경하지 않았다.

개발 API는 Vite 동일 주소 proxy를 사용해 localhost/127.0.0.1 혼용으로 refresh cookie가 다른 site로 취급되는 문제를 피한다. 5173 proxy 로그인 검사는 더 이상403이 아니라 DB의 invalid_credentials 401까지 도달함을 확인했고, 8000의 JWT 검증 경로도 설정 누락503 대신 유효하지 않은 토큰401을 반환했다. 이는 의도적인 가짜 계정/토큰 검사이며 기존 사용자의 실제 로그인 성공을 대신 주장하지 않는다.

기존 연결 DB의 Alembic head를 0017로 확인했다. 기존 DB에서 유료 수집·자동 번역·사용자 역할 변경은 실행하지 않았다. 테스트용 5187 로그인 화면에는 별도 검증 DB임을 표시한다.
