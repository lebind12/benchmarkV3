# benchmark — 축구 정보 사이트 (방송용 페이지 포함)

## 1. 프로젝트 개요

축구 정보를 제공하는 웹사이트. 일부 페이지는 **방송용** 으로 디자인되어 방송 소프트웨어가 크로마키로 합성해 송출하는 용도로 사용된다.
데이터 소스는 API-Football(Ultra plan), DB는 Supabase, 캐시/세션 보조는 Upstash, 백엔드는 FastAPI + SQLAlchemy.

## 2. 대상 리그 (초기 5개, STREAMER / ADMIN 이 동적 추가/제외 가능)

초기 시드 리그 (모두 `is_active=true`):
- Premier League (external_id 39)
- UEFA Champions League (external_id 2)
- UEFA Europa League (external_id 3)
- Carabao Cup / League Cup (external_id 48)
- FA Cup (external_id 45)

운영 중 인증된 STREAMER / ADMIN 이 관리 endpoint 로 추가/제외 가능 (예: 월드컵, 유로). 수집 대상 설정은 전체 서비스 공통이다. daily-sync 는 최신 2시즌 안의 활성 리그·시즌 대상만 처리해야 하며, 대상 활성 상태와 `league.is_active` 는 일관되게 관리한다. 현재 코드의 차이와 정합화 제안은 `plan.md` 참조.

## 3. 데이터 정책

- **보관 범위**: 최신 2시즌 (현재 시즌 + 직전 시즌)
- **컵 대회 fixture**: 시즌 전체. 추첨 미정 라운드는 빈 슬롯으로 두고 6시간 sync 시 채움
- **외부 ID upsert**: API-Football 의 `fixture_id`, `team_id`, `player_id`, `league_id` 를 unique key 로 upsert

## 4. 워커 (4종)

워커는 외부 데이터 → DB 적재 전담. API endpoint 와 분리된 독립 기능.

| 워커 | 주기 | 책임 |
|---|---|---|
| `daily-sync` | KST 00/06/12/18 (4회/일) | 활성 league (is_active=true) 의 fixtures / 상세 / team / player / coach / standings / transfers / injuries 적재 |
| `translation-filler` | 1분 간격 (큐 비면 종료) | 번역 테이블 (`*_translation`) 의 `name_ko IS NULL` row → OpenAI 음역 |
| `news-fetcher` | 1시간 간격 | EPL 관련 외신 RSS 폴링 → `news_article` 적재 (제목 + 요약 + URL, EPL 팀 키워드 필터) |
| `news-translator` | 1분 간격 (큐 비면 종료) | `news_article.title_ko IS NULL` row → OpenAI 번역 (의역) |

방송용 페이지의 라이브 데이터는 **워커가 아니라 API endpoint + 캐시** 로 처리 (스트리머가 활용할 때만). 워커 영역과 분리.

운영 원칙:
- **API-Football rate limit (Ultra plan)**: 450 req/min ≈ 7.5 RPS. 동시 호출 semaphore 상한 = **6** (안전 마진 포함)
- **재시도**: API 실패는 지수 백오프, 한 사이클 내 최대 3회. 그 이상은 다음 주기로 이월
- **멱등성**: 외부 ID 기반 upsert. 부분 적재 후 재시작 안전
- **단일 인스턴스 전제**: Koyeb 단일 service 이므로 분산 락 불필요. APScheduler in-process 단일 스케줄러로 충분
- **수동 트리거**: 수집 관리·실행은 인증된 STREAMER / ADMIN 에게 제공하고 서버에서도 권한을 검증한다. 다른 워커의 수동 endpoint 유무와 실행 연결은 실제 코드로 확인하며, 이번 범위 밖 워커 API를 선제 구현하지 않는다.

## 5. 번역 테이블

영문/원본 데이터는 entity 테이블 (`league`, `team`, `player`, `coach`) 에서 관리. 번역 테이블은 **한글 표기만** 별도로 관리한다.

### 5.1 테이블 구성 (4개 분리)

| 테이블 | 컬럼 (개념) |
|---|---|
| `league_translation` | `league_id` (FK), `name_ko`, `short_name_ko`, `updated_at` |
| `team_translation` | `team_id` (FK), `name_ko`, `short_name_ko`, `updated_at` |
| `player_translation` | `player_id` (FK), `name_ko`, `short_name_ko`, `updated_at` |
| `coach_translation` | `coach_id` (FK), `name_ko`, `short_name_ko`, `updated_at` |

