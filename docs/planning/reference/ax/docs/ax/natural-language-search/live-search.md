> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/ax/natural-language-search/live-search.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 실제 검색 v1 — 로컬 개발 구현

2026-10-25 최신 화면/문맥 경로는 [대화형 검색 v1](conversational-search.md)을 따른다. 아래 단발 검색 단계의 기록과 구분한다.


2026-10-25. 목업 이후 S-3~9의 첫 실행 가능한 수직 경로를 구현했다. **운영 공개·전체 지원 범위·품질 인수 완료와 구분한다.** 직접 사용은 사용 안내 (원문 참조 경로: `evaluation/manual-live-search.md`; 이 기획 묶음에 포함되지 않음), 재현 근거는 검증 보고서 (원문 참조 경로: `evaluation/reports/live-search-20261025.json`; 이 기획 묶음에 포함되지 않음)를 따른다.

## 구현 범위

`/search/live` → 실제 계정 로그인 → Vertex `gemini-4-argon` → 서버 사전/이름/시즌/자료 범위 도구 → 구조화 계획 → 사용자 조건 확인 → Core SQL 조립/SQLGlot 검사 → 전용 SELECT-only role → 실제 저장 결과다. 서버는 모델 생성 SQL을 받지 않는다. 지정 모델 접근과 구조화 출력·수동 function calling이 실제 계정에서 확인됐다. 모델 제품을 추가하지 않고 동일 모델의 Retriever와 Planner 역할을 나눈다.

현재 선수×대회×시즌의 득점, 도움, 출전 시간/횟수, 경고, 퇴장, 득점+도움, 90분당 득점 8개를 지원한다. 목록·순위·최대 두 선수 비교, 한 대회/시즌, 팀/선수와 지표 조건을 조합한다. 원천별 정의 정본은 `app/ax/search_types.py`의 `METRICS`다. 기존 `semantic-catalog.json` 전체는 여전히 비활성 설계 초안이며 모든 지표를 활성화한 것이 아니다. 유사 검색(pg_trgm), 새 별칭 관리, 팀/경기 통계, 평점·국적·포지션·여러 대회·실시간은 미지원이다. 일반 사이트의 실제 상세 slug를 수집·검증하지 않아 결과 상세 링크는 제공하지 않는다.

이름은 실제 DB의 원어/한국어/짧은 이름 14,326개에 연결한다. 원문에 존재하는 연속 표현으로 정확 조회하고, 호출마다 서버가 후보 ref를 발급한다. type은 힌트이며 전역 충돌·잘림을 숨기지 않는다. 후보의 모호함은 사용자 확인이 필요하다. 조회하지 않은 ID/ref, 찾지 못한 이름 조건을 빼고 나머지를 실행하는 경우, 조회한 이름 조건을 계획에서 누락한 경우는 차단한다. 오타는 정확 후보 없음으로 안내한다. 자연어 의미를 모든 경우에 서버가 독립 검증할 수 있다는 보장은 없으며 추가 독립 평가가 필요하다.

최신 두 시즌은 카탈로그의 현재 시즌과 그보다 작은 실제 직전 시즌이다(월드컵 2026/2022 등). 활성 대회/수집 대상/current 시즌 정책 충돌은 차단한다. 현재 설정이 일치하는 EPL/UCL/UEL/카라바오컵부터 조회하며 FA컵/월드컵 등을 임의로 설정 변경하지 않는다. source rows는 일부 수집 상태로 표시하고 complete라고 추론하지 않는다. 일부 팀 row의 필수 원천 값이 NULL이면 해당 선수의 합계도 NULL이다. per90는 팀 row 합계의 비율이며 양수 분모/사용자가 지정한 최소 출전 분이 필요하다. 모든 원천이 미상인 범위와 알려진 값에서 조건에 맞는 행이 없는 경우를 구분한다. 동률은 원시값 공동순위/ID 안정정렬, 상위 N은 행 상한이다.

## 인증과 데이터 분리

이 AX checkout의 과거 mock 로그인은 재사용하지 않는다. 명시적으로 설정한 공통 authority(현재 `127.0.0.1:8000`)의 `/api/v1/auth/login`, `/refresh`, `/logout`, `/me`를 전달한다. access token은 브라우저 메모리에만 두며 refresh HttpOnly cookie는 authority가 관리한다. 검색 요청마다 `/me`로 JWT와 DB 활성 사용자/USER·STREAMER·ADMIN을 확인한다. mockRole/이름 점검 코드는 검색 권한이 아니다. 계정 검증 실패나 authority 오류에 모델/DB 실행으로 fallback하지 않는다. 기존 세션/Redis 키 정책은 authority가 담당하며 AX가 키를 추가하지 않는다.

원본 DB의 기존 계정은 BYPASSRLS/role 생성 권한이 있어 검색 실행에 사용하지 않았다. operator export만 READ ONLY·REPEATABLE READ·8초 timeout으로 이름/축구 통계·수집 설정을 추출했다. 사용자/세션/비밀 테이블은 추출하지 않는다. 실제 축구 데이터 16,805개 통계 row를 이 세션 전용 로컬 PostgreSQL 17.6에 적재하고 `ax_search_reader`를 만들었다. NOSUPERUSER/NOBYPASSRLS/NOCREATEROLE/NOCREATEDB/NOINHERIT, 허용 view SELECT만 부여한다. 공통 원격 DB의 schema/role/데이터는 변경하지 않았다.

