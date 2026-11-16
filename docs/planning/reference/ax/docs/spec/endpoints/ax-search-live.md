> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/spec/endpoints/ax-search-live.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 실제 검색 endpoint v1

FE 정본: [ax-search-live.md](../../features/ax-search-live.md). 활성 실제 사용자 인증 전에는 이름/모델/통계 DB 조회를 시작하지 않는다. JWT 발급/refresh/rotation은 기존 authority API가 담당하며 새 인증 프로토콜을 만들지 않는다. 요청마다 authority `/auth/me`로 활성 상태/역할을 검증한다. 인증 실패401/403·authority unavailable503, client mockRole 불허.

한 요청에 Retriever 도구 최대2라운드/합계6호출, 최종 구조화 출력1회. 서버가 실제 candidates/catalog/definition/season/availability를 제공하고 발급 ref만 선택 가능. Planner의 typed draft를 서버가 source/관계/조건/버전으로 재검증해 실행 plan을 저장한다. LLM SQL은 받지 않는다. 모호한 entity/지표/시즌/per90 최소 분은 재질문, 해결은 서버 choice_ref만 허용한다.

운영 전 experimental budget: 모델 요청60초·전체 해석180초·출력4,096tokens/회·입력 문맥64KiB/도구결과32KiB·사용자 해석1개/전체2개, DB statement3초/lock250ms·pool2·결과100행/256KiB·EXPLAIN estimated cost100,000. 측정 후 조정하며 출시 SLO가 아니다. 버전·토큰/호출·구간 지연은 제한된 진단 자료에 기록하고 질문/이메일/토큰을 로그로 남기지 않는다.

SQLAlchemy Core가 allowlist된 지표/집계·매개변수를 조립한다. PostgreSQL SQLGlot AST는 단일 SELECT/허용 테이블·컬럼·함수/구문을 검사하며 권한·의미 검증을 대신하지 않는다. 실행은 NOSUPERUSER/NOBYPASSRLS/NOCREATEROLE/NOCREATEDB·SELECT-only views/transaction READ ONLY·REPEATABLE READ·timeout·EXPLAIN(no ANALYZE) 아래서만 한다. privileged source 계정은 export 도구에서만 사용하며 search 실행에 재사용하지 않는다.

NULL은0으로 채우지 않는다. 팀별 일부값 누락 시 complete 합계NULL, per90=합계 득점*90/양수 합계분. rank는 저장 범위 내 원시값 공동순위/ID 안정정렬이며 상위N은 행 상한(동률 일부 제한 안내). coverage는 미인증 completeness를 complete로 만들지 않고 source export/row update·제외/누락 수·정책 conflict를 보존한다.

통합 검증: 실제 SDK 호출/계정 오류·도구 인수/참조 위조·정의 의존/NULL/분모/다중팀·SQL write/function/CTE/중복문 차단·권한/시간/행·byte·auth 미검증시 호출0·재질문/계획 TTL/다른 사용자·provider/DB 오류·실제API FE 흐름·독립 고정 답안. 원격 role/DDL·배포·기존 worker 변경 없음.
