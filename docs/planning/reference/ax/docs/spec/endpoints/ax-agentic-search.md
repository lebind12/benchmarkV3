> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/spec/endpoints/ax-agentic-search.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

---
contract: ax-agentic-search
version: 2026-10-29
status: planning-reference
---

# 에이전트 검색 API — 현행 FE 기반 계약

입력: [검색 FE spec](../../features/ax-agentic-search.spec.md), [진행 FE spec](../../features/ax-agentic-progress.spec.md), `frontend/endpoint-requests/POST__api_v1_search_agentic_{conversation,conversation_stream,conversation_cancel}.request.json`. 요청은 현재 FE 목업에서 도출한 초안이며 독립 FE 구현 리뷰/정식 머지 전이다. 이 명세와 현재 `SPEC_REVIEW`는 운영·구현·머지 승인을 소급하지 않는다. 이전 2026-10-25 개요 계약을 현재 FE의 구조화 metadata 요구로 정제했다.

## 1. Endpoint와 공통 인증

| endpoint_id | Method / path | 입력 | 성공 |
|---|---|---|---|
| POST__api_v1_search_agentic_conversation | POST `/api/v1/search/agentic/conversation` | ConversationInput | 200 ConversationResponse JSON |
| POST__api_v1_search_agentic_conversation_stream | POST `/api/v1/search/agentic/conversation/stream` | 동일 ConversationInput | 200 SSE progress → result 또는 error |
| POST__api_v1_search_agentic_conversation_cancel | POST `/api/v1/search/agentic/conversation/cancel` | CancelInput | 200 `{status:"cancelled"}` |

서버에서 공통 JWT 서명/만료·활성 USER/STREAMER/ADMIN을 검증한다. FE role/mockRole/질문에 포함된 관리자 지시는 권한이 아니다. 미인증/위조/만료401, 비활성/금지 role403. 기존 공통 auth가 비활성을401로 분류하는 경우 로그인 공통 계약과 정합을 맞추되 모델/축구 reader 호출은0회다. 인증 장애는503이며 lab code나 운영 권한으로 fallback하지 않는다. 실제 계정·공통 토큰 refresh/rotation/권한 회수 인수는 현재 미완료다.

## 2. 입력과 소유권

모든 입력 객체는 strict/extra-forbid. 문자 길이는 Unicode 문자 수, byte 한도는 별도로 UTF-8 인코딩한 전송 크기다.

| 필드 | 타입/경계 | 규칙 |
|---|---|---|
| request_ref | string, 16..64 chars | 현재 검증된 사용자·access/session binding의 nonce. opaque하며 SQL/role/ID 권한을 담지 않는다. |
| message | string, 1..500 chars | 제출 시 trim 후 공백만 있는 입력 거절. 임의 role/system 지시도 비신뢰 데이터. |
| conversation_ref | string 1..128 또는 생략 | parent_turn_ref와 쌍. 서버 발급/current owner·snapshot·TTL 검사. |
| parent_turn_ref | string 1..128 또는 생략 | 현재 대화의 최신 완료 턴이어야 한다. |

신규 agentic 입력은 message가 필수이며 `choice_ref`를 지원하지 않는다. 확인 질문에는 자연어 message로 답한다. 클라이언트가 SQL/숫자 ID/metric/scope/artifact/role 필드를 보내면422. 질문 안에 그런 문자열이 있는 것은 권한 필드가 아니며 정상 인용·이름을 일괄 차단하지 않는다.

CancelInput은 request_ref만 받는다. 같은 사용자 binding·nonce·동일 payload의 완료 응답은30분 ledger 내 그대로 반환하며 모델/DB 추가 실행0. 같은 nonce·다른 payload409, 실행 중인 동일 요청429. stale parent/다른 사용자·세션/자료 버전·30분 만료409. 한 대화12턴, 사용자 실행1개/전체 실행2개, 최대64대화/256요청은 현재 로컬 자원 기준이며 출시 실측 후 확정한다. 한도는 서버가 집행하고 question/model 제안으로 변경하지 않는다.

토큰 rotation으로 binding이 바뀌면 과거 ref/nonce를 자동으로 새 binding에 재전송하지 않는다. FE는 안전한 표시 이력·입력을 보존하고 새 대화를 안내한다. 안정적 session binding으로 이어받는 변경은 별도 공통 인증 검토가 필요하다. 서버 재시작은 메모리 대화 소실·409/새 대화이며 영속 보관을 약속하지 않는다.

## 3. 공개 JSON 타입과 상한

`Ref=string(1..128)`, `SafeText=string`(필드별 아래 상한), `Scalar=finite number|string(max2000)|null`. 공통 object는 extra-forbid, finite 수만 허용. 서버는 schema를 검증한 뒤 직렬화하며 JSON 전체 **262144 UTF-8 bytes(256KiB)** 이하. 초과는413 safe error; stream 개시 후라면 error event다. FE의 legacy metadata-optional 호환은 출시 서버의 누락 허용 근거가 아니다.

