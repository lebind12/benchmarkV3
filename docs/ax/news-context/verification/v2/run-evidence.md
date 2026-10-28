# v2 독립 검증 실행 근거

- 담당: news-tester, FULL news-context-v2, revision 1.
- 제출/실행 HEAD: `e678b7684a98081201fe958c8fe21a297d1c0282`. 실행 전후 HEAD 동일, `git diff --stat <SHA>` 출력 없음. 미커밋 경로는 `docs/ax/news-context/progress.md`, `docs/ax/news-context/verification/`뿐이며 제품 변경 없음.
- 실행 시간: 2026-10-28 05:27~05:30 UTC (14:27~14:30 KST).
- 환경: 전용 news-context worktree, Python `/Users/woolee/benchmark/.venv/bin/python`, 기존 frontend/node_modules, Chromium headless. 실제 FastAPI news/general/auth router와 JWT decode/active-user/manager-role 코드, 메모리 SQLite 후보 및 상세 데이터. current_user/manager_user override 없음.
- 서버: 8027 API, 5197 Vite. 시작 전 해당 포트 LISTEN 없음. 본인 실행 exec session API=4827, frontend=11974. 후속 config 재검증을 위해 운영자에게 세션을 알리고 일시 유지하며 본인이 종료한다.

## 명령과 결과

| 명령 (repository root 기준; npm은 frontend cwd) | 종료 코드 | 실제 결과/근거 |
|---|---:|---|
| `PYTHONPATH=. /Users/woolee/benchmark/.venv/bin/python docs/ax/news-context/verification/v2/fixture_server.py` | 서버 실행 중 | api-server.log, 외부 서비스 미사용 |
| `VITE_USE_MOCK=false VITE_BACKEND_URL=http://127.0.0.1:8027 npm run dev -- --host 127.0.0.1 --port 5197 --strictPort` | 서버 실행 중 | frontend-server.log |
| `PYTHONPATH=. /Users/woolee/benchmark/.venv/bin/python docs/ax/news-context/verification/v2/api-check.py` | 0 | api-command-r2.log / api-results.json: 6 시나리오 PASS |
| `node docs/ax/news-context/verification/v2/browser-check.mjs` | 0 | browser-command.log / browser-results.json: 10 시나리오 PASS |
| `node docs/ax/news-context/verification/v2/browser-extra.mjs` | 0 | browser-extra-command-r2.log / browser-extra-results.json: 6 시나리오 PASS |
| `/Users/woolee/benchmark/.venv/bin/python -m pytest tests/unit/test_news_analysis.py tests/integration/test_news_analysis.py -q` | 0 | pytest.log: 33 passed |
| `npm run test:unit -- --config /tmp/news-context-vitest.config.mjs` | 0 | vitest-targeted.log: 2 files, 11 passed. 설정 내용을 직접 읽어 이 전용 worktree alias와 src/**/news-analysis*.test.ts include 확인 |
| `npm run build` | 0 | build.log: vue-tsc 및 Vite build 성공 |
| `/Users/woolee/benchmark/.venv/bin/ruff check app/api/v1/news_analysis.py app/services/news_analysis.py app/services/news_analysis_vertex.py tests/unit/test_news_analysis.py tests/integration/test_news_analysis.py` | 0 | ruff.log: All checks passed |
| `./node_modules/.bin/vitest run src/components/news-analysis/news-analysis.test.ts src/components/news-analysis/news-analysis-annotations.test.ts` (기본 설정) | 1 | vitest-default-discovery.log: include=tests/unit/**/*.spec.ts이므로 신규 tests 미발견 |

## 수용 기준별 실제 관찰

