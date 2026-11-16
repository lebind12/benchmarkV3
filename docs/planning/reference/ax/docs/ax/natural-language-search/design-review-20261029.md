> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/ax/natural-language-search/design-review-20261029.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 자연어 검색 설계 비평 보완 — 2026-10-29

이 제출은 동결 계약 R1–R8의 설계 비평 문서다. 현재 단계는 **설계 비평 보완 후 독립 명세·구현 검토 대기**이며 제품 구현, 독립 승인, 서비스 인수 완료가 아니다. 이번 변경은 이 문서, `design-review-preservation-20261029.json`, `design-review-next-contract-20261029.json`뿐이다. 후속 JSON은 실행하지 않는 초안이다.

## 1. 근거의 권위와 증거 범위 (R1, R8)

사용자 원문은 `review-inputs/20261029/request.txt`, 정책은 AGENTS.md, 현행 제품 범위는 `docs/features/ax-agentic-search.md`(이하 AS), 진행은 `docs/features/ax-agentic-progress.md`(AP), 공개 계약은 `docs/spec/endpoints/ax-agentic-search.md`(API), 검증 계획은 같은 디렉터리의 `ax-agentic-search.testplan.md`(TP)로 대조했다. 경로 약칭은 이 문서 안에서만 사용한다.

결정 근거는 `docs/decisions/2026-10-25-natural-language-search.md`, `2026-10-25-natural-language-search-stack.md`, `2026-10-25-ax-agentic-search.md`, `2026-10-25-ax-conversational-search.md`, `2026-10-29-ax-service-completion.md`다. 지정 모델 `gemini-4-argon`, 로그인, 기존 API-Football DB, 사전/실제 ID 연결은 확정 정책이다. 8지표 최초 출시와 다른 통계 보류는 현행 문서 범위이며 이번 비평이 새 사용자 제외 결정을 만들지 않는다. 초기 SQLAlchemy 조립 결정 뒤 에이전트 설계 기록이 SQL 제안 역할과 반복 실행 방향을 기록했다. 따라서 역할 분리는 사용자 방향에 근거하지만 특정 구현만 영구 허용하는 제약이나 전면 교체 승인은 아니다. 저장된 비교 비평의 “두 결정 문서에 Planner 언급 없음”만으로 전체 결정에 사용자 방향이 없다고 추론하면 안 된다.

`research.json`, `independent.json`(저장된 Opus 독립안), `critique.json`은 비신뢰 검토 자료다. 제안·표본·미확인을 코드와 대조했다. 원본 private 실행·credential·환경값·외부 runtime은 열지 않았다. 외부 조사·모델·DB 호출, 호스트 테스트 및 개발 제어 테스트는 실행하지 않았다. 공개 소스 파일을 읽는 것은 런타임 실행이나 credential 파일 열람이 아니다.

증거를 다음과 같이 구별한다. **P** 정책/명세는 해야 할 일, **C** 현재 소스 읽기는 구현 존재와 제어 흐름, **H** 기존 문서에 보고된 실행은 당시 환경의 역사, **D** 운영자 allowlist 진단은 단일 실패 실행의 제한된 관측이다. 이번 C는 실행 통과가 아니다. H의 unit197/build, DB15 skip→로컬 mirror15 PASS, 모델 연결1회 반환 및 TP의 과거 Red(51 failed/8 passed, DB2 failed)는 현재 재실행/정답/운영 증거가 아니다. 원본 로그는 열지 않았고 보고된 수치를 그대로 역사로만 사용한다. D는 execution completed이지만 structured incorrect, acceptance 미충족이다. 파일 조회 exit0와 JSON 구조 확인은 독립 의미 인수와 별개다.

## 2. 현행 요구–증거 대조 (R1)

모든 행은 필수 보존 대상이며 ‘현재 코드’는 충족 선언이 아니다. 다음 완료 조건은 후속 계약에서 검증할 항목이다.