```typescript
type ConversationResponse = {
  conversation_ref: Ref
  expires_in: number // finite >0, 현재1800초 이하
  turn: {
    turn_ref: Ref
    question: string // <=500
    answer: string // <=12000; 실제 ref에서 렌더링한 fact+자유 설명
    status: 'results'|'partial'|'no_matches'|'clarification_required'|'unsupported'|'data_unavailable'
    tables: Table[] // <=4
    steps: {label:string /*<=240*/,status:string /*<=40*/}[] // <=128
    missing: string[] // <=100, item<=600
    sources: {artifact_ref:Ref,description:string /*<=600*/,exported_at:OffsetISO}[] // <=16
    applied?: Applied[] // <=16; 결과 상태에서는 필수, 규칙은 아래
    coverage?: Coverage[] // <=16; 결과 상태에서는 필수
    clarification?: {question:string /*<=600*/,options:[]} // 자연어 확인
    progress_steps?: ProgressStep[] // <=128, id unique
  }
}
type Table = {
  artifact_ref: Ref; title:string /*<=240*/
  columns:{key:string /*1..80*/,label:string /*<=160*/,unit?:string /*<=40*/}[] // 1..24
  rows:Record<string,Scalar>[] // <=100
}
type MetricKey = 'player_goals'|'player_assists'|'player_minutes'|'player_appearances'|
 'player_yellow_cards'|'player_red_cards'|'player_goal_contributions'|'player_goals_per90'
type Applied = {
  artifact_ref:Ref
  scopes:{league_id:positiveInteger,league:string /*1..160*/,season:integer /*1900..2200*/,team:string /*<=160*/|null}[] // 1..4
  metrics:{key:MetricKey,label:string /*<=80*/,unit:string /*<=40*/,definition:string /*<=600*/}[] // 1..8
  filters:{metric:MetricKey,op:'gte'|'lte'|'eq',value:finiteNumber}[] // <=8
  minimum_minutes:positiveInteger|null
  sort:{key:string /*1..80*/,direction:'asc'|'desc',nulls:'first'|'last'}[] // <=8
  selection:{basis:string /*<=240*/,limit:integer /*1..100*/,truncated:boolean}
  derivations?:Derivation[] // <=24, derived release artifact에서는 필수; §6.3
}
type Coverage = {
  artifact_ref:Ref; state:'partial'|'unavailable'|'unknown'
  observed_rows:nonnegativeInteger
  known_metric_players:nonnegativeInteger|null
  excluded_unknown_players:nonnegativeInteger|null
  truncated:boolean
  exported_at:OffsetISO; source_as_of:OffsetISO|null
  dataset_version:string /*1..128*/
  limitations:string[] // <=16, item<=600
}
```

OffsetISO는 UTC `Z` 또는 명시 offset을 가진 유효 ISO8601 시각이다. `exported_at`은 snapshot 채취 시각, `source_as_of`는 실제 원천 업데이트의 보수적 기준이다. FE 현재 시각이나 모델 서술에서 만들지 않는다. source freshness·수집 완전성은 export 시각과 구분한다.

### 3.1 관계·상태 불변식

- table artifact_ref, columns.key, metadata artifact_ref, progress step id는 각 배열 안에서 unique. 각 row의 key 집합은 그 table columns.key 집합과 정확히 같다. 내부 player_id/league_id/source_rows를 columns에서 숨기면 공개 rows에서도 제외한다. 내부 ID는 서버 artifact에 보관하며 공개 row에 우연히 누출하지 않는다.
- 공개하는 모든 값/이름·열 label/unit은 검증된 artifact/등록 의미에서 온다. SQL alias/모델 label은 신뢰된 label/정의가 아니다.
- results/partial/no_matches는 `applied`와 `coverage` 각1개 이상이며 **동일한 artifact_ref 집합**을 갖는다. 공개 table과 source가 참조하는 모든 artifact에 metadata가 있어야 한다. metadata는 table 또는 source의 발급 ref와 연결하고 미발급 ref/중복은 거절한다. derived artifact의 원천은 내부 lineage로 보존한다.
- no_matches는 조회 가능한 관측 범위에서 필터 결과0건이다. tables=[]여도 빈 결과의 source ref·적용 조건·coverage를 반환한다. 미수집/NULL만 있는 것·보관 범위 밖을 no_matches로 바꾸지 않는다.
- partial은 일부 필수 requirement/원천/기록이 없거나 잘림/실행 예산으로 완전하지 않음. 확인된 자료만 공개하고 missing/coverage 이유를 남긴다. NULL은 null이며0으로 치환하지 않는다.
- coverage counts는 서로 다른 개념이다. observed_rows는 해당 scope의 관측 원천 행 수, known/excluded는 지표 유효 선수 수. 알 수 없으면 null; 전체 선수 모집단으로 해석하지 않는다. complete 상태를 임의 생성하지 않는다.
- per90은 명시·합의한 최소 출전 분이 있어야 한다. 분모0/NULL은 null/자료없음. 다중 소속 합계·동률·순서·단위는 등록 정의와 독립 정답을 따른다.
- clarification_required에는 clarification.question과 빈 options가 있고 선택되지 않은 후보를 인기순으로 추정하지 않는다. unsupported/data_unavailable는 안전한 이유·누락을 제공하며 가짜 표로 성공을 가장하지 않는다.

