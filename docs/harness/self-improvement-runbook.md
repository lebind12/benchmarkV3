# 하네스 자기 개선 운영 안내

이 문서는 운영자가 재현된 하네스 문제를 조사하고, 격리 후보를 실제 행동으로 평가한 뒤, 사용자의 명시적 동의를 받아 제한된 파일을 적용하거나 복구하는 절차다. 정책 정본은 [하네스 개선 명세](../spec/harness-self-improvement.md), 프로젝트 제한은 [`.harness/AGENTS.md`](../../.harness/AGENTS.md), 개선 대상과 상한은 [`.harness/config.json`](../../.harness/config.json)이다.

`harness-improve`는 기록과 제한된 로컬 명령 실행을 돕는다. 신원 인증기, 전체 도구 호출 기록기, 진단기, 보안 격리 환경이 아니다. CLI의 상태나 평가 PASS는 사용자 승인을 대신하지 않는다.

## 1. 시작 전 확인

1. 원본 관찰에서 실제로 본 파일·도구·오류와 수집 범위를 확인한다. 직접 기록한 내용만 기록한다. Codex 내부의 모든 도구 호출이나 추론이 자동 수집된 것처럼 쓰지 않는다. 비밀, 전체 환경변수, 불필요한 대화 원문은 넣지 않는다.
2. 운영자는 조사 가치가 있는 신호를 선별한다. 서비스 코드 또는 환경 원인, 원인 미확정, 재현 불가이면 하네스 후보 절차로 진행하지 않고 각각 서비스 개발, 환경 해결, 추가 조사로 돌린다.
3. 개발자와 분리된 `harness-inspector`에게 원래 작업 목표, 관찰, 기존 규칙, 대체 원인과 반증 조건을 검토하게 한다. 아직 재현 전이면 하네스 원인은 가설이다.
4. 후보는 운영자가 관리하는 별도 격리 worktree에서만 다룬다. 기존 앱의 `create_worktree`로 현재 같은 로컬 저장소와 기준 ref에서 기준본용과 후보용 두 worktree를 만들고, 생성 상태 확인 및 attach를 마친 뒤 각 작업공간 경로를 기록한다. 두 worktree는 같은 HEAD여야 하며 각자 깨끗해야 한다. 이 안내는 worktree를 만들지 않는다. 관리/메인/AX checkout을 바꾸거나 과거 `benchmark.fe-feat-main-home` worktree를 재사용하지 않는다.

허용 후보는 현재 `.harness/config.json`의 기존 7개 역할 TOML과 `docs/spec/agentic-workflow.md`뿐이다. 추가·삭제, 보호 정책, `.harness*`, 개선 엔진/스키마, root `AGENTS.md`, 권한/모델 설정은 이 절차에서 수정할 수 없다.

## 2. 명령과 상태 흐름

저장소 루트에서 아래 명령을 사용한다. `scripts/harness-improve.sh`가 프로젝트 가상환경 Python이 있으면 사용하고, 없으면 `python3`를 선택한다. 정확한 옵션은 `scripts/harness-improve.sh --help`가 표시하는 현재 parser를 따른다.

```sh
scripts/harness-improve.sh observe --event <관찰-JSON-경로>
scripts/harness-improve.sh init <proposal-id> --report <진단-JSON-경로>
scripts/harness-improve.sh status [proposal-id]
scripts/harness-improve.sh validate [proposal-id]
```

관찰 JSON은 `.harness-engineering/schemas/observation.schema.json`, 진단 입력은 `diagnosis.schema.json`에 맞춘다. `observe`는 `file_read`, `tool_call`, `error`, `workflow` 종류와 작업 참조, 메타데이터, 근거를 받는다. 진단은 `code`, `environment`, `harness`, `unknown` 중 하나로 구분한다. `init`은 `DIAGNOSED`를 만든다. 비하네스 원인은 `close <proposal-id>`로 종결하거나 서비스 흐름으로 돌린다.