| 요구·근거 | 현재 코드/관측 | 기존 증거 출처·범위·한계 | 부족한 증거와 다음 완료 조건 |
|---|---|---|---|
| 로그인/활성 USER·STREAMER·ADMIN, 인증 전 모델·축구 reader0회: 사용자 결정, AS §2/7, API §1 | `agentic_api.current`는 공통 current_user 또는 명시 authority, `search_auth.AuthAuthority.verify`는 /auth/me 위임. `send/stream/cancel`에 Depends(current) | C: 서버 경로 존재. TP BE-A01 계획, H 실제 공통 계정 인수 미완료 | 실제 공통 계정 role/비활성/만료/회수·장애401/403/503 일치, 인증 실패 시 호출 spy0; FE role은 권한 아님 |
| DB-only/6h/no polling: AGENTS §6, AS §7 | `Dataset.fresh`는 captured_at의 -60~21600초, runner.check/send freshness 검사. runtime은 로컬 snapshot만 허용 | C: snapshot TTL만 확인. H mirror는 Supabase 운영 갱신 증명 아님 | source 수집 관측 기반6h, generation 변경 감지·실패/부분 안내; reload로 시계 재설정/12h 이중 지연0. 검색의 외부 통계·worker 호출0 |
| 동적 활성 리그·대회별 현재+실제 직전 시즌: AS §5, AGENTS §2/3 | `Dataset.seasons`는 current와 저장된 이전 최대 year, scope는 active/catalog/targets 검사; `Run.ref/query`와 SQL scoped subquery | C: 5개 하드코딩 대신 dataset 기반. 운영 view 실재 미확인 | 리그 추가/제외·시즌 간격/전환·보관밖·정책충돌을 독립 expected로 검증, view와 서버 양쪽 제한 |
| 8지표·NULL/0/per90 최소분·동률·복수소속: AS §5/9, API §3 | `search_types.METRICS`, `agentic_sql.AgenticExecutor.execute`의 NULL 보존 SUM/NULLIF, 최소분 검사, `query_intent`/runner 계산 | C: 득점/도움/출전분/출전횟수/경고/퇴장/득점+도움/90분당득점. TP BE-A03·DERIVED-META, H 과거 테스트 수치만 존재 | 독립 원천행/기준 SQL로 ID·값·단위·정렬·동률·최소분·NULL/0분모·다중소속 일치. NULL을0건/0으로 승격 금지 |
| 다중 선수/두 시즌 차이·비율·후속 질문/자연어 확인/새 대화: AS §3/5/6, 대화 결정 | runner.query의 selection_ref/positions/ID·calculate, `search_conversation.ConversationService` history/parent/owner, 새 conv | C: 구조 존재, TP BE-A03/05/06. D의 단일 질문 실패는 기능 인수 아님 | 3명 이상·결합조건·이전 표시순위 참조·조건 상속/수정·동명이인/추상기준 재질문·새 대화 격리. 2명 제한으로 단순화 금지 |
| 정확한 조건·값·출처/누락/잘림/상태: AS §5/6, API §3/6 | VerifiedQueryIntent mint→SQL 비교, runner.record/query_metadata/public, `public_response` 검증 | C: source lineage/typed metadata 존재, TP SEC/META/BE-A04/09. D artifacts0·오답 | 질문→intent 의미도 독립 판정; SQL 일치만으로 충분하지 않음. results/partial/no_matches의 applied/coverage 같은 ref, rows/columns 정확 일치, 시각·단위·연산·근거·비전수 표시, 미수집≠no_matches |
| 실제 SSE 진행·유실 복구·취소·late commit0: AP §3–7, API, AS §6 | `agentic_progress`, `agentic_api.stream`, conversation cancel ledger/commit 검사, FE parser | C: 전송·상태 검증 존재. TP BE-S01~03/BE-C01~04는 계획; 현재 실행 없음 | 실제 단계/sequence/terminal1개·no-store, EOF/역순/중복/과대/개행, 같은 nonce 복구의 중복실행0; disconnect≠cancel, 명시 cancel 후 늦은 반영0. 즉시 유료 호출 종료 보장은 없음 |
| 세션/소유권/토큰교체·TTL/restart: API §2, AS §12 | binding=토큰 hash, ledger key=(binding,nonce), conv owner 비교; FE searchSessionGeneration | C: 토큰별 격리. TP BE-A06/07. 실계정 rotation 미인수 | 교체 후 과거 ref/nonce 재사용X, 안전한 읽기 전용 이력·입력 보존/새대화. 다른 사용자/버전/30분/12턴·재시작409, 취소 격리 |
| 직접·간접 인젝션 및 정상 질문 오차단: AS §7, SEC/PI 문서 | gate/_meaning/validate_query_intent, 서버 scope/ref, safe reason, API schema/JSON·FE 텍스트 | C: 방어 계층, TP §3/4와 테스트 소스 표본. H Red는 당시 재현, 현재 Green 불명 | §4의 PI-01~12·SEC-01/02 공격/정상 쌍과 부작용·실제 모델 독립 holdout 모두 인수. 정적 수치/ref검사가 자유 설명 진실성 전체를 입증하지 않음 |
| 운영 reader/사전·번역·통계·정책 갱신/공통 서비스: AS §12, production-runtime.md | main은 opt-in runtime 자원과 agentic router 등록; runtime local-only, SQL ax_search 고정 | C: 로컬 연결 경로와 보호 설정 확인. P 운영 view/generation은 구현 전 요구 | 운영 mode/view/권한/RLS·migration/ORM 정합·원자 generation·자원정리·모델 대기 중 연결반환·실계정→FE 인수. source freshness/삭제/번역/정책변경 관측 |
| 지정 모델/품질·비용·p95/안전 오류·예산: 모델 결정, AS §7 | runner 180초/24 model/12 plan/6 SQL, provider 지정 모델·안전 code; executor EXPLAIN/행/byte 제한 | C: 한도 존재. H 429/504, D planner3회/DB0; 실제 품질·비용/p95 미측정 | 환경/예산 고정 후 실제 지정 모델 정답·공격/정상 분모·provider실패/skip·토큰/비용/p95 별도 보고. 목표 수치는 실측·독립 검토 전 미정 |
| 독립 리뷰→머지→명시 승인 배포/사후검증: 원문2, 서비스완성 결정, AGENTS §13 | plan AX-R-7/8, API status spec-review, AS in-fe-pipeline | P/H: 완료/승인 근거 없음 | 독립 FE/BE 리뷰·표준 검증·충돌 검토·검토 가능한 PR 후 통합. 자동배포 유발 merge도 배포 경계. “배포해” 전 배포성 동작0, 실제 L4 후 서비스 완료 |