공개 정상 예제는 FE 요청 파일의 `response_example`다. 해당 예제는 합성임을 표시한 XSS 정상 대조군이며 실제 통계 정답이 아니다. no_matches/오류/경계 예제와 테스트는 [testplan](ax-agentic-search.testplan.md)에 연결한다.

## 4. SSE 계약 — stream endpoint 전용

인증·입력 오류는 개시 전 HTTP JSON. 개시 후는200 `text/event-stream`, `Cache-Control:no-store`, `X-Accel-Buffering:no`. UTF-8·LF 또는CRLF, chunk 경계/여러 data line을 처리한다. JSON 문자열 안 개행은 JSON escaping되어 새로운 frame이 되지 않는다. comment keepalive는 진행/데이터가 아니다.

| event | data | 불변식 |
|---|---|---|
| progress | `{sequence:nonnegativeInteger,step:ProgressStep}` | sequence 증가; 중복/역순은 적용하지 않음. 같은 id는 동일 stage/label/started_ms이며 running→completed/failed만 허용. |
| result | ConversationResponse | 단일 JSON endpoint와 동일 결과·nonce. 최종 progress_steps와 전달 이벤트의 identity/종료 상태 일치. |
| error | `{status:integer(400..599),detail:SafeCode}` | 개시 후 안전한 오류. 원문 exception/prompt/SQL 없음. |

`ProgressStep={id:string(1..64),stage:accepted|planning|review|lookup|scope|sql_generation|validation|database|calculation|answer,label:string(<=160),status:running|completed|failed,started_ms:finite>=0,duration_ms:finite>=0|null}`. running iff duration_ms=null. stage label은 서버 허용 목록에서 발행하며 모델 사고 전문/내부 payload가 아니다. 실제 phase 시작/완료/실패만 발행하고 퍼센트·추정 완료시간은 없다.

전체 stream **2097152 bytes(2MiB)**, 미완성 buffer/frame **300000 bytes**, progress 이력128개. terminal은 result 또는 error 중 정확히1개. terminal 뒤 추가 data/두번째 terminal, identity 회귀·일치하지 않는 최종 이력·malformed JSON/UTF-8·한도 초과는 안전한 전송 실패다. 연결 종료까지 terminal이 없으면 유실이며 성공으로 append하지 않는다. 프록시가 실제로 buffering하지 않는지는 서비스 L3에서 검증한다.

연결 해제는 cancel이 아니다. 서버의 bounded 작업과 nonce ledger를 보존해 같은 요청으로 복구한다. FE는 자동 재연결/자동 새 실행을 하지 않는다. 이미 실행 중인 모델/DB 호출의 즉시 중단을 보장하지 않는다. timeout/취소가 반환되면 취소 턴은 이후 commit/append하지 않아야 한다.

## 5. Cancel endpoint 전용

현재 사용자 binding·nonce에만 tombstone을 등록한다. 요청 전 도착·중복 cancel도 같은 응답이며 타사용자 결과를 찾아 반환하지 않는다. 다른 사용자 nonce 문자열이 같아도 별도 namespace다. tombstone은30분이며 bounded256개. 실행 중 요청은 다음 서버 취소 확인 지점에서 중단하고 commit 전 최종 검사한다. 완료된 최신 턴만 rollback 가능하며 후속 턴이 있는 과거 턴을 파괴하지 않는다. 복구된 이전 pending 문맥도 owner/버전/TTL을 유지한다.

200 응답은 정확히 `{status:'cancelled'}`이며 UI 수신 실패·누락·다른 status는 취소 확인 실패다. 성공한 cancel 응답은 모델/DB 과금의 즉시 중단을 뜻하지 않는다. unknown nonce도 타사용자 존재여부를 노출하지 않는 동일 안전한 ack를 사용할 수 있다.

## 6. 서버 실행·의미 무결성·프롬프트 인젝션

