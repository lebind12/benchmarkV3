# 스크래퍼 실현 가능성 사실 조사

작성: 2026-11-11 (KST). 성격: 읽기 전용 사실 조사. 구현·설치·유료 호출·DB 쓰기·커밋/스테이징 없음. 이 문서는 설계·수정·대안 선택을 제안하지 않고, 관측된 사실과 아직 모르는 것을 구분해 적는다.

## 0. 실행 세션 메타데이터 (실제 확인)

| 항목 | 관측값 | 근거 |
|---|---|---|
| 개발 모델 제공자 | `hive` | `~/.dsh/sessions/--Users-woolee-benchmark--/960af2a7-1a8a-420e-be2f-ef4b796e1338/session.v4.jsonl.zstd`의 `model/selection` 레코드 |
| 모델 ID | `deepseek-ai/deepseek-v4.1-flash-1017` | 같은 레코드 |
| 추론 강도 | `max` | 같은 레코드 |
| DSH 프로필 | `dsh-tui` | 환경변수 `DSH_PROFILE`, `DSH_PROFILE_DIR=/Users/woolee/.dsh/profiles/dsh-tui` |
| 실행 하네스 | `dsh-tui` (Orca worker 터미널) | `ORCA_TERMINAL_HANDLE=term_0af3e742-b346-4474-b556-88611800359c`, `DSH_SHELL=1` |
| 작업 디렉터리 | `/Users/woolee/benchmark` | 세션 레코드 `cwd`, 셸 `pwd` |
| 세션 생성 시각 | `createdAt` 1794350993601 | 세션 레코드 |

기대값(실행 환경 `hive`/`deepseek-ai/deepseek-v4.1-flash-1017`/Max, `dsh-tui`)과 실제 세션 레코드가 일치한다. 제품이 호출하는 모델(`gemini-3.5-flash`, Vertex global)은 이 개발 세션 모델과 별개다.

## 1. 실제 의존성과 사용 가능한 도구 (설치 없이 확인)

### 1.1 제품 런타임 의존성 (`requirements.txt`, `pyproject.toml` 실제 내용)

- `fastapi==0.115.6`, `uvicorn[standard]==0.34.0`, `SQLAlchemy==2.0.36`, `psycopg[binary]==3.2.3`, `alembic==1.14.0`, `argon2-cffi==23.1.0`, `pydantic==2.14.3`, `pydantic-settings==2.7.0`, `langgraph==1.2.20`, `langgraph-checkpoint==4.3.1`, `google-genai==3.0.0`.
- 테스트 전용: `pytest==8.3.4`, `httpx==0.28.1`.
- `requires-python = ">=3.11"`.

### 1.2 로컬 venv 실제 설치 상태 (`.venv/bin/pip list`, Python 3.11.4)

| 패키지 | 상태 |
|---|---|
| `trafilatura` | **미설치** |
| `crawl4ai` | **미설치** |
| `playwright` | **미설치** |
| `selenium` | **미설치** |
| `readability-lxml` / `newspaper3k` / `justext` / `html2text` | **미설치** |
| `lxml` | venv **미설치** |
| `bs4` (beautifulsoup4) | venv **미설치** |
| `requests==2.34.2` | 설치됨 |
| `httpx==0.28.1` | 설치됨 |
| `urllib3==2.8.0` | 설치됨 |

- 제품 venv에는 HTML 본문 추출 라이브러리가 하나도 없다. 즉 **현재 배포 런타임에 스크래핑/본문 추출 기능은 존재하지 않는다.**
- 별도 시스템 인터프리터(`/opt/homebrew/anaconda3/bin/python3`)에는 `bs4 4.12.2`, `lxml 4.9.2`가 이미 설치돼 있다. 이번 조사의 텍스트 추출 측정은 설치 없이 이 기존 라이브러리로 수행했다. 이것은 venv나 배포 환경의 사용 가능성을 뜻하지 않는다.
- 브라우저 실행 도구(playwright/selenium 등)는 어느 인터프리터에도 없다. 로컬 GUI Chrome.app 존재는 서버사이드 자동화 도구의 존재가 아니다.

### 1.3 애플리케이션 코드 안의 웹 접근/추출 흔적