- 분리 이유: 각 entity 별 FK 로 참조 무결성 확보, ORM 모델 명확
- `name_ko` / `short_name_ko` 가 NULL 인 동안 API 응답은 entity 테이블의 영문 이름 그대로 fallback
- 자동번역 결과를 노출하되, STREAMER / ADMIN 의 리그·팀·선수·감독 번역 검색·수정·번역/미번역 상태·수정 이력·동시 수정 충돌 처리를 이번 개발 범위에 포함한다. 수정은 전체 서비스에 공통 적용되고 사람이 수정한 값은 이후 수집·자동번역·import에서 보호한다. 뉴스 번역 편집·AI 의심 표기 추천은 필수 범위가 아니다.

### 5.2 적재 책임 분담

| 동작 | 주체 | 방식 |
|---|---|---|
| entity 테이블 (league/team/player/coach) 적재 | `daily-sync` | upsert (전체 덮어쓰기) |
| 번역 테이블에 row 보장 (새 entity 발견 시) | `daily-sync` | INSERT (외부 ID unique 충돌 시 무시). 한글 컬럼은 NULL. **기존 row 절대 갱신 안 함** |
| 번역 테이블의 한글 컬럼 채움 | `translation-filler` | `name_ko IS NULL` row 탐지 → OpenAI 호출 → UPDATE |

이 분담으로 daily-sync 의 "전체 덮어쓰기" 가 번역 테이블의 기존 한글값에 영향을 주지 않는다.

### 5.3 시드 데이터

| 대상 | 출처 | 방식 |
|---|---|---|
| **player_translation** | 이전 프로젝트 산출물 `_Player__202605131748.csv` (6,422 row) | gpt-3.5-turbo few-shot 자동번역 + 주요 선수 수동 수정 |
| **team_translation** | 이 세션에서 사용자가 5 리그 대상 팀 번역 진행 | 시드 CSV 생성 |
| **league_translation** | 이 세션에서 사용자가 5 리그 한글표기 결정 | 시드 CSV 생성 |
| **coach_translation** | `fixture_detail.lineups` 의 coach payload 에서 row 생성 | 운영 중 `translation-filler` 음역 |

백필 작업 중 대량으로 적재된 팀/선수 번역은 `translation-filler` 자동 음역에 맡기지 않고, 직접 조회해 축구 커뮤니티와 인터넷 기사에서 자주 쓰이는 한국어 호칭을 시드 CSV에 반영한 뒤 import 한다.

### 5.4 운영 중 자동번역 (`translation-filler`)

- 대상: 시드에 없는 신규 entity (신규 선수, 신규 컵대회 참가팀, 신규 감독 등) — daily-sync 가 만든 NULL row
- 모델: **`gpt-3.5-turbo` + few-shot prompting** (음역 중심, web_search 사용 안 함)
   - 이유: 시드 CSV 와 같은 방식이라 표기 일관성 유지, 비용이 web_search 방식 대비 ~1/100
   - 한계: 한국 매체 통용 표기 검증 불가. 마이너 entity 는 단순 음역. MVP 허용 범위
- few-shot 예시: 시드 CSV 에서 무작위 추출하여 일관성 강화
- 1분 폴링, `name_ko IS NULL` row 가 있을 때만 호출 (없으면 즉시 종료)
- 비용: 신규 entity 등장 빈도 낮아 월 부담 무시 가능

## 6. 데이터 신선도 SLA

| 페이지 종류 | 데이터 출처 | 신선도 | 클라이언트 polling | 라이브 표시 |
|---|---|---|---|---|
| **모든 일반 사용자 페이지** (홈 / 경기 / 매치 디테일 / 순위 / 팀 / 선수 / 스탯 / 뉴스 / ...) | **DB 만** | 6h | **불가** | 카운트다운 / 라이브 score 표시 X |
| **방송용 페이지** (`/broadcast/...`, STREAMER role 만) | API endpoint + Upstash 캐시 | 실시간 | 허용 (10초) | 라이브 score / events 표시 |
| 번역명 | best-effort | - | - | NULL 시 영문 fallback |