[보안 요구](../../ax/natural-language-search/prompt-injection-security.md)의 SEC-01/02·PI-01~12를 모두 연결한다. 요청/이전 대화/이름·별칭/조회 문자열/모델 출력은 비신뢰 데이터다. instruction/data 분리와 프롬프트 금지문은 보조 방어다.

### 6.0 독립 typed QueryIntent — BE-SPEC-01 보완

아래는 **공개 요청 필드가 아닌 내부 실행 계약**이다. Planner의 QueryTask는 `intent` 제안을 포함한다. 기존 label·metrics·scopes만으로 SQL 목적을 추정하지 않는다. 사용자 자연어의 의미 해석은 여전히 모델/독립 oracle 평가 대상이지만, SQL 역할이 받은 목적을 조용히 변경하는 것은 결정론적으로 차단한다.

```typescript
type ScopeReceipt = {
  league_id:positiveInteger; season_year:integer /*1900..2200*/
  team_id:positiveInteger|null; player_ids:positiveInteger[] // unique, <=100
}
type ProjectionIntent = {
  output_key:string /*1..80, safe identifier*/
  operation:'source'|'rank'|'max'|'difference'|'ratio'
  source_key:SourceColumn|null // source/rank/max: registered column; calculation: null
  input_refs:{artifact_ref:Ref,column:string /*1..80*/}[] // 0 for source/rank/max, exactly2 for calculation
  unit:string /*<=40, registry-resolved; model cannot choose*/
  nullable:boolean
}
type SortIntent = {
  key:string /*registered projected/source key, 1..80*/
  direction:'asc'|'desc'; nulls:'first'|'last'
}
type QueryIntentProposal = {
  operation:'source'|'rank'|'max'|'calculation'
  projections:ProjectionIntent[] // 1..24, unique output_key
  grain:('player_id'|'league_id'|'season_year')[] // unique, canonical order
  group_by:('league_id'|'season_year')[]
  filters:{metric:MetricKey,op:'gte'|'lte'|'eq'|'is_not_null',value:finiteNumber|null}[] // <=8, AND only
  sort:SortIntent[] // <=8
  minimum_minutes:positiveInteger|null
  rank:null|{
    function:'rank'|'dense_rank'|'row_number'
    metric:MetricKey; direction:'asc'|'desc'; nulls:'first'|'last'
    partition_by:('league_id'|'season_year')[]
    tie_policy:'competition'|'dense'|'ordinal'
  }
  selection:{
    kind:'limit'|'rank_cutoff'|'all_selected'
    limit:integer /*1..100*/; ties:'exact'|'include'
    source_artifact_ref:Ref|null; positions:positiveInteger[] // unique, <=100
  }
}
type VerifiedQueryIntent = QueryIntentProposal & {
  version:1; intent_ref:Ref; request_ref:string /*16..64*/
  owner_binding:Ref; question_digest:string /*sha256 hex64*/
  dataset_version:string /*1..128*/; definition_version:string /*1..128*/
  scopes:ScopeReceipt[] // 1..4, server-resolved and unique
}
```

`SourceColumn=player_id|name|league_id|season_year|source_rows|MetricKey`. 모든 객체 extra-forbid/strict/frozen이며 receipt의 중첩 객체/배열도 tuple/deep-freeze로 불변 보관한다(속성 대입만 막고 list를 바꿀 수 있게 두지 않는다). 모든 수치는 finite; gte/lte/eq 값은0..100000, is_not_null 값은null만 허용한다. source_rows는 내부 검증용이며 공개 row에 노출하지 않는다. QueryTask의 기존 scopes/player_refs/team_ref/selection_ref는 서버 scope resolve 입력이며 minimum_minutes는 intent 값과 일치해야 한다. ProjectionIntent의 unit/nullable·lineage와 intent의 receipt 필드는 서버가 registry/검증된 자료에서 채우거나 제안값과 대조하며, 모델이 arbitrary 값으로 self-certify하지 못한다.

#### 생성·동결·비교 책임

