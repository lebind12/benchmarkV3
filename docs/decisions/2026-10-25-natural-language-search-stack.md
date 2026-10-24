# 2026-10-25 — 자연어 검색 구현 기술 선정

## 결정 배경

사용자가 비교군 점검 이후 후보군 확정과 문서 작성을 요청했다. 아래를 검색 구현의 채택 기술로 정한다. 기존 [모델·접근·데이터 결정](2026-10-25-natural-language-search.md)을 유지한다. 선택 근거와 검토한 대안은 [비교 문서](../ax/natural-language-search/stack-comparison.md)에 남긴다.

## 채택 기술

| 역할 | 채택 | 선정 이유 |
|---|---|---|
| 검색 FE | 기존 Vue 3·TypeScript·Zod | 목업과 응답 검증 기반 재사용 |
| 검색 API | 기존 FastAPI | 기존 인증·서비스·테스트 구조 활용 |
| 인증 | 기존 JWT 세션과 서버 사용자 검증 | 활성 USER/STREAMER/ADMIN의 로그인 필수 정책 적용 |
| LLM | Vertex AI `gemini-4-argon` | 사용자 지정 모델/공급자 유지 |
| LLM 클라이언트 | Google Gen AI Python SDK (`google-genai`) | 구조화 응답·타입·비동기 호출 활용. 검색 전용 어댑터로 격리 |
| QueryPlan/사전 검증 | Pydantic | 기존 설치 활용, 타입/범위와 서버 의미 규칙 검증 |
| SQL 조립 | SQLAlchemy Core | 기존 기반에서 허용된 조건·관계·집계를 조합하고 값 바인딩 |
| SQL 구조 검사 | SQLGlot, PostgreSQL 방언 | AST 전체 순회로 문장·참조·함수·관계 allowlist 검사 |
| SQL 실행 | 기존 SQLAlchemy + psycopg | 기존 Supabase DB의 전용 읽기 role/view·별도 작은 pool 사용 |
| 지표/범위/관계 사전 | 버전 관리되는 JSON 파일 + Pydantic | 새 YAML 의존성 없이 리뷰/버전 관리, Python 표현식 registry와 연결 |
| 이름/별칭 사전 | 기존 entity/번역 + DB 별칭 테이블 | 실제 ID/FK 연결, 표시명과 검색 별칭 분리, 근거와 여러 후보 관리 |
| 이름 후보 검색 | 정규화/정확 일치 우선 + PostgreSQL `pg_trgm` | 기존 DB 안에서 후보 탐색, 유사도는 자동 확정이 아닌 후보 제시에 사용 |
| 평가 | 기존 pytest·Playwright | 독립 정답 세트·SQL/권한·검색 흐름 검증 |

## 선정에 따른 구현 규칙

- LLM은 typed QueryPlan 또는 확인 질문을 반환한다. 모델 원문 SQL을 실행하지 않는다.
- JSON 사전에는 지표 key·표현·단위·허용 연산·집계/NULL 규칙·서버 표현식 참조를 둔다. JSON의 SQL/산식 문자열을 `eval`하거나 그대로 실행하지 않는다.
- SQLAlchemy는 서버가 등록한 view·컬럼·함수·관계 표현식만 조합한다. 값은 바인딩하고 모델의 식별자 문자열을 직접 SQL로 삽입하지 않는다.
- SQLGlot의 파싱 성공이 PostgreSQL 문법·카탈로그·권한·의미 검증 완료를 뜻하지 않는다. 제한된 읽기 role의 EXPLAIN(ANALYZE 없음), 실행 timeout·동시성·행/byte·비용 제한을 함께 둔다.
- 검사 불가/미인식 구문·노드·함수는 차단한다. 파서가 재작성한 SQL을 무검증 실행하지 않는다. 검사/실행의 바인딩·구조 정합을 테스트한다.
- 별칭 테이블의 구체 분리/컬럼/동시 수정 방식은 실제 entity 조사와 명세에서 결정한다. 실제 FK를 보장하고 동일 별칭의 여러 후보를 허용한다. 관리 UI/API는 선제 구현하지 않는다.
- `pg_trgm`의 운영 활성 여부·한글/짧은 이름·성능·인덱스를 검증한 뒤 유사 검색을 연결한다. 별칭 매핑의 의미를 문자열 유사도에 맡기지 않는다.
- SDK의 Vertex 인증·리전·구조화 출력·timeout/retry·사용량 응답을 지정 모델로 확인한다. 검색 설정을 분리하고 방송/프리뷰 모델은 변경하지 않는다.

## 채택하지 않는 대안

- pglast/sqlparse: 초기 의존성에 넣지 않는다. SQLGlot의 요구 충족 실패가 입증되면 결정 기록을 갱신해 재검토한다.
- SQLGlot builder: 주 SQL 조립기로 사용하지 않는다. 검토된 SQL 템플릿은 기준 SQL/고정 내부 질의에만 보조 활용한다.
- 직접 REST 검색 어댑터: 초기 검색 구현은 SDK로 통일한다. 기존 방송 REST 코드를 일괄 교체하지 않는다.
- YAML 사전·RapidFuzz·asyncpg·별도 jsonschema validator: 초기 추가 의존성에서 제외한다.
- 벡터 DB·별도 검색 서버·에이전트 프레임워크·SSE·검색 응답 캐시 확대: 초기 구성에서 제외한다.

## 확정과 미검증의 경계

기술 채택은 확정했으나 신규 패키지 설치·DB 확장/마이그레이션 적용·모델 실호출·정확도/부하/공격 테스트·검색 인증/실제 연동은 완료하지 않았다. 패키지 정확 버전은 구현 시 호환/회귀 검증 후 고정한다. SDK는 [공식 Argon 가이드](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/guides/gemini-4-argon)의 Python 요구 버전 `google-genai >= 2.30.1`을 충족하도록 검증한다. SQLGlot 버전과 PostgreSQL 방언도 고정·회귀 검증한다.

다음 작업은 사전 정의와 기존 DB의 ID/컬럼/coverage 확인이다. 그 뒤 FE 계약·BE 명세/테스트·구현·연동 순서를 따른다. 이번 요청은 문서화이며 패키지 설치·운영 변경·배포를 수행하지 않는다.
