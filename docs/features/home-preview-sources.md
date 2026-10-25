# PRE-02 소스 확인 — 2026-10-25

## DB 실제 조회

공용 로컬 설정의 DB 연결값을 읽기만 하여 READ ONLY 트랜잭션으로 조회했다. 원본 설정·DB는 변경하지 않았다. 리그/시즌 12개 그룹, EPL 2026은 380경기 중 완료 75경기, UCL 2026은 158/68, UEL 2026은 168/78. 부상 테이블 0행. 이 결과는 API 미제공을 의미하지 않으며 기존 적재 경로가 없는 상태다. 전체 감사 출력은 로컬 out/home-preview/coverage.json, 원격 DB connection/비밀값은 기록하지 않았다.

## API-Football endpoint 우선 확인

사용자의 2026-10-25 추가 지시로 검색 보완보다 공식 API 엔드포인트를 먼저 조사했다. MCP 도구는 현재 세션에 연결되지 않아 공식 문서와 공식 API에 6개 읽기 요청을 보내 확인했다. MCP로 확인했다고 기록하지 않는다. provider 응답용 신규 ORM 모델은 만들지 않으며, 실제 캡처 dictionary를 기존 홈 JSON 계약에 정규화한다.

| 엔드포인트 | 용도/실제 결과 (fixture 1557444 Liverpool–Brighton) |
|---|---|
| GET /leagues?id=39&season=2026 | coverage.injuries/predictions/odds 모두 true. true가 모든 경기 자료를 보장하지는 않음 |
| GET /injuries?fixture=1557444 | 30행, player/team/fixture/league. Missing Fixture / Questionable 확인 |
| GET /odds/bets?id=1 | id=1, Match Winner |
| GET /odds/bookmakers | 33개 등록 업체 |
| GET /odds?fixture=1557444&bet=1 | fixture/date/league/season/update/bookmakers/bets/values, Home/Draw/Away decimal 문자열. 1페이지. update=2026-10-24T21:18:23Z |
| GET /predictions?fixture=1557444 | predictions/league/teams/comparison/h2h. API-Football 자체 알고리즘 전망이며 사이트 원문 의견/자체 AI와 구별. 출처를 API-Football로 명시한 외부 알고리즘 전망으로 게시하며 매체 원문 의견·자체 AI와 구별 |

일반 페이지 GET은 이 API들을 호출하지 않는다. 수집/생성 경로에서 fixture/킥오프/팀/시즌을 검증해 저장한 데이터만 공개한다. injury unknown type이나 불일치 응답은 error; 성공 빈 부상 응답은 ‘확인된 0명’이 아니라 missing. 배당은 Match Winner 1 / 정확히 Home·Draw·Away만, bookmaker 8/7/2 순으로 최대 3개, 제공 update가 6시간 이내일 때만 사용한다. API update와 실제 수집 시각을 모두 보존한다. 과거 업데이트/라이브·진출·승부차기 시장은 대체하지 않는다.

[공식 문서](https://www.api-football.com/documentation_v3), [공식 API 안내](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide). 문서상 부상은 약 4시간, 경기 전 배당은 약 3시간 업데이트이며 실제 이용 가능 범위는 리그/시즌/경기에 따라 달라진다. 서비스 수집 주기는 기존 6시간을 유지한다.

## 검색 보완

API에서 누락된 부상·배당은 검색으로도 찾는다. 공식 구단/대회 발표와 원문에서 확인되는 외부 전망·시장 자료만 사용한다. 현재 같은 실제 fixture에 다음 원문 후보를 확인했다: [Liverpool FC team news](https://www.liverpoolfc.com/news/liverpool-v-brighton-and-hove-albion-team-news-premier-league), [Sports Mole preview](https://www.sportsmole.co.uk/football/liverpool/title-race/preview/liverpool-vs-brighton-prediction-team-news-lineups_607574.html), [Betfair 경기](https://www.betfair.com/betting/football/english-premier-league/liverpool-v-brighton/e-36177487). 검색 후보 자체를 검증된 데이터로 취급하지 않는다. 다른 날짜 경기, 잘못된 팀, 사후 기사, 원문 접근 불가, 시장/시각 미확인은 unverified/missing으로 남긴다. 전체 기사/무제한 HTML은 저장하지 않는다.

API 자료가 모두 있으면 검색을 생략하고 analysis 모델을 1회 호출한다. 부족한 항목이 있고 검색 설정이 켜져 있으면 Google 검색 discovery → 서버 원문 검증 → analysis 순서로 최대 2회 호출한다. 검색 제안 HTML은 계약에 저장하고 FE의 script 없는 sandbox iframe으로 표시한다. [Google 검색 grounding 문서](https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/grounding-search-suggestions), [Structured output 문서](https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/control-generated-output)를 기준으로 MIME/schema와 서버 검증을 함께 적용한다. 메인 모델은 gemini-3.5-flash/global이며 AX 모델을 가져오지 않는다.

### 실제 실행 결과와 한계

- 격리 로컬 DB에서 Hull City–Brentford (1557442)의 DB 최근 경기·API 부상/배당/자체 전망 → Vertex JSON → 저장 → 공개 GET까지 성공했다. API 4회, analysis 모델 1회. 입력 5,546/출력 971/합계 6,517 토큰은 이 실행의 관측값이며 일반 비용 보장이 아니다.
- 별도 Google 검색 probe는 JSON 반환, 후보 8개, 검색 질의 4개와 제안 HTML을 확인했다. 같은 팀의 과거 2024년 자료가 섞였고 groundingChunks가 없어 검증된 원문 게시 성공으로 판정하지 않았다. 신뢰된 Google grounding redirect는 서버에서 최종 도메인·원문·날짜·인용을 다시 확인한다. 임의 URL을 믿지 않는다.
- 원문 접근은 등록 도메인, 공개 IP, HTTPS/redirect 검사, 페이지당 512KB·12초, 최대 4페이지·50초로 제한한다. 7일 이내·킥오프 전 발표와 동일 경기, 원문 인용을 확인한다. 검색 후보는 최대 8개다. 원문/상충 보도의 실제 coverage 인수 검증은 남아 있다.
- 검색을 켜지 않아도 API 우선 경로는 동작한다. 부상 빈 배열을 무부상으로 바꾸지 않는다. API 장애는 error/upstream_failed로 남기며 누락 자료와 구별한다.

### 후속 실제 매체 원문 검증 성공

검색은 이제 API 전망이 있어도 수행한다. 질의를 기사 우선으로 좁힌 실제 새 슬롯 실행에서 검색 질의 2개로 [Sports Mole의 Hull City–Brentford 프리뷰](https://www.sportsmole.co.uk/football/hull-city/preview/hull-city-vs-brentford-prediction-team-news-lineups_607564.html) 원문을 확인했다. 게시 시각 2026-10-23T17:23:24+01:00, 확인 시각 2026-10-25T03:49:32Z, 원문 예상 1–1을 경기·날짜·인용과 함께 검증해 API 전망에 추가 저장했다. 앞 절의 ‘실원문 성공 없음’은 이전 probe 결과이며 전체 매체/추천 유형 coverage를 의미하지 않는다. 정책은 기본 검색+분석 2회, API 부상·배당은 부족할 때만 검색 보완이다.