1. **Planner**: 질문·확인된 이전 조건·issued entity/artifact refs·등록 정의를 근거로 QueryIntentProposal을 제안한다. 단순 텍스트 label은 executable 의미가 아니다.
2. **서버 resolve/freeze**: 원문/확인 답변의 조건 receipt, 발급 ref·owner·TTL·snapshot, 실제 대회/시즌·선수/팀, 등록 지표/operation·단위·NULL·grain·허용 조합을 검증한다. 새 scope·비교 대상은 issued ref로만 resolve한다. 서버가 owner/request/question digest·자료/정의 version·intent_ref와 정규화된 scope를 결합해 **불변 VerifiedQueryIntent**를 만든다. 정당화할 수 없는 조건·미정 기준은 재질문/미지원이며 임의 기본값으로 목적을 만들어내지 않는다.
3. **SQL 역할**: 동결한 intent의 모델에 필요한 부분만 받고 SQL+params를 제안한다. owner binding/인증 비밀은 전달하지 않는다. 모델이 intent를 수정/승인하거나 SQL에서 새로운 목적을 등록하지 못한다.
4. **서버 SQL 비교**: `validate_query_intent(sql, params, intent)`는 structural/lineage gate와 함께 실행된다. intent는 trusted 내부 객체이고 공개 HTTP 입력에서 받지 않는다. 전체 CTE/서브쿼리를 정규화하고 바인딩 실제 값을 대입한 의미를 비교한다. 다르면 ValueError safe-code로 **DB 연결/EXPLAIN 전에 차단**한다. 통과는 검증된 Select AST를 반환한다.
5. **metadata/계산/답변**: applied·coverage·artifact column lineage는 verified intent와 실제 조회/계산에서 만들고 생성 SQL/자유 reason을 파싱해 목적을 역생성하지 않는다. replay는 동일 owner/request/digest/version의 intent만 재사용한다.

내부 구현의 계약 이름은 `app.ax.agentic_types.VerifiedQueryIntent`(strict frozen Pydantic)와 `app.ax.agentic_sql.validate_query_intent(sql, params, intent)`다. 단위의 synthetic receipt 객체는 비교 함수를 시험하기 위한 것이고 HTTP에서 receipt를 받을 수 있다는 뜻이 아니다. 기존 code에 이 인터페이스가 없는 현재는 명확한 missing-implementation Red다.

#### 허용 조합과 정확한 비교 규칙

- **source**: grain=`[player_id,league_id,season_year]`, group_by=[], rank=null. source projections만 허용한다. 실제 scope의 상수 컬럼을 출력에서 생략해도 내부 grain·identity를 잃지 않아야 한다. ID/name/metric은 같은 원천 row instance에 귀속한다. self/cross join으로 서로 다른 row를 결합하지 않는다.
- **rank**: source grain·group_by=[]를 유지하고 source+rank projections만 허용한다. rank.metric은 현재 작업의 등록 metric, rank projection source_key와 같아야 한다. function↔tie_policy는 rank↔competition, dense_rank↔dense, row_number↔ordinal로 고정한다. partition_by의 허용 집합은 정확히 `[]`, `[league_id]`, `[season_year]`, `[league_id,season_year]`다. intent에서 선택한 정확한 집합과 SQL OVER가 일치해야 하며 SQL 역할이 임의 partition/다른 metric·direction/nulls를 추가하지 못한다. rank/dense_rank의 동일값 동률을 player_id로 깨지 않는다. row_number는 sort의 결정적 player_id tie breaker를 포함한다.
- **max**: rank=null. group_by와 grain은 같은 정확한 집합으로 `[]`(요청 scope 전체 단일 집계), `[season_year]`, `[league_id]`, `[league_id,season_year]` 중 하나다. 그룹 순서는 canonical이고 SQL group 순서만 다른 경우 같은 집합으로 정규화한다. group column source projection과 등록 MAX projection만 가능하며 선수 ID/name projection은 불가하다. MAX source_key는8개 MetricKey 중 하나, 입력 표현식은 변환 없는 원천 column이어야 한다. 보호 metric key에 MAX 결과를 덮어쓰지 않는다.
- **calculation**: 생성 SQL로 실행하지 않는다. group_by=[], rank=null, grain=[player_id], source_artifact_ref/검증된 input_refs에 의한 동일 선수 집합, 정확히 두 입력 artifact·각 source column의 단위/기간/version을 검증한다. difference는 동일 단위·비교 가능 지표만, ratio는 정의된 동일 단위 지표의 raw left/right다. 식/키/단위/NULL·0분모·공개 연결은 §6.3을 따른다. validate_query_intent가 SQL+calculation intent를 받으면 거절하고 서버 계산 도구로만 dispatch한다.
- **filters**: 초기 grammar는 등록 metric의 gte/lte/eq/is_not_null을 AND로 묶는 것뿐이다. 중복·순서·괄호·named parameter 이름 차이는 정규화하되 바인딩 값·연산·metric은 일치해야 한다. 삭제/추가/완화/OR 변경은 거절한다. 정렬용 NULL 제외도 모델이 몰래 추가하지 않고 intent에 is_not_null로 고정한다. SQL3-valued NULL 의미를 보존한다. scope/team/player/minimum_minutes는 서버 source에서 강제하는 별도 receipt이며 SQL의 확대 조건으로 완화하지 못한다. 동등성 증명이 불가능한 predicate는 fail-closed·확인 필요다.
- **sort**: 최종 output ORDER BY의 key/순서/direction/nulls를 intent와 비교한다. metric 교체·역순·NULL 우선 변경·tie breaker 누락/변경을 거절한다. rank용 OVER ORDER BY는 final sort와 구별해 별도 비교한다. stable player_id tie breaker는 server source의 같은 identity여야 한다. 여러 scope에서 player_id만으로 유일하지 않으면 league_id/season_year 중 scope가 고정하지 않은 grain 키도 tie breaker로 포함해 안정 순서를 보장한다.
- **selection**: kind=limit/ties=exact는 SQL의 유효 LIMIT가 intent.limit와 같아야 한다. kind=rank_cutoff/ties=include는 검증된 rank의 `<=limit`이고 최종 physical row cap은 서버100(+잘림 감지1)로 별도 적용한다. kind=all_selected는 발급된 source_artifact_ref의 선택 positions/전체 실제 ID를 서버가 resolve하고 그 집합만 조회한다; ties=exact, limit은 반환 한도다. OFFSET·임의 추가row 선택은 불가하다. 잘림은 partial/metadata이며 complete나 전체 최고로 승격하지 않는다.

