# 요구사항과 외부 실행 제어

새 정본은 [운영 흐름](../spec/agentic-workflow.md), 도입 이유와 기존 방식 비교는 [외부 제어 결정](../decisions/2026-10-28-external-harness-control.md)이다.

현재 대화가 사용자와 기획하고, 일반 프로그램이 필수 단계와 공식 완료 상태를 관리한다. 다른 관리자 AI를 추가하는 것만으로 완료 권한을 분리했다고 보지 않는다.

1. 새 독립 요청은 QUICK/FULL을 한 번 선택한다. 기존 선택·후속 수정은 재사용한다.
2. 원문 요구사항을 계약·수용 시나리오·검증 방법으로 구체화하고 중요한 미정 사항을 해결한다.
3. 별도 읽기 전용 명세 검토 후 개발 세션을 실행한다.
4. 외부 검증 명령과 독립 코드 검토가 모두 통과하면 해당 코드 지문을 VERIFIED로 기록한다.
5. 실패는 범위를 유지해 재작업하고, 사용자 피드백과 관찰 근거로 다음 개선을 정한다.

- [실행 안내](external-control.md) — `scripts/harness-run.sh --help`
- [요구사항 작성 안내](templates/requirements.md) · [계약 JSON](templates/requirement-contract.json)
- [Karpathy 지침 비교·반영 근거](../decisions/2026-10-28-karpathy-guidelines.md) — 요구사항을 유지한 단순한 구현과 변경 범위 검토
- [FULL 서비스 기획 보조](templates/service-plan.md) · [QUICK 결과 메모](templates/quick-change.md)
- [서비스 포트폴리오](templates/service-portfolio.md)

QUICK은 짧은 계약과 필요한 확인만 사용한다. 낮은 영향 문구·스타일에 가짜 테스트를 추가하지 않는다. FULL은 모든 필수 요구사항을 실제 검증 명령에 연결한다. 원문 누락 검토와 구현 충족 검토는 서로 다른 단계다.

이번 전환에는 사용자 지시에 따라 기존 하네스의 자기 개발/평가 절차를 적용하지 않았다. 문법과 진입점만 확인하고, 실제 개발에서 사용자가 체감하며 수정 요청하는 방식으로 평가한다. 구현 완료와 행동 효과 검증을 구분한다.

## 과거 이력

기존 `work-flow`, FE/BE 상태·검증 보고서는 이력으로 보존하며 새 개발의 실행 경로로 쓰지 않는다. 과거 테스트 수치도 새 실행기 검증 결과가 아니다.

- [이전 재구축 근거](rebuild-rationale.md) · [당시 검증](rebuild-validation.md)
- [자동 개선 후보 명세](../spec/harness-self-improvement.md) · [연구](self-improvement-research.md) · [이전 운영 안내](self-improvement-runbook.md)

일반 자동 하네스 후보는 기존 사람 승인 경계를 유지한다. 사용자가 하네스 자체 수정을 직접 요청하면서 정한 범위·절차가 있으면 최신 지시를 따른다. 외부 게시·배포 승인은 별개다.
