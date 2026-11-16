> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `plan.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 자연어 검색 AX 기획 진입점

현행 기준: 2026-10-29. 사용자 목표는 완성된 검색 서비스의 머지 및 배포다. 현재 구조는 Planner·SQL 작성·답변 역할을 서버가 통제하는 에이전트 대화 검색이다.

## 6. 자연어 → SQL 검색 AX

제품 요구는 [검색](docs/features/ax-agentic-search.md)과 [진행 표시](docs/features/ax-agentic-progress.md), 실행 순서는 [서비스 완성 계획](docs/ax/natural-language-search/plan.md), 상태는 Plans.md (원문 참조 경로: `Plans.md`; 이 기획 묶음에 포함되지 않음)의 AX-R-*를 따른다. 사용자 결정과 배포 경계는 [2026-10-29 기록](docs/decisions/2026-10-29-ax-service-completion.md), 보안 인수는 [프롬프트 인젝션 대응](docs/ax/natural-language-search/prompt-injection-security.md)에 연결한다.

지정 Vertex `gemini-4-argon`, 활성 사용자 로그인, 기존 DB-only/최신2시즌/6시간, 사전/실제 ID 연결, 읽기 전용 검증을 유지한다. 로컬 선행 구현은 존재하지만 실제 모델/운영 인수·머지·배포 완료와 구분한다. v1·목업·초기 조사는 [전용 README](docs/ax/natural-language-search/README.md)의 역사 근거다.
