> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/features/ax-candidate-context.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 후보 확인과 질문 해석 미리보기

2026-10-25. 사용자 승인: 서버 후보 ref·만료·버전 검증과 선택 상태 보존을 먼저 구현하고, 질문 해석 확인 화면의 목업/API 계약을 준비한다.

## 선행 FE 요구

기존 이름 점검의 radio는 임시 선택이다. ‘이 후보로 서버 확인’ 버튼으로 현재 조회에서 발급한 후보 ref만 전송한다. 확인 중/확인 완료/만료·오래된 조회/실패를 구분한다. 이름·종류·표시 수·새 조회·취소·로그아웃은 이전 서버 문맥을 무효화한다. 라디오만 바꾼 상태를 서버 확인 완료로 표시하지 않는다. 같은 세션으로 새로고침하면 아직 유효한 조회·서버 확인 선택을 복원한다. 탭 사이에 동시에 작업해 문맥이 바뀌면409로 확인을 차단한다.

확인 결과 하단에 별도 ‘질문 해석 미리보기’ 목업을 둔다. 원문 textarea와 ‘예시 조건 보기’, 목표/대회/팀/기간/지표/조건의 확인 상태를 표시한다. 팀 후보가 서버에서 확인됐다면 예시의 팀 이름만 연결한다. 예시 질문과 다른 자유 입력은 자동 파싱/LLM 호출 없이 입력 보존 상태로 안내한다. 대회·시즌·득점 정의/조건은 예시임을 명시하며 실제 current season·소속·coverage·SQL 실행 가능을 확정하지 않는다. 현재 운영 사전 정의는 비활성 상태를 유지한다.

목업 컴포넌트는 auth 여부를 직접 판단하지 않고 인증된 local lab 안에서만 렌더링한다. 기존 glass/light/dark/reduced motion·IME·키보드·모바일 방식을 유지한다.

## endpoint-request: 로컬 점검 v2

| 경로 | 요청 | 응답 |
|---|---|---|
| POST lookup | 기존 text/type/limit + request_key(클라이언트 상관키) | 기존 결과+lookup id/상관키/남은TTL·후보별 서버 candidate_ref |
| DELETE lookup | request_key |204, 해당 조회만 무효화. 늦은 취소가 새 조회를 삭제하지 않음 |
| POST selection | lookup_id/candidate_ref/snapshot_id | 서버 selection_ref·후보·남은TTL·confirmed_name_only |
| DELETE selection | lookup_id/selection_ref |204, 해당 선택만 제거. 오래된 해제가 새 선택을 지우지 않음 |
| GET context | 세션 cookie | empty/candidates/confirmed/expired, 현재 조회와 선택 복원 |

JSON validation·오류/예산·동시성은 [endpoint spec](../spec/endpoints/ax-candidate-context.md). 질문 해석용 공개 endpoint는 아직 구현하지 않는다. 아래는 후속 FE-first 초안이다.

`POST /api/v1/search/interpretation` 입력: question, 서버가 검증할 선택 참조 목록, prior_context_ref(optional). 응답: 원문/근거 구간, entities/metric keys/scopes/filters와 각 검증 상태, 필요한 확인 질문, coverage/한계, 버전/기준시각, results_ready 여부가 아닌 interpretation 상태. 실제 로그인·candidate refs·Retriever/Planner/coverage 계약 검토 뒤 정식화한다. 현재 local selection_ref를 운영 endpoint가 신뢰해서는 안 된다.