## 3. 설계 유지·수정·대안과 복잡도 (R2)

저장된 독립안 D2/D3의 최소 완전 경로는 유용하다. 공통 인증→발급 ref/버전/범위→서버 동결 intent→검증된 쿼리→전용 reader→lineage/계산/metadata→근거 기반 자유 답변→SSE/대화 commit을 기준으로 비교한다. 모델 출력은 서버가 검증해도 질문 의미상 올바른 intent라는 보장이 자동으로 생기지 않는다.

| 관점/보존 요구 | A: 현행 SQL 제안+AST+intent | B: 검증된 intent에서 서버가 쿼리 조립 |
|---|---|---|
| 8지표/동적 scope/NULL/순위/차이·비율/다중·후속 | 구현 경로 존재. query receipt와 SQL 목적 비교, 계산은 서버. 지원 algebra가 제한되어 등록 밖 조합은 안전 실패; 정상 요구를 전부 처리하는지는 미입증 | 현 `search_sql.build_query` 재사용 가능하나 단일 QueryPlan만으로 다중scope/rank/max/후속 selection/계산 모두 충족한다고 할 수 없음. 동등 intent 전체 조립과 인수 필요 |
| 정확한 조건/수치/출처 | projection/filter/sort/rank/grain/selection 불일치 거절, source 치환/metadata 공유. 같은 오해를 공유한 planner/SQL은 의미 oracle 아님 | SQL과 intent 불일치 면적 축소. intent의 질문 해석 오류·집계/동률/누락/출처 오류는 여전히 남음 |
| 주입/정상 오차단 | SQL 구조·lineage·intent 모두 필요. 미등록 표현 거절과 정상 CTE/window/인용 이름 허용을 함께 평가 | 모델 식별자/산식 실행 면적 감소. auth/ref/scope/버전/출력/예산·DB role/READ ONLY/AST 방어를 제거할 이유 없음. 정상 질문을 유한 예문으로 제한 금지 |
| 대화/SSE/취소/격리/운영/6h | 기존 envelope 재사용, 별도 운영 미완료 | 같은 envelope/진행 의미 유지 가능하나 SQL 역할 변경과 실제 단계 표시 정합 필요. 토큰 정책·동시성·운영 미완료는 그대로 |
| 구현·운영 부담 | 기존 코드 활용, SQL 역할 호출/SQLGlot 의미 비교와 이중 표현 유지 비용 | 추가 SQL 생성 오류/호출 감소 가능하나 현재 범위 전체 compiler 구현·동등성 검증 비용. 지연/비용 이득은 미측정 |