`harness` 진단이라면 독립 inspector가 격리 worktree와 평가 suite를 준비한다. suite에는 적어도 `target`과 `regression` 종류가 각각 포함되어야 하고, 명령 인자 배열과 제한 시간이 들어간다. 현재 상한은 30개 사례, 사례당 120초다. 운영자가 각 명령을 검토하고 임의의 운영 DB/Redis 쓰기, 설치, 배포, 외부 서비스 변경이 없는지 확인한다. CLI 실행기는 보안 격리 컨테이너가 아니며 로컬 권한으로 subprocess를 실행한다.

현재 CLI의 순서와 상태는 다음과 같다.

| 단계 | 현재 명령·상태 | 통과 조건과 실패 처리 |
|---|---|---|
| 진단 | `init` → `DIAGNOSED` | 원 관찰과 근거를 보존한다. 다른 원인이면 종결/서비스 흐름으로 넘긴다. |
| 격리 준비 | `prepare <id> --baseline-root <경로> --candidate-root <경로> --suite <JSON> --inspector <id>` → `PREPARED` | 활성본을 읽어 기준 스냅샷을 만들고 두 격리 worktree에 허용 파일을 복사한다. worktree는 활성 저장소의 별도 worktree여야 하고 HEAD가 같아야 한다. |
| 기준 재현 | `reproduce <id> --inspector <id>` → `REPRODUCED` | 기준본에서 모든 target은 실패하고 모든 regression은 통과해야 한다. 실패/시간초과/상태 불일치면 멈추고 원인을 다시 분류한다. |
| 후보 제출 | optimizer가 후보 worktree만 수정한 후 `candidate <id> --optimizer <id> --change-plan <MD>` → `CANDIDATE` | inspector·개발자와 다른 optimizer여야 한다. 활성본과 기준본은 건드리지 않는다. |
| 비교 평가 | `evaluate <id> --evaluator <id> --behavior-report <JSON>` → `EVALUATED` | evaluator는 개발자·inspector·optimizer와 달라야 한다. 기준본과 후보본에 동결 suite를 각각 실행한다. 기준 target 실패 및 회귀 통과, 후보 전체 통과가 필요하다. |
| 승인 검토 요청 | `request-approval <id>` → `READY_FOR_APPROVAL` | 정확한 후보 digest, 실제 diff, 예상 효과·위험 및 비교 결과가 생성된다. 사용자에게 실제 diff와 근거를 보여주기 전에는 승인 기록을 만들지 않는다. |
| 사람 결정 기록 | `record-approval <id> --evidence <실제-승인-기록-경로>` → `APPROVED` 또는 `REJECTED` | 운영자가 실제 사용자 메시지 출처와 명시 문구가 해당 digest/action을 승인하는지 직접 확인한다. 거절/보류면 기준본을 유지한다. |
| 적용 | `apply <id>` → `APPLIED` | 상태·digest·지문·현재 활성 파일이 여전히 승인 당시와 일치할 때만 후보에서 바뀐 파일을 각각 원자적으로 교체하고 중간 실패는 저장된 기준본으로 복원을 시도한다. 여러 파일 전체가 하나의 원자적 거래인 것은 아니다. |

상태 조회와 검증은 `status <id>`, `validate <id>`로 한다. 진행 중 어느 검사든 실패하면 결과를 성공으로 표시하지 않는다. 재현에 실패했거나 기준본 회귀가 깨졌거나 후보 회귀가 실패했다면 활성 파일은 그대로 두고 사례/원인을 재검토한다. 후보가 평가 후 바뀌거나 동결 suite·설정·기준본이 바뀌면 해당 digest는 무효다. 새 평가와 승인이 필요하다.

## 3. 평가 증거 계약