원칙:
- API-Football 직접 호출은 **방송용 페이지 + 워커 (daily-sync 등)** 만 허용
- 자연어 검색은 **로그인 필수**이며 서버에서 활성 USER / STREAMER / ADMIN을 검증한다. 기존 API-Football 기반 DB 저장본을 조회하고 축구 지표·이름·별칭 사전을 실제 DB 데이터에 연결한다. 검색용 LLM은 Vertex AI `gemini-4-argon`으로 지정한다. 결정과 실제 구현 상태는 구분하며 상세는 `docs/decisions/2026-10-25-natural-language-search.md`, 실행 계획은 `docs/ax/natural-language-search/plan.md`를 따른다.
- 일반 사용자 페이지가 라이브 매치를 보고 있어도 최대 6h stale 가능 (정책상 허용)
- 메인의 오늘 추천 경기 프리뷰는 부상·최근 5경기·관전 포인트·AI 경기 예측·외부 사이트 전망·경기 전 배당을 포함하는 개발 범위다(2026-10-24 후속 결정). 외부 근거와 생성본을 수집/생성 경로에서 DB에 저장하고 일반 페이지는 저장본만 조회한다. 기존 6시간 갱신 정책은 유지한다. AI 예측은 예측으로 구분하며 사실·통계·부상·외부 사이트 의견·배당을 창작하지 않는다. 출처·자료 기준 시각·생성 시각과 누락 상태를 보존한다. 상세 및 미정 추천 순서는 `plan.md` §5 참조.
- 라이브 정보가 절실히 필요한 사용자 = 방송용 페이지로 유도 (스트리머 전용)
- 메인의 오늘 추천 경기 프리뷰는 부상·최근 5경기·관전 포인트·AI 경기 예측·외부 사이트 전망·경기 전 배당을 포함하는 개발 범위다(2026-10-24 후속 결정). 외부 근거와 생성본을 수집/생성 경로에서 DB에 저장하고 일반 페이지는 저장본만 조회한다. 기존 6시간 갱신 정책은 유지한다. AI 예측은 예측으로 구분하며 사실·통계·부상·외부 사이트 의견·배당을 창작하지 않는다. 출처·자료 기준 시각·생성 시각과 누락 상태를 보존한다. 상세 및 미정 추천 순서는 `plan.md` §5 참조.

## 7. 인증/권한

### Role (DB에 저장)
- `USER` — 일반 사이트 열람
- `STREAMER` — 방송용 페이지 및 전체 서비스 공통 수집 관리·번역 검수 사용 가능
- `ADMIN` — 운영/검수 권한

### 세션
- JWT (access) — stateless, 짧은 만료
- Refresh token rotation/blacklist 는 **Upstash** 에 저장
- Upstash 는 MVP 에서 **refresh token rotation/blacklist 용도로만** 사용. 응답 캐시 확장은 post-MVP
- 같은 Upstash Redis 인스턴스를 local / production 에서 함께 쓰는 경우에도 **키 prefix 로 환경을 반드시 분리**한다.
  - local 개발: `UPSTASH_REDIS_KEY_PREFIX=local:`
  - production: `UPSTASH_REDIS_KEY_PREFIX=prod:`
  - 방송용 캐시/모멘텀/세션 보조 키는 모두 이 prefix 를 통과해야 하며, prefix 없는 키를 새로 만들지 않는다.

### 방송용 페이지 인증
- 방송용 페이지는 일반 웹사이트의 한 라우트로 제공되며, 방송 SW 가 해당 페이지를 캡처해 크로마키 합성한다 (OBS 브라우저 소스 임베드 아님)
- 따라서 인증은 일반 웹앱과 동일: STREAMER role JWT
- 방송용 페이지 배경 크로마키 키컬러: **OBS 기본 녹색** (`#00B140`, chroma green)
- 방송 UI 내부에는 `#00B140` 또는 유사 크로마키 색상을 쓰지 않는다.
- 투명도는 크로마키 배경이 컴포넌트 안으로 비쳐 들어오는 경우만 금지한다. 불투명한 카드/이미지/에셋 위에 얹는 광택, 그림자, 내부 하이라이트 용도의 반투명 레이어는 허용한다.

## 8. 개발 프로세스

**프론트엔드 follow 방식** — 백엔드는 프론트가 정의한 엔드포인트 목록을 받아 구현한다.