판단: **현재 핵심 검색 실패를 먼저 진단하고 A의 최소 정답 흐름을 증명한다.** 인증/reader/ref/lineage/취소/갱신/metadata는 요구에 직접 연결된 필요 복잡도다. B는 같은 고정 expected로 작은 격리 비교를 할 가치가 있으나 현재 단일 QueryPlan으로 기능을 줄이거나 A를 폐기하지 않는다. 자유 설명을 템플릿 전용으로 바꾸지 않는다. 역할 분리 방향은 보존하고 SQL 역할의 검증된 intent 제안/서버 조립으로 바꾸는 것은 근거와 후속 명세 검토가 필요한 제안이다. 새 프레임워크·RAG·벡터 DB·복제 서비스·캐시/옵션 추가는 현재 장애 해결의 필요 의존성이 아니다. LangGraph 제거·재작성 역시 선행 정답 증명 없는 범위 확대다.

구조 수정이 필요할 수 있는 지점은 운영 source generation/reader와 공통 인증 연결, FE 필수 metadata/입력 계약 정합이다(R1/R4/R7). 이유와 검증은 §5/7에 연결한다. 이 제출에서 제품 구조는 바꾸지 않았다.

## 4. 공격과 정상 입력의 설계 인수 계획 (R3)

`prompt-injection-security.md` §1/3/4와 TP §2–4의 실제 ID를 대조했다. 사용자·이전 대화·DB 이름/별칭/셀·도구 결과·모델 계획/SQL/답변은 모두 비신뢰다. system 문구/role 텍스트는 실행 권한이 아니다. 등록 ref도 owner/version/scope와 연결되어야 한다.

| PI / SEC와 TP 연결 | 공격 / 정상 대조군 | 독립 판정 및 부작용 검사 |
|---|---|---|
| PI-01/02; BE-A01/02, TP §4 | 관리자/system 사칭·JSON 종료·다국어 role태그 / 공격 문구 인용, 따옴표·중괄호 이름 | 인증/strictschema/ref/scope 불변, 인증실패 모델/reader0; 등록 정상 이름 해석은 허용. 축구 외 인용 질문은 안전 미지원이며 보안 성공/정답 성공 구별 |
| PI-03/04; BE-A03/05/06 | 과거질문/답변의 지속 지시, DB 후보/별칭/조회셀 간접 지시 / 정상 후속 조건 변경, O’Neil·하이픈·Unicode·지시 같은 등록 이름 | 독립 expected의 상속/수정 조건·ID 일치, 후보/도구 출력의 지시 권위 승격0. 이름 때문에 정상 검색을 일괄 차단하면 오차단 |
| PI-05/06; SEC01-PROTECTED/UNKNOWN/ALIAS/CTE/GRAIN/NODB/CONTROL, INTENT-* | 상수·임의 alias·ID/이름 혼합·NULL→0·집계증폭·조건삭제·sort/partition/limit 변경 / 동일 의미 source/CTE/window/등록MAX | SQL에서 역생성하지 않은 expected intent·기준 SQL/원천행의 ID/값/순서/NULL/단위 비교. pure gate와 intent 비교 각각, DB spy connection0. 정상 표현도 통과해야 방어 완료 |
| PI-07/08; BE-A01/06/07, BE-C01/03 | 다른 사용자 conv/nonce/artifact/candidate·CTE shadow/nested/function/cast/schema 우회 / 자기 nonce 복구·허용 SELECT | 사용자A/B·토큰교체·버전쌍 fixture, 타사용자 응답/존재정보 노출0; 불허 relation/function/write 실행0, reader effective grants를 격리 DB에서 별도 확인 |
| PI-09/10; SEC02-CONTROL, BE-A04/05/09 | prompt/SQL/접속값/token/log dump, reason의 가짜 이름·한글수사·출처/인과 / 실제 artifact 차이·감소 설명과 조건/누락 | 합성 canary만 사용, API/SSE/답변/공개 로그 누출0. fact/자유 설명을 독립 사람이 의미 평가. safe code만으로 전체 설명 정답 선언 금지 |
| PI-11/12; BE-S01~03, BE-C01~04, BE-A08/09 | HTML/link/개행 event·반복·무한재계획·취소무시 / 텍스트 inert 표시·공격 실패 후 새 정상 질문 | FE DOM 실행/무단탐색0, JSON/SSE 프레임 보존·terminal1개·예산 준수, 취소후 late commit0·유실 재시도 중복0. 모델/DB 즉시 중단 여부와 사용자 취소 반영을 구분 |