현재 구현은 명령 종료 코드, 제한 시간, 제한된 로그, 기준/후보 파일 manifest와 suite 지문을 확인한다. 이것은 실제 에이전트가 지침을 소비했고 목표 행동이 바뀌었음을 입증하지 않는다. 서술형 규칙의 특정 문자열이 파일에 있는지만 검사한 결과도 행동 효과의 증거가 아니다.

따라서 운영자는 별도 인스턴스의 evaluator가 같은 입력·시나리오·모델/추론 설정에서 기준본과 후보본을 실제 실행했는지 확인하고, 실행 식별자, 소비한 지침의 지문, 관찰 가능한 행동 결과, 원본 응답/도구 증거를 연결해야 한다. 필수 target과 누적 regression 전체를 동결한 기준으로 비교한다. 증거가 없거나 입력/환경이 달라 비교할 수 없으면 `READY_FOR_APPROVAL`로 보내지 않는다.

`candidate --change-plan`은 평가 전에 작성한 예상 효과·파일별 이유·회귀 위험·복구 범위 Markdown을 동결한다. `evaluate --behavior-report`는 **필수**다. 보고서에는 아래 항목을 기록한다.

- 공통: `evaluator_id`, `scenario_id`, `model`, `reasoning`, `settings_id`, `environment_id`.
- `baseline`, `candidate` 각각: 서로 다른 실제 `run_id`, 실제 소비한 허용 지침 전체의 `consumed_files`(경로→SHA-256), 동결 suite와 같은 순서의 `cases`(`id`, `outcome`), 기존 원본 증거 파일의 `evidence`(`path`, `sha256`).
- 기준본 target은 FAIL, regression은 PASS이고 후보는 모두 PASS여야 한다. 누락·중복·다른 지문·같은 실행 ID는 승인 적격이 아니다.

이 보고서는 독립 평가자의 **행동 증거 확인 기록**이다. CLI가 모델 호출의 진위나 원문 의미를 자동 인증하지는 않는다. 운영자는 실제 하위 에이전트 실행과 출처를 대조한다. `reproduce` 전에 inspector가 실제 기준본 행동을 재현했는지도 운영자가 확인한다. 기준 재현 명령 자체가 단순 텍스트 검사라면 그것만으로 optimizer에 진행을 허가하지 않는다. 관찰이나 실제 에이전트 실행을 할 수 없으면 작업을 미완료로 남긴다. 테스트 코드에 사용된 가짜 에이전트 ID/응답은 운영 증거로 사용할 수 없다.

`prepare`는 동결 suite의 모든 case와 필수 회귀 집합을 고정한다. suite의 `inputs` 배열에는 명령 인자만으로 찾을 수 없는 외부 fixture·runner·시나리오·의존성 설명 파일을 명시한다. 경로는 기존 파일이어야 한다. 실행 파일과 절대 경로 파일 인자도 지문에 연결한다. 두 worktree의 허용 파일 밖 추적/미추적 파일은 동일해야 하고 실행 중 바뀌면 실패한다. Python·의존성·테스트에 전달되는 환경의 지문도 비교한다. 세션 식별자 같은 일시적 값은 테스트 환경에서 제외하며 원시 환경은 저장하지 않는다.

활성 checkout의 추적되는 제품 파일이 replay 기준과 다르면 준비가 차단된다. 현재 변경을 자동 stash/commit/reset해서 맞추지 않는다. 활성본에만 있는 미추적 제품 파일이나 ignored 외부 자료를 모두 자동 복제하는 것은 지원하지 않으므로 실제 재현에 필요한 파일은 운영자가 기준 커밋/fixture/`inputs`로 포함해야 한다. 이러한 범위 확인 없이 동일 환경이라고 주장하지 않는다.


## 4. 사용자 검토와 승인 기록

