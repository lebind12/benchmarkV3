> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/ax/natural-language-search/context.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 현재 컨텍스트

현행 기준: 2026-10-29. **에이전트 검색이 현재 구현이며, 서비스 인수는 미완료다.** 사용자 목표는 현행 기획 정리부터 검증 순서를 따라 완성된 서비스의 머지·배포까지 진행하는 것이다. 프롬프트 인젝션 대응을 출시 필수 검증에 포함한다.

현재 정본은 [서비스 완성 계획](plan.md), [제품 요구](../../features/ax-agentic-search.md), [진행 표시](../../features/ax-agentic-progress.md), [보안 인수](prompt-injection-security.md), Plans.md (원문 참조 경로: `../../../Plans.md`; 이 기획 묶음에 포함되지 않음)의 AX-R-*다. 현재 로컬 구현/과거 인수 한계는 구현 기록 (원문 참조 경로: `agentic-implementation.md`; 이 기획 묶음에 포함되지 않음)을 참조한다. 이전 완료 표기는 로컬 산출물 범위이며 정식 게이트 통과나 배포 완료가 아니다.

2026-10-29 재검증: 단위197/build/lint 통과, DB15는 명시 local config 부재로 skip. 최신 핵심 테스트4파일58개는 표준 marker 선택에서 제외되어 보완 대상이다. 실제 모델 전체 성공0·429/504 보류, 운영 reader/갱신·실제 계정·독립 holdout·성능/비용 인수는 미완료다.

2026-10-29 환경 재확인: 기존 관리 checkout의 로컬 설정에서 Vertex/DB 구성을 발견했다. 기존 서비스 계정 파싱·Google token refresh·project 일치 확인은 PASS다. 인증값은 출력/복사하지 않았다. 후속으로 fresh 축구 snapshot·전용 로컬 reader를 복원해 DB15 재실행 PASS, 지정 모델 최소 연결 요청1회 PASS를 확인했다. 환경 증거 (원문 참조 경로: `evaluation/reports/readiness-20261029.json`; 이 기획 묶음에 포함되지 않음)·모델 연결 (원문 참조 경로: `evaluation/reports/vertex-readiness-20261029.json`; 이 기획 묶음에 포함되지 않음)을 참조한다. 실제 전체 검색/의미/실계정 인수는 별도 미완료다.

## 2026-10-25 단계별 역사 기록

아래는 과거 목업·v1·초기 조사 문맥이다. “현재/다음/미구현”은 당시 단계의 기록이며 현행 작업 순서는 상단 정본을 따른다.

## 1. 사용자 지시와 현재 단계

1. 상위 `plan.md`의 AX 기능 중 자연어 검색을 검색창 목업부터 진행한다.
2. 글래스모피즘 배경과 검색창을 사용한다. 검색창은 한 줄로 시작해 긴 입력에 따라 아래로 확장하고 삭제 시 축소한다.
3. 다크 모드, 높이 변화 애니메이션, 검색 중·결과 등장 애니메이션을 제공한다.
4. 오래 걸리는 검색에서는 로딩 문구 목록을 순환한다.
5. 사용자는 목업이 현재 수준이면 충분하다고 확인했다. 이후 기술 스택 점검과 관련 AX 사례 조사를 진행했다.
6. 조사 자료와 현재 작업 컨텍스트를 전용 디렉터리에 모으고 별도 `plan.md`를 작성하도록 요청했다.
7. 사전 규칙 요청은 의미/관리 원칙만이 아니라 **사전·이름 조회를 실제로 수행할 구체 계획**을 뜻한다고 사용자가 정정했다. 조회 담당 모델·도구·검색/선택 순서·문맥 전달은 [entity-resolution.md](entity-resolution.md)를 우선 읽는다. Retriever/Planner 역할 분리와 bounded tool calling의 최초 로컬 구현·실제 모델 smoke를 완료했다. 전체 질문군/독립 평가·운영 품질은 미검증이다.