1. 프론트엔드가 화면/기능을 mockup 으로 구현
2. mockup 데이터를 가져올 **endpoint 목록 작성** (path, method, 응답 shape 초안)
3. 백엔드는 그 목록을 기준으로:
   - 요구 데이터 정의
   - 필요한 DB 컬럼/관계 점검 (없으면 추가)
   - API 구현
4. 프론트가 mock 을 실 endpoint 로 교체

이 순서를 거꾸로 가지 않는다. 백엔드가 "필요할 것 같은" API 를 선제 구현하지 않는다.

## 9. 기술 스택

| 영역 | 도구 |
|---|---|
| 백엔드 프레임워크 | FastAPI |
| ORM | SQLAlchemy |
| DB | Supabase (Postgres) — supabase CLI 로 마이그레이션/조작 |
| 캐시/세션 보조 | Upstash (Redis) — upstash CLI |
| 외부 데이터 | API-Football (Ultra plan), API-Football MCP 활용 |
| 자동번역 | OpenAI API |

## 10. CLI / MCP 활용 규칙

- DB 스키마 변경: supabase CLI 마이그레이션 파일로 관리. SQLAlchemy 모델과 마이그레이션은 항상 동기 상태 유지
- API-Football 응답 구조 확인: 코드 작성 전 **API-Football MCP** 로 실응답 조회 후 모델 정의
- Upstash 키 설계: 코드 푸시 전 upstash CLI 로 키 패턴/TTL 검증

## 11. 이미지 에셋 관리

- 프로젝트 최상위 `assets/` 는 원본/레퍼런스 이미지 에셋의 기준 위치다.
- Codex / ChatGPT 이미지 생성 도구로 만든 프로젝트용 이미지 에셋은 항상 `assets/generated/` 아래에 저장한다.
- 월드컵 중계화면 하단 바 에셋은 `assets/generated/world-cup/bottom-bar/` 아래에 저장한다.
- 웹에서 다운로드한 디자인 참고용/사용 승인된 비트맵 에셋도 앱에서 사용할 목적이면 `assets/generated/` 아래에 기능별 하위 폴더를 만들어 저장한다.
- 프론트엔드 번들에서 직접 import 해야 하는 경우에만 `frontend/src/assets/` 아래에 파생본을 복사하거나 별도 관리한다.
- 기존 코드 기반 SVG 아이콘과 수동 관리 에셋은 `frontend/src/assets/broadcast/` 등 기존 디렉터리를 유지할 수 있다.
- 공식 로고, 팀 엠블럼, 국기처럼 정확성이 필요한 에셋은 임의 생성하지 않는다. API-Football 응답, 공식 출처, 또는 사용 허가가 분명한 소스를 우선한다.

## 12. 향후(post-MVP) 검토 항목

- Upstash 를 API-Football / OpenAI 응답 캐시로 확장 (MVP 외)
- AI 번역 의심 표기 추천 (선택 후보). 직접 번역 검수·수정 UI는 이번 개발 범위로 이동
- 번역 정밀도 업그레이드: `gpt-4.1` + Responses API `web_search` + `filters.allowed_domains`(ko.wikipedia.org, 한국 스포츠 미디어). 음역 한계가 운영상 문제될 때 도입. PoC 스크립트는 `scripts/translate_poc.py` 에 보존
- 방송용 라이브 endpoint 의 캐시 TTL 튜닝 (방송용 페이지 UX 보고 결정)
- API-Football semaphore 상한 튜닝 (현재 6, 실측 후 조정)
- 다중 인스턴스 스케일 도입 시 워커 분산 락 (Upstash `SET NX`) 추가 필요

## 13. Harness 운영