이 비교는 LLM이 처음부터 사용자 질문을 잘못 해석한 경우까지 증명하지 않는다. natural language→proposal은 독립 질문/expected·실제 모델 인수, proposal→SQL 변경과 output source-lineage는 결정론적 서버 검사의 별도 책임이다. 두 성공률을 섞지 않는다.

### 6.1 SEC-01: 공개 가능한 모든 셀의 검증된 lineage

SQL은 제안일 뿐이다. 기존 전체 AST/단일 SELECT·허용 relation/function/cast·바인딩·복잡도·서버 scope subquery·read-only role·EXPLAIN·timeout/byte/row 게이트를 유지한다. SQL에 metric 열이 한 번 등장했다는 것만으로 의미를 승인하지 않는다.

| 허용 종류 | 서버가 확인할 의미 | 금지 예 |
|---|---|---|
| source pass-through | CTE/alias 경유를 포함해 원천 column과 동일 identity/value/NULL·grain. 보호 key player_id/name/league_id/season_year/등록 metric에는 그 의미만 가능. 일반 alias는 허용하되 서버가 lineage와 public label/unit을 결정한다. | `999+0*player_goals AS player_goals`, `player_assists AS player_goals`, source name 문자열 치환·player_id+1 |
| 검증된 rank/window | 허용 rank 함수·등록 지표·정렬/null/tie·파티션과 typed 조회 목적이 일치; 표시 위치와 순위를 구분 | 다른 지표 rank를 요청 지표 순위로 표시, stale/truncated 표를 전체 최고로 주장 |
| 등록 aggregate | 최초 registry는 아래 MAX만 지원한다. **승인된 operation registry**에서 함수·원천 metric·NULL 정책·그룹 grain·단위·label을 정의. 이름이 익숙해도 임의 산식은 미등록. | `MAX(999+0*player_goals) AS maximum`, 집계값을 선수-grain `player_goals`로 덮어쓰기 |
| 서버 파생 계산 | ID로 검증된 source artifacts를 결합한 difference/ratio, 입력 ref·단위·NULL/분모·순서·시즌을 보존 | 행 위치 결합, 미발급 ref, NULL→0,0분모 비율, 임의 Python/eval |

최초 공개 aggregate registry는 `MAX(metric)`(등록8개 MetricKey), 허용 group은 정확히 `[]`, `[season_year]`, `[league_id]`, `[league_id,season_year]`, grain=해당 group 조합, unit=원천 metric 단위다. 원천 metric은 변환 없는 source column이어야 하고 전체가 NULL이면 null, 부분 NULL이 있으면 원천 coverage를 표시한다. MAX를 선수별 합계나 전체 최다 선수로 설명하지 않는다. 모델이 작성한 SUM/AVG/COUNT·새 산식의 공개 output은 의미/NULL/분모 계약과 독립 oracle 추가 승인 전 fail-closed한다(서버가 신뢰한 source 집계 SQL의 SUM은 별개). 현재 정상 회귀 `MAX(player_goals) AS maximum GROUP BY season_year`는 source metric=player_goals, operation=MAX, grain=season_year, unit=골의 등록 대조군이다. 원래 source player_goals를 덮어쓰는 같은 집계는 거절한다. 등록되지 않은 연산은 명확히 미지원/검증 실패이며 모델이 registry를 추가·승인하지 못한다.

별칭명만 검사해서는 안 된다. `999+0*player_goals AS arbitrary_value`와 임의 text claim도 공개 가능한 fact로 승인하면 안 된다. CTE·중첩SELECT 전체에서 output lineage를 추적한다. 서로 다른 원천 행의 ID와 이름을 self/cross join으로 묶는 것도 잘못된 identity이며 검증된 관계가 없는 조인은 fail-closed한다. 검증 불가능한 함수·산식·관계는 DB 실행·artifact 발급 전에 거절한다.