`request-approval`이 만드는 `.harness-engineering/proposals/<id>/approval.md`는 승인 요청서이지 승인 자체가 아니다. 운영자는 여기에 더해 실제 후보 diff, 재현 및 비교 보고서/로그, 효과와 회귀 위험, 평가의 한계, 변경 파일과 지문, 복구 범위, 후보 digest를 사용자가 확인할 수 있게 제시한다. 제안 digest는 현재 기준본·후보·suite·진단·실행 보고서를 묶는다. 사용자가 보고 있는 후보의 digest와 기록하려는 digest를 글자 단위로 대조한다.

명시적 동의가 실제 사용자 메시지로 확인된 뒤 운영자만 그 메시지의 출처와 승인 문구를 정확한 digest 및 `apply` 작업에 연결해 기록한다. `approval.schema.json`의 `actor`, `source`, `quote`, `digest` 등 필드는 증거를 연결하는 기록 형식일 뿐이다. 실제 메시지를 복사·요약해 기록할 때도 출처를 사실대로 적는다. 임의의 승인 문구, 테스트 fixture, 하위 에이전트의 의사, 로그 속 문구를 사용자 동의로 꾸며내거나 승인 기록으로 재사용하지 않는다. 실제 동의가 없으면 `record-approval`/`apply`를 실행하지 않는다. 운영자 판단, 서비스 코드의 머지 승인, 테스트 통과도 승인이 아니다.

승인 이후 후보·평가·suite·기준본이 달라지거나 활성 파일이 동시 변경되면 중단한다. 새 지문으로 다시 평가하고 사용자에게 다시 검토받는다. CLI는 활성 파일이 예상 기준본과 일치하지 않으면 적용을 거부한다. 동시 변경을 덮어쓰지 않는다.

## 5. 실패, 복구, 적용 후

적용 중 오류가 발생하면 상태는 `APPLY_FAILED`일 수 있고 일부 파일 복구를 시도했을 수 있다. `status`와 `validate`로 상태 및 지문을 확인한다. `recover <id>`는 변경 파일이 기준본 또는 후보본의 알려진 지문과 일치할 때만 저장해 둔 기준본을 복원한다. 예상 밖의 편집이 하나라도 있으면 자동 복구가 거부되므로 현재 파일을 보존하고 운영자가 수동으로 조사한다. 수동으로 충돌을 덮어쓰지 않는다.

성공한 적용은 `.harness-engineering/history/`에 이력을 남기며 서비스 배포를 하지 않는다. 적용된 버전을 되돌리는 것도 별도 승인이다. `request-approval <id> --action rollback`이 출력하는 롤백 digest, 버전, 복원 파일을 먼저 사용자에게 보여주고 실제 사용자의 해당 롤백 동의를 받은 뒤에만 기록/실행한다. 현재 상태가 예상 후보 지문과 다르면 `rollback <id> --evidence <실제-승인-기록-경로>`는 거부되어야 한다. 버전 복구는 승인된 변경 파일만 대상으로 하며 이후의 별도 변경을 제거하지 않는다.

`APPLIED`는 하네스 파일이 적용됐다는 뜻이다. 생산성 향상이나 서비스 작업 완료를 뜻하지 않는다. 새 지침을 적용할 현재 작업에는 운영자가 새 지침을 명시적으로 전달하거나 새 에이전트를 사용한다. 기존 서비스 코드/목표가 바뀌었으면 기존 테스트·승인을 재사용하지 말고 서비스 작업 흐름에서 재검증한다. 과거 승인된 재현·회귀 사례는 보호된 regression-registry와 적용 이력에 남으며 다음 suite에서 같은 ID·명령의 regression으로 포함해야 한다. 누락·변경하면 준비가 차단된다. 롤백해도 과거 사례는 삭제되지 않는다. 이전 실패를 의도적으로 되살리거나 runner를 바꿔야 한다면 기존 사례를 몰래 제거하지 말고 별도 사용자 결정으로 기준을 다시 정한다.

검증 범위와 실제 운영에서 확인할 한계는 [구축 검증 기록](self-improvement-validation.md)에 정리했다.
