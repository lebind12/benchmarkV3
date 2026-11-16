> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/spec/endpoints/ax-candidate-context.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 로컬 후보 문맥 endpoint v2

FE 요구: [ax-candidate-context.md](../../features/ax-candidate-context.md). 기존 localhost 전용 경계·테스트 세션을 유지한다. 실제 JWT 사용자/통계 검색 API가 아니다.

- 세션별 활성 조회 하나. candidate_ref/lookup_id/selection_ref는 서버 난수, 입력 ID/name/SQL은 받지 않는다. candidate_ref는 실제 응답한 후보에만 발급하고 세션/조회/snapshot SHA256·수정 버전·후보 내용에 묶는다. source는 프로세스에 고정한 불변 snapshot이며 live DB 갱신 검증을 주장하지 않는다.
- TTL5분은 로컬 실험값이며 서버 monotonic clock이 정본이다. selection TTL은 조회 TTL을 넘지 않는다. 새로고침은 TTL을 연장하지 않는다. logout/session 만료/프로세스 재시작 시 참조는 사라진다.
- request_key는 클라이언트가 생성한 8~64 ASCII 상관키다. 권한 토큰이 아니다. begin에서 기존 문맥을 교체하고 완료 시 같은 활성조회인지 재확인한다. 취소 key의 tombstone을 보관해 취소가 조회보다 먼저 도착해도 늦은 조회를 거부한다. 세션당 TTL내 최대64상관키, 초과429. 기존 클라이언트 호환을 위해 생략 시 서버 키를 발급한다.
- POST lookup: 기존 입력+request_key, 응답 lookup:{id,request_key,expires_in_seconds}, 각 candidate의 candidate_ref. 응답한 최대20후보만 선택 가능하며 overflow를 unique로 처리하지 않는다.
- DELETE lookup:{request_key}, 204 idempotent. 현재 상관키가 다르면 새 조회를 지우지 않는다. 미도착 상관키도 tombstone 처리한다.
- POST selection:{lookup_id,candidate_ref,snapshot_id}, extra forbid. 서버 세션/현재조회/TTL/후보 소속/현재 pinned snapshot SHA/원본 candidate 내용 검증 후 {status:'confirmed_name_only',selection_ref,lookup_id,snapshot_id,candidate,expires_in_seconds}. 선택은 이름만 확인이며 시즌/소속/coverage·SQL 실행 허가는 아니다. 선택 변경 시 이전 selection_ref는 교체한다.
- DELETE selection:{lookup_id,selection_ref}, 204; stale ref409, 이미 없음204. GET context는 {state:'empty'|'candidates'|'confirmed'|'expired',lookup:null|LookupResponse,selection:null|SelectionResponse}. 반환 시 남은TTL 계산. snapshot 참조는 lookup과 동일.
-401 인증,409 오래된/위조/다른 세션 참조·버전/후보 불일치,410 만료,422입력,429예산. 오류를 결과0건으로 바꾸지 않는다. 후보 및 원문 source 문자열은 데이터이며 지침/SQL로 실행하지 않는다.
- 서로 다른 세션 ref 사용·동일 숫자ID 이름 바꾸기·취소/새검색/지연응답·동시선택·서버 재시작·TTL·버전변경·source 버전 훼손·선택해제 지연·복원을 검증한다. 새 API는 운영 app.main에 등록하지 않는다.
