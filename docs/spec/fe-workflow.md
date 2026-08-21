# FE Workflow — Page-led Frontend Lifecycle

프론트엔드 페이지(또는 의미 있는 컴포넌트 그룹) 1개의 라이프사이클을 3개 에이전트로 처리하기 위한 상태 머신, 핸드오프, 게이트 정책의 SSOT.

상위:
- 메인 → FE 팀 요구사항: `@docs/features/README.md`
- BE 워크플로: `@docs/spec/agent-workflow.md`
- 도메인: `@AGENTS.md`

## 1. 단위와 명칭

- **feature**: 페이지 1개 또는 작은 컴포넌트 그룹. FE 팀 1 사이클의 작업 단위.
- 한 feature 가 0~N 개의 endpoint-request 를 생성한다.
- 큰 기능은 메인이 여러 feature 로 분할해서 트리거.

## 2. FE 팀 구성 (3 에이전트)

| 에이전트 | 역할 | 도구 권한 | git |
|---|---|---|---|
| **fe-planner** | 메인 요구사항 → 정제된 spec + devplan + testplan 작성 | Read, Write (docs/features/ 하위), Edit, Bash (read-only), Glob, Grep | `fe-feat-<id>` 브랜치 commit / push (문서만) |
| **fe-dev** | mock 데이터로 구현 + Playwright 테스트 코드 작성/실행. 후속 라이프사이클에서 mock→real 스왑도 수행 | Read, Write, Edit, Bash (npm, vitest, playwright), Glob, Grep | `fe-feat-<id>` / `fe-feat-integration-<id>` commit / push |
| **fe-reviewer** | planner 산출물 검토 (PLAN_REVIEW) + 구현 검토 (REVIEW_PENDING) 모두 담당. APPROVE / REQUEST_CHANGES 만 | Read, Grep, Glob, Bash (read-only) | commit/push 불가, PR comment 만 |

원칙: BE 와 동일하게 "작성자 ≠ 합격 판정자" 분리.

## 3. 두 개의 라이프사이클

### 3.1 Mock 라이프사이클 (FE 자체 완성)

브랜치: `fe-feat-<feature_id>` (`frontend` 에서 분기)

```
TRIGGERED                                ← 메인이 fe-planner 호출
   ↓
PLAN_DRAFTING (fe-planner)
   ↓
PLAN_REVIEW (fe-reviewer)
   │   ├─ REQUEST_CHANGES → PLAN_DRAFTING (재시도 ≤3)
   │   └─ REJECT (spec SSOT 충돌 등) → PLAN_FAILED → 메인 보고
   ↓ APPROVE
PLAN_APPROVED
   ↓
IMPL_IN_PROGRESS (fe-dev)  ←──────────┐
   ↓                                   │
IMPL_PUSHED                            │
   ↓                                   │
PLAYWRIGHT_RUN (L1 + L2)               │
   │   └─ 실패 → IMPL_IN_PROGRESS (≤3)│
   ↓ 통과
REVIEW_PENDING (fe-reviewer)
   │   └─ REQUEST_CHANGES → IMPL_IN_PROGRESS (≤3)
   ↓ APPROVE
MERGE_GATE (Mock 머지 게이트)
   ↓
PR_CREATED → MERGED
   ↓ (자동)
BE_REQUEST_GENERATED  ← fe-dev 가 mock JSON + planner spec 으로 endpoint-request 자동 추출
   ↓
FE_DONE_AWAITING_BE   ← 메인에 보고. BE 팀 트리거는 메인이 결정
```

### 3.2 Integration 라이프사이클 (mock → real 스왑)

브랜치: `fe-feat-integration-<feature_id>` (`frontend` 에서 분기)

트리거: 이 feature 가 의존하는 모든 endpoint 의 BE state 가 `MERGED` 도달 시 자동, 또는 메인이 수동 트리거.