추가 사용자 결정: Vertex AI의 Gemini 4 Argon(`gemini-4-argon`) 사용, 로그인 필수, 기존 API-Football 기반 Supabase DB 재사용, 축구 지표·이름·별칭 연결 사전 우선. [결정 기록](../../decisions/2026-10-25-natural-language-search.md)을 따른다. 후속 기술 선정으로 SQLAlchemy Core·SQLGlot·Google Gen AI SDK·JSON 사전/DB 별칭·pg_trgm을 채택했다. [선정 결정](../../decisions/2026-10-25-natural-language-search-stack.md)을 따른다. 정확 패키지 버전·사전 세부 schema·운영 한도는 후속 검증 항목이다. 결정과 실제 구현은 구분한다.

## 2. 현재 구현과 증거

| 항목 | 상태 / 근거 |
|---|---|
| 진입 | 헤더 검색 메뉴 → `/search`, 라우터 (원문 참조 경로: `../../../frontend/src/router/index.ts`; 이 기획 묶음에 포함되지 않음) |
| 화면 | SearchMockView.vue (원문 참조 경로: `../../../frontend/src/views/SearchMockView.vue`; 이 기획 묶음에 포함되지 않음), 프론트 로컬 상태·예시 데이터 |
| 입력 | 한 줄 시작, 최대 7줄, 자동 확장·축소, Enter 제출·Shift+Enter 줄바꿈·한글 조합 보호 |
| 디자인 | 라이트/다크 글래스, 포커스·포인터 반사광, 높이 260ms 전환 |
| 로딩 | 기본 900ms의 모의 대기, 6개 문구를 2.8초마다 순환, 18초 긴 검색 미리보기 |
| 결과 | 선수 목록·순위·팀 비교·조건 수정·확인 질문·0건·미수집·미지원·조회 제한·실패 예시 |
| 동작 범위 | 자유 입력은 실제 검색 미연결을 안내한다. 실제 자연어 해석·검색 API·DB 조회·외부 호출·polling 없음 |
| 상세 링크 | 실제 ID를 검증하지 않았으므로 가짜 링크를 만들지 않았다. 실데이터 연동 시 필요 |
| 검증 기록 | 마지막 관련 변경에서 `npm run build`, Playwright 7개 (원문 참조 경로: `../../../frontend/e2e/search-mock.spec.ts`; 이 기획 묶음에 포함되지 않음) 통과 |
| API | [화면 기반 요청/응답 초안](../../features/ax-search-mock.md). 구현·정식 계약 확정 전 |

위 검증은 목업 동작의 증거다. 실제 검색 정확도·운영 DB 권한·데이터 적재율·운영 부하는 검증하지 않았다.

## 3. 유지할 정책

- 검색은 로그인 필수이며 서버에서 활성 USER / STREAMER / ADMIN을 검증한다. 현재 공개 목업은 인증 구현 완료의 증거가 아니다.
- 기존 API-Football 기반 DB를 재사용하고 사전을 그 데이터의 실제 지표/ID에 연결한다. 데이터 조사는 새 소스 선정을 위한 작업이 아니다.

- 일반 페이지 검색은 DB 저장본만 조회한다. 검색 요청에서 API-Football이나 외부 웹 검색으로 통계를 보충하지 않는다. LLM은 질문 해석에 사용한다.
- 최신 2시즌과 활성 수집 대상 정책을 일관되게 적용한다. 대회별 현재/직전 시즌을 단순 연도 빼기로 추정하지 않는다.
- 일반 페이지의 기존 6시간 갱신 정책을 유지하며 실시간 기록·자동 polling을 도입하지 않는다.
- NULL/미수집을 기록 0으로 바꾸지 않는다. 범위 부족·부분 수집·0건을 구분한다.
- 예시 질문은 진입 도움과 평가 자료다. 지원 문장의 whitelist로 사용하지 않는다.
- 모호한 대회·시즌·팀·지표가 결과를 바꾸면 확인한다. 임의 종합 점수나 누락 통계를 만들지 않는다.
- 결과는 DB 수치로 렌더링한다. 적용 조건·기준 시각·누락 상태를 응답의 구조화된 필드로 전달한다.
- SQL 원문·내부 스키마·공급자 오류는 일반 사용자에게 노출하지 않는다.
- 검색 전용 읽기 role·접속 경로를 검증하기 전 쓰기 가능한 공통 DB 계정으로 대체 공개하지 않는다.
- Upstash 검색 응답 캐시는 post-MVP다. 이번 문서로 용도를 확대하지 않는다.
- FE 요구 → endpoint-request → BE 명세/테스트 → 구현 → FE 연동 순서를 유지한다.
- DB 변경은 Supabase CLI 마이그레이션과 ORM 동기화 원칙을 따른다. 신규 API-Football 응답 모델이 필요하면 MCP 실응답 확인 경로를 먼저 확보한다.
- 사용자의 명시적인 배포 요청 없이 배포·배포 환경변수 변경·서비스 재시작을 수행하지 않는다.