- AC-1: 서명 JWT의 STREAMER/ADMIN 허용. 비로그인·유효하지 않은 토큰·만료·USER·비활성·삭제 계정 거부. 브라우저 직접 진입 USER/비활성 거부, ADMIN 허용.
- AC-2: 공백/빈 기사·20,001자·비HTTP/credentials/control/잘못된 port/URL초과 거부 후 모델 호출 0. 기사20,000자/URL2,048자 허용.
- AC-3/13: 전체명·한글·파생명 Bukayo Saka·Latin 악센트와 한국어 조사 연결. 번역 동명이인·파생/원명 후보 합집합 충돌은 ambiguous. 성/임의별칭/없는 대상 보류, 조작 근거·Latin 부분 단어는 링크 없음. 모델 임의 ID/path 필드가 추가된 schema는 안전하게 실패.
- AC-4/10: 실제 분석 POST→서버 DB 대조→원문 강조→기존 상세 GET. 본문 textContent 정확히 동일, HTML 요소/이벤트 미생성, 같은 이름 반복 1개만 강조. 실제 annotations 모듈에서 supplementary emoji UTF-16·강세 Latin·겹친 긴 이름 우선·부분단어 차단 확인. 원문 출처 링크 유지.
- AC-5/6: 실패 후 입력/출처 유지와 재시도, 중복 클릭 요청 1회, 입력 변경 후 늦은 분석 응답 미표시. 카드 로딩/실패/재시도 확인.
- AC-7: 브라우저 외부 요청 없음. 실제 timeout·사용자3회제한·동시2슬롯제한·안전한 오류 확인. 원문을 포함하지 않는 API 서버 로그 확인. URL은 provider에 전달하지 않는 코드와 테스트 확인.
- AC-8: SQLite runtime 쓰기 차단 상태에서 분석/상세 성공, writes=0. 기존 공개 news GET 결과를 분석 전후 비교해 동일. 팀/선수 기존 상세 GET 성공. 관리 화면 390px 링크는 헤더/탭과 겹치지 않고 실제 클릭 가능.
- AC-9: not_football/uncertain에는 mention/link 없음. 근거 빈칸/원문 외 근거는 uncertain, 잘못된 enum/schema는503. provider 지침이 association football, 미식축구·게임·명령문·혼합 글 구분을 지정함을 확인. 자연어 의미 품질을 stub 결과로 주장하지 않음.
- AC-11: hover/tap/focus 동일 카드, 이름→카드 이동 유지, ArrowDown→Tab으로 카드 상세 링크 접근, Escape 닫고 focus 복원, 본문 plain text 클릭 닫기. 390px 카드 bounds viewport 내부.
- AC-12: 실제 상세 GET에서 선수 최신2026 대회/팀별 행 표시, 2025 지표 숨김, 출전/골0와 도움NULL 구분. 팀 홈구장/최근0:1경기 표시. 동일 대상 GET1회 재사용, 실패 후 실제 GET 재시도, 느린팀A→빠른선수B→A응답에도 B 유지, polling 없음.

## 화면과 한계

- `desktop-hover.png`: 사용자 미리보기용 깨끗한 가상 글. 실제 로컬 분석 API와 합성 SQLite fixture 기록을 조회한 선수 카드. 운영 실데이터/실제 기사/모델 품질 성과로 해석하지 않는다.
- `desktop-player-hover.png`: 동일 실제 fixture 조회의 선수 대회/팀별 기록과 NULL/0 표시.
- `mobile-hover.png`, `admin-mobile.png`: 390px 카드와 관리 진입 링크. 이미지를 직접 열어 확인했다.
- 모델 stub 외부서비스 미사용. 운영자가 작성한 `live-smoke.json`(실제 Vertex+read-only DB 합성3건)을 읽었지만 독립 실행으로 재표기하지 않는다. 미식축구·게임·혼합 문맥의 실제 모델 일반 정확도는 별도 평가하지 않았다.
- SQLite는 Postgres와 다른 엔진이다. 팀 squad의 Postgres ARRAY_AGG SQL만 빈 결과로 대체했으며 카드 범위의 후보·선수기록·팀기본·최근경기 SQL은 실제 실행했다. refresh는 test-only token 발급, access JWT·활성 사용자·서버 권한은 실제 코드다. 관리 목록 GET만 모바일 레이아웃용 빈 stub이다.
- 기존 일반 페이지 전체·운영 DB·배포 환경 전체 회귀를 주장하지 않는다. 실제 공개 뉴스/팀/선수 GET 및 신규 흐름을 검증했다.
- 자동화 한계: 신규 프론트 테스트는 기본 Vitest include에 들어가지 않아 명시적 임시 config가 필요하다. 제품 행동 PASS와 구분해 운영자에게 후속 수정 요청을 전달했다.
- 초기 supplementary offset fixture에서 BMP `⚽`를2 UTF-16 단위로 잘못 기대하여1회 실패했다. supplementary `😀`로 fixture를 바로잡고 전부 재실행 PASS. 제품 파일 변경 없음. 초기 결과는 browser-extra-results-fixture-error.json에 보존했다.

머지/배포 승인은 하지 않는다.
