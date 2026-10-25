# 메인 프리뷰 구현·검증 — 2026-10-25

현재 경로 `/Users/woolee/benchmark-main`, 브랜치 `feat/home-preview-json`. 관리 공용 checkout과 AX worktree의 HEAD·index·작업 파일을 변경하지 않았다. 메인 전용 소스/문서와 공용 파일의 메인 연결 부분만 변경했다. 과거 목업은 개발 전용 `/home/mock`에 보존하고 실제 `/`는 저장 API를 읽는다.

## 구현된 흐름

1. DB의 활성 리그/수집 target·최신 2개 알려진 시즌·확정 추천 정책으로 대상을 고른다. 진행 중 우선, 추천 목록에 4개 표시 제한은 없다.
2. 생성은 추천 자격이 있는 예정 경기의 킥오프 전 24시간에만 한다. 최근 5경기는 DB 완료 경기, 부상·배당·외부 알고리즘 전망은 검증한 API-Football 응답을 우선한다.
3. 선택 검색은 API에서 부족한 자료만 원문 검증 후 보완한다. AI는 근거를 참조하는 analysis JSON만 작성하며 사실·배당을 다시 생성하지 않는다. MIME/response schema, JSON Schema/Pydantic의 필드·근거·시간·경기 검증을 통과해야 한다.
4. 불변 snapshot/version과 publication pointer를 원자 저장한다. 실패·누락 확대·킥오프 통과 시 이전 유효본과 원래 시각을 보존한다.
5. 공개 GET `/api/v1/home/recommendations`, `/api/v1/home/fixtures/{external_id}/prematch`는 DB만 읽는다. 실제 메인은 strict Zod 검증, 선택 요청 취소/identity 검증, 누락 우선 안내·출처·시각을 적용한다. 일반 페이지 polling·실시간 점수·카운트다운은 없다.

## 실행 정책과 의존성

- `HOME_PREVIEW_ENABLED=false`, `HOME_PREVIEW_SEARCH_ENABLED=false`가 기본이다. 공통 수집 실행의 성공·commit 후 후처리가 enable일 때만 실행되며 부분 수집 실패에는 실행하지 않는다. 새 생성 HTTP endpoint/cron은 만들지 않았다.
- 기존 커밋된 `worker_runs.py`의 정기/관리 수동 공통 경로를 기준으로 연결했다. 관리 세션의 새 인증·수집 실행 변경은 가져오지 않았으므로 합치기 전 해당 경로를 다시 대조해야 한다. 공개 조회는 인증/Redis 의존성이 없다.
- 메인 전용 모델 `gemini-3.5-flash`, location `global`. 기존 Vertex 프로젝트/인증을 사용하되 AX 모델 선택을 자동 적용하지 않는다. JSON 최대 출력 8192, thinking LOW, model 요청 timeout 60초. 생성 동시성 1.
- API 자료가 충분하면 모델 1회, 검색이 필요하면 discovery+analysis 2회. 검색 질의 수는 provider 결과를 usage에 기록하며 모델 호출 1회를 검색 질의 1회로 간주하지 않는다. API 호출 수는 client 실제 요청 카운터를 기록한다.
- 경기당 최대 4개 KST 00/06/12/18 슬롯(실패 포함). 같은 실패 슬롯의 명시적 재시도는 추가 1회까지, 자동 AI 재시도는 없다. 슬롯의 누적 API/model/search 횟수를 보존한다. 사이클 기본 처리 상한 24개, 나머지는 deferred IDs로 보고한다. 공개 추천 목록을 자르지 않는다.
- 기존 API-Football client의 semaphore/retry를 재사용하고 이 워커는 순차·60req/min으로 동작한다. 수집 완료 뒤 실행한다. Redis 키는 사용하지 않는다.

## 로컬 환경·실행

메인 FE 5191, Playwright 전용 FE 5192, API 8017, DB 55441. DB 컨테이너는 `benchmark-main-preview-db`, 타 세션 DB 55439와 분리한다. 예약 prefix는 `local:home-preview:test:`다. Supabase 로컬 포트는 config.toml에 별도 지정했다. API는 autoreload 없이 실행하고 출력은 `out/home-preview/api-server.log`에 저장한다.