소스 표본 확인: `tests/unit/test_ax_security_contract.py`의 `test_sec01_rejects_unverified_public_fact_lineage`(악성15), `test_sec01_rejects_fact_forgery_before_database_execution`(동일15), `test_sec01_allows_registered_source_and_operation_lineage`(정상6), `test_sec02_control_reason_does_not_publish_arbitrary_model_text`(2), `test_release_results_have_server_owned_artifact_metadata`, `test_release_empty_query_keeps_applied_and_coverage_without_fabricated_table`, `test_be_spec01_sql_cannot_change_preverified_query_intent`(12), `test_be_spec01_equivalent_sql_preserves_preverified_query_intent`(5), `test_derived_output_declares_actual_operation_sources_and_units`(2)를 읽었다. TP의59건 설명과 연결되지만 이번 실행 결과는 없다. 특히 NODB 검사는 intent 없는 호출의 공통 거절로도 통과할 수 있어 그 단독 결과로 악성별 의미 방어를 입증하지 않는다. 독립 intent 공격/정상·순수 gate·HTTP owner 연결을 함께 검증해야 한다. PI-01~12 전체와 실제 모델·운영 DB·브라우저가 이 표본으로 검증된 것은 아니다.

expected는 평가자가 고정한 버전별 원천행·기준 SQL·ID/값/조건/허용오차/상태/누락/단위이며 구현 SQL·LLM 출력에서 만들지 않는다. 결정론적 악성 모델 제안 주입→격리 reader/HTTP→실제 지정 모델 직접·간접 입력→FE 공개표시의 층을 나눠 case/test-node/run·버전을 기록한다. 수정에 사용한 holdout은 개발회귀로 이동하고 새 holdout을 둔다. 불허 실행·타사용자/비밀 노출·위조 통계 수용은1건도 출시 차단이다. provider실패/skip은 보안 통과가 아니다. 공격 성공률의 분모·입력원·실패단계와 정상 오차단률을 별도 집계한다. 품질 목표/비용/p95·오차단 출시 한도는 미측정·미정이며 이번에 숫자를 발명하지 않는다.

## 5. reader·인증·운영·FE 격차의 재판정 (R4)

**저장된 READ ONLY 의심은 현재 소스에서 보완된다.** `agentic_sql.AgenticExecutor.execute`는 REPEATABLE READ transaction 안에서 SQL 실행/EXPLAIN 전에 `self.reader._validate_connection(conn)`을 호출한다. 실제 runtime이 주입하는 `search_sql.SearchExecutor._validate_connection`은 `SET TRANSACTION READ ONLY`, `SET LOCAL statement_timeout='3s'`, `SET LOCAL lock_timeout='250ms'`, role의 super/bypassrls/createrole/createdb 거절, `ax_search.search_snapshot` version 일치를 검사한다. warmup도 같은 함수를 호출한다. 독립안 D7/비교 비평의 “agentic_sql에 문자열 없음”은 위임을 놓친 표본 한계이며 READ ONLY 미구현 결론은 철회한다. C 수준의 구현 확인이지 DB에서의 실제 effective 권한·timeout 인수는 아니다. `ax_search.search_stat/search_player/search_snapshot` 고정은 남아 있다.