내부 artifact에는 각 출력 열의 source metric/operation/input refs/grain/unit/NULL/definition version과 실제 scope/filter/sort/selection·잘림을 연결한다. 공개 column label/unit·applied/coverage는 이 서버 기록에서 만든다. SQL alias/모델 설명으로 metadata를 역생성하지 않는다. SQL의 필터/정렬/그룹·집계가 typed 조회 목적과 일치하는지도 확인하고, 자연어→typed 목적의 의미 정확성은 독립 expected/실제 모델 인수에서 별도 판정한다.

기존 DB 범위 테스트 `MAX(player_goals) AS player_goals`는 새 protected-key 정책과 충돌한다. 목적은 범위 확대 차단이므로 등록 aggregate alias로 바꾸고, 기존 표현은 새 spoof 거절 테스트로 보존한다. 이전 PASS를 현재 의미 인수로 재사용하거나 기존 테스트를 삭제해 실패를 숨기지 않는다.

### 6.2 SEC-02: 자유 설명과 확인/미지원 경계

제품의 자유 설명·답변 에이전트를 유지한다. 수치·선수명·연도·출처 같은 factual span은 검증된 artifact ref/typed metadata에서 렌더링한다. 자유 설명에 숫자가 없다는 사실만으로 진실성을 보장하지 않는다. 근거 없는 한글 수사·거짓 이름/인과/출처·prompt 반향도 공격 회귀/의미 인수에 포함한다.

clarify/unsupported의 임의 모델 reason을 실행 권한이나 공개된 사실로 취급하지 않는다. 안전한 reason code+서버 지원 문구·검증된 후보/누락 metadata로 공개하는 계약을 사용한다. 추가 LLM 심사나 금지어 denylist가 서버 권한판정자가 되지 않는다. 일반 자유 설명을 완전 템플릿 제품으로 조용히 바꾸지 않는다.

모델 입력에는 인증/DB 비밀을 넣지 않고 내부 prompt/진단·로그를 최소화한다. 모든 자연어의 진실성과 prompt 비유출을 정적 검사로 완전히 보장한다고 주장하지 않는다. **실제 지정 모델+독립 의미/유출 평가가 SEC-02 출시 차단 게이트**다. 실패/미실행/429/504·잔여위험을 분리 기록한다.1건의 비밀/타사용자 노출·근거 조작된 통계 제공은 출시 차단이다.

### 6.3 서버 파생 계산과 공개 metadata — FE 수요 보완

FE가 먼저 추가한 `Applied.derivations`와 `derived_response_example`을 따른다. 이는 기존 difference/ratio의 정의·근거를 노출하는 보완이며 새로운 축구 지표를 임의 등록하는 기능이 아니다.

```typescript
type Derivation = {
  output_key:string /*1..80*/; operation:'difference'|'ratio'
  left:{artifact_ref:Ref,column:MetricKey}
  right:{artifact_ref:Ref,column:MetricKey}
  join_keys:['player_id']
  unit:string /*1..40*/; null_policy:'propagate'
  zero_denominator:'unavailable'|null
}
```

- `Applied.derivations?:Derivation[]`는 최대24개, output_key unique다. source artifact에서는 생략 가능하고 **출시 derived artifact에는1개 이상 필수**다. legacy optional 허용은 공개 인수 PASS가 아니다.
- 최초 지원은 동일 MetricKey·원천단위·의미/정의 version을 가진 두 **source artifact**의 비교다. derived-on-derived·cross-metric 비율·임의 단위 변환은 별도 정의/oracle 승인 전 미지원이다. 각각의 left/right ref는 같은 응답의 sources·Applied·coverage에 존재하고 내부 artifact의 실제 source column과 연결되어야 한다. 내부자료 version은 같고 비교기간/league는 검증된 QueryIntent가 허용한 범위여야 한다.
- 서버는 player_id로1:1 결합한다. 중복 ID/grain·잘린 입력을 완전한 모집단으로 취급하지 않는다. 이름은 같은 source identity에서 가져오고 행순서나 모델 서술로 짝짓지 않는다. 미기록/NULL은 propagate→null이며 missing/coverage에 이유를 남긴다.
- difference는 `left[column]-right[column]`. unit은 양쪽 원천 metric의 동일 unit이며 zero_denominator=null이다. ratio는 **raw `left[column]/right[column]`**(×100 아님), unit='배', zero_denominator='unavailable'이다. 분모0 또는 입력NULL은 null/자료없음이며0·Infinity·NaN으로 만들지 않는다. 반환 finite 수의 소수 오차는 oracle별 명시 허용오차로 비교한다.
- 공개 Table columns에서 `current`는 left 원천값, `previous`는 right 원천값이며 두 column unit은 원천 단위다. `change` 또는 지정 output_key는 Derivation.output_key와 정확히 연결하고 해당 column unit은 Derivation.unit이다. source metric이 골이어도 ratio output을 골로 표시하지 않는다. 실제 시즌은 left/right artifact_ref에 대응하는 Applied.scopes로 연결하며 배열 순서를 의미로 사용하지 않는다.
- derived Applied.scopes는 양쪽 source scope를 중복 제거해 기록한다. Applied.metrics는 원천8개 정의를 유지하고 계산정의는 Derivation에서 전달한다. 공개 설명/라벨은 서버가 operation·입력 scope·단위에서 렌더링한다. 내부 artifact에는 output column별 operation/input refs/source key/grain/unit/NULL/zero/version을 보존한다. 공개 sources에는 필요한 설명/시각만 제공하고 내부 선수 ID 목록·SQL/불필요한 ref dump는 하지 않는다.
- source/derived의 applied·coverage 집합은 §3.1을 유지한다. derived coverage는 불확실성/누락을 원천에서 전파하고 원천이 partial이면 complete로 승격하지 않는다. per90를 계산의 입력으로 쓸 때 각 source의 명시 최소 출전 분·분모 정책도 그대로 유지한다.