온라인 검색은 source DB DSN으로 접속하지 않는다. 런타임 config는0600이며 로컬 reader DSN과 Google 인증 파일의 위치, authority URL만 지정한다. Google 인증에는 기존 환경 파일의 지정 키만 사용하고 복사/로그/응답하지 않는다. 코드/문서에 비밀값이 없다. `search_snapshot` view의 version과 이름·통계 snapshot SHA-256을 매 실행마다 대조한다. 6시간 지난 export는 모델/SQL 실행 전에 갱신 필요로 차단한다. row update 범위와 export 시각을 각각 노출한다. 원천에 더 오래된 row가 존재한다는 사실을 숨기거나 최신으로 덮어 표시하지 않는다.

## 실행 제한과 실패

- 모델: 최대 도구2라운드/6호출+최종 Planner1회, 모델 요청60초/전체 해석180초, 출력4,096tokens/회, 문맥64KiB/도구결과32KiB. SDK 자동 함수 실행/다른 모델 fallback 없음. 자동 provider 재시도 없음.
- 사용자별 동시 해석1개, 전체 모델/SQL 작업2개. 문맥 최대128개, 같은 로그인 세션의 이전 문맥/계획 교체, TTL5분, 선택 ref 위조·다른 사용자·만료·snapshot 교체 차단. 토큰 refresh로 바뀐 세션은 다시 해석한다.
- SQL: 단일 SELECT/허용 view·컬럼·함수/CTE 검사, 매개변수 바인딩, EXPLAIN(no ANALYZE) cost<=100,000, REPEATABLE READ/READ ONLY, statement3초/lock250ms, pool2/overflow0, 최대100행(내부 K+1), 결과256KiB.
- 브라우저 취소는 fetch/화면 갱신을 중단하고 늦게 온 응답을 무시한다. 이미 시작한 동기 SDK/SQL의 원격 취소를 보장하지 않는다. 확인 버튼 전에는 통계 SQL이 실행되지 않는다. 취소 후에도 진행 중인 모델 요청은 서버 한도/timeout 안에서 종료한다.
- 사용자 화면에 SQL/공급자 내부 오류를 노출하지 않는다. 로딩 문구 순환은 실제 단계별 진행 이벤트가 아니다.

## 검증과 해석

신규 단위35개+기존 AX88개, 실제 reader DB9개(독립 SQL4지표·쓰기/기본 테이블 차단4·snapshot 불일치1)를 통과했다. 실제 SQLAlchemy 조립에 대한 별도 산술 fixture로 다중 팀·NULL·동률·가중 per90를 검증했다. FE 통합은 테스트 전용 인증/모델 대역과 **실제 HTTP/SELECT-only PostgreSQL** 조합이며 실제 Vertex 호출 증거와 구분한다. 실제 사용자 비밀번호로 로그인하는 검증은 사용자가 수행할 수 있고 에이전트가 사용자 JWT를 임의 발급하지 않았다.

실제 모델 smoke에서 득점 상위5명(31.69초·결과5개), per90 최소 분 확인(62.29초), '잘한 선수' 지표 확인(11.08초), 두 선수 득점 비교(15.93초·2명), 직전2025시즌 도움 순위(13.46초·3명)를 관측했다. 개발 중 provider 오류2회와 불필요 대회 재질문1회를 함께 기록한다. 실패를 제외한 성공률이나 독립 holdout 점수로 제시하지 않는다. SQL만 동시2/24회 측정한 최종 결과 p50 약44ms/p95 약72ms·오류0이다. 작은 로컬 표본이며 운영 SLO가 아니다. 모델 지연은 전체15초 후보 목표를 충족했다고 할 수 없다. 토큰 사용량은 보고서에 있고 통화 비용/월간 quota/운영 부하는 미확정이다.

SDK `google-genai==2.12.1`, `sqlglot==30.24.0`은 AX 전용 `.venv`와 `pyproject.toml`의 `[ax]` extra에 고정했다. 수동 tool calling의 assistant content/thought signature를 보존한다. 근거는 [Google SDK 공식 문서](https://github.com/googleapis/python-genai), [지정 모델 안내](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/guides/gemini-4-argon), [SQLGlot 공식 문서](https://sqlglot.com/sqlglot.html)다.

## 운영 적용 전 남은 작업

독립 holdout·전체 의미 조건 유실/공격 세트, 실제 계정 인수, 반복 모델 지연/오류·비용/사용자 quota, 운영 전용 role/view의 Supabase migration·DB pool·projection 갱신·source version 동기화, 유사/별칭 검색, 실제 상세 링크, 검수/머지 게이트가 남는다. 이 단계에서 자동 배포·운영 migration·공통 서버 재시작·다른 세션의 코드 복사는 하지 않는다. 운영 schema 변경은 Supabase CLI migration과 ORM/명세를 함께 준비하는 별도 적용 작업이다.
