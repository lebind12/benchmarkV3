# Karpathy 코딩 지침의 하네스 반영

사용자 결정: `andrej-karpathy-skills`와 현재 하네스의 비교 후 “네 적용해주세요”라고 요청했다. 기존 사용자 직접 하네스 개선의 후속 작업이며, 기존 절차의 자기 평가나 행동 테스트를 다시 요구하지 않는다. 실제 효과는 사용자가 개발하며 제공하는 피드백으로 판단한다.

## 출처와 비교 기준

- 커뮤니티 저장소: [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills). 기존 `forrestchang` 주소에서 이동했다. Karpathy의 관찰을 바탕으로 작성한 행동 지침이며, 외부 상태 머신이나 검증된 성능 향상 수치를 제공하는 근거로 취급하지 않는다.
- 검토한 버전: [`2c606141936f1eeef17fa3043a72095b4765b9c2`](https://github.com/multica-ai/andrej-karpathy-skills/tree/2c606141936f1eeef17fa3043a72095b4765b9c2).
- 원문: [CLAUDE.md](https://github.com/multica-ai/andrej-karpathy-skills/blob/2c606141936f1eeef17fa3043a72095b4765b9c2/CLAUDE.md), [README](https://github.com/multica-ai/andrej-karpathy-skills/blob/2c606141936f1eeef17fa3043a72095b4765b9c2/README.md), [예시](https://github.com/multica-ai/andrej-karpathy-skills/blob/2c606141936f1eeef17fa3043a72095b4765b9c2/EXAMPLES.md).
- 프로젝트 비교 기준: `76ce50fc61b34f1ce673f1b3b74fcddb71316416`의 외부 제어 하네스.

## 기존 적용과 이번 보완

| 원칙 | 이미 존재한 구조 | 이번 반영 |
|---|---|---|
| Think Before Coding | 원문 연결, 질문/가정, 준비 검사, 독립 명세 검토 | 결과를 바꾸는 해석만 차이·권장안·이유와 함께 질문. 기존 코드·결정으로 답할 수 있는 것은 재질문하지 않음 |
| Simplicity First | 요구 범위 확대/축소 금지, QUICK 간결화 | 불필요한 추상화·설정·미래 기능 억제, 기존 패턴 우선, 필요한 구조 변경은 근거와 함께 허용 |
| Surgical Changes | 허용 파일 경로, 다른 작업 보존 | 허용 파일 안에서도 주요 변경과 요구사항/필수 의존성의 연결 확인. 무관한 리팩터링·포맷·기존 dead code 정리 제한 |
| Goal-Driven Execution | 수용 시나리오, 실제 외부 검증, 독립 검토, 완료 게이트 | 버그 수정 전 재현 근거와 동일 조건의 수정 후 검증 연결. 미재현 한계와 대체 확인을 구분 |

단순화는 모든 필수 요구와 기존 정책을 충족하는 구현 방법에만 적용한다. 기능·오류 처리·권한·데이터 보호·수용 기준을 빼거나 후속으로 미루는 근거가 될 수 없다. 코드 줄 수나 개인 취향을 완료 기준으로 사용하지 않는다. 현재 요구에 필요한 구조 변경과 통합 작업을 일률적으로 금지하지 않는다.

## 실제 실행 연결

- `scripts/harness_runtime/requirements.py`: 기획 프롬프트에 해석 선택·단순성·버그 재현 근거 작성 규칙을 추가했다. 기존 `questions`, `constraints`, `scenarios`, 검증 명령 필드를 사용한다.
- `scripts/harness_runtime/controller.py`: 실제 명세 검토·개발·코드 검토 프롬프트에 해당 기준을 넣었다. 코드 검토자는 실제 diff와 주변 코드를 읽어 관련성을 판단하고, 근거 없는 변경/복잡도를 구체적인 파일·변경 위치와 함께 기존 `coverage_gaps`에 기록해 FAIL로 제출한다.
- `.codex/agents/{developer,planning-reviewer,behavior-tester}.toml`: 직접 역할 호출에서도 같은 기준을 사용하도록 맞췄다. 외부 실행기는 자체 프롬프트를 구성하므로 역할 파일만 수정하지 않았다.
- `AGENTS.md`, `docs/spec/agentic-workflow.md`, 요구사항·기획·구현/검토 템플릿: 운영자가 준비하고 인계할 근거를 연결했다. 템플릿은 해당하는 항목만 쓰며 별도 보고서를 매번 강제하지 않는다.

새 역할·승인 단계·계약/검토 스키마 필드를 추가하지 않는다. 기존 `coverage_gaps`/비-PASS를 처리하는 완료 게이트를 재사용한다. `owned_paths` 검사는 파일 범위의 결정론적 검사이고, 변경 내용의 필요성과 복잡도는 모델의 의미적 검토다. 지침 추가만으로 모든 불필요한 변경을 자동 차단한다고 주장하지 않는다. 변경 기준본이 없거나 수정 전 재현 근거가 없으면 그 한계를 명시한다.

## 확인과 사용 후 평가

이번 작업은 사용자 지시에 따라 Python AST 구문 분석, 세 역할의 TOML 파싱, 런타임 import, `scripts/harness-run.sh --help`, `git diff --check`와 변경 내용 확인을 수행했고 통과했다. 실제 개발 에이전트 호출, 자동 행동 테스트, 성능 비교 실험은 수행하지 않았다. 과거 하네스 테스트 통과 수치를 이번 변경의 효과로 재사용하지 않는다.

사용 중에는 불필요한 변경이 줄었는지, 구조가 불필요하게 커졌는지, 중요한 질문이 구현 전에 나왔는지와 함께 **필수 요구사항이 그대로 충족됐는지**를 관찰한다. 이상현상은 기존 feedback 경로로 실제 사례와 함께 기록한다. 현재 실행 중인 작업의 복사된 런타임을 덮어쓰지 않으며 업데이트된 진입점으로 생성하는 새 작업부터 적용한다.