## 4. 기존 코드에서 확인한 사항

| 코드 | 확인한 내용 | 후속 의미 |
|---|---|---|
| app/db.py (원문 참조 경로: `../../../app/db.py`; 이 기획 묶음에 포함되지 않음), config.py (원문 참조 경로: `../../../app/core/config.py`; 이 기획 묶음에 포함되지 않음) | 공통 SQLAlchemy 동기 engine/session, 작은 기본 pool, OpenAI·Vertex 설정 존재 | 검색 전용 engine/role/timeout/취소 경로 필요. LLM 대기 중 DB 연결을 점유하지 않도록 설계 |
| player.py (원문 참조 경로: `../../../app/models/player.py`; 이 기획 묶음에 포함되지 않음) | 득점·도움·출전 시간·평점 등, 선수×팀×대회×시즌 단위 통계와 JSONB 원본 | 다중 소속·합계·평점·비율·NULL 정의 필요 |
| fixture.py (원문 참조 경로: `../../../app/models/fixture.py`; 이 기획 묶음에 포함되지 않음) | 경기 결과 컬럼, 상세 통계·라인업 등의 JSONB | JSON 필드 존재만으로 데이터 수집을 보장하지 않음 |
| general.py (원문 참조 경로: `../../../app/services/general.py`; 이 기획 묶음에 포함되지 않음) | 이름 부분 검색, 기존 선수 목록은 현재 시즌 기준 | 자연어 조건/집계용 서비스와 최신 2시즌 적용 경로를 별도 설계 |
| league.py (원문 참조 경로: `../../../app/models/league.py`; 이 기획 묶음에 포함되지 않음), worker_sync_log.py (원문 참조 경로: `../../../app/models/worker_sync_log.py`; 이 기획 묶음에 포함되지 않음) | 대회/대상 설정·공급자 capability·실행 로그 존재 | 실제 영역별 coverage와 구분해야 함 |
| broadcast_ai_commentary.py (원문 참조 경로: `../../../app/services/broadcast_ai_commentary.py`; 이 기획 묶음에 포함되지 않음) | Vertex 인증·HTTP 호출과 방송용 프리뷰 생성 존재 | 인증/통신 기반은 참고 가능. 검색에 방송 live/web grounding 경로를 그대로 연결하지 않음 |
| 번역 OpenAI 클라이언트 (원문 참조 경로: `../../../app/workers/translation_filler/openai_client.py`; 이 기획 묶음에 포함되지 않음) | OpenAI 호출·재시도·응답 파싱 기반 존재 | 검색용 구조화 계획·모델·예산은 별도 설계 |

## 5. 확인하지 않은 사항

- 운영 PostgreSQL 버전·현재 role·view 권한·Supabase 연결 모드·남은 연결 수.
- 대회×시즌×영역별 실제 행 수·결측·중복·최근 성공 시각·부분 실패.
- 검색에 사용할 지표의 정확한 집계 의미와 기준 SQL 결과.
- 지정 모델 `gemini-4-argon`의 계정/리전 접근·호출 호환성·구조화 출력·한국어 정확도·실측 지연·비용.
- 채택한 SQLGlot 검사 계층의 PostgreSQL 구문 coverage·바인딩 정합·우회 차단 성능, pg_trgm 운영 활성/한글 검색 품질.
- 로그인 검증의 실제 검색 연결, 사용자별 제한과 전체 비용 상한. 비로그인 검색은 허용하지 않는다.

## 6. 다음 작업의 진입점

