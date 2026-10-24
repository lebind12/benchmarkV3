# 2026-10-25 — AX 전용 worktree 생성과 세션 분리

사용자는 관리·메인·자연어 검색 AX의 동시 작업을 위해 메인과 AX에 별도 worktree를 생성하도록 지시했다. 이전 단일 checkout 규칙을 이 최신 지시로 대체한다.

| 작업 | 경로 | 브랜치 |
|---|---|---|
| 관리 | `/Users/woolee/benchmark` | `fe-feat-streamer-management-mock` |
| 메인 | `/Users/woolee/benchmark-main` | `feat/home-preview-json` |
| AX | `/Users/woolee/benchmark-ax` | `feat/ax-natural-language-search` |

- AX worktree는 검색 전용 분리 커밋 `bd5204f`에서 생성했다. 생성 후 clean 상태와 브랜치를 확인했다.
- 이 세션은 이후 AX 작업 명령의 workdir를 AX 경로로 지정한다. 도구의 기본 cwd가 원래 폴더라고 해서 그 폴더를 편집하지 않는다.
- 원래 관리 폴더/HEAD/인덱스/작업 파일과 메인 worktree의 내용은 변경하지 않았다.
- 각 세션은 자기 worktree에서 편집하고, 공용 파일은 커밋 단위로 병합한다. 동일 worktree 내 역할 인계/브랜치 전환은 순차 수행한다.
- 개발 포트·테스트 DB/schema·Redis namespace의 충돌을 방지한다. 환경변수/비밀값과 의존성 폴더를 자동 복사하지 않았다.
- 이 기록은 worktree와 운영 규칙의 생성이다. 실제 검색 구현·서버 실행·배포는 수행하지 않았다.
- 이 문서/AGENTS 변경은 AX worktree에만 적용했다. 다른 세션은 최신 사용자 지시를 따르고 각 브랜치의 규칙을 조정한다.

이전 분리 범위: [branch-isolation.md](../ax/natural-language-search/branch-isolation.md).
