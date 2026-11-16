> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/ax/natural-language-search/learning-agentic-search.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 구현하며 배우는 에이전트 검색

2026-10-25. 사용자는 에이전틱 구조를 먼저 완성하고 성능 개선은 이후 진행하며, 개발 과정에서 프레임워크 설명을 함께 요청했다. 이 문서는 실제 코드의 역할을 설명한다. 실행 증거/현재 한계는 구현 기록 (원문 참조 경로: `agentic-implementation.md`; 이 기획 묶음에 포함되지 않음)을 따른다.

## 1. 구성 요소를 구분하기

| 기술 | 현재 맡은 일 | 이 프로젝트 코드 |
|---|---|---|
| FastAPI | HTTP 요청·공통 인증·오류와 응답 | `app/main.py`, `app/ax/agentic_api.py` |
| LangGraph1.2.17 | 상태를 가진 작업의 실행 순서·분기·반복 | `app/ax/agentic_runner.py` |
| Vertex/Gemini | 질문 해석·다음 작업 판단·SQL 작성·설명 | `app/ax/agentic_vertex.py` |
| Pydantic | 모델 출력과 내부 도구 입력의 타입/범위 검증 | `app/ax/agentic_types.py` |
| SQLGlot | 생성 SQL의 AST·참조·허용 구문 검사 | `app/ax/agentic_sql.py` |
| SQLAlchemy/psycopg | 바인딩·읽기 트랜잭션·권한/버전 검사·DB 실행 | `app/ax/agentic_sql.py`, `search_sql.py` |

LangGraph Node는 Python 함수다. LLM을 호출할 수도 있고 일반 계산·DB 검증만 수행할 수도 있다. 프레임워크 도입으로 모델의 지식·판단이 자동 개선되는 것은 아니며 질문 의미·근거 충분성·권한·SQL 정확성은 별도 설계와 평가가 필요하다.

## 2. State, Node, Edge

State는 지금까지의 실행 상황이다. 현재 GraphState는 Run 객체와 Decision을 운반한다. Run은 질문/이전 대화, 이름 후보, 근거 요구사항(needs), 실제 결과(artifacts), 도구 오류, 예산·취소 정보를 보관한다.

Node는 한 단계의 작업이다. 현재 그래프의 실제 노드는 planner/act/answer 세 개다. LLM 역할인 SQL 조립은 act에서 query를 수행할 때 호출된다. 계산과 조회 도구는 act에서 서버 함수로 실행한다. 논리적인 에이전트 역할 수와 그래프 노드 수가 같아야 하는 것은 아니다.

Edge는 다음 노드를 선택한다. Planner의 action이 lookup/query/calculate면 act로, clarify/finish/partial/unsupported면 answer로 이동한다. act가 끝나면 다시 planner로 간다.

```python
# 실제 구현을 축약한 예시
builder = StateGraph(GraphState)
builder.add_node("planner", plan)
builder.add_node("act", execute_action)
builder.add_node("answer", compose_answer)
builder.add_edge(START, "planner")
builder.add_conditional_edges("planner", choose_next)
builder.add_edge("act", "planner")
builder.add_edge("answer", END)
graph = builder.compile()
```

compile은 실행 가능한 그래프를 만든다. invoke는 상태를 넣어 실제 실행한다. 현재는 서버가 동기 경로의 제한된 실행 슬롯에서 invoke를 호출한다. 일반 API의 이벤트 루프에 동기 모델 함수를 직접 넣는 방식으로 작성하지 않는다. 비동기 호출/스트리밍/지연 최적화는 후속이다.

## 3. 한 질문이 실행되는 과정

예: 이번 시즌 EPL 득점 상위3명의 직전 시즌 득점을 비교하고 가장 늘어난 선수를 묻는다.

1. Planner는 필요한 근거 세 항목(현재 상위 선수, 같은 선수의 이전 기록, 증감)을 만든다.
2. 이름 도구가 EPL을 실제 대회 후보 ref에 연결한다. 동명이인은 사용자가 확인한다.
3. SQL 역할이 SELECT와 params를 작성한다. 서버가 허용 스키마·구문·범위를 검사하고 실제 DB를 조회한다.
4. 서버는 결과에 artifact_ref를 발급한다. Planner는 이 ref로 같은 선수들을 다음 조회의 대상으로 지정한다.
5. 이전 시즌 결과를 받으면 계산 도구가 player_id로 결합해 증감을 계산한다. 행 순서·모델 기억으로 결합하지 않는다.
6. Planner가 근거를 검토하고 종료를 제안한다. 서버는 실제 근거 ref와 요구사항 상태를 검사한다.
7. 답변 역할은 설명 text와 실제 결과 셀 참조를 반환한다. 서버가 확인한 값으로 문장·표를 만든다. 없는 이전 기록은0으로 바꾸지 않는다.

