# 자연어 검색 기술 스택 비교

확인일: 2026-10-25. 로컬 설치/코드 점검, 공식 문서 검토, DB에 접속하지 않는 SQLAlchemy 컴파일 확인을 수행했다. 후보 패키지 설치·파서 실험·DB 권한/확장/성능·Vertex 실호출은 수행하지 않았다. §1~7은 선정 전 점검·비교 기록이다. 후속 후보군 확정 요청에 따른 현재 결정은 §8과 [기술 선정 기록](../../decisions/2026-10-25-natural-language-search-stack.md)을 따른다.

## 1. 확정 사항과 로컬 상태

Vertex AI `gemini-4-argon`, 로그인 필수, 기존 API-Football 기반 Supabase DB 사용은 [사용자 결정](../../decisions/2026-10-25-natural-language-search.md)으로 유지한다. 공급자·모델·데이터베이스를 교체하는 비교는 하지 않는다.

| 설치 확인 | 버전 |
|---|---|
| FastAPI | 0.136.1 |
| SQLAlchemy | 2.0.49 |
| Pydantic | 2.13.4 |
| psycopg | 3.3.4 |
| httpx | 0.28.1 |
| google-auth | 2.54.0 |

`google-genai`, `sqlglot`, `pglast`, `sqlparse`, `rapidfuzz`, `jsonschema`는 현재 로컬 가상환경에 설치되어 있지 않다. DB 확장인 `pg_trgm`의 활성 여부는 미확인이다. 위 버전은 로컬 설치 기록이며 최신 버전 권장이 아니다.

## 2. SQL 조립: SQLAlchemy Core 우선 제안

| 비교군 | 특징 | 이 프로젝트의 판단 |
|---|---|---|
| SQLAlchemy Core | `select`·조건·조인·집계·바인딩을 Python 표현식으로 조합 | 기존 설치 활용. 허용된 지표/컬럼/관계 registry를 표현식으로 조립하는 우선 후보 |
| SQLGlot SQL builder | SQL AST를 만들고 방언별 SQL로 변환 | 검사와 SQL 표현식을 통일할 수 있지만 기존 SQLAlchemy 실행과 바인딩 연결을 별도로 검증해야 함 |
| 검토된 SQL 템플릿 | 개발자가 작성한 SQL에 값만 바인딩 | 고정 view·기준 SQL·검증 예시에 유용. 자유로운 조건/집계 조합의 주 조립기는 Core로 두는 제안 |