[dictionary-design.md](dictionary-design.md)를 기준으로 용어/엔티티 연결 사전을 우선 구체화한다. [plan.md](plan.md)의 AX-9 읽기 전용 데이터 점검을 함께 수행해 실제 컬럼·ID·누락과 연결한다. 목업을 완료했다는 이유로 AX-9~12 전체를 완료 처리하지 않는다. 현재 세션의 변경은 별도 브랜치로 분리했으며 기존 체크아웃의 관리·홈 미커밋 작업은 그대로 보존했다. 분리 기록 (원문 참조 경로: `branch-isolation.md`; 이 기획 묶음에 포함되지 않음)을 따른다.


## 2026-10-25 실측 진행

기존 DB를 READ ONLY로 33개 조회했다. 조사 보고서 (원문 참조 경로: `data-audit.md`; 이 기획 묶음에 포함되지 않음)와 쿼리/증거 JSON을 남겼다. 선수 이름 충돌 1,400개 키·EPL 2026 복수 팀 선수 9명·상세 JSON의 빈 값·활성 league/target 차이·검색 전용 최소 권한 role 필요를 확인했다. 이는 조사 시 저장값이며 외부 최신 사실/전체 수집 완료 인증이 아니다.

[semantic-catalog.json](semantic-catalog.json.md)에 9개 지표·7개 범위·2개 관계를 비활성 초안으로 연결했다. [내부 도구 계약](retrieval-tool-contracts.md)은 mention/ref 검증, 기존 이름 원천, 후보 잘림, 관계 unknown과 availability 한계를 구체화했다. 도구 런타임·지정 모델 호출·검색 API·마이그레이션은 미구현이다.

다음은 실제 정규화/이름 후보 repository와 catalog loader 명세·구현, 지표별 기준 SQL/독립 평가 세트다. AX-9는 진행 중이며 다른 세션의 관리/홈 구현은 이 worktree에 임의 반영하지 않는다.


## 2026-10-25 개발 전 평가 준비 요청

사용자 요청으로 [evaluation-plan.md](evaluation-plan.md)에 정답/고정 데이터 준비, 사전·이름 조회→Retriever→Planner→DB/서버→전체의 단계별 정확도·안전성·성능/비용 분석을 정리했다. 기능 연동 전에 평가 문항·fixture/기준 SQL·offline runner를 준비한다. 현재 5개 offline 검증과 DB 관측을 검색 품질/성능 검증으로 해석하지 않는다. 약 100문항·부하 단계·지연/비용 목표는 제안/미정이며 실제 평가 세트·runner·모델/부하 실험은 미실행이다.


## 2026-10-25 offline E1 첫 구현

`app/ax/`에 strict/frozen JSON catalog 로더·의존성/활성/예산 검사, 버전 정규화, 메모리 exact 이름 후보 색인을 구현했다. 상세는 offline E1 README (원문 참조 경로: `evaluation/README.md`; 이 기획 묶음에 포함되지 않음)다. 가상 entity 37개와 평가용 사전, 실행 가능한 개발 52개·명시적 미구현 10개를 준비하고 `scripts/evaluate_ax_lookup.py`가 버전/checksum·기대/실제/오류/미구현·반복·lookup smoke 지연을 기록한다.

최소 구현에 대한 평가이며 실제 자연어 추출·DB/fuzzy·후보 ref/관계/coverage·지정 모델·QueryPlan/SQL·인증/FE는 미연결이다. 이름 unique_exact는 최종 resolved가 아니다. 운영 사전 정의의 비활성 상태와 다른 세션의 코드/작업은 유지했다. EVAL-CASES/RUNNER/BASELINE 전체 완료가 아니며 실제 snapshot·수치/SQL 정답·독립 holdout 준비가 다음 과제다.


## 2026-10-25 실제 이름·통계 정답 확장

평가 README (원문 참조 경로: `evaluation/README.md`; 이 기획 묶음에 포함되지 않음)에 실제 DB 이름 snapshot 14,326개·개발 평가19개와 가상 통계14행·기준 SQL oracle12개를 추가했다. snapshot은 단일 READ ONLY REPEATABLE READ로 이름/번역/수정 시각만 추출했다. 외부 ID 0인 감독1건은 원래 값/사유를 metadata에 보존하고 유효 외부 연결 키에서 제외했으며 DB는 변경하지 않았다.

