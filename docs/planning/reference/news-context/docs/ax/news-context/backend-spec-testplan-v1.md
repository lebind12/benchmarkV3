> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `news-context` 워크트리의 `docs/ax/news-context/backend-spec-testplan-v1.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 뉴스 문맥 백엔드 명세·구현 방향·독립 테스트 설계

상태: **읽기 전용 설계 산출물**. FE 브라우저·독립 검토와 gold 검토가 남아 있다. 이 문서는 API 구현 착수 승인이나 구현·테스트·검토 완료 증거가 아니다. 파일 수정, 테스트, 네트워크 호출, DB 쓰기, git 변경은 수행하지 않았다.

기준은 `contract-v12-operator-amended.json`의 **필수 요구 14개·수용 시나리오 58개**, `replan-v6`, `feedback-policy-v2`, `query-catalog-v2`, `evaluation-plan-v2` 및 실제 FE 코드다. 과거 구현의 PASS를 승계하지 않는다.

## 1. Endpoint 요청 정합성과 최소 DTO 보완

### 1.1 현재 구현에서 확인한 차이

- `productionContextAdapter`는 모든 동작에 연결 미준비 오류를 반환한다. 실제 문맥 API 연결은 아직 없다.
- 기존 `/news/analyze`는 본문 **20,000자**, 팀·선수 추출 **최대 30개**, 이름별 중복 제거 방식이다. 전체 50,000자·등장별 문맥 분석의 기반 완료로 간주할 수 없다.
- 기존 `NewsVertexProvider`의 STOP 확인, 민감 예외 차단, 실제 호출 `finally`에서 슬롯 반환하는 방향은 재사용할 수 있다. 기존 추출 스키마·프롬프트·이름 연결기는 새 요구에 맞게 분리해야 한다.
- `useNewsContext`는 완료 결과에서 `allValidated`, 문서 버전, span과 revision을 검사한다. 그러나 전체 구간 처리 여부를 검증할 데이터는 현재 `ContextResult`에 없다.
- `CandidateEditor`는 거부 시 `target:null`로 preview하고, 저장 시 `rejectedTarget`을 보낸다. preview 결과의 빈 후보로 선택 상태가 초기화되는 경로까지 독립 검증해야 한다.
- 현재 서버 인증은 비활성 계정에 401을 반환한다. endpoint 요청 계약의 비활성 403과 다르므로, 새 문맥 경계에서 계약에 맞게 처리하고 기존 인증 전체를 불필요하게 변경하지 않는다.

### 1.2 FE 조작에서 도출된 API

기준 경로는 `/api/v1/admin/management/news/context`다. 아래 외의 백엔드 전용 제품 endpoint는 추가하지 않는다.

| FE 조작 | 요청 | 서버 책임 |
|---|---|---|
| 분석 제출 | `POST /jobs` | 입력 검증, 요청자 소유 작업 생성, 제출 키 중복 제거, 202 |
| 작업 통지·재연결 | `GET /jobs/{jobId}/events?after=…` | 인증 fetch stream, 동일 작업·cursor 재생, 순서 보장 |
| 취소 | `POST /jobs/{jobId}/cancel` | 취소 요청과 실제 정리 완료 구분, 멱등 처리 |
| hover/focus/tap 카드 | `POST /cards/resolve` | 문서·등장·조건·revision·자료시각 검증, DB 재조회 |
| 다른 DB 후보 찾기 | `GET /candidates` | 다섯 entity 종류 검색, 필터 검증, 빈 결과와 장애 구분 |
| 이 글에 적용 | `POST /corrections/preview` | 대상·조건·거부 후보 검증, 공통 저장 없는 재조회 |
| 최신성 확인 | `GET /decisions/revision` | 현재 revision 및 변경 범위 확인 |
| 완료 이후 판단 변경 통지 | `GET /decisions/events?after=…` | 작업 통지와 독립된 인증 구독, gap 검출 |
| 생성·수정 | `POST /decisions` | 사람 확인, 범위 검증, 판단·감사·revision 원자 저장 |
| 저장 응답 유실 확인 | `GET /decision-submissions/{submissionKey}` | 동일 원자 결과 반환, 미확정은 202 |
| 판단 취소 | `POST /decisions/{id}/revoke` | 버전·revision 검사, 새 취소 버전과 감사 저장 |
| 이력 | `GET /decisions/history` | 공유 판단의 생성·수정·취소 이력 및 편집자 표시 |

모든 요청은 **현재 활성 STREAMER/ADMIN**을 검사한다. 임시 작업·문서 증명·결과 재생에는 **소유자 일치**도 필요하다. 다른 ADMIN이라도 타인의 작업은 404다.

### 1.3 목업 검토 후 반영할 최소 DTO 보완

아래는 기존 요구를 표현하기 위한 계약 정정이다. 새로운 사용자 결정을 요구하지 않는다.

| 항목 | 현재 부족한 점 | 필요한 최소 보완 |
|---|---|---|
| 제출 응답 | 어댑터는 `{jobId}`만 표현 | `rootRequestId`와 서버가 바인딩한 문서 식별·증명 반환 |
| 문서 소유권 | 임의 `documentVersion` UUID와 span만으로는 소유권 증명 불가 | 서버 발급 `documentBinding`을 카드·preview·저장 요청에 전달. 사용자·입력 digest·원문 버전·출처·등장에 결속 |
| 거부 preview | `target:null`만으로 거부 대상 식별 불가 | `action:'reject'`, `rejectedTarget:{kind,id}` 명시. preview 이후에도 거부 ID 유지 |
| 조회조건 | `intent/metric/team/competition/season/aggregation`이 자유 문자열 | 입력 제안은 유지하되 서버 검증 결과인 `resolvedQuery` 추가: Q enum, DB 참조, metric key, 시즌·기간·단위·집계·확인 상태 |
| 경기 범위 | 팀 문자열 하나로 양 팀·경기 조건 표현 불충분 | 검증된 양 팀 참조, fixture 참조, 대회·시즌·기준일 표현 |
| 사실 근거 | `evidenceKo` 문자열만으로 독립 대조 불가 | 구조화 `provenance`: 테이블·행/경기 ID·JSON 경로·단위·분모·관측/자료시각 |
| 선택 결과 | 후보 배열만으로 연결·모호·거부·미확인을 명시하기 어려움 | `resolution`과 선택된 DB 참조 또는 명시적 거부 참조 |
| 전체 결과 | `allValidated:boolean`만 존재 | 원문 길이/digest, 서버 분절 목록·범위·처리 상태, 전체 coverage, 검증 버전·판단 revision·자료 근거 추가 |
| 작업 취소 | `JobEvent` union에 취소 완료 없음 | `cancelling`과 terminal `cancelled` 추가. `complete`만 result 허용하는 판별 union |
| revision | `checkRevision():string`이 변경 범위를 버림 | `{revision,changedScopes,gap}` 반환. 기존 revision 이후를 같은 endpoint에서 확인 |
| 판단 구독 | `RevisionEvent`에 cursor·변경 범위 없음 | cursor·changedScopes 추가, 재연결 cursor 입력 지원 |
| 후보 검색 | 반환 배열에서 revision 소실 | `{items,knowledgeRevision}` 보존 |
| 오류 | `ContextError` 종류·ID가 제한적이고 일부 UI가 고정 ID 사용 | 안전 오류 DTO의 실제 request/root/job/stage/attempt 정보 전달 |
| 충돌 | 단일 `latest`만으로 여러 중첩 범위 충돌 표현 부족 | 기존 `latest`에 충돌 이유·관련 범위/판단 목록을 선택적으로 추가 |

`documentVersion`은 FE가 보내는 `clientInputVersion`과 대응시키되, **그 UUID 자체를 권한 증명으로 사용하지 않는다**. FE가 현재 수행하는 버전 일치 검사를 깨지 않도록 서버 소유권 증명을 별도 필드로 둔다.

카드 식별은 최소한 다음 요소를 포함한다.

`문서 binding + occurrenceId + 대상 kind/id + 카드 kind + resolvedQuery hash + knowledgeRevision + sourceAsOf`

같은 등장에 프로필·기록 카드가 여러 개 있는 경우도 구분한다. 현재 FE의 occurrence 중심 상태가 카드 종류를 합쳐 버리지 않는지 확인한다.

## 2. 저장 스키마·제약·트랜잭션

### 2.1 가장 단순한 구성

FastAPI, SQLAlchemy, 기존 Postgres, 단일 프로세스 메모리 작업 관리자를 사용한다. Celery·분산 큐·새 Redis 캐시는 도입하지 않는다.

| 자료 | 저장 위치 | 핵심 제약 |
|---|---|---|
| 실행 중 작업·원문·분절·시도 | 프로세스 메모리 | 요청자 소유, 유한 작업 수·호출 예산 |
| 완료 결과·통지 재생 | 프로세스 메모리 | 전문 없이 종료 후 최대 10분 |
| 종료 표식 | 프로세스 메모리 | 본문 없이 종료 후 최대 24시간 |
| 공통 판단 현재값 | 신규 Postgres 테이블 | 활성 상태·버전·정규화 범위 키 |
| 판단 감사 이력 | 신규 Postgres 테이블 | append-only, 판단별 버전 유일 |
| 저장 제출 결과 | 신규 Postgres 테이블 | `(actor_id, submission_key)` 유일 |
| 지식 revision·변경 범위 | 신규 Postgres 테이블 | 단조 증가, 판단 transaction과 함께 기록 |

테이블명은 구현 시 기존 naming에 맞추되 역할은 다음과 같이 고정한다.

- `news_context_decision`: 종류, 표면형/검색용 정규화값, action, 대상/거부 대상, 검증된 조건·범위, 최소 구절·필요 문맥·출처, active, version.
- `news_context_decision_audit`: 판단 ID·버전·revision, 전후값·사유, actor FK와 표시 snapshot, 시각.
- `news_context_submission`: actor·제출 키·operation·정규화 payload digest·확정 응답.
- `news_context_revision`: 단일 revision 행.
- `news_context_change`: revision·판단 ID·변경 전후 범위.

기존 `TranslationAudit`의 `editor_id SET NULL + editor_name 보존` 패턴을 따른다. 계정 참조가 사라져도 표시와 감사는 보존한다. 판단에 새 만료·hard delete 정책을 만들지 않는다.

### 2.2 참조와 범위 제약

다형 대상은 검증 없는 JSON ID 하나로 저장하지 않는다.

- 팀·선수·감독·리그·경기별 nullable FK와 종류 일치 CHECK를 두거나, 동등하게 FK 무결성을 보장하는 관계 구조를 사용한다.
- link는 정확히 하나의 유효 대상, reject는 정확히 하나의 명시적 거부 대상이 필요하다.
- 삭제된 대상은 새 연결 근거로 적용하지 않는다. 감사에는 당시 ID·표시 snapshot을 보존한다.
- scope의 팀·대회·경기 참조도 서버가 실제 DB에서 검증한다.
- 기간은 문자열을 그대로 비교하지 않고 검증된 시작/끝·시즌 관계로 정규화한다.
- document_reference의 동일성은 소유자·서버 문서 binding·등장까지 포함한다.
- `extra='forbid'`로 `editor_id`, 자유 SQL, 원천 수치 덮어쓰기 등 계약 외 필드를 거절한다.

동일 범위 키는 target을 제외한 판단 의미를 기준으로 만든다. 다만 후보 거부는 **거부 대상별 구분**이 필요하다. 여러 정당한 후보 거부를 하나로 합치지 않는다. 서로 다른 종류 사이의 link/reject 상충과 기간 중첩은 유일 인덱스 하나로 해결되지 않으므로 저장 서비스에서 검사한다.

### 2.3 원자 저장 순서

가장 단순한 초기 구현은 짧은 transaction에서 revision 단일 행을 잠가 판단 쓰기를 직렬화하는 방식이다.

1. 현재 actor 권한을 다시 검사한다.
2. 제출 키가 있으면 actor·operation·payload digest를 비교한다.
3. 동일 요청의 확정 응답은 그대로 반환한다. 같은 키의 다른 payload는 충돌이다.
4. revision 행을 `FOR UPDATE`로 잠근다.
5. 개별 `expectedVersion`, `expectedRevision`, 동일/중첩 범위 상충을 검사한다.
6. DB 대상·scope·소유 문서 증명을 검증한다.
7. 판단 생성/새 버전, 감사, revision 증가, 변경 범위, 제출 응답을 함께 기록한다.
8. commit 이후 구독자를 깨운다.

LLM 호출 중 DB transaction이나 row lock을 유지하지 않는다. 감사 저장 실패 시 판단·revision·제출 결과도 rollback한다.

동시에 제출된 동일 키의 두 요청은 하나만 저장하고 다른 요청은 그 결과를 받는다. commit 이후 HTTP 응답만 유실돼도 조회 endpoint에서 같은 결과를 얻는다. revoke에도 같은 규칙을 적용한다.

무관한 revision 변경은 변경 범위를 검사한 뒤 최신 revision으로 재기준화할 수 있다. 관련 범위·영향 불명확·동일 버전 충돌은 자동 덮어쓰기하지 않는다.

### 2.4 Migration과 기존 baseline

- `0018_home_preview_storage` 및 기존 SQL은 변경하지 않는다.
- 신규 기능 SQL은 새 `supabase/migrations/<timestamp>_news_context_*.sql`로 작성한다.
- 새 Alembic revision은 실제 부모 revision을 명시하고 **같은 Supabase SQL 파일**을 읽는 기존 mirrored 방식을 따른다.
- 신규 ORM·CHECK·FK·유일/부분 인덱스와 SQL의 parity를 실제 Postgres에서 검사한다.

외부 `staging-baseline-parity-v1.json`의 **기존 9개 representation 차이**는 별도 baseline이다. `management_one_active`, 뉴스 인덱스의 정렬 표현, 선수 득점 인덱스, transfer 날짜 인덱스 관련 차이를 그대로 식별한다.

검사는 “알려진 baseline 차이와 정확히 같음” 및 “신규 기능 차이 0”을 구분한다. 기존 차이를 이유로 관계없는 모델을 재작성하거나 모든 차이를 무시하지 않는다. baseline 자체가 달라지면 조사 대상으로 남긴다.

## 3. Provider·작업 프로토콜·수명

### 3.1 실제 Vertex 처리

기존 Vertex 인증·설정 경로를 재사용하되 모델 응답이나 인증 값을 저장·노출하지 않는다. 실제 모델 식별자·프롬프트·generation config는 평가 전에 지문으로 고정한다.

처리 단계는 다음과 같다.

1. **입력 검증:** 변형 없는 원문, 코드포인트 길이, URL, 선택 기준일·시각·시간대 검사.
2. **분절:** 원문 전체 `[0,lengthCp)`를 덮는 서버 구간 목록 확정.
3. **공통 문맥:** 명시 날짜·대회·대상 관계·혼합 주제를 추출한다.
4. **구간 추출:** 축구 관련 영역, 원문 인용, 구간 내 등장 순번, 대상 종류, Q 의도·조건 제안을 얻는다.
5. **DB 후보 검색:** 정식명·번역명·확인된 별명·초성·소속/시즌 관계를 검색한다.
6. **문맥 판별:** 모델에는 서버가 제공한 후보 키를 선택하게 한다. 실제 ID·kind·관계는 서버가 다시 검증한다.
7. **고정 DB 조회:** 검증된 Q01~Q13 handler를 실행한다.
8. **전역 검증:** 전체 구간, 인용·등장, DB 참조·값·시점·한국어 표시, 최신 판단을 검사한다.
9. **전체 공개:** 모든 검증이 끝난 결과 하나만 `complete`로 보낸다.

30개 제한과 이름 단위 중복 제거는 제거한다. 같은 원문 등장만 병합하고, 반복·중첩·교차 등장과 다른 종류의 카드는 보존한다.

입력 언어를 10개 허용목록으로 제한하지 않는다. 대표 10언어와 혼합 언어는 평가 범위다. 한국어 사실 영역은 DB 값·번역·도메인 렌더러로 만들고 생성 설명과 분리한다.

본문 속 도구 명령·자기 승인·HTML은 데이터다. 모델에는 SQL 실행·네트워크·저장 권한을 주지 않는다. 출처 URL을 가져오거나 게시일을 추정하지 않는다.

### 3.2 오프셋과 전체 coverage

모델의 숫자 offset을 정본으로 삼지 않는다. 모델은 `segmentId + literal quote + occurrenceIndex`를 반환하고 서버가 원문에서 정확한 위치를 결정한다.

- Python 코드포인트 기준 `[startCp,endCp)`를 사용한다.
- 원문 CRLF, NFC/NFD, 결합 문자, 보조평면, RTL을 그대로 유지한다.
- 인용의 여러 등장 중 어느 것인지 확정되지 않으면 자동 연결하지 않는다.
- 분할 경계의 중복 문맥은 원문 좌표로 되돌리고 동일 등장만 병합한다.
- 모든 구간은 `분석됨 / 축구 아님 / 해석 확인 필요`로 종료해야 한다.
- 처리 실패 구간이 하나라도 있으면 `allValidated=true`나 `complete`를 허용하지 않는다.

구간 검증과 별도로 필수 자동 연결 누락을 gold로 검사한다. coverage가 100%라는 이유만으로 의미 정확도를 통과시키지 않는다.

### 3.3 자동 복구와 자원 제한

| 상황 | 처리 |
|---|---|
| 일시 timeout·429·5xx | 실패 단위만 지수 백오프, 최초 포함 최대 3회 |
| `MAX_TOKENS`·잘린 JSON | 성공으로 채택하지 않고 실패 단위를 제한적으로 재분할 |
| 스키마·인용 불일치 | 검증 실패로 처리, 유한 복구 후 전체 실패 |
| DB 일시 조회 장애 | 해당 조회만 복구, 정상 모델 단위 재호출 금지 |
| 영구 인증·안전 차단 | 의미를 숨긴 안전 코드로 종료, 무의미한 반복 금지 |
| 취소·권한 철회 | 후속 호출·재분할·저장 예약 중단 |
| 작업 기한 소진 | 전체 실패, 부분 결과 공개 금지 |

초기 재분할 깊이는 부모 설계대로 1단계다. 분절 수에 따른 총 호출 예산, 재판별 예산, 작업 deadline을 제출 시 고정한다. 복구·재분할·revision 재검토가 모두 같은 예산을 소비한다. 숫자는 50,000자 실제 측정으로 조정하되 지원 길이나 평가 기준을 낮추지 않는다.

뉴스 provider의 호출 슬롯은 API-Football semaphore와 별개다. 기존 슬롯 2개는 초기 재사용 후보이며 실측 전 성능 보장이 아니다.

**취소한 await나 브라우저 연결 종료는 실제 provider 종료가 아니다.** 동기 HTTP 호출을 thread에서 수행한다면 그 thread가 끝나는 내부 `finally`에서만 provider 슬롯을 반환한다. 작업 정리·원문 파기도 실제 호출 종료를 기다린다. 같은 사용자의 후속 작업은 정리 완료 전에 시작하지 않는다.

### 3.4 통지·재연결·취소

- `POST /jobs` 중복 제출은 같은 actor·제출 키·payload에 같은 작업을 반환한다.
- 스트림 단절은 같은 job과 마지막 cursor로 재연결한다. 새 분석을 제출하지 않는다.
- `processing/recovering/reconnecting/cancelling`에는 최종 결과를 넣지 않는다.
- `cancelled`는 provider 정리와 원문 파기가 끝난 terminal 상태다.
- 취소 endpoint의 202는 요청 접수다. 어댑터 Promise는 같은 job 스트림의 정리 완료 또는 200 확인 후 resolve한다.
- FE가 기존 스트림을 abort한 경우 취소 어댑터가 같은 endpoint로 정리 확인을 이어간다. polling endpoint를 신설하지 않는다.
- 통지 구독 해제 자체가 사용자 취소는 아니다.
- 프로세스 재시작 후 없는 작업은 명시적 `lost`다. 자동 재실행하지 않는다.

판단 변경 구독은 작업 완료 후에도 유지한다. DB 변경 이력과 cursor를 이용해 누락을 동기화하며, 클라이언트의 주기 polling은 추가하지 않는다.

### 3.5 원문 수명과 종료 이후 검증

| 시점 | 처리 |
|---|---|
| 실행 중 | 원문·임시 provider 응답은 메모리에서만 처리 |
| 실제 종료·취소 정리 | 원문·prompt·원시 응답·미완료 추출 자료 참조 해제 |
| 종료 후 10분 이내 | 전문 없는 검증 결과·최소 인용·이벤트 재생 |
| 재생 만료 후 | 본문 없는 terminal 표식으로 `replay_expired` 구분 |
| 종료 후 24시간 경계 | 임시 표식 해제 |
| 공통 판단 | 위 TTL 적용 없음 |

브라우저가 이미 받은 결과는 재생 버퍼 만료만으로 지우지 않는다.

원문을 파기한 뒤 카드·저장을 검증하려면 서버 발급 증명이 필요하다. 가장 단순한 방식은 프로세스 수명에 결속된 인증 증명으로 다음을 묶는 것이다.

- actor, 문서 버전·입력 digest·출처 digest
- occurrence·범위·정확한 인용
- 서버가 확인한 최소 문맥 범위/내용 digest
- 카드 종류·검증 조건·DB provenance·판단 revision

사용자가 제출하는 구절은 증명된 인용의 부분 범위여야 한다. 필요 문맥도 증명된 최소 문맥 안에서 검증하며 임의 본문을 받지 않는다. 전체 글을 `necessaryContext`, 사유, JSON에 우회 저장하지 못하게 한다.

증명에 전문을 싣지 않으며 개별 증명들을 모아 전체 원문을 재구성하는 응답도 피한다. 최소 문맥 상한은 gold의 모호성 사례와 함께 동결한다.

재시작으로 증명을 검증할 수 없으면 저장을 성공시키지 않고 현재 입력 재분석을 안내한다. 기존 공유 판단을 수정할 때는 서버가 보관한 해당 판단의 원본 provenance를 재사용할 수 있으며, 새 문맥으로 바꾸는 경우 새 소유 증명이 필요하다.

### 3.6 안전한 오류 상관관계

요청 ID는 body 검증·인증 dependency **이전**에 부여한다. 성공·401·403·404·409·410·422·429·503·504 모두 안전한 ID를 갖는다.

```json
{
  "code": "SAFE_ERROR_CODE",
  "messageKo": "한국어 행동 안내",
  "requestId": "server-generated",
  "rootRequestId": "validated-root",
  "jobId": "optional",
  "segmentId": "optional",
  "attemptId": "optional",
  "parentAttemptId": "optional",
  "stage": "safe-stage"
}
```

기존 `failure_metadata`의 allowlist 방향을 확장한다. 로그에는 단계·시도·버전·길이·token·시간·허용 finish reason만 남긴다. Pydantic 오류의 입력값, provider 응답, 원문, SQL bind 값, 원시 예외 문자열을 기록하지 않는다.

후속 요청이 보낸 root/job ID도 소유권과 연결 관계를 확인한다. 다른 사용자의 진단 흐름에 합류시키지 않는다.

## 4. Q01~Q13 고정 조회 구현

자유 SQL이나 모델 생성 JSON 경로를 실행하지 않는다. Q enum별 서버 handler와 코드 기반 metric 사전을 둔다.

metric 사전은 `key → 허용 Q·대상 grain·DB 컬럼/JSON 경로·타입·단위·NULL 의미·집계·분모·표시명`을 정의한다. unknown metric은 확인/미지원 상태이며 유사 필드로 임의 대체하지 않는다.

공통 반환에는 실제 행/경기 참조, 대회·시즌, 조건, 요청/관측 표본, 자료시각, 사건/관측시각, 누락·충돌 상태가 필요하다.

| Q | 고정 조회 방향 | 독립 검증 핵심 |
|---|---|---|
| Q01 기본정보 | entity와 4종 translation 조회. 소속·감독은 관계/관측을 별도 표시 | 현재 프로필을 과거 사실로 사용하지 않음. 한글 미등록 주표시 |
| Q02 선수 경기 기록 | fixture→detail.players에서 실제 player external ID·팀을 확인하고 허용 경로 추출 | 분·골·도움·카드·슈팅·패스 등. NULL과 키 없음, 실제 0 구분 |
| Q03 최근 기록 | 명시 기준일·대회·시즌으로 경기 집합을 먼저 만들고 선수 기록 연결 | 팀 N경기와 선수 N출전 구분. 득점>0으로 출전 판정 금지 |
| Q04 시즌 기록 | `player_season_stat`의 선수×팀×대회×시즌 grain 유지 | 이적 선수의 복수 팀 행 합산 조건·중복 방지. 평점 단순 평균 금지 |
| Q05 기간 비교 | 같은 metric·단위·집계·기간 의미를 가진 Q02~04 결과 비교 | 시즌 전체/동일 경기 수/동일 시점 구분, NULL·부분 표본 명시 |
| Q06 경기 결과 | 양 팀·날짜·대회·시즌으로 fixture 후보 조회 | FT/AET/PEN, 정규/연장/승부차기 분리. 원문 주장과 사실 구분 |
| Q07 상대전적 | 양 팀의 보관 범위 내 종료 fixture 조회, 안정 정렬 | 수록 2시즌을 역대 전적으로 표시하지 않음. 승부차기 별도 |
| Q08 순위 | 대회×시즌×그룹×팀 조회, raw_data와 정규화 컬럼 대조 | 실제 0·NULL·키 없음·원천 없음·충돌 전수 검사 |
| Q09 팀 흐름 | 기준일·대회·홈/원정·시즌의 순서 있는 fixture 집합 | 진행/누락 경기를 제거해 연승을 부풀리지 않음 |
| Q10 팀 경기 통계 | detail.statistics의 팀 external ID와 type 사전 매핑 | `%`·숫자·NULL·알 수 없는 type, 합계/평균/비율 구분 |
| Q11 소속·감독 관측 | 시즌 관계 및 fixture+lineups의 선수·감독 관측 | A→B→A, 공백·복수 대회. `team_coach` first/last를 연속 재임으로 사용 금지 |
| Q12 이적 | transfer와 실제 player/team FK 조회, 날짜·유형·원천 update 구분 | 실제 적재 양성 사례 필수. 이적 발생일과 관측시각 분리 |
| Q13 부상 | injury와 fixture/player/team/league 조회 | reported_at은 관측/보고 시각. onset·회복일·기간 창작 금지 |

### 4.1 NULL·시점·coverage 규칙

- `0`은 유효한 수치다. NULL·키 없음·미수집을 0으로 변환하지 않는다.
- 최근 N경기 합계에는 선택된 경기 목록과 지표별 유효 표본 수를 붙인다.
- 부분값은 “요청 N경기 중 확인 M경기 합계”로 표시한다.
- 날짜만 있으면 시간은 null이다. 일중 선후가 필요한 해석을 자정으로 확정하지 않는다.
- 상대 날짜는 기준일·필요 시간대가 없으면 확인 대상으로 남긴다.
- 현재 시즌 합계·순위로 과거 기준일 값을 대신하지 않는다. 재구성할 수 없으면 `historical_missing`이다.
- 보관범위 밖과 보관범위 안 미수집은 다르다.
- 대회별 실제 현재·직전 시즌을 사용한다. 월드컵처럼 희소한 **2026/2022**를 연도 차이로 제외하지 않는다.
- 활성 수집 여부와 DB 수록 범위는 별도 정보다.

순위는 `rank/points/goalsDiff`, `all.played/win/draw/lose`, `all.goals.for/against`의 존재·타입·NULL을 먼저 검사한다. raw와 정규화 값이 다르면 충돌로 남긴다.

### 4.2 기존 helper 재사용 범위

`app/services/fixture_detail.py`의 `_team_recent_fixtures`, `get_team_recent_matches`, `get_h2h`, `get_league_standings`, `get_statistics`, `get_fixture_lineups`와 관련 파서·참조 구성 코드를 검토해 재사용한다.

다만 현재 의미를 그대로 승계하지 않는다.

- recent helper는 종료 상태·cutoff가 있지만 추가 대회·시즌·누락 검사가 필요하다.
- `get_h2h`는 h2h 테이블 우선 및 현재 경기 제외 의미가 있다. Q07의 요청 범위와 일치할 때만 사용한다.
- standings helper는 정규화 수치를 반환하므로 Q08 원천 존재/충돌 검사를 추가해야 한다.
- 기존 lineups·통계 파서의 0 기본값이나 표시용 축약이 provenance를 잃지 않는지 검사한다.

조회 로직을 내부 서비스로 재사용하며 기존 HTTP endpoint를 서버 내부에서 다시 호출하지 않는다.

## 5. 피드백 범위·재사용·버전·무효화

| 종류 | 일치 조건 | 효과 | 비적용 기준 |
|---|---|---|---|
| alias | 표면형·언어·대상 종류 및 확인된 팀/대회/기간 | 후보 포함·판별 근거 강화 | 다른 팀·시점·비유에 강제 적용 금지 |
| reject_candidate | 표면형·명시 후보 ID·문맥 범위 | 해당 후보만 자동 연결에서 제외 | 다른 후보·범위는 유지 |
| fixture | 양 팀·대회·시즌/날짜·기준일 | 같은 경기 후보 강화 | 기준 다른 ‘어제’에 재사용 금지 |
| metric | 용어·언어·축구 문맥·단위·집계 | 검증된 metric key로 해석 | 비축구 ‘공포’ 등에 적용 금지 |
| document_reference | 서버 문서 binding·등장·해석 대상 | 해당 문서 등장만 교정 | B의 새 글·편집된 원문에 전역 재사용 금지 |

모든 적용은 `match/mismatch/unknown`과 이유를 남긴다. 미입력 제약은 전역 검증을 뜻하지 않는다. unknown은 자동 확정 근거로 쓰지 않는다.

자동 분석은 공통 확정 판단을 생성하지 않는다. 사용자의 명시 선택·거부·최소 문맥·범위 확인 후 저장 조작만 영속 판단을 만든다.

공개 직전, 카드 열기, focus 복귀, 저장·취소 직전에 revision을 확인한다. 사용한 판단 ID가 없어도 분석 중 새로 생긴 같은/중첩 범위 거부를 검출해야 한다.

- 관련 변경: 영향받은 판별·조회·카드를 내부 갱신한다.
- 영향 불명확: 보수적으로 재검토한다.
- 이벤트 gap·연결 단절: 최신성 미확인으로 표시하고 저장 차단한다.
- 재동기화 완료 전: 구버전 근거를 현재 판단으로 표시하지 않는다.
- 반복 변경: 같은 작업 기한·예산 안에서만 복구한다.
- 역할 철회: 새 조작·구독·결과 접근과 후속 provider 호출을 차단한다. 기존 판단을 일괄 삭제하지 않는다.

공유 판단 수정·취소 권한과 개인 작업 소유권은 별도다. 현재 권한을 가진 B가 공유 판단을 수정할 수 있어도 A의 임시 원문·작업은 열 수 없다.

## 6. 워커 데이터 흐름과 평가 원천

### 6.1 관찰된 선행 의존성

외부 원천 snapshot은 `0018_home_preview_storage` 기준이며 다음 상태다.

- snapshot ID: `613c5cb41cad6aee3e8192526b26b1398619b68c9e5485991bbb130f651ee2b4`
- snapshot hash: `5028c34c2ba9b36ed4921d3876fca9ff55de9d4765e0a5b834935f29c670a7a9`
- `transfer=0`, `injury=0`, `h2h_fixture=0`
- manifest의 `coverage_sufficient=false`

실제 HTTP 관찰은 injuries 1,078개, transfers 306개 응답 항목 및 EPL 시즌 coverage를 포함한다. 이름·현실 관계가 독립적으로 검증된 전체 사실집이라는 뜻은 아니다. 실제 값은 관찰 provenance와 독립 DB 근거로 판정한다.

`independent-facts-v1.json`도 이적 자료 없음, 현재 스냅샷의 과거화 금지, NULL의 0 변환 금지를 명시한다. 실제 기사·모델 결과를 보고 gold를 역작성하지 않는다.

### 6.2 필요한 적재 경로

실제 관찰 HTTP → 기존 daily-sync client 경계 → mappers → store → runner의 commit/진행·오류 처리 → disposable staging → 양성 Q12/Q13 → 새 immutable snapshot 순서다.

현재 존재하는 사전 테스트 인터페이스를 구현 대상으로 삼는다.

```text
transfer_rows_from_api(entry, *, season_windows)
injury_from_api(entry, *, observed_at)
upsert_transfer_entry(session, entry, counts, *, season_windows)
upsert_injury_entry(session, entry, counts, *, observed_at, allowed_seasons)
```

현재 확인한 mappers/store에는 이 transfer/injury 함수가 없다. `select_latest_two_actual_seasons`는 이미 존재한다.

- injury는 검증된 대회·시즌과 fixture 관계를 따른다.
- transfer는 season/league 컬럼이 없으므로 선수·팀 관계와 명시적인 시즌 날짜 범위로 포함 근거를 만든다.
- 첫/마지막 fixture 날짜를 transfer 허용 범위로 사용해 여름 이적을 누락시키지 않는다.
- 기존 테스트의 날짜 범위는 테스트 입력이다. 모든 대회에 같은 시즌 경계를 적용하는 정책으로 승격하지 않는다.
- player/team 등의 필수 부모가 없으면 건너뛰고 미적재 이유를 집계한다. 부분 payload로 기존 프로필을 덮어쓰거나 가짜 부모를 만들지 않는다.
- 실제 source에서 fixture가 없는 경우와, 외부 fixture ID는 있지만 로컬 FK가 아직 없는 경우를 구분한다.
- 관측 시각을 부상 발생일로 바꾸지 않는다.
- 프로필·사람 수정 번역은 보호한다. 필요한 부모 수집은 기존 entity 수집 경로에서 해결한다.

API-Football의 전역 semaphore **6**, Ultra 한도 **450 req/min**, 최초 포함 최대 **3회**를 유지한다. 현재 client 기본 rate는 300이므로 이를 450 실동작으로 오인하지 않는다. 기존의 더 보수적인 설정을 임의로 올리지 않는다.

뉴스 API에는 외부 축구 API 호출을 넣지 않는다. 이번 범위 밖 워커의 수동 endpoint도 추가하지 않는다.

### 6.3 NULL 유일성의 입증 후 정정

현재 transfer 유일키에는 nullable 양 팀 FK가, injury 유일키에는 nullable fixture FK가 포함된다. Postgres의 일반 UNIQUE는 NULL을 동일하게 취급하지 않으므로 멱등성 위험이 있다.

먼저 실제 Postgres에서 다음을 재현한다.

- 같은 NULL 포함 행 두 번 적재
- 다른 미해결 external 부모를 가진 행 적재
- 부모 FK 삭제/미존재와 재실행
- 부분 commit 뒤 재시작

중복 또는 서로 다른 사건의 오합침이 입증되면 그 자연키에 필요한 최소 migration만 추가한다. `NULLS NOT DISTINCT`나 부분 인덱스만으로 외부 부모 식별까지 해결됐다고 주장하지 않는다. 서로 다른 미해결 fixture/팀을 구분해야 한다면 원천 external ID를 보존하는 최소 구조가 필요하다.

### 6.4 Staging과 준비 도구 정정

기존 snapshot은 보존하고, 실제 워커로 staging을 보강한 뒤 **부모 snapshot·HTTP hash·수집 코드·허용 범위·새 테이블 hash**를 연결한 새 snapshot을 만든다. 앱에는 최종 원천을 읽기 전용으로 제공하고 피드백 쓰기 영역을 분리한다. 운영 DB는 쓰지 않는다.

외부 준비 기록의 `tests/unit/test_news_context_evaluation_tools.py` **33 passed**는 준비 도구 단위검사 기록이다. 실제 Postgres 복원 성공이나 제품 PASS가 아니다.

실제 restore 실패는 SQLSTATE `42601`, `TIMESTAMP WITH TIME ZONE` cast를 regex로 잘못 제거한 문제다. 정정 방향은:

- reflection으로 얻은 quoted identifier
- 명시적으로 typed bindparam을 가진 bound INSERT
- identity에 `OVERRIDING SYSTEM VALUE`
- compiler SQL regex 제거
- 실제 Postgres에서 timestamp·JSONB·NULL·identity·FK·sequence 다음 값·행 hash 회귀검사

기존 baseline 9개 차이는 앞 절의 명시적 비교로 처리한다.

## 7. 58개 시나리오 → 독립 테스트·파일·명령

### 7.1 테스트 파일·명령 표기

실제 Postgres가 필요한 P assertion의 파일·명령은 §9에서 live suite/control 경로로 정정한다.

아래는 **향후 구현할 테스트 계약**이다. 현재 실행 결과가 아니다.

| 코드 | 파일·명령 |
|---|---|
| U | 신규 `tests/unit/test_news_context_rules.py` → `python -m pytest -q tests/unit/test_news_context_rules.py -k <메서드>` |
| J | 신규 `tests/unit/test_news_context_jobs.py` → `python -m pytest -q tests/unit/test_news_context_jobs.py -k <메서드>` |
| P | 신규 `tests/integration/test_news_context.py` → `python -m pytest -q tests/integration/test_news_context.py -k <메서드>` |
| L | 신규 `tests/integration/test_news_context_live.py` → `python -m pytest -q tests/integration/test_news_context_live.py -k <메서드>` |
| W | 기존 `tests/unit/test_daily_sync_transfers_injuries.py` → `python -m pytest -q tests/unit/test_daily_sync_transfers_injuries.py` |
| T | 기존 `tests/unit/test_news_context_evaluation_tools.py` 및 신규 실제 PG 준비 회귀 → 각각 해당 파일의 pytest |
| B | `frontend/e2e/news-context-live.spec.ts` 확장 → `npm --prefix frontend run test:e2e -- --config=playwright.news-context.config.ts e2e/news-context-live.spec.ts --grep <테스트명>` |
| M | 기존 목업 `frontend/e2e/news-context.spec.ts` → 같은 명령에서 파일명을 변경. 목업 증거로만 사용 |
| E | 수정된 host runner·evidence checker. 아래 전체 명령 사용 |

표의 메서드는 Python에서는 `test_` 접두사를 붙이고, B/M에서는 같은 이름을 테스트 제목으로 사용한다. 복수 코드가 있으면 각 계층의 독립 증거가 필요하다.

| 시나리오 | 메서드·파일/명령 | 고정 oracle·필수 관찰 |
|---|---|---|
| R01-S01 | `snapshot_preserves_input` — U,P,B | 원문·URL·언어·줄바꿈 동일, URL fetch 0 |
| R01-S02 | `codepoint_input_boundaries` — U,P,B | 49,999/50,000 전체 처리, 50,001/빈 글/잘못된 URL은 provider 호출 전 거절 |
| R01-S03 | `late_result_never_rebinds` — J,B | 입력/출처 수정·취소 뒤 원문 유지, 이전 binding 결과 미반영 |
| R02-S01 | `multilingual_same_entities` — L,B,E | 10언어 고정 대상·한국어 출력, 실제 모델 3회 |
| R02-S02 | `unicode_span_dom_identity` — U,L,B | 혼합·발음부호·조사·emoji·RTL 인용과 DOM 범위 일치 |
| R02-S03 | `korean_name_missing_state` — U,P,B | 번역 유/무·매핑 누락·오류 구분, 추정 음역의 DB 번역 가장 금지 |
| R02-S04 | `facts_and_explanation_separated` — P,L,B | coach_translation 포함, 언어별 ID·값·날짜·집계 동일 |
| R03-S01 | `community_relevance_positive_negative` — L,B,E | 실제 축구/비축구 gold, must_link 누락과 금지 연결 모두 0 |
| R03-S02 | `mixed_document_segment_relevance` — L,B | 축구 영역 유지, 게임·일상·비유 영역 오연결 0 |
| R03-S03 | `article_instructions_are_data` — U,P,L,B | 본문 명령의 호출·저장·권한 영향 0, HTML 실행 0 |
| R04-S01 | `only_validated_db_candidates` — U,P,L | 조작 ID/kind·관계 거절, coach/league/fixture 포함 |
| R04-S02 | `same_surface_distinct_occurrences` — U,L,B | 같은 이름의 다른 대상·경기가 각 위치에 대응 |
| R04-S03 | `ambiguity_not_search_probability` — U,L,B | 짧은 이름·초성·별명 후보와 한국어 근거, 유일 검색만으로 확정 금지 |
| R04-S04 | `overlap_crossing_offsets` — U,P,B | 반복·교차·중첩·NFC/NFD·CRLF의 전수 span 대응 |
| R05-S01 | `recent_five_correct_grain` — P,L,B | 독립 경기 목록·기록·분모·누락, 시즌 합계 대체 금지 |
| R05-S02 | `fixture_candidates_and_scores` — P,L,B | 독립 대진·날짜·대회·스코어, 복수 후보 수정 가능 |
| R05-S03 | `history_and_coach_observations` — P,L,B | 같은 기준 비교, 감독 A→B→A·공백·대회 교차 관측 |
| R05-S04 | `worker_ingestion_positive_history` — W,P,L | 실제 HTTP→실제 store/runner→PG, 재실행·재시작·양성 Q12/Q13 |
| R05-S05 | `catalog_q01_to_q13` — P,L,E | 13개 각각 구절·조건·행·JSON 경로·값/NULL·분모 대조 |
| R06-S01 | `relative_time_requires_reference` — U,P,L,B | 명시 날짜 우선, 기준 없는 어제/지난 시즌 확인 필요 |
| R06-S02 | `claims_are_not_confirmed_facts` — L,B | 부정·루머·가정·비유와 DB 사실 분리 |
| R06-S03 | `missing_zero_conflict_historical` — U,P,B | 순위 raw 실제 0/NULL/키 없음/충돌, 과거 프로필·재임 날조 금지 |
| R06-S04 | `db_only_actual_two_seasons` — P,L,B | 뉴스 경로 football 외부 호출 0·UI polling 0, 2026/2022 유지 |
| R06-S05 | `reference_edit_and_counting_units` — P,L,B | 날짜/시간/시간대 수정, 5팀경기/5출전·과거 snapshot 의미 |
| R07-S01 | `profile_and_context_hover` — B | 이름/문장 카드, 포인터 이동 유지, 후보·링크 조작 |
| R07-S02 | `accessible_overlapping_cards` — B | focus/tap/Escape/바깥 클릭·모바일 경계, 겹친 대상 각각 접근 |
| R07-S03 | `card_keys_recovery_reverse_order` — J,P,B | 역전 응답·조건·종류·revision·자료시각 분리, 내부 복구·소진 |
| R08-S01 | `candidate_choice_updates_occurrence` — P,B | 팀·대회·시점으로 구별한 선택이 해당 등장만 변경 |
| R08-S02 | `search_outside_initial_candidates` — P,B | DB 정답 추가 검색·보류, 빈 검색과 장애 구분 |
| R08-S03 | `correction_requeries_validated_plan` — U,P,B | 날짜·대회·시즌·지표 수정 후 실제 재조회, 임의 수치/SQL 거절 |
| R08-S04 | `explicit_rejection_survives_preview` — P,B | no-link preview 뒤 거부 kind/id 유지·저장, 다른 연결 보존 |
| R09-S01 | `a_confirmation_affects_b_new_text` — L,B,E | A 저장 뒤 B의 다른 글에서 실제 적용 ID·버전·효과 |
| R09-S02 | `scope_mismatch_and_unknown` — U,P,L | 팀·시점·대회·언어·비유·기준일 반례, unknown 자동 확정 금지 |
| R09-S03 | `minimal_human_confirmed_atomic_save` — P,B | 확인 없는 저장 0, 최소 문맥만 보존, 동일 제출 한 번, 실패 rollback |
| R09-S04 | `rejection_effect_and_counterexample` — L,B,E | v0/v1 잘못된 후보 재연결 방지, 다른 범위 정답 보존 |
| R09-S05 | `five_feedback_kinds_states` — U,P,L,B,E | 5종 match/mismatch/unknown·v0/v1/v2, 대명사 새 글 효과 금지 |
| R10-S01 | `versioned_history_and_revoke` — P,B | 생성/수정/취소 전후·actor·시간·범위·버전과 최신 재사용 |
| R10-S02 | `concurrent_version_conflict` — P,B | 두 실제 transaction/브라우저, 한 성공·한 409, 자동 덮어쓰기 0 |
| R10-S03 | `restart_rollback_invalid_target` — P | commit 후 재시작 보존, 감사 실패 전부 rollback, 삭제 대상 재사용 0 |
| R10-S04 | `revision_invalidation_all_boundaries` — J,P,B | 신규 같은 범위 거부·열린 카드 취소·gap·focus·save·publish 검사 |
| R10-S05 | `sequential_scope_conflict_role_loss` — P,B | 최신 revision이어도 동일 범위 상충 생성 거절, 역할 철회 뒤 감사 유지 |
| R11-S01 | `whole_50k_over_thirty_links` — U,L,B,E | 한/영/혼합 앞·중간·끝·경계의 30개 초과 필수 등장 전수 대조 |
| R11-S02 | `truncation_never_partial_success` — J,B | candidate 1+MAX_TOKENS/잘린 JSON, 재분할 성공 또는 전체 실패 |
| R11-S03 | `bounded_attempts_and_real_finally` — J,P,B | provider barrier 해제 전 슬롯 유지·후속 호출 0, 기한/시도 상한 |
| R11-S04 | `real_vertex_50k_measurements` — L,B,E | 실제 호출·finish reason·token·시간·완료, 실측 없는 SLA/비용 금지 |
| R11-S05 | `automatic_whole_publish_recovery` — J,B | 제출 이후 추가 사용자 조작 0, 정상 단위 재호출 0, 전역 검증 전 공개 0 |
| R11-S06 | `reconnect_lifetimes_and_loss` — J,P,B | 같은 job/cursor, 10분/24시간 경계·restart·권한·독립 판단 구독 |
| R12-S01 | `request_lineage_all_error_paths` — U,J,P,B | auth/input/429/503/504 포함 root→job→segment→attempt→최종 오류 |
| R12-S02 | `no_sensitive_content_in_diagnostics` — U,P,B | canary 원문·provider 문자열·비밀이 응답/로그/SQL 저장에 없음 |
| R13-S01 | `roles_and_job_ownership` — P,B | 허용 역할 전체 흐름, 무인증/USER/비활성/만료/위조 거절, 타인 ADMIN도 404 |
| R13-S02 | `actor_spoof_and_midjob_revocation` — J,P,B | editor 위조 거절, 구독·재연결·결과·후속 호출/저장 차단 |
| R14-S01 | `reviewed_prediction_blind_gold` — T,E | 출처·구절·대상·조건·필수/금지/허용 확인의 사전 동결·독립 검토 |
| R14-S02 | `real_full_feedback_roundtrip` — L,B,E | 실제 Vertex→DB→한국어 카드→A 저장→B 새 글→수정/취소 |
| R14-S03 | `all_scenarios_fingerprints_required` — T,E | 58개 누락/skip/실패·지문 불일치가 전체 완료 차단 |
| R14-S04 | `frontend_acceptance_precedes_backend` — M,E | FE 목업 브라우저·독립 검토→DTO 정정→BE, 과거 PASS 불승계 |
| R14-S05 | `immutable_source_independent_oracles` — P,T,E | 첫 모델 실행 전 snapshot/gold hash, 원천 write 거절, 결정적 조회 재현 |
| R14-S06 | `three_actual_semantic_repetitions` — L,B,E | 매 회 must_link 누락·금지 연결·필수 값/ID/span 오류 0, 적용 가능한 v0/v1/v2 |
| R14-S07 | `host_evidence_integrity_handoff` — T,E | 실제 명령·종료코드·원본 관찰·지문, 변조/누락/재생의 실제 실행 가장 실패 |

### 7.2 의미 있는 Postgres 테스트 방식

P 계층은 SQLite나 SQL 문자열 RecordingSession으로 대체하지 않는다.

- **유일성:** 실제 중복 INSERT·upsert·NULL 조합을 commit하고 행 ID·행수를 검사한다.
- **FK:** 실제 부모 없는 참조 및 부모 삭제 후 대상 무효화를 검사한다.
- **충돌:** 서로 다른 connection 두 개와 barrier로 같은 버전 저장을 겹친다.
- **순차 충돌:** 두 번째 요청이 최신 revision을 알고 있어도 동일 범위 반대 판단을 새 생성할 수 없는지 검사한다.
- **원자성:** 판단 반영 후 감사 INSERT 지점에서 transaction 실패를 일으키고 모든 관련 테이블을 새 connection에서 확인한다.
- **재시작:** 첫 API 프로세스를 실제 종료한 뒤 두 번째 프로세스에서 판단·이력·제출 결과 보존을 읽는다. 임시 job은 lost여야 한다.
- **적재 재시작:** 부분 batch commit 후 중단·재실행하여 중복·프로필 손상·번역 변경 여부를 확인한다.
- **snapshot 보호:** 앱 계정의 원천 테이블 INSERT/UPDATE/DELETE가 실제 권한 오류로 거절되는지 검사한다.

기존 `RecordingSession` 테스트는 SQL 쓰기 범위와 호출 의도 검사로만 유지한다.

### 7.3 Offline fault seam과 실제 모델 평가 구분

J 계층은 주입 가능한 provider·clock·DB seam을 사용한다. barrier로 provider가 실제 종료되지 않은 상태를 만들고, 취소·deadline 뒤 슬롯 수·후속 호출·최종 정리를 관찰한다. 이 증거는 **제어된 장애 시험**이며 실제 모델 의미 평가 3회에 포함하지 않는다.

실제 의미 평가는 다음을 고정한다.

- 코드·계약·DTO·프롬프트·모델 config·corpus/gold·snapshot 지문
- 각 사례의 `must_link / must_not_link / may_ask`
- 독립 조회 명세와 예상 행·값·NULL·분모
- 사례별 필요한 사용자·판단 상태

일반 의미 사례마다 무의미하게 A/B×v0/v1/v2 여섯 셀을 강요하지 않는다. 적용 가능한 피드백 종류는 세 상태를 실제 모델로 각각 3회 비교한다.

대명사는 A의 같은 문서 등장 교정만 유효하다. **B 새 문서의 v0→v1 개선을 요구하지 않는다.** 새 문서에 전역 재사용되지 않는 것이 정답이다.

이미 v0에서 정답인 사례는 최종 ID 변화만 강요하지 않는다. 적용 근거·제외 후보·조회 계획 등 사전 지정한 효과를 검사한다. 피드백 효과를 입증할 사례는 그 차이를 사전에 oracle에 정의한다.

### 7.4 Host 실행·증거 검사 명령

아래의 `EVAL`은 운영자가 준비한 외부 평가 디렉터리 경로다. 현재 실행하지 않는다. 새 suite와 준비 도구·checker 수정 및 검토 후 사용한다.

```bash
python scripts/run_news_context_evaluation.py \
  --corpus "$EVAL/corpus.jsonl" \
  --gold "$EVAL/gold.jsonl" \
  --evaluation-manifest "$EVAL/evaluation-manifest.json" \
  --snapshot-manifest "$EVAL/snapshot-manifest.json" \
  --local-manifest "$EVAL/local-manifest.json" \
  --server-manifest "$EVAL/server-manifest.json" \
  --repetitions 3 \
  --decision-states v0,v1,v2 \
  --output-dir "$EVAL/evidence/final" \
  --manifest-output "$EVAL/evidence/final/manifest.json"