- `app/preview/sources/__init__.py`는 `httpx`·`requests`·`socket`을 import하지 않는다고 명시하고, 실제로 `app/` 전체에 `import requests`/`import httpx`가 없다.
- `app/`, `scripts/`, `tests/` 전체에서 `HTMLParser`, `BeautifulSoup`, `trafilatura`, `crawl4ai`, `readability` 사용처 0건.
- `scripts/`에도 `httpx`/`requests`/`urlopen` 사용처 0건.
- 결론: 현재 코드베이스에는 URL 본문 수집·HTML 추출 구현이 없다. 본문 수집을 붙일 자리는 새로 생겨야 한다(§4의 경계 참조).

## 2. Koyeb 배포 자원 메타데이터 (`benchmark-v3/api`)

인증된 기존 CLI(`/Users/woolee/.koyeb/bin/koyeb`, v4.1.2, 로그인 상태)로 조회했다. **설정/환경변수/비밀값은 출력하지 않았다.** 아래는 자원·컨테이너 한도만이다.

| 항목 | 관측값 | 출처 |
|---|---|---|
| 앱 | `benchmark-v3` (`e42817bc`), HEALTHY | `koyeb apps list` |
| 서비스 | `api` (`5178062c-1ff2-49a3-a683-e96df3d672cb`), WEB, HEALTHY | `koyeb services list` / `services get` |
| 활성 배포 | `6b6fbe4f-92eb-4cbe-9a09-68e1e9082287`, HEALTHY, 2026-11-08 | `koyeb deployments get` |
| 리전 | `tyo` (인스턴스 datacenter `tyo2`) | deployment `definition.regions` |
| 인스턴스 타입 | `small` (scope `region:tyo`) | deployment `definition.instance_types` |
| 스케일링 | `min 1 / max 1` | deployment `definition.scalings` |
| 컨테이너 포트 | `8000/http` | deployment `definition.ports` |
| 헬스체크 | `GET /health` on 8000 | deployment `definition.health_checks` |
| 볼륨 | 없음(`[]`) | deployment `definition.volumes` |
| 빌드/실행 | buildpack, run `uvicorn app.main:app --host 0.0.0.0 --port 8000` | deployment `definition.archive` |
| 환경변수 키 개수 | 14개(키 목록만 확인, 값 미출력) | deployment `definition.env` |
| 현재 인스턴스 | 1개 `835b374c`, HEALTHY, `tyo2` | `koyeb instances list` |