`production-runtime.md`의 production_db_views/view/generation/수집 관측은 **구현 전 요구**다. `search_runtime.create_runtime`은 local_real_db_snapshot·loopback·ax_search_reader만 허용한다. role flag 검사만으로 membership/effective grants/view owner/RLS·사용자/세션 원천 비노출이 증명되지는 않는다. `Dataset.fresh`의 export TTL만으로 원천6h 신선도도 증명되지 않는다. 운영용 view/role/migration·삭제/번역/활성/시즌 변경과 원자 generation, request snapshot 고정/각 SQL 및 commit 전 확인·bounded reload/503, 새세대 nonce replay 만료·cancel ledger 보존·모델 대기 중 connection 반환이 후속 필수다. 실제 운영 계정·DB 상태는 조회하지 않아 미확인이다.

**토큰 binding을 안정 user ID로 자동 변경하지 않는다.** API §2는 rotation 후 과거 ref/nonce 무효화, 읽기 전용 표시 이력·입력 보존 및 새 대화를 명시한다. `search_auth`와 `agentic_api.current`의 토큰 hash, conversation의 owner/nonce key가 이 방향과 맞는다. 독립안 D8/critique의 “refresh에도 소유권 지속” 제안은 기존 무효화 계약과 충돌한다. user ID binding은 별도 공통 인증/세션 검토 없이는 채택할 수 없다. local authority의 비활성401/금지role403 및 upstream 비200→503과 monolith의 비활성403을 API가 허용한 공통 인증 정책에 맞춰 실제 계정으로 검증해야 한다.

내부 test owner는 `Run.__init__`의 principal=None 기본값에 남아 있다. 공개 경로는 `agentic_api.current`→send/stream→`ConversationService.send(principal)`→`AgenticSearch.run_agentic(principal,...)`→`runner.run(..., principal, request_ref)`→Run으로 추적되며 cancel도 인증 dependency를 쓴다. 현재 읽은 일반 요청 경로가 기본값으로 빠진다는 근거는 없다. 그러나 모든 factory/추가 caller·배포 wiring에서 불가능하다는 실행 증명은 없으므로 ‘공개 경로 소스상 principal 전달 확인, 전체 운영 도달성 미인수’로 분류한다. 후속 HTTP/설정 경계 검증으로 principal 생략 시 fail-closed를 확인한다.

FE/legacy는 무조건 dead code나 삭제 대상으로 보지 않는다. `axSearch.ts:69–85`에 legacy interpretation/query/conversation/cancel export, `search_app.create_search_app`에 legacy route 등록이 실제 존재한다. 이 local factory는 agentic도 등록한다. 반면 `app/main.py:97`은 agentic router를 등록하고 임시 resources 앱의 legacy router를 include하지 않는다. 따라서 ‘로컬 factory에 노출 확인’과 ‘현재 main 등록상 legacy 검색 노출 근거 없음’을 구별하고 실제 서비스/proxy exposure는 미확인으로 남긴다.

`frontend/src/router/index.ts:100–103`은 flag에 따라 /search 목업 또는 /search/agentic 이동, /search/live도 flag 허용, names는 DEV 조건이다. `AgenticSearchView.vue`는 agentic client를 사용하며 preview는 DEV 조건이나 기존 choice 분기가 남아 있다. 출시 canonical /search·DEV/live 격리·공통 auth store 정합은 아직 인수되지 않았다. `axSearch.ts:83`의 message?/choice_ref? 공유 타입은 strict AgenticInput/API의 message 필수·choice_ref422와 어긋난다. 같은 파일132행은 applied/coverage optional, 140행은 숨긴 내부 row key 일부를 허용하여 API §3의 required metadata/정확한 row key 규칙보다 느슨하다. spec §6.0·TP의 ‘VerifiedQueryIntent 없음’도 현재 코드 존재와 달라 역사/현재 표기 수정 후보다. 수정은 후속 FE mock→endpoint-request→BE 명세 정합 순서로 한다. 이번에는 소스/주석/미사용 export를 삭제하지 않았다. 관련 없는 기존 dead code는 이 조사로 확정하지 않았으며 legacy의 사용처 전수 확인 전 삭제할 수 없다.