```

```bash
python scripts/verify_news_context_evidence.py \
  --manifest "$EVAL/evidence/final/manifest.json" \
  --expected "$EVAL/evaluation-manifest.json" \
  --workspace /Users/woolee/.codex/worktrees/news-context/benchmark \
  --require-real-runs 3 \
  --require-decision-states v0,v1,v2 \
  --reject-incomplete
```

기존 동결 V01~V07 명령과의 연결을 유지한다. 목업 V04는 실제 브라우저 의미 평가를 대신하지 않는다. 신규 live 파일·판정 metadata는 후속 계약 산출물에 명시적으로 연결하며 기존 승인 증거를 수정하지 않는다.

현재 host checker에는 다음 정정이 필요하다.

- 사례별 필요한 state/user 셀을 사용한다.
- 대명사의 범위 밖 비적용을 올바르게 검사한다.
- 모든 피드백에 무조건 최종 결과 변화식을 적용하지 않는다.
- 비용은 실제 청구 또는 출처·버전 있는 별도 추정으로 기록한다. token만으로 숫자를 창작하지 않으며 미확인은 unknown이다.
- mock/replay/smoke는 actual model로 계산하지 않는다.
- source 보강은 실제 staging worker ingestion과 부모 provenance를 요구한다.
- 실제 세션 증거는 실제 Upstash를 사용해야 한다.

## 8. 단계별 소유권·의존성과 실제 Host 인계

| 단계 | 담당 범위 | 완료에 필요한 산출물 |
|---|---|---|
| FE 목업 수용 | FE 및 독립 검토자 | 후보 수정·거부·취소·장문·오류·접근성 실제 브라우저 관찰 |
| 최소 계약 정정 | FE 계약 소유자, BE 설계 검토 | 위 DTO 차이 반영·타입 정합성·endpoint 변경표 |
| 데이터 준비 | daily-sync 소유자 | 실제 HTTP 적재, PG 멱등/재시작/NULL FK, 양성 Q12/Q13 |
| 평가 준비 정정 | 준비 도구 소유자 | 실제 PG restore 회귀, baseline 차이 분리, checker 의미 정정 |
| Gold 동결 | 외부 작성자·독립 검토자 | prediction-blind 정답, 행/값/NULL·범위·금지 출력·승인 지문 |
| BE 구현 | endpoint 수용 이후 BE | API·작업·provider·판단 저장·신규 migration·독립 테스트 |
| 실제 통합 | Host 실행 담당 | 실제 로그인·JWT·Vertex·Postgres·Upstash·두 브라우저 |
| 최종 독립 검토 | 구현·의미 검토자 | 58개 증거 대조, 실제 모델 3회, 미실행·실패·skip 0 |

실제 Host 전체 흐름은 두 독립 브라우저 context에서 **로컬 비밀번호 로그인**을 수행해야 한다. 토큰 주입이나 로그인 대역을 사용하지 않는다. Upstash는 고유 `local:` 하위 prefix로 기존 refresh 용도에만 사용한다.

인계 증거에는 실행 전후 코드 지문, 계약·프롬프트·모델 config, corpus/gold·snapshot hash, 부모 원천/HTTP hash chain, 판단 ID·버전·revision, 실제 argv·종료코드·시간, provider 호출·finish reason·token·지연, 한국어 UI 관찰을 연결한다. 토큰·비밀번호·전문·원시 provider 응답은 제외한다.

현재 부모 통합/live suite는 아직 작성되지 않았으며, 기존 FE live scaffold만으로 58개 전체 흐름을 충족하지 않는다. FE 수용, gold 작성·독립 검토, 데이터 적재, 준비 도구 정정, 실제 실행과 최종 독립 검토가 모두 남아 있다.
## 9. 운영자 검토 정정: 닫힌 검증과 실제 PG 테스트의 실행 위치

2026-10-29 Opus 실행 준비 검토(`full-readiness-opus-v2/critique.json`)의 지적에 따라 §7.1의 P 파일 지정과 §7.2의 실행 위치를 이 절로 대체한다. 검증 assertion은 모두 유지한다.

- `tests/unit/test_news_context.py` 및 `tests/integration/test_news_context.py`는 in-process ASGI·SQLite·명시적 provider/clock fault seam만 사용한다. 네트워크·실제 PG·서버 프로세스 의존성이나 skip은 두지 않는다.
- 실제 PG의 두 connection 동시 수정 409, commit/재시작 후 영속성, 감사 실패 원자 rollback, FK/partial unique/NULL 제약, 원천 전용 DB role 쓰기 거부와 실제 서버의 타인 작업 404는 `tests/integration/test_news_context_live.py` 또는 이 파일이 명시적으로 호출하는 control 모듈에서 실행한다. R10-S02/S03/S05·R11-S06·R13을 포함한 기존 P assertion 전체가 이 대상이다.
- 실제 실행기는 반복마다 브라우저를 먼저 실행하고 live pytest를 실행한다. 별도 Python control 모듈은 live pytest가 import/dispatch하고, browser control 모듈은 `frontend/e2e/news-context-live.spec.ts`가 import/dispatch한다. `control_bindings`의 module은 실제 이 경로로 실행되는 파일만 지정한다. 모든 92개 control 및 세부 operation 사례를 실제 관찰과 함께 남긴다.
- 정답 정본은 외부 `expanded-oracle-v6`이며 독립 검토 `gold-expanded-final-review-v6-result.json`의 manifest SHA는 `7391f9133a9db84c0b093dce4e878b902e06e0cc158780a1fa20b5e9fbf0aaf1`이다. 저장소의 이전 v3(83/411), top-level corpus/gold/evaluation-manifest는 폐기하지 않은 준비 이력이며 실제 평가 입력으로 사용하지 않는다. 실제 4개 발췌는 `real-excerpts-v2.jsonl`과 `real-excerpt-binding-v3.json`에 출처·관찰시각·해시로 연결한다. snapshot scope의 빈 excerpt target 배열은 DB 수집 범위이며 이 별도 corpus의 부재를 뜻하지 않는다.
- 실제 browser는 DEV mock 선택이 꺼져 있고 분석 요청이 실제 context API 및 실제 JWT 인증을 사용함을 DOM·프로토콜 관찰로 확인한다. production adapter가 mock으로 fallback하지 않음을 단위 테스트로 검증한다.
- FE 단위 테스트 helper는 `tests/unit/news-context` prefix 전체를 수집한다. HTTP·zod·취소·권한·오류 ID 및 composable 추가 테스트도 여기에 포함한다.
- 루트는 실제 host 실행 및 최종 manifest를 완료한 뒤 준비 완료 binding을 발행한다. V06 대기는 동시 host 실행을 보장하는 성능 예산이 아니다. 기한 초과는 실패이며 성공/skip으로 바꾸지 않는다. 재수정이 필요하면 실제 최종 코드에 대해 다시 실행하고 source/code/model/prompt/config 지문을 갱신한다.
