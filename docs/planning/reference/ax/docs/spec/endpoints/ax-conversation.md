> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/spec/endpoints/ax-conversation.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# POST /api/v1/search/conversation

FE 요구: [대화형 검색](../../features/ax-conversational-search.md). 활성 사용자 인증 후에만 시작한다.

요청: 최초 `{message:string(1..500)}`. 후속 `{message,conversation_ref,parent_turn_ref}`. 선택 답변 `{choice_ref,conversation_ref,parent_turn_ref}`. message/choice는 배타적. 새 대화는 ref없이 보낸다. 사용자 ID/SQL/결과 ID/조건 patch/이전 결과 원문은 클라이언트가 보내지 않는다.

응답: `{conversation_ref,expires_in,turn:{turn_ref,question,status,answer,applied?,coverage?,columns?,rows?,has_more?,limitations?,clarification?:{question,options:[{label,choice_ref}]}}}`. status results/no_matches/clarification_required/data_unavailable/unsupported. 오류401/403/409/429/502/503은 기존 안전 코드로 반환하고 원문 입력을 유지한다. 명확한 질문은 서버가 기존 Core/SQLGlot/읽기 전용 실행 경로까지 연결한다. result에 가짜 설명/수치를 넣지 않는다.

followup 모델 출력은 base_turn_ref + 변경 필드 목록 + typed Draft + 결과 위치 참조다. 서버가 해당 대화의 저장된 Draft를 복사하고 명시된 변경만 적용한다. 이름/metric 새 근거는 현재 발화에서 검증하고, 상속한 조건은 저장된 근거를 사용한다. base ref/선수 위치/공동순위 값은 실제 대화 기록에서 검증한다. 단순히 전체 대화를 붙여서 만든 SQL이나 클라이언트가 재전송한 결과를 신뢰하지 않는다.

부모 turn ref는 최신 교환과 일치해야 한다. pending 선택은 그 교환에서 발급된 choice만 허용한다. 모델 오류는 성공한 이전 기록을 삭제하지 않으며 재시도할 수 있다. 브라우저 취소는 늦은 응답을 표시하지 않고 서버 동기 호출은 timeout으로 종료한다. context TTL30분·교환12개·대화64개, 기존 사용자 해석1/전체작업2, 모델60초/회·180초/해석·6toolcalls·64KiB, SQL3초/100행/256KiB를 유지한다.

검증: 최초→자유문장 시즌 응답→순위→상위2 비교→지표/시즌 변경, 오래된 결과 선택·공동순위·없는 행/조작된ref·다른 사용자·parent충돌·만료·source변경·예산·오류 재시도, 실제 HTTP/SQL UI와 실제 Vertex probe를 구분한다.

각 제출은 `request_ref`(16..64자, UI UUID)를 포함한다. 같은 세션/nonce/요청은 성공한 응답을 재전송하며 다른 본문으로 nonce 재사용은409다. 성공 응답 유실 시 같은 nonce로 재시도한다. `POST /api/v1/search/conversation/cancel {request_ref}`는 해당 세션의 작업에 tombstone을 남긴다. 취소한 작업은 기존 대화에 답변/새조건을 commit하지 않는다. 이미 시작한 외부/DB 호출 자체의 원격 취소는 보장하지 않는다. 요청/취소 ledger는256개·30분 TTL, 먼저 도착한 취소도 보호한다.