## 6. DB 조회0회 실행의 제한된 진단 (R6)

입력 `existing-run-diagnostic.json`은 운영자가 private 실행에서 allowlist 추출한 비민감 projection이다. 원본 report hash는 `a7e6ff5a7ada9d1fa172ef8a5e64a680393101cd50ff92bb2cc2aa0fa00a3cd2`로 기록돼 있으나 원본을 열어 재검증한 것은 아니다. execution=completed, result_status=unsupported, model_call_attempts=3, database_queries=0, structured_semantic=incorrect, artifacts_count=0, server_gate_rejections_count=0이다. planner lookup(6.043초)→query(10.558초)→unsupported(46.17초), progress는 planning completed→lookup completed→review completed→**scope failed**→review completed다.

현재 `AgenticRunner.query`는 scope phase에서 task/이름확정/SQL budget/need·발급 ref/실제 시즌·dataset.scope/selection·중복선수/team·intent/최소분/지표·VerifiedQueryIntent 구성까지 검사한 후에야 SQL 모델을 호출한다. `act`는 SearchError를 전파하고 다른 예외는 제한된 ValueError safe code 또는 query_or_tool_unavailable로 run.error에 넣어 재계획한다. `answer`의 unsupported는 안전 reason code 문구로 종료할 수 있어 마지막 answer 역할 모델 호출이 없어도 세 planner 호출과 모순되지 않는다.

따라서 관측은 **lookup 완료→query 시도→SQL 생성 이전 scope 실패→재계획 unsupported**와 정합적이다. 실행 완료는 기대 검색 성공이 아니다. gate 목록이 비었다는 것은 SQL 실행 가능/권한 정상의 증거가 아니며 SQLgate 거절이나 provider 실패라고 단정할 수도 없다. exact scope 예외코드와 원 제안이 projection에 없어 어느 분기가 실패했는지는 미진단이다. raw planner proposal·원문 exception/secret/private runtime을 추가로 읽지 않는다.

다음 관찰은 별도 계약에서 운영자가 code-owned allowlist로 제공해야 한다: 비민감 run/case ID와 code/dataset/definition/scope-policy 버전, terminal node/status/reason_code, stage/sequence/status/duration, 모델 role/action/outcome·호출수, scope 실패 safe enum·검사 단계, task/intent 존재·schema valid 여부, 발급 ref의 존재/kind/owner/version/ambiguity/overflow 유효성 boolean, scope 정책 reason(enum), need/selection/최소분/metric 정합 boolean, intent mint/SQL 생성/gate/DB 연결·조회 시도 횟수, artifact 수와 취소/만료/generation 변경 여부다. 실제 ref·질문·이름·SQL·모델 원문·token/hash binding·DSN은 공개 진단에 넣지 않는다. 임의 exception 문자열을 code로 승격하지 말고 알려진 enum 외에는 generic code를 쓴다.

진단 순서: (1) 기존 projection과 동일 코드 버전 여부 확인; (2) safe code가 남아 있으면 운영자의 추가 allowlist 추출로 분기 축소; (3) 없으면 복원 불가능을 기록하고 합성 dataset/provider·고정 expected로 각 scope 분기 재현을 후속 검증에 준비; (4) 별도 환경/예산이 정해진 뒤 필요한 최소 실제 호출로 같은 case를 관측한다. 재현 전 증거는 이번 projection뿐이며 pre-fix 테스트/성공한 재현을 주장하지 않는다. **원인 확인 전 prompt/budget/gate 완화·기능축소를 해결책으로 확정하지 않는다.** 이 문서는 진단 계획을 보완했으며 제품 버그를 고쳤다고 주장하지 않는다.

