> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/features/ax-search-live.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 실제 자연어 검색: 선행 화면/endpoint 요구

사용자 승인: 사전/시즌/자료 조회→실제 로그인/읽기 DB→Gemini→계획/SQL/결과까지 나머지 단계를 구현한다. 기존 `/search` 목업과 `/search/names` 점검은 유지하고 DEV `/search/live`를 추가한다.

화면 순서: 실제 사이트 이메일/비밀번호 로그인(공통 auth authority) → 질문/예시 → 실제 해석된 조건·재질문 선택 → ‘이 조건으로 조회’ → 저장 기록 목록/순위/선수 비교. 조건/자료 기준 시각·NULL/부분 자료·지원 범위를 표시한다. pending/취소/세션 만료/0건/자료 없음/미지원/제한/오류를 분리한다. SQL·비밀값·raw 모델 trace는 노출하지 않는다. 500자 질문/최대100행. 실제 JSON을 zod로 검증한다.

MVP는 선수 시즌 통계의 득점·도움·분·출전·경고·퇴장·득점+도움·90분당득점, 선수 목록/순위/선수 비교다. 팀/경기 상세·평점·국적/포지션 등 추가 조건·실시간·전체 범위 밖은 명시적으로 미지원/확인한다. 최초 범위는 한 대회/한 시즌, 최대 두 선수 비교다. 같은 대회/시즌의 실제 팀별 행을 합친다. per90은 명시 최소 출전 분이 있어야 한다. 컵/시즌·활성 설정 불일치는 데이터 한계로 차단하며 수집 원천을 임의 보완하지 않는다.

Endpoint 요청:
- `/api/v1/auth/login|refresh|logout|me`: 기존 공통 인증 API를 명시적인 authority로 전달. 서버 검증된 활성 USER/STREAMER/ADMIN만 검색. 로컬 이름 점검 코드는 허용하지 않는다.
- `POST /api/v1/search/interpretation`: `{question}` 또는 `{context_ref,choice_ref}`. `interpretation_ready|clarification_required|unsupported|data_unavailable|limited|failed` + conditions/questions/plan_ref/coverage.
- `POST /api/v1/search/query`: `{plan_ref}`. `results|no_matches|data_unavailable|limited|failed` + applied/columns/rows/coverage/source timestamp. 사용자 임의 SQL/ID/metric 필드는 받지 않는다.

이름 ref·plan_ref는 실제 사용자/현재 access token·원문·자료 버전·5분TTL에 묶는다. 이전 로컬 lab 참조는 받지 않는다. 질문 변경·취소는 UI의 늦은 응답을 무효화하며 DB/LLM 취소의 서버 보장 범위는 별도 표시한다.

로컬 통합은 기존 API-Football DB를 READ ONLY 추출한 저장본과 전용 read role을 사용한다. 운영 production role DSN·projection migration 적용은 배포로 간주하지 않고도 별도 운영 변경이며 이번 로컬 구현으로 완료 표시하지 않는다. 실제 source completeness는 보증하지 않고 항상 관측/부분 자료 상태를 반환한다. LLM이 metric/ref를 창작하면 서버가 거부한다.