근거: [SQLAlchemy Expression API](https://docs.sqlalchemy.org/en/20/core/expression_api.html), [SELECT 구성](https://docs.sqlalchemy.org/en/20/tutorial/data_select.html), [SQLGlot](https://sqlglot.com/sqlglot.html).

SQLAlchemy 사용 자체가 임의 식별자·SQL 주입을 차단한다는 뜻은 아니다. 모델의 문자열을 `text()`·컬럼명·함수명으로 직접 넘기지 않고, 서버가 허용한 표현식만 선택한다. 조건값은 파라미터로 바인딩한다.

## 3. SQL 파서: SQLGlot과 pglast를 실제 쿼리로 비교

| 비교군 | 공식 문서에서 확인한 특성 | 검증/유지 과제 | 초기 판단 |
|---|---|---|---|
| SQLGlot | 여러 방언 지원, AST 순회·변환·생성, Python 기반 | PostgreSQL 방언 고정, 전체 트리/참조/함수 정책 직접 구현. 관대한 파서이므로 파싱 성공이 DB 문법/의미 검증을 보장하지 않음 | 정책 검사 코드 작성의 우선 실험 후보 |
| pglast | `libpg_query`에 포함된 PostgreSQL 파서의 구문 트리를 Python으로 노출 | 내장 PostgreSQL 파서 버전과 운영 버전 정합, native extension 배포, 노드 순회 정책 작성 | PostgreSQL 전용 구조/문법 검사 비교 후보 |
| sqlparse | SQL 분리·서식·토큰 트리 탐색, non-validating parser | 문법·참조·안전성 검증을 제공하지 않으므로 주 검사기로는 부족 | 단독 SQL 게이트에서 제외 제안 |

근거: [SQLGlot 문서/FAQ](https://sqlglot.com/sqlglot.html), [pglast 개요](https://pglast.readthedocs.io/en/latest/), [pglast parser](https://pglast.readthedocs.io/en/latest/parser.html), [sqlparse 개요](https://sqlparse.readthedocs.io/en/stable/).

공식 라이선스 표기는 SQLGlot [MIT](https://github.com/tobymao/sqlglot/blob/main/LICENSE), pglast [GPL-3.0-or-later](https://pglast.readthedocs.io/en/latest/)다. 실제 도입 버전의 배포 조건까지 선정 시 확인한다. 이 문서는 법적 적용 판단을 하지 않는다.

두 파서 중 하나를 선정하기 전에 다음을 같은 입력으로 확인한다.

- 정상: join·집계·NULL·비율·window·CTE·quoted identifier·필요 JSONB 표현식.
- 거부: 여러 문장·변경 명령/CTE·위험 함수·허용 밖 schema/table·금지 관계·재귀/과도한 복잡도·파서의 미인식 노드.
- table alias·CTE 이름과 실제 테이블 참조를 구분하고 하위 쿼리 전체를 검사하는 구현 난이도.
- SQLAlchemy 바인딩, 파라미터 순서, 검사 SQL과 실행 SQL의 구조 정합.
- 제한된 PG 문법/관계 검사 뒤에도 별도 role/view·EXPLAIN·실행 timeout·비용/동시성 제한 유지.

파서는 스키마 실재 여부·권한·조건 의미·비용을 자동 보장하지 않는다. pglast도 해당 DB의 카탈로그나 데이터에 접속하지 않는다. PostgreSQL 자체의 EXPLAIN은 읽기 role로 제한해서 수행하며 ANALYZE는 사용하지 않는다.

## 4. 용어 사전 저장과 이름 후보 검색

### 저장 방식

| 비교군 | 장점 | 고려할 점 | 제안 |
|---|---|---|---|
| 코드/JSON/YAML 파일 | 변경 리뷰와 버전 관리가 쉽고 지표 규칙을 서버 표현식에 연결 가능 | 운영 중 변경에 배포가 필요할 수 있음. YAML이면 로더 의존성과 안전한 읽기 필요 | 지표·범위·관계의 초기 정의에 적합 |
| 기존 DB + 별칭 테이블 | 실제 entity와 FK 연결, 근거·중복 후보·갱신 이력 관리 가능 | 마이그레이션·수정 책임/권한 정의 필요 | 이름/별칭에 우선 검토 |
| 파일/DB 혼합 | 지표 규칙은 코드 리뷰, 많은 엔티티 이름은 DB에서 조회 | 버전·참조 정합 규칙 필요 | 현재 권장 방향, 스키마 미확정 |

### 검색 방식

| 비교군 | 역할과 근거 | 판단 |
|---|---|---|
| 정규화 + 이름/별칭 정확 일치 | 기존 원문/번역명·실제 ID를 활용 | 첫 단계. 검토된 별칭과 동명이인 규칙이 핵심 |
| PostgreSQL `pg_trgm` | trigram 유사도와 GiST/GIN 인덱스를 제공. [공식 문서](https://www.postgresql.org/docs/current/pgtrgm.html) | DB에서 오타/표기 후보를 찾는 우선 실험 후보. 확장·인덱스와 짧은 한글 질의의 품질/성능 확인 필요 |
| RapidFuzz | Python의 문자열 유사도/거리 계산. [공식 문서](https://rapidfuzz.github.io/RapidFuzz/) | 작은 후보 집합의 재정렬에 검토. 매 요청마다 전체 선수명을 Python으로 가져오는 방식은 피함 |
| 임베딩 검색 | 의미가 가까운 설명/예시를 찾는 후보 방식 | 이름/ID의 정확 연결은 별도 필요. 현재 필수 인프라로 채택하지 않음 |

문자열 유사도만으로 통용 별칭의 의미를 알 수는 없다. 검토한 별칭 매핑이 필요하며, 유사 검색은 후보 탐색에 사용한다. 높은 점수만으로 한 명을 확정하지 않는다. 지표/시즌/경기 범위 해석은 [사전 설계](dictionary-design.md)의 별도 규칙을 따른다.

## 5. Vertex 호출 방식

| 비교군 | 장점 | 고려할 점 | 제안 |
|---|---|---|---|
| 기존 google-auth + httpx REST | 기존 인증·네트워크 기반 재사용, 새 SDK 없이 요청/timeout 통제 | 모델별 body·응답·오류·구조화 출력 처리 직접 구현. 기존 방송용 매개변수 복사 금지 | 의존성 최소 대안 |
| Google Gen AI SDK (`google-genai`) | 공식 클라이언트·타입/스키마·비동기 API 활용 | 새 의존성, 지정 모델 지원 버전·인증 방식·timeout/retry·사용량 응답 실호출 검증 | 검색 전용 어댑터의 우선 실험 후보 |

근거: [SDK 공식 문서](https://googleapis.github.io/python-genai/), [Argon 개발 가이드](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/guides/gemini-4-argon).

SDK 사용도 Vertex 인증을 유지하는 방식이며 공급자를 바꾸는 것이 아니다. 기존 방송/프리뷰 호출은 그대로 두고 검색 경로에서만 검증한다. 공식 Argon 가이드는 SDK 사용 시 Python `google-genai >= 2.30.1`을 안내한다. 이 하한만으로 실제 호출/호환성을 보장하지 않으므로 구현 시 버전을 고정하고 확인한다.

## 6. 계획 검증·실행·평가

- **Pydantic vs 별도 JSON Schema validator:** 기존 Pydantic의 strict 검증과 필드/모델 검증을 우선 활용한다. strict 모드의 JSON 입력 예외까지 확인하고 enum·범위·허용 관계·실제 ID를 서버에서 검증한다. 구조화된 출력의 형식 준수는 질문의 정답을 보장하지 않는다. [Pydantic 문서](https://docs.pydantic.dev/latest/concepts/strict_mode/)
- **psycopg 유지 vs asyncpg 추가:** 현재 SQLAlchemy+psycopg를 유지하는 것이 출발점이다. LLM 대기와 DB 실행을 분리하고 비동기 API에서 동기 DB 처리가 이벤트 루프를 막지 않도록 설계한다. 드라이버 변경은 실측 필요성이 생기면 검토한다.
- **서버 자체 흐름 vs 에이전트 프레임워크:** 지금은 단계가 제한된 검색 API이므로 명시적인 서비스 함수와 상태/응답 타입부터 구성한다. 프레임워크 도입은 도구/흐름 복잡도와 진단 필요로 판단한다.
- **기존 pytest/Playwright:** 기준 SQL·ID·값·순서·재질문·보안/권한·지연/비용을 측정한다. 후보마다 같은 입력으로 비교하며 패키지 이름만으로 정확도·속도 우열을 단정하지 않는다.

## 7. 로컬 컴파일 확인과 남은 검증

SQLAlchemy Core로 임시 논리 테이블에 대한 SELECT·조건·정렬·LIMIT를 구성하고 PostgreSQL 방언으로 컴파일했다. 실제 DB 엔티티를 매핑한 검증은 아니다.

```sql
-- PostgreSQL 파서에 전달할 수 있는 형태의 컴파일 예시
SELECT review_only_stats.player_id, review_only_stats.goals
FROM review_only_stats
WHERE review_only_stats.season_year = $1 AND review_only_stats.goals >= $2
ORDER BY review_only_stats.goals DESC
LIMIT $3
```

같은 표현식의 psycopg용 출력은 `%(season)s` 같은 placeholder를 사용했다. 따라서 파서 입력과 드라이버 실행 입력의 차이를 다루어야 한다. 문자열 치환이나 사용자 값을 SQL에 삽입하는 방식 대신, 같은 검증된 표현식에서 검사/실행용 출력을 만들고 매개변수 순서·타입·구조 정합을 테스트한다. 파서가 재작성한 SQL을 무검증 실행하지 않는다. [psycopg 바인딩 문서](https://www.psycopg.org/psycopg3/docs/basic/params.html)

이 확인으로 Core 조립 가능성만 검증했다. 두 파서의 해당 SQL 수용·공격 차단·DB 실제 실행, pg_trgm 확장/한글 품질, SDK 호출/비용은 미검증이다.

## 8. 후속 확정 — 현재 구현 기준

사용자의 후보군 확정 요청에 따라 아래를 채택했다. 상세 경계는 [기술 선정 결정](../../decisions/2026-10-25-natural-language-search-stack.md)을 따른다.

| 역할 | 확정 기술 |
|---|---|
| API/인증 | FastAPI + 기존 JWT/활성 사용자 검증 |
| LLM/클라이언트 | Vertex `gemini-4-argon` + Google Gen AI Python SDK |
| 계획/사전 검증 | Pydantic |
| SQL 조립 | SQLAlchemy Core |
| SQL 구조 검사 | SQLGlot, PostgreSQL 방언 + 서버 allowlist |
| DB 실행 | 기존 Supabase + SQLAlchemy/psycopg, 검색 전용 읽기 role/view·pool |
| 지표/범위/관계 | JSON 파일 + Pydantic + 서버 표현식 registry |
| 이름/별칭 | 기존 entity/번역 + 실제 FK를 보장하는 DB 별칭 테이블 |
| 이름 후보 검색 | 정규화/정확 일치 우선 + PostgreSQL pg_trgm |
| 검증 | pytest + Playwright |

pglast·sqlparse·SQLGlot builder·검색 직접 REST 어댑터·YAML·RapidFuzz·asyncpg·별도 jsonschema validator는 초기 추가 구성에서 제외한다. 별도 벡터 DB/검색 서버/에이전트 프레임워크도 도입하지 않는다.

기술 선택은 확정되었으나 정확 버전·운영 확장·실제 API·파서 안전성·한국어 검색 품질·지연/비용 검증은 남아 있다. 검증 실패가 입증되면 결정을 명시적으로 갱신하며 다른 후보로 조용히 대체하지 않는다. 현재 문서 작성에서 패키지 설치·스키마 적용·배포를 수행하지 않았다.