- 계획 정본은 `Plans.md`, 도메인/규칙 정본은 본 파일이다. 운영 정본은 `docs/spec/agentic-workflow.md`, 최신 결정은 `docs/decisions/2026-10-28-external-harness-control.md`다. 이 결정은 이전 운영자 중심 work-flow의 실행·완료 절차를 대체한다.
- 새 실행 진입점은 `scripts/harness-run.sh`, 구현은 `scripts/harness_runtime/`, 사용 안내는 `docs/harness/external-control.md`다. 원문·계약·실행 상태·증거는 개발 workspace 밖의 SQLite/파일에 보존한다. 이전 `.codex/state/{work-flow,feature-flow,endpoint-flow}/`와 CLI·보고서는 조회용 이력이며 새 작업의 완료를 대신하지 않는다.
- 현재 루트 대화가 운영자다. 별도 운영 모델을 고정하거나 관리자 하위 에이전트를 필수 생성하지 않는다. 사용자와 요구사항·기획·기술 선택·작업 분할을 진행하고 결과를 설명한다. 실행기는 별도 개발/검토 세션과 실제 검증 명령을 실행하고 필수 단계·재작업·완료 상태를 관리한다.
- 새 독립 개발 요청은 **제품 파일 수정·개발 실행 전에** QUICK/FULL을 한 번 묻고 실제 선택을 받는다. 이미 명시된 선택과 같은 작업의 후속 수정·하위 작업은 재사용한다. 읽기 전용 범위 파악은 가능하며 무응답을 선택으로 간주하지 않는다.
- QUICK은 기존 기능의 국소 수정이다. 짧은 목표·범위·수용 시나리오로 계약을 작성하며 기획 팀·서비스 계획·커밋·포트폴리오를 강제하지 않는다. 낮은 영향 문구/스타일은 가짜 테스트 없이 독립 검토자의 실제 파일 조회로 확인할 수 있다. 동작 변경·회귀 우려에 맞는 검증을 선택한다.
- FULL은 요구사항 구체화·필요한 조사·개발·독립 검토를 진행한다. 기술 비교/불확실성에는 `tech-researcher`, 사용자 문제에는 `service-researcher`, 기획 누락에는 `planning-reviewer`, 비용/외부 데이터/운영 부담에는 `operations-reviewer`를 필요한 만큼 배정한다. 확정 자료는 재사용하며 모든 수정마다 전체 팀을 만들지 않는다.
- 원문 인용 → 필수 요구사항 → 관찰 가능한 수용 시나리오 → 실제 검증 명령을 연결한다. 작성 안내는 `docs/harness/templates/requirements.md`, 계약/검토 스키마는 `.codex/schemas/{requirement-contract,harness-review}.schema.json`이다. 중요한 질문·확인되지 않은 가정이 남으면 구현을 시작하지 않는다. 운영자가 조회 가능한 자료를 먼저 확인하고 필요한 결정만 사용자에게 묻는다.
- 구조 검사에 더해 독립 읽기 전용 명세 검토가 원문 전체와 계약을 비교한다. 일부 요구를 누락한 명세에 완벽한 테스트를 붙여 완료하는 것을 경계한다. 필수 요구를 임의로 MVP/후속/선택 사항으로 낮추지 않는다.
- 2026-10-28 Karpathy 지침 반영: 결과·권한·데이터·범위가 달라지는 모호함은 기존 근거부터 확인하고 남은 해석·차이·권장 이유만 질문한다. 모든 요구를 충족하는 단순한 구현을 택하며 불필요한 추상화·설정·미래 기능·무관한 리팩터링/포맷/기존 dead code 정리를 추가하지 않는다. 단순화를 이유로 기능·오류 처리·권한·데이터 보호·수용 기준을 줄이지 않는다. 주요 변경은 요구사항 또는 필수 의존성과 연결해 독립 검토하며, 버그 수정은 실제 수정 전 재현 근거와 동일 조건의 수정 후 확인을 연결한다. 근거가 없으면 한계와 대체 확인을 명시한다. 상세·출처: `docs/decisions/2026-10-28-karpathy-guidelines.md`.
- 개발 workspace와 제어 코드/상태 저장소를 분리한다. 운영자는 사용자 요청과 계약을 보존한 뒤 외부 실행기를 호출한다. 개발·검토는 별도 Codex CLI 세션이며 개발자는 계약/승인/제어 상태를 수정하거나 완료를 확정하지 않는다. 하위 세션은 운영자를 또 만들거나 QUICK/FULL을 재질문하거나 하네스를 재귀 실행하지 않는다.
- 실행기는 동결된 검증 명령의 실제 종료 코드·로그와 코드 지문을 수집한다. 독립 검토자가 요구사항/시나리오별 실제 관찰 근거를 제출하고 모든 필수 조건이 충족되어야 VERIFIED가 된다. 개발자의 자체 보고나 과거 코드의 테스트 결과로 대체하지 않는다. VERIFIED는 병합·push·배포 완료가 아니다.
- 범위 변경은 실제 사용자 메시지·출처·이전/새 계약 digest를 연결해 기록하며 최초 원문을 보존한다. 새 계약은 기존 PASS를 무효화한다. 이미 받은 권한을 재승인받지 않되, 요구사항 삭제·검증 약화·중요 정책 변경을 스스로 승인하지 않는다. 파일 receipt만으로 사용자 신원을 인증했다고 주장하지 않는다.
- 검증 실패는 같은 요구사항을 유지한 제한 재작업으로 처리한다. 실패/권한 거절/재시도 한도 소진을 성공이나 범위 축소로 바꾸지 않는다. QUICK에서 신규 기능·구조·권한·외부 연동이 필요하면 추가 범위를 설명하고 FULL 전환 또는 원래 범위 유지를 묻는다. 실패한 FULL을 QUICK으로 우회하지 않는다.
- native 대화의 final 응답을 가로채는 전역 훅은 없다. 공식 완료 제어는 새 실행기로 실행한 작업에 적용된다. 엔진이 막히면 원인과 필요한 조치를 설명하며 native 직접 구현/자기 완료 선언으로 조용히 우회하지 않는다.
- 하위 기본 모델: 개발/독립 검토/복잡한 판단 `gpt-6.1-sol`, 범위가 명확한 조사·비교 `gpt-6.1-terra`, 기존 자료 요약 `gpt-6-luna`. 추론 medium, 속도 fast를 기본으로 하며 역할 파일은 모델을 고정하지 않는다. 루트 대화 모델은 유지한다. 실행기 모델은 `--model`로 선택한다.
- 작업 소유 파일·목표 동작·수용 기준·인계물을 명시한다. 같은 파일을 여러 개발자에 동시에 맡기지 않는다. 도메인 정책과 FE mock → endpoint 계약 → BE → 통합 순서를 지킨다. 호출/근거 도구와 실제 실행·병합·배포를 구분한다.
- `service-portfolio`는 주요 기획/개발 이정표의 근거를 모아 핵심 사용자 흐름 완성 시 **서비스 전체 단위 모션그래픽**을 제작한다. 수정/머지마다 조각을 양산하지 않는다. Notion 등 외부 기록은 목적지·범위가 승인된 경우에만 수행한다.
- 개발 중 이상현상은 `harness-run.sh feedback`으로 원본 근거와 기록한다. 원인은 코드/환경/하네스/미확정으로 구분하며 관찰만으로 원인을 확정하지 않는다. 엔진의 실제 이벤트 범위와 명시적 관찰만 기록하며 모든 Codex 내부 호출을 자동 수집한다고 주장하지 않는다.
- 일반 **자동 생성 하네스 후보**에는 `.harness/AGENTS.md`, `docs/spec/harness-self-improvement.md`의 관찰·원인 분류·독립 재현·격리 후보·비교·실제 사용자 승인 경계를 유지한다. 필요한 경우 `harness-inspector`, `harness-optimizer`, `harness-evaluator`를 배정한다. 수정 대상 하네스의 자체 PASS를 개선 효과의 증거로 삼지 않는다.
- **이번 사용자 직접 지시한 하네스 전환은 예외**다. 사용자는 기존 하네스를 무시하고 계획을 완전히 반영하며 직접 개발해 보면서 평가하라고 지시했다. 이번 변경에는 기존 FULL/후보 평가/추가 digest 승인 절차와 행동 테스트를 적용하지 않고 직접 반영한다. 문법/import/도움말 연결만 확인하고 실제 개발 피드백으로 보완한다. 미래의 모든 자동 후보나 배포에 대한 일괄 승인은 아니다.
- 하네스 후보와 직접 수정 모두 다른 세션의 변경을 보존한다. 자동 후보는 별도 worktree에서 작성하며 관련 파일의 최신 지문을 비교해 적용한다. 하위 에이전트는 승인·apply·rollback·merge·push·배포를 하지 않는다. 사용자 직접 수정 요청에 명시된 최신 범위·절차가 기존 하네스보다 우선한다.
- 에이전트 명세는 `.codex/agents/*.toml`, 대화 설정은 `.codex/config.toml`이다. Claude/FE·BE legacy 지침은 보관 이력이며 새 실행 지시로 사용하지 않는다.
- 2026-10-25 최신 사용자 결정: 관리 세션은 `/Users/woolee/benchmark`, 메인 세션은 `/Users/woolee/benchmark-main`, 자연어 검색 AX는 별도 전용 worktree에서 작업한다. 이 결정은 이전 단일 checkout/새 worktree 금지 규칙을 대체한다. 결정 기록: `docs/decisions/2026-10-25-parallel-worktrees.md`.
- 메인 통합 브랜치는 `feat/home-preview-json`이며 이 worktree 안에서만 메인 작업을 수행한다. 관리/AX의 HEAD·실제 인덱스·작업 파일을 변경하지 않는다. 원본에서 stash/reset/clean/브랜치 전환/전체 변경 일괄 커밋을 하지 않는다.
- 공용 파일은 메인 관련 변경만 가져오며, 다른 세션의 미커밋 인증·모델·검색 정책을 자동 적용하지 않는다. 공통 의존성은 실제 커밋 기준으로 별도 검토한다.
- 각 worktree 안에서는 task branch를 순차 사용하고 브랜치 전환 전 해당 worktree의 clean 상태를 확인한다. 과거 `benchmark.fe-feat-main-home` worktree는 재사용/초기화하지 않는다.
- 본 AGENTS.md 는 도메인/규칙의 SSOT. 변경 시 PR 또는 명시적 결정 기록 동반
- 2026-10-24 정책 변경: 공통 수집 관리·번역 검수를 STREAMER / ADMIN 에게 제공한다. 결정 기록은 `docs/decisions/2026-10-24-streamer-management-and-ax.md`, 상세 기획은 `plan.md`, 작업·DoD·의존성·상태 정본은 `Plans.md`. 문서의 정책 확정과 기능 구현 완료를 구분한다.
- 배포 금지 원칙: 사용자가 **"배포해"** 라고 명시적으로 요청하지 않는 한 Koyeb/Vercel/GitHub Actions 등 어떤 서비스에서도 deployment 를 트리거하지 않는다.
- 배포성 명령에는 `koyeb services update`, `koyeb deploy`, `vercel deploy`, 배포 환경변수 변경, 서비스 재시작/롤링 업데이트가 포함된다. "서비스에 연결", "설정해", "환경변수 넣어" 같은 표현은 배포 허가가 아니다.