```
INTEGRATION_TRIGGERED
   ↓
INTEGRATION_IN_PROGRESS (fe-dev)
   - mock 코드 제거
   - 실 API 호출 + zod 런타임 schema 검증 코드 추가
   - L3 Playwright 테스트 추가 (Vercel preview + prod BE)
   ↓
INTEGRATION_PUSHED
   ↓
L3_RUN (Vercel preview deploy 에서)
   │   └─ 실패 → INTEGRATION_FAILED (재시도 ≤3) → INTEGRATION_IN_PROGRESS
   ↓ 통과
REVIEW_PENDING (fe-reviewer)
   ↓ APPROVE
MERGE_GATE (Integration 머지 게이트)
   ↓
PR_CREATED → MERGED → main 머지 시 Vercel prod 배포
   ↓ (자동)
L4_SMOKE (prod 배포 후 1회)
   │   └─ 실패 → 알림 (자동 롤백은 별도 정책)
   ↓
DONE
```

재시도 한도: 모든 루프 최대 3회. 초과 시 `ESCALATED`.

## 4. 상태 파일

위치: `.codex/state/feature-flow/<feature_id>.json` (Mock + Integration 한 파일에 phase 로 구분)

```jsonc
{
  "feature_id": "main-fixtures-list",
  "feature": {
    "title": "메인 페이지 — 오늘의 경기 리스트",
    "requirements_doc": "docs/features/main-fixtures-list.md"
  },
  "phase": "mock" | "integration",
  "state": "REVIEW_PENDING",
  "owner": "fe-reviewer",
  "iteration": {
    "plan_review_loop": 0,
    "playwright_loop": 0,
    "review_loop": 1,
    "integration_loop": 0
  },
  "endpoint_requests": ["GET__api_v1_fixtures"],
  "be_dependency_state": {
    "GET__api_v1_fixtures": "FE_REQUESTED"
  },
  "artifacts": {
    "spec_path": "docs/features/main-fixtures-list.spec.md",
    "devplan_path": "docs/features/main-fixtures-list.devplan.md",
    "testplan_path": "docs/features/main-fixtures-list.testplan.md",
    "branch": "fe-feat-main-fixtures-list",
    "commit": "def5678",
    "playwright_e2e_paths": ["frontend/e2e/main-fixtures-list.spec.ts"]
  },
  "evidence": {
    "vitest_log": "...",
    "playwright_mock_log": "...",
    "playwright_integration_log": null,
    "lint_log": "...",
    "type_log": "...",
    "bundle_size_delta_pct": 3.2
  },
  "gates": {
    "plan_approved_by": "fe-reviewer",
    "review_approved_by": null,
    "merge_approved_by": null
  },
  "blockers": [],
  "next_action": { "agent": "fe-reviewer", "command": "review impl at commit def5678" }
}
```

history: `.codex/state/feature-flow/<feature_id>.history.jsonl` (append-only)

## 5. 메인 → FE 팀 핸드오프

1. 메인이 `docs/features/<id>.md` 작성 후 사용자 확정
2. 메인이 사용자에게 "FE 팀 트리거" 확인
3. 메인이 `scripts/feature-flow.sh init <feature_id>` 호출 → state 파일 생성, state=`TRIGGERED`
4. 메인이 Codex subagent role `fe-planner` 를 호출
5. 이후 FE 팀 내부 자율 진행

## 6. FE → BE 핸드오프 (BE_REQUEST_GENERATED 단계)

Mock 머지 직후 fe-dev 가 다음 작업 자동 수행:

1. 사용한 `frontend/mocks/<endpoint_id>.json` 들과 planner 의 spec 을 조합해 `frontend/endpoint-requests/<endpoint_id>.request.json` 생성
2. 각 endpoint 마다 `scripts/endpoint-flow.sh init <endpoint_id> --from-request <path>` 호출 → BE 측 state 가 `FE_REQUESTED` 로 생성
3. FE state 의 `endpoint_requests[]` 와 `be_dependency_state` 채워짐
4. FE state 를 `FE_DONE_AWAITING_BE` 로 전이 → 메인에 보고

## 7. 머지 게이트

### Mock 머지 (`fe-feat-* → frontend`)

L1 + L2 통과 + 코드 품질 항목:

1. Vitest (L1) exit 0
2. Playwright mock mode (L2) exit 0 (`VITE_USE_MOCK=true`)
3. lint / type (vue-tsc) / build 통과
4. 번들 사이즈 회귀 < 10%
5. fe-reviewer APPROVE
6. 방송용 페이지 변경 시 크로마키 배경 (`#00B140`) 시각 회귀 통과
7. CI status check 통과

### Integration 머지 (`fe-feat-integration-* → frontend`)

위 7개 + 추가:

8. **Playwright integration (L3)** exit 0 — Vercel preview deploy 환경에서 **prod BE 직접 호출**
9. zod 런타임 schema 검증 통과 (모든 응답)

> **L3 가 prod BE 를 호출** 하므로 다음 안전장치 필수:
> - 읽기 endpoint 만 자유롭게 호출. 쓰기 endpoint 는 테스트 전용 계정 + 정리 hook
> - L3 가 prod 데이터를 변경하지 않도록 fe-reviewer 가 PR 단계에서 차단

### Prod smoke (L4)

- Vercel prod 배포 직후 1회 자동 실행
- 핵심 경로 (홈 로드 + 주요 리스트 표시) 만 검증
- 실패 시 알림. 자동 롤백 없음.

## 8. 테스트 레이어 (L1~L4)

| 레이어 | 도구 | 데이터 | 어디서 실행 |
|---|---|---|---|
| L1. Unit / Component | Vitest | 인메모리 mock | 로컬 + CI (모든 PR) |
| L2. E2E mock | Playwright + MSW | mock JSON | 로컬 + CI (모든 PR) |
| L3. E2E integration | Playwright | prod BE 직접 | Vercel preview deploy (integration PR) |
| L4. Prod smoke | Playwright | prod | Vercel prod (배포 후 1회) |

## 9. 데이터 검증

- **Mock 단계**: TS 타입 (openapi-typescript 생성) + mock JSON 이 컴포넌트 가정과 일치하면 충분
- **Integration 단계**: 실 BE 응답을 **zod** 런타임 스키마로 검증. 불일치 발견 시:
  - 원인이 BE 면 spec 갱신 요청 (메인 또는 BE 팀에 보고)
  - 원인이 FE 면 컴포넌트/zod 스키마 보정
- **Prod 단계**: smoke test 가 핵심 응답 shape 1~2 개 검증

## 10. 사람 개입 트리거

| 트리거 | 행동 |
|---|---|
| `plan_review_loop ≥ 3` 또는 `playwright_loop ≥ 3` 또는 `review_loop ≥ 3` 또는 `integration_loop ≥ 3` | `ESCALATED` |
| `PLAN_FAILED` | 메인 결정 (spec 자체 문제) |
| BE 의존 endpoint 가 장기 미완료 / ESCALATED | state.blockers 기록 + 메인 보고 |
| L3 에서 prod 데이터 의도치 않은 변경 감지 | 즉시 정지 + ESCALATED |
| 위젯/인증/마이그레이션 동급의 위험 영역 변경 | MERGE_GATE 에서 사람 승인 필수 |

## 11. 외부 의존성 mock 정책

| 의존성 | L1 | L2 | L3 | L4 |
|---|---|---|---|---|
| BE API | MSW | MSW | 실 prod | 실 prod |
| 외부 CDN / 폰트 | 실 | 실 | 실 | 실 |
| OpenAI / API-Football | n/a (FE 가 직접 호출 안 함) | n/a | n/a | n/a |

## 12. 브랜치 정리

- Mock 라이프사이클: `fe-feat-<id>` task branch 1개
- Integration 라이프사이클: 필요 시 `fe-feat-integration-<id>` task branch 1개
- 별도 worktree 를 생성하지 않고 하나의 checkout 에서 해당 task branch 로 전환한다.
- 브랜치 전환 전 작업 디렉토리가 clean 하고 다른 구현 에이전트가 작업 중이지 않은지 확인한다.
- 서로 다른 브랜치의 구현은 동시에 진행하지 않는다. Mock 을 머지한 뒤 Integration 을 순차적으로 시작한다.
- 머지 흐름: `fe-feat-* / fe-feat-integration-* → frontend → main`

