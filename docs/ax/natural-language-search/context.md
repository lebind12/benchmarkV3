# 현재 컨텍스트

기준일: 2026-10-25. 이 문서의 구현·설치 상태는 당시 로컬 확인 기록이다.

## 1. 사용자 지시와 현재 단계

1. 상위 `plan.md`의 AX 기능 중 자연어 검색을 검색창 목업부터 진행한다.
2. 글래스모피즘 배경과 검색창을 사용한다. 검색창은 한 줄로 시작해 긴 입력에 따라 아래로 확장하고 삭제 시 축소한다.
3. 다크 모드, 높이 변화 애니메이션, 검색 중·결과 등장 애니메이션을 제공한다.
4. 오래 걸리는 검색에서는 로딩 문구 목록을 순환한다.
5. 사용자는 목업이 현재 수준이면 충분하다고 확인했다. 이후 기술 스택 점검과 관련 AX 사례 조사를 진행했다.
6. 조사 자료와 현재 작업 컨텍스트를 전용 디렉터리에 모으고 별도 `plan.md`를 작성하도록 요청했다.
7. 사전 규칙 요청은 의미/관리 원칙만이 아니라 **사전·이름 조회를 실제로 수행할 구체 계획**을 뜻한다고 사용자가 정정했다. 조회 담당 모델·도구·검색/선택 순서·문맥 전달은 [entity-resolution.md](entity-resolution.md)를 우선 읽는다. Retriever/Planner 역할 분리와 bounded tool calling은 현재 구현 제안이며 실제 모델 호출은 미검증이다.

추가 사용자 결정: Vertex AI의 Gemini 4 Argon(`gemini-4-argon`) 사용, 로그인 필수, 기존 API-Football 기반 Supabase DB 재사용, 축구 지표·이름·별칭 연결 사전 우선. [결정 기록](../../decisions/2026-10-25-natural-language-search.md)을 따른다. 후속 기술 선정으로 SQLAlchemy Core·SQLGlot·Google Gen AI SDK·JSON 사전/DB 별칭·pg_trgm을 채택했다. [선정 결정](../../decisions/2026-10-25-natural-language-search-stack.md)을 따른다. 정확 패키지 버전·사전 세부 schema·운영 한도는 후속 검증 항목이다. 결정과 실제 구현은 구분한다.

## 2. 현재 구현과 증거

| 항목 | 상태 / 근거 |
|---|---|
| 진입 | 헤더 검색 메뉴 → `/search`, [라우터](../../../frontend/src/router/index.ts) |
| 화면 | [SearchMockView.vue](../../../frontend/src/views/SearchMockView.vue), 프론트 로컬 상태·예시 데이터 |
| 입력 | 한 줄 시작, 최대 7줄, 자동 확장·축소, Enter 제출·Shift+Enter 줄바꿈·한글 조합 보호 |
| 디자인 | 라이트/다크 글래스, 포커스·포인터 반사광, 높이 260ms 전환 |
| 로딩 | 기본 900ms의 모의 대기, 6개 문구를 2.8초마다 순환, 18초 긴 검색 미리보기 |
| 결과 | 선수 목록·순위·팀 비교·조건 수정·확인 질문·0건·미수집·미지원·조회 제한·실패 예시 |
| 동작 범위 | 자유 입력은 실제 검색 미연결을 안내한다. 실제 자연어 해석·검색 API·DB 조회·외부 호출·polling 없음 |
| 상세 링크 | 실제 ID를 검증하지 않았으므로 가짜 링크를 만들지 않았다. 실데이터 연동 시 필요 |
| 검증 기록 | 마지막 관련 변경에서 `npm run build`, [Playwright 7개](../../../frontend/e2e/search-mock.spec.ts) 통과 |
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
| [app/db.py](../../../app/db.py), [config.py](../../../app/core/config.py) | 공통 SQLAlchemy 동기 engine/session, 작은 기본 pool, OpenAI·Vertex 설정 존재 | 검색 전용 engine/role/timeout/취소 경로 필요. LLM 대기 중 DB 연결을 점유하지 않도록 설계 |
| [player.py](../../../app/models/player.py) | 득점·도움·출전 시간·평점 등, 선수×팀×대회×시즌 단위 통계와 JSONB 원본 | 다중 소속·합계·평점·비율·NULL 정의 필요 |
| [fixture.py](../../../app/models/fixture.py) | 경기 결과 컬럼, 상세 통계·라인업 등의 JSONB | JSON 필드 존재만으로 데이터 수집을 보장하지 않음 |
| [general.py](../../../app/services/general.py) | 이름 부분 검색, 기존 선수 목록은 현재 시즌 기준 | 자연어 조건/집계용 서비스와 최신 2시즌 적용 경로를 별도 설계 |
| [league.py](../../../app/models/league.py), [worker_sync_log.py](../../../app/models/worker_sync_log.py) | 대회/대상 설정·공급자 capability·실행 로그 존재 | 실제 영역별 coverage와 구분해야 함 |
| [broadcast_ai_commentary.py](../../../app/services/broadcast_ai_commentary.py) | Vertex 인증·HTTP 호출과 방송용 프리뷰 생성 존재 | 인증/통신 기반은 참고 가능. 검색에 방송 live/web grounding 경로를 그대로 연결하지 않음 |
| [번역 OpenAI 클라이언트](../../../app/workers/translation_filler/openai_client.py) | OpenAI 호출·재시도·응답 파싱 기반 존재 | 검색용 구조화 계획·모델·예산은 별도 설계 |

## 5. 확인하지 않은 사항

- 운영 PostgreSQL 버전·현재 role·view 권한·Supabase 연결 모드·남은 연결 수.
- 대회×시즌×영역별 실제 행 수·결측·중복·최근 성공 시각·부분 실패.
- 검색에 사용할 지표의 정확한 집계 의미와 기준 SQL 결과.
- 지정 모델 `gemini-4-argon`의 계정/리전 접근·호출 호환성·구조화 출력·한국어 정확도·실측 지연·비용.
- 채택한 SQLGlot 검사 계층의 PostgreSQL 구문 coverage·바인딩 정합·우회 차단 성능, pg_trgm 운영 활성/한글 검색 품질.
- 로그인 검증의 실제 검색 연결, 사용자별 제한과 전체 비용 상한. 비로그인 검색은 허용하지 않는다.

## 6. 다음 작업의 진입점

[dictionary-design.md](dictionary-design.md)를 기준으로 용어/엔티티 연결 사전을 우선 구체화한다. [plan.md](plan.md)의 AX-9 읽기 전용 데이터 점검을 함께 수행해 실제 컬럼·ID·누락과 연결한다. 목업을 완료했다는 이유로 AX-9~12 전체를 완료 처리하지 않는다. 현재 세션의 변경은 별도 브랜치로 분리했으며 기존 체크아웃의 관리·홈 미커밋 작업은 그대로 보존했다. [분리 기록](branch-isolation.md)을 따른다.
