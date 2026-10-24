# 세 세션의 전용 worktree 분리 — 2026-10-25

근거: 사용자가 관리·메인·자연어 검색 AX 세 세션의 동시 작업을 확인하고 전용 worktree 분리를 명시적으로 지시했다. 기존 AGENTS.md의 단일 checkout/새 worktree 금지보다 이 최신 지시를 우선한다.

- 관리: `/Users/woolee/benchmark`의 현재 브랜치/HEAD/실제 인덱스/작업 파일을 유지한다.
- 메인: `/Users/woolee/benchmark-main`, 통합 브랜치 `feat/home-preview-json`. 실제 확인에서 해당 경로/브랜치가 없어 커밋 `e3e8f40a8e045174d06544116a933cc03507c33a`에서 생성했다.
- AX: 해당 세션이 별도의 전용 worktree를 관리한다. 이 세션은 경로/브랜치를 만들거나 변경하지 않는다.
- 과거 `/Users/woolee/benchmark.fe-feat-main-home`은 다른 브랜치 `fe-feat-main-home`의 기존 worktree이며 손대지 않는다.
- 원본의 18개 홈 전용 파일은 이전 세션 분리 payload와 SHA-256 일치를 읽기 전용으로 확인했다. 전용 파일·홈 endpoint/schema·홈 계획만 반영하고, 라우터는 HEAD 기준 `/home/mock` 1개만 추가했다.
- 공통 DefaultLayout의 홈 exemption은 다른 세션의 미커밋 인증 코드에 의존하므로 가져오지 않았다. 공통 인증·관리·검색·proxy·seed·환경/DB 변경은 제외했다. 공유 plan/Plans/decision은 홈 소유 절만 분리했다.
- 원본에 stash/reset/clean/checkout/실제 인덱스 staging/commit을 수행하지 않았다. 원본 브랜치의 변경은 작업 디렉터리에 그대로 남는다. worktree 생성에 필요한 Git 공통 worktree/브랜치 메타데이터만 추가했다.
- 메인 개발 포트 5191, Playwright 5192, 향후 BE 8017, 격리 PostgreSQL 55441 예약. Redis가 필요한 테스트는 `local:home-preview:test:<run>:` prefix를 사용한다. 지금 FE 계약 작업에는 DB/Redis가 필요하지 않다.
- 원격 push·원격 merge·배포·기존 서비스 재시작·배포 환경변수 변경은 이번 지시에 포함하지 않는다.
