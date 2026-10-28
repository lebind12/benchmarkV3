# 이전 FE·BE 워크플로 안내

2026-10-28 사용자 결정으로 새 작업은 [운영 에이전트 중심 하네스](agentic-workflow.md)를 따른다.

이전 명세는 [보관본](../harness/legacy/fe-workflow.md)으로 옮겼다. 보관본의 에이전트별 머지 권한, 단일 checkout, 자동 push·배포 규칙은 현재 운영 지시가 아니다.
기존 `.codex/state/feature-flow/`, `.codex/state/endpoint-flow/` 상태·리뷰·이력은 그대로 보존하며 자동 변환하지 않는다.
진행 중인 작업은 운영 에이전트가 현재 코드·미완료 기준을 검토해 새 work-flow 작업으로 인계한다. 과거 PASS/승인은 새 작업에 승계하지 않는다.

프론트 mock → endpoint 요청 → 백엔드 구현 → 실 API 연결 순서와 도메인 정책은 `AGENTS.md`에 따라 유지한다.
