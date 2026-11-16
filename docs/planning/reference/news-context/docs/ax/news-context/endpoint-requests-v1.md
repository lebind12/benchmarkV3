> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `news-context` 워크트리의 `docs/ax/news-context/endpoint-requests-v1.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 뉴스 문맥 FE 동작에서 도출한 endpoint 요청목록 v1

2026-10-29 구현 제출 정정: 새 DTO/실제 transport는 `docs/spec/endpoints/news-context.md`를 따른다. job 제출에 rootRequestId/documentBinding/documentVersion, 카드/저장에 owner-bound documentBinding, preview 거부에 action+rejectedTarget, 카드에 selected/rejected/resolution/resolvedQuery/provenance, 전체 coverage 증명을 추가했다. 후보 검색 envelope와 revision/cursor/gap을 유지한다. 실제 adapter는 기존 JWT/refresh fetch와 zod 검증을 사용한다. 아래의 과거 연결 미준비 상태 설명은 목업 단계의 이력이며 현재 transport 상태가 아니다. 구현 제출과 3회 실제 E2E·독립 수용 완료는 구분한다.

FM04 산출물. 이 목록은 프론트 목업의 조작을 구현한 뒤 작성한 **BE 요청 계약**이며, 해당 HTTP API가 이미 구현됐다는 뜻이 아니다. 기존 `/news/analyze`의 이름 목록 응답으로 아래 계약을 충족했다고 간주하지 않는다. 현재 기본 어댑터는 명시적 연결 미준비 오류를 반환한다. 가상 어댑터는 개발·테스트에서 명시적으로 선택해야 하며 서버·모델·DB·영속 저장을 호출하지 않는다.

기준 경로: `/api/v1/admin/management/news/context`. 모든 요청·스트림·재연결·저장은 서버에서 **현재 활성 STREAMER/ADMIN** 세션을 검사한다. USER·비활성·역할 철회는 403, 인증 없음·만료는 401. job과 임시 입력은 요청자 개인 소유다. 다른 STREAMER/ADMIN의 읽기·통지·취소는 404로 숨긴다. 공유되는 것은 확인한 최소 판단과 감사 이력이다. 방송/외부 API를 호출하지 않고 기존 저장 DB만 조회한다.

## 실제 조작과 요청

| FE 조작 / 어댑터 메서드 | 요청 | 응답 및 오류 |
|---|---|---|
| 글 분석하기 / `startAnalysis` | `POST /jobs`, `InputSnapshot` | 202 `{jobId}`. 안전한 root 요청 ID는 아래 작업 통지의 requestId로 전달. 같은 `submissionKey`는 같은 작업. 코드포인트 50,001 이상/빈 본문/잘못된 HTTP(S) URL은 422. 지원 목표를 줄이지 않는다. |
| 전체 분석 상태 / `observeJob` | `GET /jobs/{jobId}/events?after={cursor}` 인증된 fetch stream | `JobEvent`의 순서 있는 NDJSON 또는 동등한 SSE. 동일 작업·마지막 cursor로 재연결. 새 분석 제출 금지. processing/recovering/reconnecting은 결과 없음. complete만 전체 `ContextResult`. failed/lost/replay_expired는 완료가 아니다. |
| 분석 취소 / `cancelJob` | `POST /jobs/{jobId}/cancel` | 202 취소 요청 후 같은 작업 통지에서 정리 완료 확인, 또는 정리 완료 후 200. 어댑터 Promise는 실제 정리 확인 후 resolve. 진행 중 공급자 호출의 종료 전 슬롯 재사용·새 작업 금지. 멱등 취소. |
| hover/focus/tap / `openContextCard` | `POST /cards/resolve`, `{span,kind,conditions,knowledgeRevision,sourceAsOf}` | 검증된 `ContextCard`. 조건·원문·등장·종류·revision·자료시각이 다른 카드 공유 금지. 실패는 최대 3회 내부 자동 복구 후 안전 오류. 다른 정상 카드 유지. |
| 다른 대상 찾기 / `searchCandidates` | `GET /candidates?query=&kind=&team=&competition=` | `{items:EntityRef[],knowledgeRevision}`. DB 대상만. 빈 목록/검색 실패 구분. 순위 점수는 정답 확률이 아니다. |
| 조건 수정 및 이 글에 적용 / `previewCorrection` | `POST /corrections/preview`, `{span,target,conditions}` | 범위·DB ID·지표·조건을 검증하고 실제 DB 재조회한 `ContextCard`. 거부는 target:null 및 로컬 action:reject, 보류는 요청하지 않음. 공통 저장은 하지 않음. |
| 최신성 확인 / `checkRevision(afterCursor,signal)` | `GET /decisions/revision?after={cursor}` (최초 cursor 생략) | `RevisionSnapshot` `{revision,cursor,changedScopes,gap}`. 마지막 확인 위치 이후의 생성·수정·취소 범위. 결과 공개 직전·카드 열기·focus 복귀·저장 전 확인. 사용한 ID 외 새 동일/중첩 범위 거부도 포함. 영향 불명확하면 보수적 재검토. |
| 완료 후에도 판단 변경 / `observeDecisionChanges(afterCursor,signal)` | `GET /decisions/events?after={cursor}` 인증 스트림 | `RevisionEvent` `{cursor,revision,gap,reasonKo,changedScopes}`. 연결 시 현재 위치의 snapshot 통지부터 전송하므로 누락 변경이 없는 재연결도 확인 가능하다. 작업 통지 수명과 분리. 누락/연결 끊김 후 revision/범위 동기화 전 최신 표시·저장 금지. 주기 polling 없음. |
| 공통 판단으로 저장 / `saveDecision` | `POST /decisions`, `DecisionWrite` | `SaveReply`. 생성 201, 수정 200. 판단+감사+revision 단일 transaction. 본문 전체·editor_id를 받지 않음. 같은 제출 키의 원자 결과 재사용. |
| 응답 유실 / `submissionResult` | `GET /decision-submissions/{submissionKey}` | 확정 `SaveReply`, 처리/확인 중 202 `{status:'pending'}`. FE 어댑터는 미확정을 null로 표현. 새 저장 금지, 같은 키 결과 확인 유지. |
| 기존 판단 수정 / `saveDecision` | 동일 `POST /decisions`, `decisionId`, `expectedVersion` 포함 | 새 버전·전후값·사유·편집자·시각·감사 저장. 자동 병합/덮어쓰기 없음. |
| 판단 취소 / `revokeDecision` | `POST /decisions/{id}/revoke`, `{expectedVersion,expectedRevision,submissionKey,reasonKo}` | `SaveReply`, 기존 판단은 성공 전 유효. 취소 새 버전·감사 보존, 이후 재사용 중단. 원래 편집자 역할이 바뀌어도 기존 감사 삭제 금지. |
| 판단 변경 이력 / `readHistory` | `GET /decisions/history` (필요시 판단 ID/표현·범위로 제한) | `{items:DecisionRecord[]}`. 로딩/빈 목록/실패 구분. 편집자 참조가 사라져도 저장된 표시 보존. |

## DTO

공개 TypeScript 정본은 `frontend/src/lib/api/news-analysis.ts`다. JSON의 필드명은 해당 타입과 동일하게 요청한다. HTTP 어댑터에서 202 pending, 409 conflict 등의 transport를 아래 union으로 변환한다.

- `InputSnapshot`: clientInputVersion, **변형 없는** rawText, sourceUrl, 선택 reference `{date,time:null|string,timezone:null|string}`, submissionKey. 기준일을 오늘로 채우지 않는다. 날짜만 지정하면 time=null. 전문은 처리 중 임시 메모리 외 로그/영속 저장에 두지 않는다.
- `SpanRef`: documentVersion, segmentId, occurrenceId, occurrenceIndex, startCp, endCp, quote. `[startCp,endCp)`는 Unicode 코드포인트. CRLF·정규화·보조평면 보존. 모든 등장과 교차 범위를 반환하며 quote 불일치를 프론트 문자열 탐색으로 보정하지 않는다.
- `EntityRef`: DB id, kind(team/player/coach/league/fixture), nameKo:null 허용, originalName, reasonKo. 한국어 이름이 없으면 주표시 `한국어 이름 미등록`, 원문 이름은 보조 식별값.
- `QueryConditions`: intent Q01~Q13, metric, team, competition, season, entityRefs, competitionIds, seasons, unresolvedFields, periodStart/periodEnd, reference, count, unit(team_match/player_appearance/period), aggregation. 편집 가능한 이름·용어는 조회 조건 제안이다. 서버는 기존 DB/지표 사전의 ID로 검증·해결하고 불명확한 조건은 unresolvedFields로 반환한다. 자유 SQL·모델 생성 ID·원천 숫자 편집을 허용하지 않는다.
- `ContextFact`: labelKo, value:null|string|number, unitKo, status(present/null/uncollected/partial/empty/outside/unsupported/conflict/historical_missing), evidenceKo, evidenceRefs `[{kind:fixture|row,id,descriptionKo}]`. 0과 누락은 다른 상태. 근거에는 실제 DB 경기/행 참조·대회·시즌·분모·범위가 필요하다. 수치·이력을 창작하지 않는다.
- `ContextCard`: span, kind, titleKo, candidates, conditions, facts, coverage `{requested,available,descriptionKo}`, sourceAsOf, analyzedAt, eventTime, explanationKo, knowledgeRevision, decisionEffects `[{id,version,effectKo,scopeMatch:match|mismatch|unknown,reasonKo}]`. 생성 설명과 DB 사실을 분리한다. Q01 현재/당시, Q02~05 집계·분모, Q06 정규/연장/승부차기, Q07 수록 범위, Q08 그룹·원천 충돌, Q09 종료/누락 경기, Q10 단위/NULL, Q11 경기별 관측, Q12~13 사건/보고/관측 시각을 보존한다.
- `ContextResult`: documentVersion, cards, relevanceKo, knowledgeRevision, allValidated, coverage `{expectedSegments,completedSegments,spansValidated,dbValidated,revisionValidated}`. 전체 구간 coverage·원문 범위·DB 참조·판단 revision 검증 전 allValidated=true 또는 complete 금지. FE도 완료 구간 수 일치·세 검증 플래그를 확인한다. 부분 성공 응답으로 바꾸지 않는다.
- `DecisionScope`: kind(alias/reject_candidate/fixture/metric/document_reference), language, team, competition, period, documentVersion. document_reference는 현재 원문 버전·등장만. 미입력 제약을 전역 검증으로 취급하지 않는다. 별명·후보 거부·경기·지표의 세부 유효 범위는 판단 정책 v2로 검증한다.
- `DecisionWrite`: submissionKey, span, selectedExcerpt, necessaryContext, sourceUrl, action(link/reject), target, rejectedTarget, conditions, scope, reasonKo, expectedRevision, expectedVersion:null|number, decisionId:null|string. 최소 구절·필요 문맥만 보관한다. 전문 영속 보관·프롬프트·편집자 ID 입력은 금지. link는 target, reject는 rejectedTarget에 **명시적 후보 ID**를 보존한다. 거부된 연결의 target은 null이며 다른 후보·범위까지 거부하지 않는다.
- `DecisionRevoke`: id, expectedVersion, expectedRevision, submissionKey, reasonKo. 취소 응답 유실도 동일 제출 결과 조회를 사용한다.
- `DecisionRecord`: id, version, revision, active, **editorKey**, editorKo, at, write, before, after. `editorKey:string`은 인증 행위자의 안정적인 snapshot 식별자이며 표시명과 분리한다. 서버가 인증 세션에서 확정하며 클라이언트 쓰기 입력으로 받지 않는다. 동명이인은 다른 key, 같은 사람의 표시명 변경은 같은 key와 당시 표시명을 유지한다. 계정 삭제로 FK가 NULL이어도 key·당시 표시명·감사 기록은 보존한다. UI는 표시명과 식별자를 함께 보여준다. 변경 전후·사유·범위·취소 모두 감사 기록으로 남긴다.
- `RevisionSnapshot`: revision:string, cursor:string, changedScopes:DecisionScope[], gap:boolean. cursor는 불투명한 재개 위치이며 순서/범위 계산은 서버 책임이다. after 위치 이후의 범위를 반환한다. 최초 또는 재생 불가 위치는 전체 현재 revision을 확인하고 누락 여부를 gap으로 알린다. `RevisionEvent`는 여기에 reasonKo:string을 더한다. 범위가 불명확하거나 gap이면 전체 카드 재검증이며 현재 소비자는 알려진 범위도 전체 카드 재검증으로 보수적으로 처리한다.
- `SaveReply`: `{status:'saved',record}` / `{status:'conflict',latest}` / `{status:'invalid_target'}`. 저장과 감사 모두 성공해야 saved. 충돌은 최신값·내 변경·범위·근거·버전을 비교한 후 명시적으로 다시 저장한다.

## 오류·복구·보호

422 입력/범위/조건 검증, 409 개별 버전 또는 동일 범위의 순차 상충, 410 작업/재생 유실, 429 제한, 503 일시 의존성 장애, 504 내부 기한 초과. 오류 본문은 `{code,messageKo,requestId,rootRequestId,jobId?,stage?}`. FE에는 한국어 행동 안내와 안전 ID만 노출한다. 원시 예외·모델 출력·credential·전문을 반환/기록하지 않는다. transient 오류는 같은 작업 내부 최대 3회·유한 예산으로 복구하며 정상 구간을 다시 호출하지 않는다. 구간별 사용자 재시도 버튼 없음.

`JobEvent.requestId`는 같은 작업 전체의 root 요청 ID다. HTTP 어댑터는 개별 HTTP 요청 ID와 rootRequestId를 구분하여 받고, 화면의 작업 요청 ID에는 root를 연결한다. 가상 어댑터는 동일 job의 모든 통지에 같은 가상 ID를 사용한다.

어댑터 오류는 `ContextError`로 변환한다. 연결 미준비 unavailable, 권한 거절 forbidden, 확정 실패 failed, **쓰기 성공 여부를 알 수 없는 전송 단절은 lost_response**다. 마지막 경우 저장/수정/취소 모두 같은 submissionKey 결과 조회로 이동하며 확인 없이 새 쓰기를 만들지 않는다. 제출 키는 인증된 요청자·조작·payload에 귀속시키고 다른 사용자나 다른 payload의 재사용을 거절한다.

생성/수정/취소의 미확정 조작은 종류·payload·같은 submissionKey를 소비자가 보존한다. 결과 조회가 null 또는 실패면 confirming을 유지하며 새 수정·취소를 차단한다. 감사·버전·revision은 commit당 한 번만 증가한다. 실패가 확정된 동일 조작을 다시 제출할 때도 같은 키를 유지한다. 취소는 성공 확인 전 기존 유효 판단을 유지한다.

판단 변경 연결 단절은 소비자가 즉시 최신성 미확인·공통 저장 차단으로 처리한다. 같은 마지막 확인 cursor로 **최초 연결 포함 최대 3회**, 재연결 대기 300ms/600ms의 유한 복구를 수행한다. 연결 snapshot을 받아 revision/누락 범위를 동기화하고 카드 재검증 및 최종 revision 대조 후에만 cursor를 전진시키고 저장을 해제한다. 새 분석·쓰기 요청은 만들지 않는다. 재연결 자체의 성공만으로 최신 상태로 표시하지 않는다. 예산 소진은 실패·전체 재분석 경로, 권한 상실·화면 종료는 구독 중단이다. 상세 재검증 한도는 기존 카드의 최대 3회 복구를 따르며 주기적 polling은 추가하지 않는다.

작업 재생은 원문 없는 종료 결과 최대 10분, 본문 없는 종료 표식 최대 24시간의 기존 설계값을 따른다. 공통 판단·감사에는 임시 TTL을 적용하지 않는다. 서버 재시작·재생 만료는 자동 새 작업이 아닌 명시적 상태다. 이미 받은 결과는 재생 만료만으로 삭제하지 않는다. 최신 2시즌·DB 전용 일반 페이지 정책을 유지한다.

## 증거 구분과 후속 의존성

- `news-context.spec.ts`: 가상 모델·DB·명시적 auth 대역, FM01-S1~FM04-S2의 목업 관찰. 실제 정확도·영속성·두 사용자 공통 재사용 증거가 아니다.
- 추가 실제 목업 브라우저 조작: `FM-ACTOR` (동명·이름 변경과 감사 key), `FM-SUBSCRIPTION-RECOVERY` (스트림 단절·같은 cursor·gap/범위·저장 차단과 복구·분석/쓰기 증가 없음), `FM-EDIT-LOST`/`FM-REVOKE-LOST` (commit 후 응답 유실·같은 key 조회·정확히 한 버전/감사·후속 취소 비적용). 개발 전용 호출 관찰은 키·횟수·revision/범위만 메모리에 표시하고 원문을 담지 않는다. 실행 receipt 전에는 통과를 뜻하지 않는다.
- `news-context-live.spec.ts`: 실제 로컬 로그인 두 개, 실제 API/모델/DB, 다른 두 글 v0→v1→v2. 실제 endpoint/어댑터가 없거나 고정 corpus·계정이 준비되지 않으면 FAIL. skip·route 대역 없음. 현재 이 코드만으로 부모 E2E 완료를 주장하지 않는다.
- 부모 R01~R14/58개 시나리오, 3회 의미 평가, 서버 권한·작업 소유권·실제 장애/재시작·원자 저장 검증과 독립 구현 검토는 후속 통합 단계의 필수 작업으로 남는다.
- 호스트 목업 실행은 운영자가 지정된 `scripts/verify_news_context_mock.py run --output …/frontend-mock-browser-v1`을 실행한다. worker는 서버/브라우저/테스트를 실행하지 않았다. 생성 파일·Vite envDir/cache/output·Playwright 출력은 `NEWS_CONTEXT_MOCK_ARTIFACT_DIR` 외부 scratch만 사용한다. 증거 없이는 PASS가 아니다.


## 독립 구현 검토 §15 보완 제출 — FM01~FM04

HTTP 목록·권한·원자 저장·부모 요구는 유지한다. 소비자는 모든 어댑터 조작과 두 비동기 스트림을 공통 접근 경계로 감싼다. 어느 조작의 ContextError('forbidden', requestId)도 해당 화면에서 서버 거절을 고정하며, 아직 허용인 auth store나 개발 접근 선택만으로 해제하지 않는다. 기존 로그인 경로에서 세션을 다시 확인한다. 결과·카드·후보·이력을 숨기고 작업/판단 구독을 중단한다. 입력 메모리는 유지한다. 거절 뒤 새 분석·후보·preview·최신성·이력·쓰기·제출결과·재연결 요청은 보내지 않는다. 이미 생성한 소유 job만 같은 취소 Promise로 한 번 정리하며, 늦게 도착한 job ID도 기존 소유자가 정리한다.

안전 오류 메타데이터는 실제 ContextError.requestId를 화면까지 전달한다. 현재 식별자 표시 경계는 영문/숫자로 시작하는 영문·숫자·점·밑줄·콜론·하이픈의 1~128자 토큰만 허용한다. ID 미제공 또는 이 형식 밖 메타데이터는 '요청 ID: 미제공'으로 구분하며 합성 대체 ID를 만들지 않는다. 향후 HTTP 어댑터는 서버의 안전 ID를 이 계약에 맞춰 전달해야 한다. 원시 예외의 message나 임의 객체 필드는 표시하지 않는다. 시작·작업 통지·정리·카드·검색·preview·revision/판단 구독·저장/수정·취소·이력·제출결과 조회가 동일 원칙을 따른다. lost_response는 원래 안전 ID를 유지하며, 결과 조회 자체가 실패하면 그 실제 요청 ID로 갱신한다. 미확정 저장은 계속 confirming이다.

개발 목업의 오류 조작·종류 선택은 서비스 설정이나 새 endpoint가 아니다. 메모리의 조작명별 가상 오류와 호출/열린 스트림 수만 관찰하며 전문·인증값·원시 예외를 진단 출력에 담지 않는다. 기존 실제 로그인/API/모델 E2E 코드는 그대로 후속 통합 검증에 남긴다. FM-FORBIDDEN/FM-ERROR-IDS 추가 브라우저 코드와 단위 코드의 실행은 외부 컨트롤러가 담당한다. 이 제출은 PASS 증거가 아니다.