## 7. 오류 계약

SafeCode는 ASCII `^[a-z][a-z0-9_]{0,79}$`, 내부 원문을 그대로 코드로 만들지 않는다. JSON `{detail:SafeCode}`; stream 개시 후 동일 code를 error event로 보낸다.

| HTTP | 조건 | 대표 code/동작 |
|---|---|---|
| 401 | 없거나 위조/만료 access | login_required; 모델/reader0 |
| 403 | 금지 role·비활성 계정/출처 | forbidden 또는 active_user_required; 모델/reader0 |
| 409 | nonce payload 재사용·stale parent·취소/만료/타owner | request_reference_reused/conversation_parent_changed/turn_cancelled/conversation_expired |
| 413 | 입력/문맥/결과 byte 예산 | agent_context_budget/agent_result_budget; 안전하게 종료 |
| 422 | schema·추가필드·잘못된 ref/계획 | invalid_question/invalid_query_plan/unissued_entity_reference 등 검토한 code |
| 429 | 사용자/전체동시성·실행/모델 예산·provider quota | user_request_in_progress/search_concurrency_limit/provider_rate_limited; 무한retry0 |
| 502 | provider 구조/근거/공개 schema 불일치 | agent_output_unavailable/ungrounded_answer_reference/ungrounded_answer_number; 위조값 공개0 |
| 503 | auth/reader/구성/신선도 | authentication_unavailable/query_execution_unavailable/agentic_search_not_configured/dataset_refresh_required |
| 504 | 전체/모델 deadline | agent_deadline/interpretation_timed_out |

입력 Pydantic의 기본422 details 배열과 위 safe-code 계약 차이는 implementation gap이다. 공개 schema 오류는 code로 정규화하며 내부 field/value/prompt를 오류에 반향하지 않는다. 공통 auth의 한국어 detail도 검색 endpoint 경계에서는 검토된 code로 정합화한다.

## 8. 데이터·DB·실제 인수 의존

공통 API의 opt-in 검색 router를 사용한다. 기존 API-Football 저장본만 조회하고 검색에서 외부 통계/API-Football·웹검색/워커를 호출하지 않는다. 실제 활성 대회·대회별 현재+직전 시즌·6시간을 적용한다. reader는 전용 SELECT-only views/pool이며 기본 쓰기 계정으로 fallback하지 않는다. READ ONLY·snapshot/definition version·statement3초/lock250ms·EXPLAIN cost≤100000·100행/결과 예산·bounded model loop는 현재 로컬 안전 기준이고 운영 값은 실측/리뷰로 확정한다.

운영 reader/view migration·ORM 정합·snapshot/projection 갱신/일관성·권한 회수·공통 실제 계정·source freshness는 출시 필수 미완료 의존이다. 평가용 새 local mirror는 별도 격리 증거며 운영 구조 완료가 아니다. 쓰기/부하·schema 생성은 운영 public에 수행하지 않는다. source public의 읽기 전용 snapshot은 운영 통계 원천 확인용이며 테스트 데이터/사용자 인증 행을 추출하지 않는다.

단위에서는 외부 의존성·reader를 mock한다. DB 통합은 격리 schema fixture/전용 테스트 mirror를 사용하고 production public에 DDL/테스트 쓰기 금지. 실제 모델 평가는 독립 expected ID/값/조건/상태/근거와 비교한다. runner의 `completed`는 실행완료이지 정답/인수 PASS가 아니다. 변경 구현 coverage≥80%·unit/integration marker 선택·FE L2/L3-local/실서비스L3/L4를 별도 기록한다.
