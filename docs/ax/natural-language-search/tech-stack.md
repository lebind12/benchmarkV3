# 기술 스택 — 채택 구성과 검증 과제

확인일: 2026-10-25. 로컬 의존성과 코드 점검 결과이며 운영 배포 버전·접근 가능 모델을 확인한 기록은 아니다.

사용자의 후보군 확정 요청에 따라 SQLAlchemy Core·SQLGlot·Google Gen AI SDK·JSON 사전/DB 별칭·pg_trgm을 채택했다. [선정 결정](../../decisions/2026-10-25-natural-language-search-stack.md)이 현재 구현 기준이며 [비교 문서](stack-comparison.md)는 선택 근거를 보존한다. 기술 채택과 설치/운영 검증 완료는 구분한다. 파싱 성공만으로 실제 PostgreSQL 문법·스키마·권한·질문 의미가 검증되는 것은 아니다.

## 1. 재사용 가능한 기반

| 영역 | 확인한 기반 | 사용 방향 |
|---|---|---|
| FE | Vue 3·TypeScript·Pinia·Zod, 검색 목업 | typed 응답 검증·목록/순위/비교·조건 재질문 |
| API | FastAPI 0.136.1 | 검색 endpoint·오류/제한·인증 정책 연결 |
| 스키마 | Pydantic 2.13.4 | QueryPlan·응답·의미 검증. 외부 출력은 신뢰하지 않음 |
| SQL 조립 | SQLAlchemy 2.0.49 | 허용된 관계·연산으로 매개변수 SQL 구성 |
| DB 드라이버 | psycopg 3.3.4 | 별도 읽기 연결·pool·timeout·취소 |
| DB | Supabase Postgres | 축구 데이터용 view·role·실행 비용 검사. 실제 버전/권한 미확인 |
| OpenAI | Python SDK 2.37.0 | 기존 설치 기록. 자연어 검색 공급자로 사용하지 않음 |
| Google | google-auth·httpx 기반 Vertex 호출 코드 | Vertex AI + `gemini-4-argon` 지정. 기존 인증 활용, 검색 전용 어댑터/설정·실제 호출 검증 필요 |
| 검증 | pytest·Playwright | SQL 기준답안·권한·부하·UI 연동 검증 |

의존성 정의는 [pyproject.toml](../../../pyproject.toml), [requirements.txt](../../../requirements.txt), [frontend/package.json](../../../frontend/package.json)을 따른다. 위 숫자는 권장 최신 버전이나 고정 버전 결정이 아니다.

## 2. 추가할 계층과 채택 기술

| 계층 | 구현할 책임 | 선택 상태 |
|---|---|---|
| 의미 사전 | 지표·분모·집계·관계·시즌·NULL·지원 범위 | 사용자 지정 우선 과제. JSON 파일 + Pydantic, [사전 설계](dictionary-design.md) |
| 엔티티 해석 | 한글/영문/별칭 → 후보 ID, 모호함 확인 | 기존 원문/번역명 + DB 별칭 테이블, 정확 일치 우선·pg_trgm 후보 검색 |
| LLM 어댑터 | 구조화된 계획/확인 질문, deadline·실패 처리·비용 기록 | Google Gen AI SDK로 Vertex AI `gemini-4-argon` 호출/검증 |
| QueryPlan 검증 | 연산·지표·관계·범위 allowlist, 식별자 검증 | Pydantic 채택. 실제 ID·관계·조건 의미는 서버 규칙으로 추가 검증 |
| SQL 조립/검사 | 매개변수 SQL, 단일 문장·전체 트리·함수/참조 검사 | SQLAlchemy Core 조립 + SQLGlot PostgreSQL AST 검사. SQLGlot 미설치 |
| 검색 실행 | 전용 계정·view·pool·EXPLAIN·실행 제한·취소 | 필요. 운영 지원 확인 전 공개 불가 |
| coverage | 대회×시즌×영역별 수집/누락/부분 실패·시각 | 필요. 기존 capability·로그와 구분 |
| 평가/진단 | 기준 SQL/ID/값/순서, 단계별 오류·지연·비용 | 필요. 기존 테스트 기반 활용 |

