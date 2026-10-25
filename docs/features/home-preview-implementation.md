# 메인 프리뷰 구현·검증 — 2026-10-25

현재 경로 `/Users/woolee/benchmark-main`, 브랜치 `feat/home-preview-json`. 관리 공용 checkout과 AX worktree의 HEAD·index·작업 파일을 변경하지 않았다. 메인 전용 소스/문서와 공용 파일의 메인 연결 부분만 변경했다. 과거 목업은 개발 전용 `/home/mock`에 보존하고 실제 `/`는 저장 API를 읽는다.

## 구현된 흐름

1. DB의 활성 리그/수집 target·최신 2개 알려진 시즌·확정 추천 정책으로 대상을 고른다. 진행 중 우선, 추천 목록에 4개 표시 제한은 없다.
2. 생성은 추천 자격이 있는 예정 경기의 킥오프 전 24시간에만 한다. 최근 5경기는 DB 완료 경기, 부상·배당·외부 알고리즘 전망은 검증한 API-Football 응답을 우선한다.
3. 외부 기사·칼럼 검색은 API 자체 예측이 있어도 수행하고, 부상·배당은 API에서 부족한 자료만 원문 검증 후 보완한다. AI는 근거를 참조하는 analysis JSON만 작성하며 사실·배당을 다시 생성하지 않는다. MIME/response schema, JSON Schema/Pydantic의 필드·근거·시간·경기 검증을 통과해야 한다.
4. 불변 snapshot/version과 publication pointer를 원자 저장한다. 실패·누락 확대·킥오프 통과 시 이전 유효본과 원래 시각을 보존한다.
5. 공개 GET `/api/v1/home/recommendations`, `/api/v1/home/fixtures/{external_id}/prematch`는 DB만 읽는다. 실제 메인은 strict Zod 검증, 선택 요청 취소/identity 검증, 누락 우선 안내·출처·시각을 적용한다. 일반 페이지 polling·실시간 점수·카운트다운은 없다.

## 실행 정책과 의존성

- `HOME_PREVIEW_ENABLED=false`, `HOME_PREVIEW_SEARCH_ENABLED=true`가 기본이다. 자동 생성은 여전히 OFF이며 운영 설정은 변경하지 않았다. 공통 수집 실행의 성공·commit 후 후처리가 enable일 때만 실행되며 부분 수집 실패에는 실행하지 않는다. 새 생성 HTTP endpoint/cron은 만들지 않았다.
- 기존 커밋된 `worker_runs.py`의 정기/관리 수동 공통 경로를 기준으로 연결했다. 관리 세션의 새 인증·수집 실행 변경은 가져오지 않았으므로 합치기 전 해당 경로를 다시 대조해야 한다. 공개 조회는 인증/Redis 의존성이 없다.
- 메인 전용 모델 `gemini-3.5-flash`, location `global`. 기존 Vertex 프로젝트/인증을 사용하되 AX 모델 선택을 자동 적용하지 않는다. JSON 최대 출력 8192, thinking LOW, model 요청 timeout 60초. 생성 동시성 1.
- 검색을 포함한 기본 생성은 discovery+analysis 2회다. 검색 설정을 명시적으로 끄면 analysis 1회다. 검색 질의 수는 provider 결과를 usage에 기록하며 모델 호출 1회를 검색 질의 1회로 간주하지 않는다. API 호출 수는 client 실제 요청 카운터를 기록한다.
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

실제 생성 fixture의 상태/현재 시각에 따라 이미 처리한 슬롯·24시간 밖·킥오프 이후에는 생성하지 않는다. 로컬 샘플의 실패 이력을 지우거나 강제로 호출 제한을 우회하지 않았다. 기본 선택 1557444는 후속 12시 슬롯에서 LLM 선정 이유를 포함해 정상 생성됐고, 1557445는 일부 자료 저장본, 1557442는 API 전망까지 포함한 정상 저장본이다. L3는 명시적 config에서만 켜지며 준비된 로컬 DB fixture를 요구한다. 일반 E2E는 준비되지 않은 실제 DB 테스트를 실행하지 않는다.

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

### 주요 결장자·외부 기사·팀별 배당 후속 — 2026-10-25