## 13. CLI

```bash
# 새 feature 등록
feature-flow init <feature_id> --requirements docs/features/<id>.md

# 상태 전환
feature-flow transition <feature_id> <new_state> --by <agent> --note "..."

# 현재 상태
feature-flow status <feature_id>

# integration 라이프사이클 트리거
feature-flow start-integration <feature_id>

# 전체 in-flight 목록
feature-flow list
```

본 CLI 의 구체 구현은 Plans.md Phase 10 의 task 로 추적.

### 13.1 Harness TaskList 강제 규칙

FE feature 전체를 첫 stage owner 에게 단일 task 로 assign 하지 않는다. `fe-planner` 는 plan stage 만 소유하고, feature 전체 mock 구현의 owner 가 아니다.

금지:

```json
{
  "subject": "FE1: main-home 페이지 mockup 구현",
  "owner": "fe-planner",
  "description": "fe-planner → fe-dev (Mock 라이프사이클)"
}
```

허용되는 표현은 둘 중 하나다.

1. Stage 별 task 분리:

```text
8.plan         main-home plan 작성       owner=fe-planner
8.plan-review  main-home plan 리뷰       owner=fe-reviewer
8.impl         main-home mock 구현       owner=fe-dev
8.impl-review  main-home 구현 리뷰       owner=fe-reviewer
8.merge        main-home mock merge      owner=team-lead
```

2. 단일 feature task + stage owner 갱신:

```json
{
  "tasklist_id": "8",
  "feature_id": "main-home",
  "state": "IMPL_IN_PROGRESS",
  "current_stage": "IMPL_IN_PROGRESS",
  "owner": "fe-dev"
}
```

TaskList owner 와 feature-flow owner 는 항상 같아야 한다. 다르면 하네스는 다음 assignment / completion 을 차단한다.

### 13.2 `stage_completed` 와 `task_completed`

중간 단계 완료는 `task_completed` 가 아니다. 각 stage 는 다음 명령으로만 전이한다.

```bash
scripts/feature-flow.sh transition <feature_id> <next_state> --by <agent> --note "..."
```

`TaskCompleted` hook 은 성공 final state 에서만 통과한다.

TaskList 상 하네스 워크플로우 작업으로 보이는데 `feature-flow` state 가 `tasklist_id` 로 연결되어 있지 않은 경우도 차단한다. 이 규칙 때문에 planner/dev/reviewer 중간 단계가 state 없이 TaskList 완료로 빠져나갈 수 없다.

| phase | 성공 final state | 의미 |
|---|---|---|
| Mock | `FE_DONE_AWAITING_BE` | mock 구현/리뷰/머지/endpoint-request 생성까지 완료 |
| Integration | `DONE` | mock→real, L3/L4, 리뷰/머지까지 완료 |

필수 차단 예:

| 현재 state | sender | 잘못된 신호 | 결과 |
|---|---|---|---|
| `PLAN_REVIEW` | `fe-planner` | `task_completed` | 차단. reviewer approval 전 |
| `PLAN_APPROVED` | `fe-planner` | `task_completed` | 차단. fe-dev 구현 전 |
| `IMPL_PUSHED` | `fe-dev` | `task_completed` | 차단. L1/L2 + reviewer 전 |
| `REVIEW_PENDING` | `fe-reviewer` | `task_completed` | 차단. merge + endpoint-request 전 |
| `FE_DONE_AWAITING_BE` | `team-lead` | `task_completed` | 허용 |

### 13.3 검증 명령

```bash
scripts/feature-flow.sh validate <feature_id>
scripts/feature-flow.sh validate-all --strict-tasklist
```

`--strict-tasklist` 는 다음을 오류로 처리한다.

- `tasklist_id` 누락
- TaskList owner 와 workflow owner 불일치
- TaskList 는 `completed` 인데 workflow state 가 final 이 아님
- workflow 는 final 인데 TaskList status 가 `completed` 가 아님