아래 명령은 메인 worktree에서 실행한다. `HOME_PREVIEW_TEST_DB_URL`은 격리 로컬 DB 연결값으로만 지정한다. 운영 연결을 넣지 않는다. `.env.home-preview.local`은 필요한 provider 설정을 가진 별도 로컬 파일이며 저장소에 추가하지 않는다.

```sh
# DB 조회/대상 산정만 수행: 외부 API/생성/DB 쓰기 없음
.venv/bin/python -m app.workers.home_preview --database-url "$HOME_PREVIEW_TEST_DB_URL" --env-file .env.home-preview.local

# 명시적 로컬 생성: 실제 provider 호출 및 로컬 DB 저장
.venv/bin/python -m app.workers.home_preview --database-url "$HOME_PREVIEW_TEST_DB_URL" --env-file .env.home-preview.local --fixture-id 1557442 --execute

# 보관 정리 미리보기. 실제 삭제는 별도 --execute일 때만 수행
.venv/bin/python -m app.workers.home_preview --database-url "$HOME_PREVIEW_TEST_DB_URL" --env-file .env.home-preview.local --prune

# FE 단위/화면 테스트와 실제 로컬 서버 L3
cd frontend
npm run test:unit -- tests/unit/home-preview
npm run build
./node_modules/.bin/playwright test --config playwright.home-preview.config.ts
./node_modules/.bin/playwright test --config playwright.home-preview-l3.config.ts
```

실제 생성 fixture의 상태/현재 시각에 따라 이미 처리한 슬롯·24시간 밖·킥오프 이후에는 생성하지 않는다. 로컬 샘플의 실패 이력을 지우거나 강제로 호출 제한을 우회하지 않았다. 기본 선택 1557444는 실패 상태 예시이고, 1557445는 일부 자료 저장본, 1557442는 API 전망까지 포함한 정상 저장본이다. L3는 명시적 config에서만 켜지며 준비된 로컬 DB fixture를 요구한다. 일반 E2E는 준비되지 않은 실제 DB 테스트를 실행하지 않는다.

## 확인한 결과

- BE 77 PASS: 공통 계약·우선순위·실제 API capture 매핑·Vertex 실패·원문 검증·공통 수집 후처리·격리 Postgres·기존 홈/관리 워커/스케줄/방송 AI 회귀. 통합 테스트 skip 없음. Starlette/AnyIO deprecation warning 1건.
- FE unit 24 PASS, Playwright 16 PASS, production build PASS. 실제 API/로컬 DB L3 1 PASS. 늦은 응답 경합·mock 공개 거절·모바일 표 너비까지 확인했다.
- Supabase CLI 신규 migration은 로컬 55441에만 적용했다. 테스트마다 별도 schema에서 FK/unique·원자 전환/rollback·최대 슬롯·재시도 누적 호출량·보관 정리/fixture cascade를 확인했다.
- 실제 1557442 생성: API 4회 + AI 1회, 입력 5546/출력 971/합계 6517 토큰, validated ready JSON 저장/조회 성공. 1557445 저장본을 실제 메인에 표시한 데스크톱/모바일 L3를 확인했다.
- Python lint와 git diff 공백 검사 통과. 개발 환경은 Python 3.14, FastAPI 0.136.1/Starlette 1.0.0이며 다른 세션 venv는 변경하지 않았다. 기존 홈 endpoint 등록 테스트는 public OpenAPI로 검사하도록 고쳤다.

## 남은 인수

실제 웹 원문·상충 보도 coverage, 전체 추천 유형의 실자료 인수, 독립 spec/code review, 관리 세션의 최신 수집 공통 경로 통합 대조가 남아 있다. PRE-12는 완료가 아니다. 운영 DB migration·자동 생성 활성화·원격 push·merge·배포·서비스 재시작은 수행하지 않았다.

### 부상 선수 한글 표시 후속 수정

API 영문 이름을 그대로 노출하던 누락을 수정했다. 신규 수집에 선수 ID를 보존하고 DB 번역은 공개 조회에서 최신 값으로 적용한다. 기존 저장본의 고유한 정확 이름도 안전하게 연결한다. 로컬 표시 검증에 필요한 공개 선수·번역만 원본 DB READ ONLY 조회 후 격리 DB로 복사했다(선수 20명/한글 번역 20건). 원본 DB·불변 프리뷰는 수정하지 않았고 새 AI 호출은 없다. 약칭으로만 저장된 과거 행은 다음 수집에서 ID를 확보하기 전까지 영문일 수 있다.
