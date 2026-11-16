> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/decisions/2026-10-25-ax-local-name-lab.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# AX 이름 점검의 로컬 실행 경계

2026-10-25. 사용자 요청은 전체 자연어 연동 전에 직접 이름/후보를 확인할 중간 화면을 만드는 것이다. [요구](../features/ax-name-lookup-lab.md)와 실행법 (원문 참조 경로: `../ax/natural-language-search/evaluation/manual-name-lab.md`; 이 기획 묶음에 포함되지 않음)을 따른다.

확인한 현재 AX 브랜치의 `POST /api/v1/auth/login`은 user JSON만 반환한다. 프론트는 authUser/mockRole을 localStorage에 보관하며 JWT/활성 사용자 검증을 새 검색 endpoint에 연결할 준비가 되지 않았다. 이 정보를 실제 인증으로 채택하지 않는다. 다른 관리/메인 세션의 인증 구현을 임의 복사하거나 공통 로그인 코드를 변경하지 않는다.

이번 구현 선택은 **별도 localhost 도구**다. 전용127.0.0.1 API/Vite launcher, 임시 접근 코드와 HttpOnly opaque cookie·서버 세션, 고정 이름 snapshot만 사용한다. 사용자 계정/운영 DB·외부 API·worker에 접근하지 않고 app.main/router에 이름 lab API를 등록하지 않는다. frontend route는 DEV와 명시 flag에서만 연다. 이는 운영 인증 정책 변경이나 JWT 구현 완료가 아니다.

제품 검색은 기존 결정대로 로그인 필수이며 서버에서 활성 USER/STREAMER/ADMIN을 검증한다. 로컬 테스트 identity/접근 코드는 이 정책의 대체물이 아니다. 실제 인증·후보 ref/관계·coverage·모델/SQL/FE 실서비스 연결은 후속 과제로 남긴다. 다른 worktree·배포 서비스는 변경하지 않는다.


후속 로그인 경로 수정: 사용자 보고로 점검 화면의 공통 로그인 링크가 다른8000번 API에 연결되는 동선과 점검 서버 종료를 확인했다. DEV 점검 모드의 헤더/로그인·회원가입 route/API proxy를 로컬 lab으로 한정했다. 일반 사이트 모드는 유지하며 DB URL/계정은 변경하지 않았다. launcher에 readiness 확인과 분리 백그라운드 실행을 추가했다. 이는 단일 checkout/Git 정책 변경이나 신규 worktree 생성이 아니다.
