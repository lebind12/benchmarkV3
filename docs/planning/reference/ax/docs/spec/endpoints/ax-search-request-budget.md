> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/spec/endpoints/ax-search-request-budget.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# AX 검색 요청 본문 예산 — 명세 보완안

2026-10-29. 대상은 POST `/api/v1/search/agentic/conversation`, `/conversation/stream`, `/conversation/cancel`의 세 endpoint다. 현재 승인된 필드·역할·결과·의미 검증 계약을 유지하고, JSON 파싱 전의 메모리/입력 자원 경계를 보완한다. 이 파일은 독립 SPEC_REVIEW 전에는 제안이다.

- 전체 HTTP request body 최대 **16384 bytes(16KiB)**. Unicode 문자 수 제한과 별개이며 실제 수신한 UTF-8/JSON 전송 bytes를 기준으로 한다. JSON의 의미 없는 whitespace도 예산에 포함한다.
- 정상 최대 입력(message500 Unicode 문자, ref128씩, nonce64 및 JSON escaping)을 수용한다. 기존 field별 길이/extra-forbid 검증을 이 byte cap으로 대체하지 않는다.
- Content-Length가 한도를 넘으면 조기413 `request_body_budget`. 길이 헤더가 없거나 작게 선언돼도 실제 stream을 누적해 한도 초과 시413으로 닫는다. 초과 본문 전체를 먼저 `.body()`/JSON decode하거나 임시 파일로 무제한 저장하지 않는다.
- router의 bounded body 수신을 완료한 뒤 FastAPI/Pydantic과 auth dependency로 넘긴다. cap 초과에서는 모델·축구 reader 호출0회이며 offending body/비밀/SQL을 응답·SSE·로그에 반향하지 않는다.
- 스트림 개시 전이므로 일반 JSON `{detail:"request_body_budget"}`, `Cache-Control:no-store`. 결과 SSE/서버 작업/nonce ledger를 만들지 않는다.
- 수신 중 disconnect·손상된 헤더/형식은 검토된 안전 code로 종료한다. 내부 exception·본문 반향 금지. 다른 일반 API/워커의 body 정책을 변경하지 않는다.

독립 회귀는 (1) cap 경계·초과와 split/chunked 실제 bytes, (2) Content-Length 조기·실제 누적 검사, (3) 한도 안 whitespace/JSON→기존 schema 검증, (4) 정상 최대 Unicode·JSON-escaped 입력 허용, (5) 차단 시 모델/reader/작업시작0 및 no-store·원문 비노출을 포함한다. 실제 서버 프록시의 별도 한도가 이보다 작으면 인수에서 정합을 확인한다.
