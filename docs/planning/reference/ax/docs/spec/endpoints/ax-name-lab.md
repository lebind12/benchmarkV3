> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/spec/endpoints/ax-name-lab.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 로컬 이름 점검 endpoint spec v1

FE 요구: [ax-name-lookup-lab.md](../../features/ax-name-lookup-lab.md). 로컬 전용 standalone FastAPI. 운영 엔드포인트·JWT 구현 완료와 구분한다.

- factory는 명시한 테스트 코드(16~128자)를 요구한다. launcher는 임의 코드 생성·127.0.0.1 고정 bind, app .env/DB/worker/외부 API에 접근하지 않는다.
- cookie `ax_name_lab_session`, HttpOnly, SameSite=Strict, path=/api/ax-name-lab, TTL1h, process 내 opaque token. 로그인 실패 rate limit, 최대16세션. logout/서버 재시작/만료 후 재사용 불가. local HTTP이므로 Secure=false이며 운영 사용 금지.
- 허용 origin은 launcher가 선택한 localhost frontend origin만; 다른 Origin POST/DELETE는403, CORS 허용 없음. API credentials는 클라이언트 메모리/localStorage에 보관하지 않는다.
- 모든 응답 Cache-Control=no-store. lookup에 cookie가 없거나 유효하지 않으면401, snapshot 로딩·검색 전에 차단한다. X-Mock-Role·프론트 authUser·서버 미검증 role은 허용 근거가 아니다.
- session POST `{code}` extra forbid·길이1~128. 성공204, 실패401, 과도 요청429. GET은 authenticated/mode/role만 반환. DELETE는 해당 세션 제거/쿠키삭제204.
- lookup POST `{text:string(1..256), entity_type:null|'league'|'team'|'player'|'coach', limit:5|20}` extra forbid. 기본 null/5, 비정상 입력422. 잘못된 JSON/초과 입력은 shape validation에서 거부한다.
- lookup 응답: `{query, result:NameSearchResult, snapshot:{id, captured_at, entity_count, normalization_version}, limitations:string[]}`. result의 후보에는 실제 type/ID/원문 fallback 표시명·match source/value·source_version, snapshot ID를 포함한다. snapshot 데이터는 checked-in manifest SHA256/버전/READ ONLY metadata를 검증한 뒤 프로세스 내 cache. 손상/버전 불일치/조회 오류는503, 원문 예외/접속 정보는 반환하지 않는다.
- backend는 기존 ExactNameIndex를 사용한 **snapshot memory 조회**다. PostgreSQL runtime 운영 연결이나 신규 수집/별칭 추론/fuzzy를 가장하지 않는다. empty exact 결과는 unavailable/fuzzy_not_implemented, 충돌은 ambiguous, K+1 초과는 has_more/truncated. unique_exact는 최종 resolved가 아니다.
- 사용자 선택은 FE의 현재 응답 후보만 대상이며 새 이름/필터/조회/세션/취소 때 초기화한다. 선택으로 임의 entity ID를 서버에 보내거나 SQL/모델 호출을 시작하지 않는다.

테스트: 미인증/위조 role/실패 로그인·origin·만료·logout/rate limit, 조회 전 차단, 실제 맨유/맨시티·스미스 overflow/20확장·표기/유형·길이·manifest 손상, 반환 candidate source version; UI 로그인/재조회/선택초기화·취소·401/503·malformed response·mobile/dark/reduced motion.