현재 역할 호출은 Google SDK의 구조화 JSON 출력으로 action/작업을 받으며, 서버가 도구를 dispatch한다. native function-call 응답을 SDK가 자동 실행하는 경로와 구분한다. 역할별 호출 모델은 모두 지정 `gemini-4-argon`이다.

## 4. 왜 스키마 검증이 두 단계인가

모델 전송 스키마는 제공자 API가 처리할 수 있어야 한다. 내부 Pydantic 계약은 실행할 때 필요한 정확한 타입·길이·허용 값·범위를 강제해야 한다. 둘은 목적이 다르다.

실제 개발 중 첫 Planner 요청이 제공자의 일반400 INVALID_ARGUMENT로 거절됐다. 공개 문서는 복잡한 스키마가400을 만들 수 있다고 안내한다. 전송용 제약을 줄이고 도구 인자를 명시적으로 정의한 뒤 Planner의 lookup/query 출력은 실제 호출에서 확인했다. 제공자 오류의 구체 필드는 응답에 없으므로 특정 필드 하나가 유일한 원인이라고 단정하지 않는다.

SQL 응답은 sql/params_json이라는 작은 wire schema를 사용하고, 수신 후 params_json을 JSON 객체로 해석해 내부 SqlProposal로 다시 검증한다. 전송 스키마를 단순화해도 실행 검증을 생략하지 않는다.

## 5. 그래프와 실행 권한

SQL 역할은 football_players라는 가상 relation만 사용한다. 서버가 허용된 대회·시즌·실제 선수 ID로 이 relation을 구성하고 읽기 전용 DB view에 연결한다. 에이전트는 접속 비밀을 보유하거나 SQL을 직접 실행하지 않는다.

SQLGlot의 AST 검사는 SQLAlchemy의 바인딩, DB role 권한, snapshot 버전 검사, EXPLAIN·timeout과 함께 적용한다. 파싱이 된다는 사실만으로 질문의 의미에 맞는 SQL임을 보장하지 않는다. 다른 쿼리 형태도 허용하되 실제 정답 ID/수치와 독립적으로 비교한다.

## 6. 상태 저장과 현재 한계

현재 compile에는 영속 checkpointer를 연결하지 않았다. 대화·artifact는 소유권/TTL/예산이 있는 서버 메모리에 있다. 같은 세션의 후속 질문/응답 유실 재시도는 지원하지만 프로세스 재시작 후 중간 작업 복구는 지원하지 않는다. LangGraph를 설치한 것만으로 영속 저장이 생기는 것은 아니다. 운영 복구 요구가 확정되면 별도 Supabase 상태 테이블과 마이그레이션/권한·보존 정책을 검증해야 한다. Upstash 용도를 임의 확대하지 않는다.

학습 순서: State/Node/Edge → 구조화 계약 → 반복 계획·근거 추적 → SQL 경계 → 취소/멱등성·체크포인트 → 실제 모델 품질 평가 → 성능 개선. 각 단계의 코드 변경·테스트 의미·관측된 실패를 개발 설명에 함께 남긴다.

## 실행 제어와 진행 표시

현재는 작업 안에 Progress.phase를 두어 시작·완료·실패를 기록하고 SSE로 브라우저에 전달한다. LangGraph가 실행 경로를 제어하고, Progress가 실제 작업 경계를 관측하며, 브라우저가 현재 역할·경과 시간·이력을 표시한다. 과거 결과를 다시 조회할 때는 Planner/SQL 단계가 반복될 수 있다. SSE의 error 이벤트는 스트림이 열린 후의 실패를 전달하며 네트워크 단절과 구분한다. [진행 시각화 구현](progress-visualization.md)을 함께 읽는다.

## 참고

- [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Google structured output](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/control-generated-output)

공식 문서는 프레임워크 기능의 근거다. 위 역할 분리·근거 장부·실행 제한은 이 프로젝트가 직접 구현하는 설계다.
