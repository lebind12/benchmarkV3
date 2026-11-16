> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `news-context` 워크트리의 `docs/spec/endpoints/news-context.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 뉴스 문맥 API 구현 계약

기준 경로는 `/api/v1/admin/management/news/context`다. 현재 구현 제출이며 실행·수용 검증 완료 문서는 아니다. FE 목업에서 도출된 목록을 따라 구현했다.

모든 조작은 기존 JWT를 검증하고 DB에서 활성 STREAMER/ADMIN을 다시 확인한다. 임시 job·binding·등장은 요청자 전용이며 다른 ADMIN도 404다. 원천 축구 데이터는 DB만 조회한다. 출처 URL을 가져오지 않는다.

| Method | Path | 요청 / 응답 |
|---|---|---|
| POST | `/jobs` | 변형 없는 `InputSnapshot` → 202 `{jobId,rootRequestId,documentBinding,documentVersion}` |
| GET | `/jobs/{id}/events?after=` | 인증 fetch SSE. cursor 이후 재생. complete만 전체 result 포함 |
| POST | `/jobs/{id}/cancel` | 요청 접수 202 cancelling, 실제 종료 후 200 terminal |
| POST | `/cards/resolve` | binding·span·kind·conditions·typed target → 현재 DB/판단으로 재조회한 카드 |
| GET | `/candidates?query=&kind=&team=&competition=` | `{items,knowledgeRevision}` |
| POST | `/corrections/preview` | binding·span·조건과 link target 또는 reject rejectedTarget → 임시 카드. 공통 저장 없음 |
| GET | `/decisions/revision?after=` | `{revision,cursor,changedScopes,gap}` |
| GET | `/decisions/events?after=` | 작업 수명과 별개인 인증 SSE. 연결 snapshot 및 revision 변경 |
| POST | `/decisions` | `DecisionWrite` → 생성 201, 수정 200, 충돌 409 SaveReply |
| GET | `/decision-submissions/{key}` | 확정 SaveReply 또는 202 `{status:'pending'}` |
| POST | `/decisions/{id}/revoke` | 버전·revision·제출 키·사유 → 새 취소 버전 |
| GET | `/decisions/history` | `{items:DecisionRecord[]}` |

입력은 1–50,000 Unicode 코드포인트이며 공백만인 본문을 거절한다. CRLF·NFD·RTL·보조평면 문자를 정규화하거나 절단하지 않는다. URL은 2,048자 이하 HTTP(S)이며 credential·제어문자·백슬래시를 거절한다. 기준일과 시각·시간대는 선택 값이며 null을 오늘이나 평가 기준시각으로 채우지 않는다.

`documentBinding`은 프로세스 메모리의 요청자·문서 버전·입력/출처 digest·검증된 등장 증명에 결속된다. span은 코드포인트 범위·정확한 인용·segment·등장 ID/순번을 포함한다. 모델 offset이나 식별자를 정본으로 쓰지 않는다. 모든 요청 DTO는 계약 외 필드를 거절한다.

카드는 선택 대상/거부 대상과 resolution, 검증된 `resolvedQuery`, 사실별 source table/row/JSON path·단위·분모·시점 provenance를 반환한다. `conditions.metrics`는 한 문장의 복수 지표를 보존한다. 표시 값과 원천 값이 다른 한국어 매핑은 provenance의 `sourceValue`로 대조할 수 있다. missing·명시 NULL·0·충돌·과거 자료 없음은 구분한다.

결과 coverage에는 lengthCp·입력 SHA256·연속 segment 범위·coveredCp·검증 버전과 revision이 있다. production 어댑터는 zod 검증과 제출 원문의 SHA256·버전·길이·binding 대조를 수행한다. mock은 명시적인 DEV 선택만 사용한다.

작업은 600초의 기술적 기한, provider 슬롯 2개, 동시 작업 4개와 사용자별 실행 중 작업 1개로 제한한다. 종료 표식 수는 1,024개로 제한한다. 정상 단위는 다시 실행하지 않으며 일시 실패는 최대 3회, 출력 중단/잘린 JSON은 깊이 1의 재분할을 사용한다. 이 값은 승인된 응답시간 SLA나 비용 한도가 아니다. 실제 공급자 호출 finally 이후에만 슬롯과 원문을 정리한다. 결과 재생 10분, 본문 없는 증명/종료 표식 24시간이며 타이머와 요청 시 정리를 함께 사용한다.

판단·감사·revision·change·제출 결과는 한 transaction으로 저장한다. revision singleton row lock, 사용자 row lock, 버전/범위 충돌 검사와 actor별 제출 digest를 사용한다. 원문 전체 대신 검증된 최소 구절/문맥을 저장한다. 저장 span은 선택 구절로 축소하고, 전문을 사유·조건에 복사한 쓰기도 거절한다. 문서 지시어는 actor·binding·문서 버전·등장까지 일치해야 한다.

오류는 `code,messageKo,detail,requestId,rootRequestId,stage`와 `X-Request-ID`를 제공한다. root ID는 인증/검증 전에 서버가 발급한다. 401 인증, 403 권한, 404 타인 임시 자료, 409 충돌, 410 작업 유실, 422 입력/조건, 429 한도, 503 의존성 장애, 504 timeout을 구분한다. 일반 로그에는 원문·원시 모델 응답·credential·민감 예외 메시지를 쓰지 않는다.
