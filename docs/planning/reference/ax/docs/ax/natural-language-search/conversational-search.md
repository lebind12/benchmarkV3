> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/ax/natural-language-search/conversational-search.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 대화형 검색 v1 — 로컬 구현과 검증

2026-10-25. 사용자 요구는 검색 결과를 대화의 다음 질문에 재사용하는 것이다. 기존 단발 화면을 `/search/live`의 대화 화면으로 교체했고, 실제 검색 모드의 `/search` 메뉴도 이 화면으로 연결한다. 다른 개발 세션의 파일/브랜치·운영 DB·배포는 변경하지 않았다.

## 사용 흐름

`이번 시즌 EPL 득점 순위 5명을 보여줘` → `상위 두 선수의 기록을 비교해줘` → `그 둘 중 도움은 누가 더 많아?` → `직전 시즌은?`처럼 묻는다. 대회·시즌·선수·필터 중 바꾸지 않은 조건을 이어받는다. `전체 선수의 득점 순위로 돌아가자`는 선수 선택을 해제하고, `처음 순위의 세 번째와 네 번째`는 처음 표시했던 결과의 행을 참조한다. 시즌 확인에 `이번 시즌으로`처럼 문장으로 답하거나 선택 버튼을 눌러도 된다.

첫 화면은 승인 목업의880px 중앙 구성·64px 한 줄 글래스 검색창·돋보기/원형 전송·예시 카드·블루/라벤더 배경·라이트/다크를 따른다. 검색 후26px 소개·사용자 질문/답변 누적·하단 후속 입력·새 대화를 제공한다. 로딩 문구6개/2.8초·파형/스켈레톤·행 등장 효과·높이/폭/폰트 재계산·IME/모션 줄이기를 유지한다. 명확한 질문은 조회까지 한 번에 처리하며 불필요한 별도 실행 확인 버튼을 제거했다. 로그인 전에도 검색창/입력을 유지하고 제출 시 로그인 dialog를 연다.

기존 계정으로 로그인해서 `http://127.0.0.1:5188/search/live`에서 사용한다. 검색 기록은 현재 페이지 메모리에 있고 계정에 영속 저장하지 않는다. 새로고침/로그인 토큰 교체/서버 재시작 후에는 새 대화를 시작한다. 이름 점검용 접근 코드는 실제 검색에 사용할 수 없다. 초기 선수 시즌8지표·한 대회/시즌·최대2선수 비교·실제 DB 로컬 저장본 범위는 [단발 검색 구현](live-search.md)과 같다.

## 문맥을 검증하는 방식

클라이언트는 message 또는 발급된 choice, conversation_ref/최신 parent_turn_ref, request_ref만 보낸다. 이전 결과·선수 ID·SQL·필터는 클라이언트가 재전송하지 않는다. 서버가 실제 결과와 검증된 Draft를 보관한다. 후속 LLM은 base_turn_ref/변경 필드 목록/typed Draft/결과 위치를 반환한다. 서버는 그 대화의 실제 이전 초안에 명시된 변경만 적용한다.

모델에는 최대12개 교환의 질문·조건·결과 ref/표시 행 수와 최근4개 결과의 앞10명만 전달한다. 전체 표시 결과는 서버에 있어 오래된 결과의 행도 검증한다. '상위 두'는 표시 행1/2이며 명시 순위는 실제 공동순위 값을 확인한다. 범위를 벗어난 행·없는2위·3명 이상 공동순위는 되묻고 인물/ID를 추정하지 않는다. 새로 조회하는 이름/지표는 현재 발화에서 검증한다. 모델이 정식 명칭으로 검색하더라도 실제 DB의 원문 별칭으로 다시 전역 조회해 동명이인/타입 충돌을 숨기지 않는다. 비교 대상이 같은 선수의 별칭2개이거나 필터 때문에 한 선수만 남으면 정상적인2선수 비교로 표시하지 않는다.

조회 담당 Retriever의 수동 tool round에서는 thought signature를 보존한다. Planner는 중복 대화 transcript 대신 서버가 구성한 단일 RetrievalBundle(문맥/후보/정의/조회 결과)을 받는다. 중첩 Draft의 모든 필드를 구조화 응답 schema에 필수화했다. 단순히 changed_fields만 반환하고 변경값을 비우던 실제 모델 문제를 이 경계에서 수정했다. 지정 모델은 계속 Vertex `gemini-4-argon`이다.

답변 문장/비교 우위·차이는 반환된 실제 DB 수치를 서버에서 계산한다. LLM이 통계를 지어낸 설명을 사실 답변으로 노출하지 않는다. NULL/부분 수집/보관 시즌/출전 분·SQL 게이트는 기존 규칙을 따른다. 비교 표에는 득점·도움·출전 횟수·분을 함께 제공하고 없는 값은 자료 없음으로 남긴다.

## 요청/취소/상한

대화는 로그인 binding/자료 버전에 귀속하며30분·12교환·64대화, request/cancel ledger256개로 제한한다. 로그인 access token 교체는 기존 대화를 다시 사용하지 않는다. 부모 ref 충돌·다른 사용자/다른 대화·source 변경/6시간 지난 저장본은 차단한다. 기존 pending 선택 참조는5분 제한이 있고 이후 문장으로 다시 답할 수 있다.