## 7. 보존·인계와 다음 보완 순서 (R5, R7)

보존 manifest는 입력 `preservation-baseline.json`의 HEAD `bc4ccf8890de1df06698eb9c4629bf194e439ca7`, 모든 files 항목의 path/git_status/sha256 및 기존 분류/이유를 그대로 보존한다. 추가 handover 분류는 유지/수정/폐기 후보/판단보류 중 하나이며 각 파일의 관련 요구·이유와 별도로 붙인다. 이는 수정/삭제 허가가 아니다. 입력 준비 폴더는 baseline 생성 때 제외된 범위이고 이번3개 출력도 기존 작업으로 귀속하지 않는다. `.codex/state/reviews/tasks`와 하네스 산출물은 역사/다른 소유자 자료로 유지하며 신규 승인으로 사용하지 않는다. 전체 일괄 commit/stash/reset/clean·다른 worktree 편집은 하지 않았다.

| 단계·요구 | 소유범위/선행조건 | 검증수단·통과조건 |
|---|---|---|
| S0 현재 비평 보완 R1–R8 | 이번3개 문서만, 동결 계약/입력 | 외부 controller의 구조 검사와 독립 의미/명세·구현 리뷰를 별개로 수행. 필수 누락/오류 없을 때 이 문서 단계만 종료 |
| S1 핵심 원인 진단·정답 흐름 R1/R2/R6 | AX scope/intent/runner 및 격리 fixture의 구체 파일을 후속 계약에 확정; S0 독립 검토 | safe 관측으로 실패 분기 확인, 독립 expected의 대표3명/두시즌·NULL·후속 경로 증명. 필요시 A/B 동등 요구 비교, 전면 교체 선행 금지 |
| S2 기존 FE mock/endpoint 기반 수정 R1/R3/R4 | FE 검색 화면/client/mock/request→현행 endpoint 명세→BE 순서, 기존 승인 아님 | 필수 metadata·strict 입력·상태·SSE/유실/취소/새대화·접근성/UI, 직접/간접 공격·정상쌍. legacy 사용/노출 조사 후 명시 결론 |
| S3 공통 인증·운영 reader/갱신 통합 R1/R3/R4/R5 | 공통 파일 소유자 조정·격리 migration/ORM/view mapping, main과 작업트리 차이는 commit 기반 인계 | 실제 공통 auth 계약/rotation 무효화, 최소권한·generation·6h·연결반환·실패/부분·일반API/worker 영향/복구. 운영 적용은 아직 별도 경계 |
| S4 실제 모델/정답/보안/비용 인수 R1/R3/R4/R6 | S1–3, 지정 환경·권한·quota/예산·holdout·출시 기준을 후속 계약에서 고정 | 실제 gemini-4-argon, 독립 oracle/holdout·PI01–12·오차단·질문/후속/FE L3, 비용/p95 실측. 실패/skip 미인수 |
| S5 독립 리뷰/머지 준비 R5/R7 | 전체 blocker 해소, FE/BE 독립 reviewer, 명시 경로·기존 작업 귀속 | 표준 unit/격리integration/coverage≥80%·type/build/UI 등 후속 필수 검증과 버전별 증거; PR/충돌·복구 검토. 이번 worker는 merge/push하지 않음 |
| S6 명시 승인 배포/사후검증 R7 | “배포해” 요청·대상/자동배포 영향 확인, S5 | 승인된 운영 적용·권한/인증/정답/갱신/오류 L4·복구 증거 뒤 서비스 완료. 목표 문구만으로 승인 대체 금지 |

후속 초안은 이 순서와 전 요구를 required:true로 연결한다. 실제 수정 경로는 owner와 manifest를 기준으로 독립 명세 검토 때 확정해야 하며 새 외부 호출·환경/비밀 열람·운영 DDL/설정·배포 권한은 이 문서로 생기지 않는다. 품질/비용/p95 한도·운영 자격 가용성·현재 코드 버전의 정확 예외코드가 남은 중요한 미확인이다. 이는 operator가 후속 계약에서 해소할 항목이며 일상적 구현 선택을 위해 사용자 재확인을 요구하지 않는다.