Koyeb 공개 가격/인스턴스 표 기준 `Small` 사양은 **vCPU 0.25 / RAM 1 GB / 스토리지 ∞, $0.04/hr** 다([Koyeb pricing](https://www.koyeb.com/pricing) 2026-11-11 조회, 외부 페이지). CLI 자체는 인스턴스 타입의 CPU/RAM 숫자를 출력하지 않으므로 이 수치는 외부 공개 문서 근거이며, 배포 메타데이터가 말하는 사실은 "타입=small, min/max=1"이다.

관측 한계:
- `koyeb metrics get`은 실행 자체는 성공했지만(CPU/메모리/요청/응답시간/전송량 섹션 반환) 조회한 모든 구간에서 값이 `0.000000`이었다. 이 값은 실제 사용량 0으로 해석하지 않는다. **실사용 CPU/RAM 피크는 미확인**이다.
- 환경변수 키 이름만으로 "연결됐다/안 됐다"를 판정하지 않는다. 비밀값이 이미 존재하는 것은 외부 연결이 실제로 동작한다는 증거가 아니며, 이번 조사는 어떤 외부 연결도 실행하지 않았다.

## 3. 저장된 후보 URL 실제 접근 결과 (최대 6개, GET only)

조건: 공개 URL만, `curl -L --max-time 25 --max-redirs 5 --connect-timeout 10`, 브라우저 UA, 재귀 크롤 없음, CAPTCHA/페이월 우회 없음. 6개 모두 stderr 비어 있음(curl 오류 0). 본문 텍스트 길이는 기존 설치된 `bs4`+`lxml`(시스템 인터프리터)로 script/style 제거 후 측정했다.

| # | 후보 (출처) | HTTP | 최종 목적지 | HTML 바이트 | 추출 텍스트 | 판정 |
|---|---|---|---|---|---|---|
| 1 | `forebet.com/en/predictions-tips-manchester-city-fulham-1925345` (최신 응답 R4 evidence) | **403** | 동일 URL (리다이렉트 0) | 5,843 | 16자 (`Just a moment...`) | **차단** — Cloudflare류 챌린지. 본문 없음 |
| 2 | `manchestercitynews.co.uk/squad` (최신 응답 R4 evidence) | **200** | 동일 | 100,581 | 2,096자 | **본문 확보 가능** — 정적 HTML에 스쿼드 목록 포함. 페이지 표기 "Updated 2026-11-10" |
| 3 | `fulhamfc.com/news/2026/november/06/josh-king-called-up-to-england-squad/` (최신 응답 R4 evidence) | **200** | 동일(끝 슬래시 유지) | 1,581,891 | **0자** | **JS 셸** — Nuxt, `#__nuxt` 비어 있고 `serverRendered":2`(SSR off). HTML 안에 "josh king" 문자열 0회 |
| 4 | grounding redirect → **plstats.uk** `/players/erling-haaland/` (이전 성공 chunks[0]) | 200 | `https://plstats.uk/players/erling-haaland/` (redirect 1) | 84,849 | 4,097자 | **본문 확보 가능** — Haaland 10경기 890분 9골 등 수치, "Updated November 8, 2026" |
| 5 | grounding redirect → **theguardian.com** `/football/2026/nov/04/rb-leipzig-manchester-city-champions-league-match-report` (chunks[1]) | 200 | 위 최종 URL (redirect 1) | 483,322 | 8,026자 | **본문 확보 가능** — 기사 본문·"Wed 4 Nov 2026" 표기 |
| 6 | grounding redirect → **en.wikipedia.org** `/wiki/Oscar_Bobb` (chunks[2]) | 200 | 위 최종 URL (redirect 1) | 279,903 | 18,246자 | **본문 확보 가능**(단 잡음 많음) — 문서 제목 `Oscar Bobb`, 2026 시즌 Fulham 소속 정보 포함. 사이드바/편집 링크 등 부수 텍스트 비중 큼 |

핵심 관측:
- **저장된 grounding redirect URL은 만료되지 않고 실제로 살아 있었다.** 3개 모두 200 + 1회 리다이렉트로 실제 기사 URL에 도달했다. 다만 이 3개는 이전 성공 응답의 chunk이고, **최신 응답에는 chunks 필드 자체가 없어서** 최신 실행의 후보 URL은 모델 evidence의 3개(#1~#3)뿐이다.
- 모델 evidence URL 3개 중 실제로 평문 HTML 본문을 얻은 것은 **1개(#2)** 다. #1은 봇 차단, #3은 SSR 꺼진 JS 셸이다.
- grounding chunk URL 3개는 모두 평문 HTML에서 본문을 얻었다.
- 즉 "저장된 public URL 6개" 기준 **평문 HTML만으로 본문 확보 4/6, 실패 2/6(차단 1 + JS 1)**. 브라우저 렌더링이 없으면 #3은 확보 불가, #1은 브라우저로도 우회하지 않는다는 보장이 없다(우회 시도하지 않았다).

### 3.1 경기 관련성 (페이지에 보이는 것만)

| URL | 보이는 경기/날짜 관련 정보 |
|---|---|
| #2 manchestercitynews squad | 페이지에 "Manchester City squad and players 2026-27", "Updated 2026-11-10". 경기 상대·킥오프 정보 없음. `Josh King` 문자열 0회, `Rayan Cherki` 1회(16경기 7골) |
| #4 plstats Haaland | 2026-27 프리미어리그 개인 기록, 최근 경기 목록("L at Nottingham 7 Nov 2026" 등). Manchester City vs Fulham 경기 자체는 없음 |
| #5 Guardian | RB Leipzig vs Manchester City 챔피언스리그 경기 리포트(2026-11-04). **해당 fixture(Manchester City vs Fulham)와 다른 경기** |
| #6 Wikipedia Bobb | 선수 신상·커리어. `current_club: Fulham`, 2026– Fulham 23경기 1골. 경기 날짜 없음 |

최신 응답이 인용한 선수 사실(예: Haaland "리그 9골", Cherki "15경기 6골", Josh King "리그 전 경기 선발·2골·대표팀 발탁")과 위 페이지 값은 일부만 맞는다. #4는 Haaland 9골을 지지하고, #2의 Cherki는 "16 Apps · 7 Goals"로 모델 문장("15경기 6골")과 다르다. Josh King은 #2/#3 어느 쪽에서도 본문으로 확인되지 않았다. 이는 페이지 내용과 모델 문장의 불일치를 **보여줄 뿐**, 모델 주장의 진위나 스크래퍼 설계의 정오를 판정하지 않는다.

## 4. 현재 구조에서 scraping이 끼어들 수 있는 경계 (사실만)

- 그래프 노드 순서(코드): `PIPELINE_NODES = ("D0","R1","R2","R3","R4","V0","S1","V1")`, `app/preview/pipeline.py`의 그래프는 `START → D0 → (R1‖R2‖R3) → V0 → S1 → V1 → END`.
- D0(`prepare_match_data`)는 외부 호출 0으로 저장 자료만 읽고 `SourceSnapshot`을 남긴다(`app/preview/data.py`).
- 각 조사 모듈은 모델 호출이 **정확히 1회**다: `form.py`(R1), `availability.py`(R2), `outlook.py`(R3), `players.py`(R4) 모두 `provider.request_model` 1회. `synthesis.py`(S1)도 1회. V0/V1에는 `request_model` 호출이 없다.
- 조사 4개 모두 `{"tools": [{"google_search": {}}]}`를 요청에 넣는다(`form.py:1353`, `outlook.py:114`, `players.py:1032`, `availability.py:1541`).
- 제공자 응답의 검색 출처는 `form.parse_grounding`이 `grounding_metadata.grounding_chunks[].web.uri/title/domain`, `grounding_supports`, `web_search_queries`, `search_entry_point`로 파싱한다. chunks가 없으면 `citation_chunks_missing=True`와 "출처 없는 내용은 사실로 채택하지 않습니다" note를 남긴다.
- 근거 인정 경계: `form._resolve_sources`는 모델이 인용한 값이 `allowed_ids`(API fact id) 또는 `grounding_urls`(공급자 chunk URL 집합)에 **정확히** 있을 때만 인정한다. 모델이 만든 URL이 chunk 목록에 없으면 근거 없음으로 판정된다(최신 run의 실제 탈락 경로).
- 문장 사실 검사: `_cited_fact_text`는 `FormFacts.facts[].text`(API 자료)만 합치고, `_clause_supported`는 그 문자열과 연도만 대조한다. **수집한 웹 본문은 이 대조 입력에 들어가지 않는다.**
- 저장 경계: `store.record_source_snapshot(...)`은 `source_kind`(`SourceKind` = `api` | `search`), `provider`, `collected_at`, `artifact_id`, `validation_status` 등을 받는다. `artifacts.save_artifact`는 임의 텍스트/JSON 본문을 비밀값 마스킹 후 `body`/sha256/byte_size로 저장할 수 있다. 즉 **본문 텍스트를 담을 수 있는 저장 그릇은 이미 있으나, `SourceKind`에 web/scrape 종류는 없다.**
- 예산 경계: `BudgetLimits`는 `model_requests=8`, `api_requests=24`, `attempts_per_call=3`, `model_concurrency=2`, `api_concurrency=2`, `deadline_seconds=1800`. `RequestClass`는 `model`/`api` 두 가지뿐이고 `api_requests`가 D0 외부 API 요청 예산이다. **스크래퍼 HTTP는 현재 어느 예산에도 속하지 않는다.**

### 4.1 예산 산술 (현재 값 기준)

- 정상 경로: 조사 4(R1/R2/R3/R4) + 종합 1(S1) = **5회**. `NORMAL_MODEL_CALLS = 5`, 전체 상한 `MODEL_REQUEST_BUDGET = 8`이라 재시도 여유는 3회.
- 조사 섹션별 "검색 1 + 근거기반작성 1"을 R1~R4 **각각** 적용하면 4×2 = 8, 여기에 S1 1회를 더해 **9회**가 되어 현재 상한 8을 넘는다. 이는 코드에서 확인되는 상수(`8`, `5`)와 설계 문서에 적힌 9회 계산이 서로 어긋나는 지점이다.
- 단일 섹션(R4)만 보면 "조사 1 + 작성 1 = 2회"는 현재 상한 안에서 성립한다. 실제 R4 live 실행 예산도 `model_requests=1 / used=1 / remaining=0`으로 기록됐다.
- 스크래퍼를 `api_requests`(24)에 넣을지 별도 상한을 둘지는 코드에 정해진 바가 없다. 현재 `RequestClass`·`BudgetLimits`에는 그 자리가 없다.

## 5. 관측된 사실 vs 아직 모르는 것

관측된 사실:
1. 배포 런타임과 제품 venv에 HTML 추출·브라우저 도구가 **없다**. 추출 라이브러리 추가는 새 의존성 도입이다.
2. 코드에 웹 본문 수집 경로가 없고, `sources` 패키지는 의도적으로 HTTP를 import하지 않는다.
3. 배포는 `small`(0.25 vCPU/1 GB — 외부 공개 표 기준) 1인스턴스, 볼륨 없음, buildpack, `min=max=1`.
4. 저장된 public URL 6개 중 4개는 평문 HTML로 본문 확보, 1개는 봇 차단(403), 1개는 SSR 꺼진 JS 셸(0자).
5. 저장된 grounding redirect 3개는 조사 시점 현재 모두 유효했고 실제 기사로 1회 리다이렉트됐다.
6. 현재 근거 인정 로직은 공급자 chunk URL 정확 일치 또는 API fact id만 인정하며, 웹 본문 텍스트는 사실 대조 입력에 쓰이지 않는다.
7. 정상 5회/상한 8은 코드 상수로 존재하고, 섹션별 2회 확장 시 9회가 되어 상한을 넘는다.

아직 모르는 것(이번 조사로 확정되지 않음):
1. `small` 인스턴스에서 Trafilatura급 추출을 수십 URL 규모로 돌릴 때의 **실제 CPU/메모리/시간**. Koyeb metrics가 전부 0으로 나와 사용량 근거가 없다.
2. 실제 축구 사이트 모집단의 차단율·JS 의존율. 이번 표본은 6개뿐이고 그중 2개가 실패했다.
3. 대상 사이트 약관·robots 정책 준수 여부(이번에 확인하지 않았다).
4. 후보 URL이 경기와 실제로 관련 있는지를 URL/페이지 메타데이터만으로 판정할 수 있는 비율.
5. `api_requests` 24 예산과 스크래핑 HTTP를 어떻게 합칠지(코드에 미정).
6. 최신 응답처럼 chunks가 아예 없을 때, 모델 evidence URL만으로 충분한 본문을 얻을 수 있는 비율 — 표본 3개 중 1개만 성공.

## 6. 가장 작은 다음 실험 (제안이 아니라 최소 검증 단위)

가장 작은 실험은 **모델·DB·설치 없이** 이미 저장된 URL 후보만으로 "평문 HTML 본문 확보율"을 재는 것이다.

- 대상: 저장된 후보 URL 집합(최신 응답 evidence 3개 + 이전 성공 chunks의 실제 목적지 5개 = 최대 8개).
- 방법: 기존 venv의 `requests`로 GET(리다이렉트·시간 상한), **HTML 원문 저장**. 추출은 venv에 없는 라이브러리를 새로 설치하지 않고, 이미 있는 도구로만 수행하거나, 설치 승인 후 Trafilatura 1회 비교.
- 측정: 상태코드/최종 URL/본문 글자수/경기·선수 키워드 포함 여부/차단·JS 셸 구분.
- 판정 기준 예시: "평문 HTML로 본문이 나오는 URL 비율"과 "브라우저 렌더링이 반드시 필요한 URL 목록"을 분리해 기록.
- 이 실험은 모델 호출 0, API-Football 0, DB 쓰기 0으로 수행 가능하다.
- plain HTML 충분성에 대한 현재 답: **이 6개 URL 한정으로는 부분적으로 충분하다.** grounding chunk URL 3/3 성공, 모델 evidence URL 1/3 성공. 남은 2개(Cloudflare 403, Nuxt SSR-off)는 plain HTML로 불가능하며, 그중 #3은 JS 실행 브라우저가 있어야 본문이 나올 가능성이 있다. 이는 6개 표본의 관측이지 일반화된 성공률이 아니다.

## 7. 이번 조사의 범위 준수

- 제품 코드·테스트·스크립트·설정·`Plans.md` 수정 없음. 작성한 파일은 이 문서 하나다.
- 설치·유료 모델 호출·API-Football 호출·DB 쓰기·스테이징/커밋 없음.
- 기존 808개 삭제와 dirty 파일은 그대로 두었다(`git status` 총 839항목: 삭제 808 / 수정 7 / 미추적 24).
- 외부 요청은 §3의 6개 공개 URL GET과 Koyeb 가격 페이지 1회 조회뿐이며, CAPTCHA·페이월 우회나 재귀 크롤은 하지 않았다.
- Koyeb 조회는 자원 메타데이터만 읽었고 환경변수/비밀값은 출력하지 않았다.

EDITING STOPPED