- 2026-10-26 메인 후속 결정: 추천 자격 경기의 킥오프 전 6시간 이내 마지막 정기 수집 완료 후 경기당 1회 프리뷰 생성. 외부 전망은 API-Football 포함 총 3개. 운영 홈은 추천 경기·프리뷰만 표시하고 생성 예정/실제 시각을 안내하며 출처·자료 시점은 접는다. 이전 24시간/4회·웹매체3곳 정책을 대체한다. 상세: `docs/decisions/2026-10-26-home-final-sync.md`.

- 2026-10-25 목업 평가 결정: 번역 상태는 한국어 이름 유무에 따른 번역/미번역만 제공하며 별도 검수 완료 체크는 두지 않는다. 짧은 이름은 선택 사항이다. 사람 수정 보호·감사 이력·동시 수정 충돌은 유지한다. 동일 결정 기록의 2026-10-25 절을 따른다.

- 2026-10-25 병렬 작업 운영: 사용자 지시에 따라 관리·메인·AX는 각각 별도 worktree를 사용한다. 위 단일 checkout 규칙보다 이 결정이 우선한다. `docs/decisions/2026-10-25-parallel-worktrees.md` 참조. 2026-10-26 사용자는 검증된 홈 작업의 로컬 main 병합과 필요한 운영 DB migration 적용을 승인했다. 원격 push·배포·서비스 재시작은 금지한다.

- 2026-10-26 홈 추천 후속: 카라바오컵(external_id48)과 FA컵(45)은 준결승/결승에서만 기존 추천 자격을 평가한다. 8강 이하·라운드 미정은 진행 중이어도 홈 추천 및 신규 프리뷰 생성 대상에서 제외한다. 기존 빅6/우선순위 조건과 다른 대회 정책은 유지한다. `docs/decisions/2026-10-25-home-preview-json.md`의 후속 결정을 따른다.