NULL/0·부분 합계·다중 소속·서로 다른 팀별 분모·시즌/대회 경계의 독립 산술 정답을 확인한다. SQL oracle는 로컬 SQLite, PostgreSQL은 bind 컴파일까지만 검증한다. 실제 통계 원천 완전성·생성 SQL/권한·fuzzy·후보 ref/관계·holdout·지정 모델/FE/성능 기준선은 남아 있다.


## 2026-10-25 격리 PostgreSQL repository·정답 재현

PostgreSQL 검증 (원문 참조 경로: `evaluation/postgresql.md`; 이 기획 묶음에 포함되지 않음)에서 로컬 PostgreSQL17.6, 실제+합성 이름14,363개/검색키41,813개로 exact 이름 repository를 구현·검증했다. 실제 이름19개와 기존 통계 oracle12개가 일치하고 권한/버전/잘림/입력 경계 integration44개를 확인한다. SELECT 전 READ ONLY/REPEATABLE READ·statement timeout·최소 권한 계정을 검증하고 source version/snapshot을 보존한다.

projection DDL은 평가용 임시 schema이며 production schema·마이그레이션/적재/갱신·HTTP/auth·모델에 연결하지 않았다. 다음은 production projection/별칭·갱신/회수와 후보 ref/관계·coverage adapter·독립 holdout/지정 모델 PoC다.


## 2026-10-25 사용자 직접 이름 점검 화면

사용자 승인에 따라 DEV `/search/names`에 실제 snapshot 이름/원문/일치 근거·후보 선택·잘림/20개확장·미등록/오류/취소와 light/dark/mobile을 추가했다. 직접 실행 안내 (원문 참조 경로: `evaluation/manual-name-lab.md`; 이 기획 묶음에 포함되지 않음)를 따른다. `run_ax_name_lab.py`는 별도127.0.0.1 API/Vite와 임시 테스트 코드/서버 세션을 사용한다. 실제 사이트 JWT/활성 사용자 구현이 아닌 로컬 도구이며 `app.main`·공통auth/API·운영DB/외부API·worker와 연결하지 않는다. [구현 경계 결정](../../decisions/2026-10-25-ax-local-name-lab.md)을 기록했다.

이 화면에서 사용자는 맨유·맨시티·스미스 등 저장된 표기의 연결을 직접 확인할 수 있다. 선택은 현재 화면 확인이며 서버 candidate ref/소속/시즌/coverage·LLM/통계 실행 확정은 아니다. 실제 계정 로그인 정책과 후속 검색 계약/구현 과제는 유지한다.


사용자 로그인 실패 보고 후 `/search/names`의 전용 서버 종료 및 공통 헤더의 사이트 로그인(8000번) 혼재를 확인했다. 점검 모드의 header/route/proxy를 로컬 API로 한정하고 `--background`/readiness 확인을 추가했다. DB 연결은 변경하지 않았다. 실제 계정 로그인 검증 완료와 구분한다.


## 2026-10-25 서버 후보 문맥·질문 해석 목업

로컬 점검에 세션별 active lookup·서버 candidate_ref/selection_ref·5분TTL·snapshot SHA/후보 원문 수정 버전 검증·선택 해제·복원을 추가했다. 새 조회/취소/세션 종료로 참조를 무효화하고 취소가 요청보다 먼저 도착해도 tombstone으로 늦은 조회를 차단한다. 참조 검증은 pinned snapshot 이름만 대상으로 하며 운영 DB의 live 갱신·최종 의미 판정/SQL 허가는 아니다.

기존 glass 화면에서 ‘이 후보로 서버 확인’ 후 새로고침해 선택을 복원한다. 질문 해석 확인 목업은 서버 확인 팀 이름만 반영하고 대회/시즌/기록은 예시·미검증으로 남긴다. 자유 입력을 파싱/LLM 호출하지 않는다. FE 요구/로컬 endpoint spec과 후속 공개 질문 endpoint 초안을 `ax-candidate-context.md`로 기록했다. 실제 JWT·생산 projection·관계/coverage·Retriever/Planner·SQL은 후속이다.
