# 2026-10-28 사용자 승인형 하네스 개선 검증

## 구현과 검토

운영 에이전트가 원본 코드와 진단·승인·적용 경로를 검토했고, 구현자와 별도인 `improvement_tests`가 임시 Git 저장소/worktree에서 검증했다. 독립 기획 검토는 실제 행동 근거, 비교 환경 고정, 필수 회귀 집합을 보완한 뒤 APPROVE했다.

- 개선 CLI/관찰·진단·평가·승인·적용·복구, 3개 역할과 운영 문서 구현 완료.
- 새 개선 절차: 광범위 검사 **69 passed in 226.80s**.
- 최종 방어 수정 후 경로 보호·정상 승인/적용/롤백·중단 복구 **8 passed in 27.85s**.
- 잘못된 관찰 입력의 비밀값 오류 출력 차단 **1 passed in 0.31s**.
- 위 실행에 포함된 서로 다른 사례는 **76개**다. 마지막 파일에 전체 76개를 한 번에 실행했다는 의미는 아니며 아래 소스 버전을 구분한다.
- 기존 work-flow/legacy 전환/모델·역할 구성 회귀: 운영자 직접 실행 **96 passed in 59.90s**.
- Ruff, 셸 구문, 스키마 자체 검증, `git diff --check` 통과.

광범위 검사 소스: `f5ae980e23fba9a7dc4e21113a9fc0bc693822a3646db90c5ac7fb6b249467a2`. 이후 심볼릭 링크 거부와 schema 오류 원문 비노출만 추가하고 영향 경로를 독립 재검증했다. 최종 파일은 아래 SHA-256을 기준으로 한다.

## 주요 확인 범위

- 코드/환경/미확정 진단의 후보 진행 차단, 독립 재현·역할 분리.
- 승인 전 활성 하네스 보존, 같은 저장소의 별도 기준본/후보 worktree.
- 실제 subprocess 결과, 목표 실패→통과, 회귀 전체 통과, 시간초과/출력 누락 차단.
- 실제 행동 확인 기록 필수, 실행 ID·소비 지침·시나리오 결과·증거 지문 검사. **실제 에이전트 효과는 별도 검증 대상**이다.
- 기준/후보/서비스 파일/runner/input/환경/보고서/로그/변경계획이 바뀌면 승인 적격 차단.
- 세션 메타데이터는 제외하고 테스트의 실제 환경·의존성 변화는 감지.
- 실제 사용자 메시지를 가리키는 승인 형식, 정확한 digest, 변경된 승인 기록의 적용 차단.
- 회귀 등록 파일 기록이 중단돼도 보존된 승인 이력에서 과거 사례를 복구하여 누락 방지.
- 허용 파일만 적용, 변경된 활성본 거부, 별도 승인 롤백, 중단 복구와 외부 경로/심볼릭 링크 거부.

## 재실행

```sh
.venv/bin/python -m pytest tests/unit/test_harness_improvement.py -q --confcutdir=tests/unit
.venv/bin/python -m pytest tests/unit/test_work_flow.py tests/unit/test_harness_flow_scripts.py tests/unit/test_harness_configuration.py -q --confcutdir=tests/unit
```

## 범위와 남은 운영 확인

테스트의 사용자 승인과 행동 보고서는 **합성 fixture**다. 실제 사람 동의나 실제 모델 행동 개선을 증명하지 않는다. 운영자가 실제 사용자 메시지와 실제 에이전트 실행 출처를 확인해야 한다. 관찰은 명시적으로 제공한 일부 기록이며 전체 Codex 내부 trace가 아니다.

실제 benchmark에는 이 시스템의 소스/정책만 추가했고 개선 제안을 생성·승인·적용하지 않았다. 서비스 코드/기존 상태·HEAD·인덱스를 변경하지 않았으며 commit/push/deploy/DB 변경/Notion 게시도 하지 않았다. lock 파일만 운영 smoke에서 생겼고 추적 제외했다.

평가 대상 밖의 미추적 활성 제품 파일·ignored 자료·외부 서비스 상태는 운영자가 별도 확인한다. 로컬 argv 실행기는 보안 격리가 아니며, 과거 worktree나 환경이 사라지면 보수적으로 검증/복구를 차단할 수 있다. 그때는 원본을 보존하고 사용자와 확인한 수동 복구가 필요하다. 파일 추가·삭제/모드 변경 후보는 MVP 범위 밖이다.

## 최종 지문

| 파일 | SHA-256 |
|---|---|
| `scripts/harness-improve.py` | `df53e0fe75810d2dd2b05ffe39710288f22819069cb85baaf3222d08643b7c38` |
| `scripts/harness-improve.sh` | `cb7f6cd3d98bdaf6e839699f17041cc6c399dcf6ca82bc20641a32c347f144b9` |
| `.harness/config.json` | `3f900bfae9db40909e90a193b1b7a6099da838f01e4565d5115df5f0387eade7` |
| `tests/unit/test_harness_improvement.py` | `83aa8b6d2ac1ae355e33c46777bf3f75bc01927414a2a6276e8e322967119b64` |