SQLGlot은 [SQL 파싱·트리 순회 기능](https://sqlglot.com/sqlglot.html)을 제공하지만 보안 정책 엔진 자체는 아니다. PostgreSQL 방언과 버전을 고정해 검증하고, 파서가 허용하지 못하는 구문은 차단한다. 모델 원문 SQL을 운영 DB에 직접 전달하지 않는다.

## 3. 지정 LLM의 적용·검증

- 사용자 결정으로 Vertex AI의 Gemini 4 Argon을 사용한다. [공식 가이드](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/guides/gemini-4-argon)에서 호출 ID `gemini-4-argon`을 확인했다. 공급자 비교 선정을 지정 모델의 실측 검증으로 바꾼다.
- 기존 Vertex 인증 기반은 활용하되 검색 모델 설정은 방송/프리뷰와 분리한다. 해당 기능의 공통 모델·운영 환경변수는 이번 문서에서 변경하지 않는다.
- 기존 방송 코드의 `thinkingBudget` 등 매개변수를 그대로 복사하지 않는다. 공식 가이드는 Argon에서 thinking level 사용을 설명하며, 실제 전송 형식·지원 매개변수는 검색 호출에서 검증한다. SDK 도입 시 요구 버전도 확인한다.
- [Google 공식 문서](https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/control-generated-output)는 응답 스키마 기반 구조화 출력을 설명한다. 지정 모델의 지원 스키마 제약을 확인한다.
- 구조가 유효한 응답도 의미가 틀릴 수 있다. 이름·시즌·집계 정답, 재질문/거절, 지연 p50/p95, 토큰·요청 비용을 같은 평가 세트로 비교한다.
- refusal·출력 중단·파싱 실패·429·deadline을 처리한다. 재시도 횟수와 전체 예산을 제한한다.
- 질문 해석에는 필요한 스키마/의미 정보만 전달한다. 실제 데이터 값이 필요할 때 허용된 공개 축구 데이터로 범위를 제한한다.

## 4. DB 실행 설계에서 점검할 사항

- 기존 SQLAlchemy+psycopg를 유지한다. asyncpg는 초기 추가 의존성에서 제외한다. API/LLM 대기 중 이벤트 루프를 막지 않고 DB 연결도 잡아두지 않도록 실행 경계를 검증한다.
- 검색 전용 계정은 비소유·비superuser·비BYPASSRLS이고 허용 view에 필요한 권한만 갖는다. view 소유자 권한·기본 PUBLIC 함수 권한 등 우회 경로도 검사한다.
- [Supabase 연결 문서](https://supabase.com/docs/guides/database/connecting-to-postgres)는 사용자 정의 role 연결을 지원한다. 현재 프로젝트의 연결 모드·계정·연결 수는 별도 확인한다.
- [PostgreSQL 설정 문서](https://www.postgresql.org/docs/current/runtime-config-client.html)를 참고해 role/트랜잭션 범위 제한을 설계하되 실제 운영 버전에서 검증한다.
- EXPLAIN은 ANALYZE 없이 실행한다. 계획 비용은 추정이므로 실행 timeout·동시성·행/열/byte 제한도 둔다.
- 단일 인스턴스의 동시성 제한은 서버 내부 방식부터 검토한다. 비용 집계의 영속성·재시작 시 동작은 별도로 설계한다. Upstash 용도 확대를 자동 승인하지 않는다.

## 5. 채택 구성

검색은 로그인 필수로 하고 기존 세션/사용자 검증을 서버에 연결한다. 데이터는 API-Football로 수집한 기존 Supabase DB를 그대로 조회한다. 검색용 view·읽기 계정은 같은 DB의 접근 경로를 제한하기 위한 구성이다.

`Vue/Zod → FastAPI 로그인 검증 → JSON 지표/범위 + DB 이름/별칭(pg_trgm 보조) → Google Gen AI SDK/Vertex gemini-4-argon → Pydantic → SQLAlchemy Core → SQLGlot + PostgreSQL 제한 검사/실행`

벡터 DB·Elasticsearch·별도 에이전트 프레임워크·SSE는 초기 필수 구성으로 두지 않는다. 데이터/스키마 규모와 지연 측정으로 필요성을 판단한다. 현재 로딩 애니메이션은 로컬 UI 상태이며 실제 서버 처리 단계나 스트리밍 구현의 근거가 아니다.