같은 request_ref/본문 재시도는 완료 응답을 반환한다. 다른 본문으로 nonce를 재사용하면409다. 응답이 유실되어도 중복 질문/SQL로 처리하지 않는다. 취소 tombstone은 도착 전/처리 중 요청을 보호하며, 완료 직후 응답이 유실된 최신 턴은 rollback한다. 원격 SDK/DB 실행 자체의 취소는 보장하지 않는다. 실패/취소가 성공한 이전 조건을 교체하지 않도록 한다.

provider429는 provider_rate_limited, provider504는 interpretation_timed_out으로 구분한다. 사용자에게 내부 원문 오류/SQL/비밀을 노출하지 않고 재시도할 입력과 대화를 유지한다. 모델/SQL 동시성·deadline·예산과 읽기 전용 계정은 기존 정책을 유지한다. 새 Redis 키/외부 통계 수집을 추가하지 않았다.

## 시나리오와 결과

시나리오 목록 (원문 참조 경로: `evaluation/conversation-scenarios.md`; 이 기획 묶음에 포함되지 않음), 개발 세트 (원문 참조 경로: `evaluation/cases/conversation-development.json`; 이 기획 묶음에 포함되지 않음), 검증 보고서 (원문 참조 경로: `evaluation/reports/conversation-20261025.json`; 이 기획 묶음에 포함되지 않음)를 따른다. 이 개발 세트는 모델 문맥에 예제로 넣지 않지만 독립 검수된 holdout은 아니다.

- 현재 AX 전체 단위·로컬 DB 테스트:164개(단위154/실제 reader DB10), 신규 대화/별칭/경계 단위31개 포함.
- 대화 UI9개: 실제 HTTP/읽기 전용 PostgreSQL + 테스트 전용 인증/모델. 기존 이름/목업 회귀18개는 별도로 확인한다.
- 실제 Vertex 개발14턴 중13턴 기대 충족. 순위→비교→도움→직전 시즌→전체 순위→오래된 결과의 행 참조, 자유 문장으로 시즌 답변,0건→분 조건만 해제→지표 변경 시 득점 필터 유지, 참조 없음의 재질문을 확인했다.
- 마지막 비지원/민감정보 질문1건은 provider429(Resource exhausted)로 보류했다. 단독 분리 실행에서도 같은 응답이었고 통계 SQL/민감 테이블 조회는0이었다. 이를 정상 unsupported 응답 검증 완료나 모델 정답으로 계산하지 않는다.
- 수정 전 r1~r4의 실패도 보고서에 남겼다. 별칭 검증/비어 있는 nested Draft 문제를 고쳤으며, 실제 자료에 없는900분 조건과 모호한 '위에 나온 두 선수'의 잘못된 기대값도 바로잡았다. 외부504/429를 성공 결과로 대체하지 않았다.

실제 모델 평가에는 호출 간격12초를 둬 공급자 부하를 제한했으므로 보고된 턴 지연을 사용자 경로의 p95/SLO로 사용하지 않는다. 통화 비용·운영 quota·독립 holdout·대규모 부하·정식 리뷰·운영 적용은 미완료다. 단위/테스트 모델의 성공을 자연어 이해 정확도 점수로 사용하지 않는다.

## 재현

AX checkout의 `.venv`에 `.[ax,dev]`를 설치한다. `scripts/run_ax_search.py --config <private JSON> --frontend-port 5188 --background`로 실행한다. private config/원본 환경 파일/DSN은 커밋하지 않는다.

```sh
AX_SEARCH_TEST_CONFIG=/private/tmp/benchmark-ax-search/runtime.json .venv/bin/python -B -m pytest tests/unit/test_ax_*.py tests/integration/test_ax_search_live_db.py -q
```

프론트 디렉터리:

```sh
AX_SEARCH_TEST_CONFIG=/private/tmp/benchmark-ax-search/runtime.json AX_PYTHON=/Users/woolee/benchmark-ax/.venv/bin/python ./node_modules/.bin/playwright test --config playwright.ax-search.config.ts
npm run build
```

실제 유료 모델 평가는 아래 명령을 명시적으로 실행한다. provider 자동 재시도는 하지 않고, 상태/의미 조건/실제 결과 ID·변경·유지 여부·토큰/시간을 기록한다. 특정 질문은 `--case-id <id>`로 분리할 수 있다.

```sh
.venv/bin/python -B scripts/evaluate_ax_conversation.py --config /private/tmp/benchmark-ax-search/runtime.json --suite docs/ax/natural-language-search/evaluation/cases/conversation-development.json --output /private/tmp/conversation-evaluation.json --max-turns 14 --min-call-interval 12 --live
```

로컬 서버는 시작 시 전용 reader로 읽기 전용 트랜잭션·권한·snapshot 버전을 확인하고 연결 풀을 준비한다. 검색 때도 같은 검사를 매번 유지한다. UI 첫 요청이 연결 생성에서 대기하던 현상은 이 준비 단계 추가 후 브라우저 9개 시나리오 전체 통과로 재검증했다. 준비 실패 시 서버를 열지 않으며 실제 통계나 모델은 미리 조회하지 않는다.