- 부상 응답 30행/실선수 15명 중복을 확인했다. 경기별 팀·선수 ID로 중복 제거하고, ID 없는 과거 저장본은 같은 팀의 정확한 이름으로만 제거한다. 상태가 충돌하면 확정 결장으로 단정하지 않고 출전 상태 확인 필요로 표시하며 주요 선수 후보에서 제외한다.
- 최근 완료 최대 10경기의 DB 선발·출전 기록, 해당 리그에서 알려진 최신 2개 시즌의 팀별 선수 출전 수·시간을 조립한다. fixture/detail/season stat의 관찰 시각과 킥오프 cutoff를 확인한다. 라인업은 선발 11명이 확인된 표본만 센다. 없는 기록은 NULL이며 0으로 채우지 않는다.
- 후보 기준은 최근 선발 3회 이상, 확인된 최근 출전 합계 180분 이상, 또는 명시된 시즌 출전 5회/450분 이상 중 하나다. 과거 시즌 근거를 써도 연도를 명시한다. 모델 유명세/사전 지식만으로 후보가 될 수 없다.
- 기존 analysis 호출에서 key_absences를 순위대로 최대 팀당 2명/합계 4명 선택한다. 알려진 적격 선수 ID·팀·부상/DB 근거를 검증한다. 선정 근거 문장은 DB에서 조립한 selection_reason을 그대로 사용하도록 검증해 포지션이나 시즌/최근 기록이 모델 문장 안에서 새로 만들어지지 않게 한다. 이전 생성본도 조회 시 검증된 출전 수치 문장으로 표시하며 원본은 보존한다.
- 기본 주요 선수 요약과 닫힌 ‘전체 부상·출전 정보 N명’을 분리했다. 과거 저장본에 선별 정보가 없으면 전체 명단은 볼 수 있지만 주요 선수를 임의로 채우지 않는다.
- API 알고리즘 전망을 보존하면서 별개 매체 원문을 추가한다. 출판사별 한 건, 전체 최대 4개 전망(기존 API 포함), 후보 8개·원문 fetch 시도 4개·총 50초 탐색, 원문별 12초/512KB 제한. 점수 없는 칼럼 의견도 동일 경기·발표 시각·20단어 이내 원문 인용 검증 후 그대로 발췌한다. 점수는 원문에 명시된 경우만 사용한다. 검색 질의는 3개 이하로 지시하며 provider가 6개를 넘기면 게시에 사용하지 않는다. 추가 자동 재검색은 없다.
- 배당 표시를 fixture.home.name + ‘승’ / 무승부 / fixture.away.name + ‘승’으로 바꿨다. 경기 선택 전환의 라벨·가격 대응을 E2E로 검증한다.
- 실제 새 슬롯의 1557442 생성은 API 4회 + 검색 1회 + 분석 1회, Google 검색 질의 2개, 검증된 Sports Mole 전망 1건이었다. 전체 결장 12명 중 주요 3명(팀별 1/2명) 선별과 외부 원문 URL의 DB 저장·공개 GET을 확인했다. 원본 DB는 읽기 전용이며 공개 선수/출전 기록만 격리 로컬 DB에 준비했다.
- 기본 정책에서 경기당 4개 슬롯은 모델 호출 최대 8회(검색 4+분석 4)다. 명시적 실패 재시도는 별도 기존 상한을 따른다. 부상 선별 때문에 세 번째 모델 호출을 추가하지 않는다. 운영 활성화·배포는 하지 않았다.

최종 후속 검증: BE 89 PASS, FE unit 24 PASS, E2E 17 PASS, 실제 생성본을 사용하는 로컬 DB L3 1 PASS, production build와 Python lint PASS. 새 생성 버전은 home-preview-1.1-prompt-4이며 근거 문장 고정 정책을 구별한다.

### 선수 관전 포인트·2×2 사진 카드·접힌 기록 — 2026-10-25

최신 요구/계약/실제 검증은 [home-preview-players.md](home-preview-players.md)를 따른다. 기존 ‘유명세를 사용하지 않음’은 사용자 후속 지시로 바뀌었다. 인지도는 알려진 부상 후보의 순위 보조에만 사용하며 사실/숫자는 근거에서만 나온다. 선수별 관전 포인트는 독립 섹션에 한글 이름·우측 사진과 기본 접힌 선정 이유/기록을 제공한다. 부상/징계 카드는 홈·원정 고정 2×2, 팀당 최대 2명을 유지한다. 공개 GET의 DB 전용·6시간 정책, 기존 검색+분석 2회는 유지한다. PRE-12는 완료로 바꾸지 않는다.

선수 선정 이유 후속 확정: 사용자 요청으로 기존 고정 설명 대신 LLM 응답의 선수별 reason을 저장·표시한다. 기록 수치는 DB에서 조립하고 상세에서 분리한다. 과거 저장본은 reason 없이 호환하며 고정 문장을 모델 결과로 가장하지 않는다. 1557444 새 슬롯 실제 생성은 API4/검색1/분석1, player_watchpoints 2명과 선수별 reason/연속 기록을 확인했다. 최신 검증은 BE100/FE27/E2E17/L3 4/build PASS이며 세부는 home-preview-players.md를 따른다.

최신 후속: 선정 이유를 확인된 시즌·최근 표본·연속 기록·팀 폼을 연결하는 3~5문장으로 확장했다. 숫자와 항목별 표본 수를 분리한다. 로컬 교정 검증의 별도 개발 모델 1회는 snapshot metadata에 명시하며 worker 슬롯/기존 버전을 변경하지 않았다. 운영 자동 생성 호출 수와 OFF 설정은 유지한다. 세부·검증은 home-preview-players.md의 복합 이유 절을 따른다.
