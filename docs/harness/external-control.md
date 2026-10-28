# 외부 개발 실행기 사용 안내

운영자는 대화에서 요구사항을 정리하고 아래 CLI를 사용자를 대신해 실행한다. 사용자가 직접 명령을 조작할 필요는 없다. 새 정본은 [운영 흐름](../spec/agentic-workflow.md)이며, 이번 반영은 사용자의 요청에 따라 행동 테스트 없이 진행했다. 다음 실제 개발에서 사용성을 확인한다.

## 준비

- Python 3.11 이상, 설치·인증된 `codex` CLI가 필요하다. 연결은 이 환경의 Codex 0.164.0 help 기준이다.
- 제어 소스 `/Users/woolee/benchmark`와 **다른 개발 worktree**를 사용한다. 메인/관리/AX 소유권을 지키고 기존 작업을 reset·stash·전환하지 않는다. 생성할 worktree와 기준 커밋은 작업에 맞게 운영자가 정한다.
- 의존성·로컬 fixture는 운영자가 준비한다. 개발/검증 도구의 네트워크는 닫혀 있다. 실제 외부 시스템이 필요한 검증은 로컬 대체 가능 여부와 필요한 사용자 결정을 먼저 정한다.
- 원문·계약·기록은 workspace 밖에 둔다. 기본 저장소는 `${XDG_STATE_HOME:-~/.local/state}/benchmark-harness/<workspace 경로 해시>`다. 필요하면 모든 명령에 같은 `--state-root`를 지정한다. 한 workspace에 여러 state-root를 혼용하지 않는다.
- 일반 옵션 `--workspace`, `--state-root`, `--model`, `--json`은 하위 명령 앞에 쓴다.

## 요청 구체화와 실행

```bash
HARNESS=/Users/woolee/benchmark/scripts/harness-run.sh
WORKSPACE=/absolute/path/to/development-worktree
INPUTS=/absolute/path/to/operator-inputs

# request.txt는 사용자 요청 원문. 계약 파일은 매번 새 버전으로 작성한다.
"$HARNESS" --workspace "$WORKSPACE" draft --mode FULL \
  --request "$INPUTS/request.txt" --output "$INPUTS/contract-v1.json"

# 선택 사항: 질문·가정·명령 연결 등 구조적 준비 상태만 확인한다.
"$HARNESS" --workspace "$WORKSPACE" check-contract \
  --request "$INPUTS/request.txt" --contract "$INPUTS/contract-v1.json"

"$HARNESS" --workspace "$WORKSPACE" init \
  --request "$INPUTS/request.txt" --contract "$INPUTS/contract-v1.json"

# init이 반환한 실제 id를 입력한다.
WORK_ID=<returned-id>
"$HARNESS" --workspace "$WORKSPACE" run "$WORK_ID"
```

`draft`는 파일을 읽고 초안을 만드는 모델 호출이며 제품을 수정하지 않는다. 직접 [계약 템플릿](templates/requirement-contract.json)을 작성해도 된다. QUICK/FULL은 사용자가 이미 선택한 값을 사용한다. 중요한 질문이 남으면 사용자 답변을 받고 계약을 갱신한다. 이미 받은 결정·일상 구현 방식은 재승인받지 않는다.

`init`은 보존만 한다. `READY`는 구조적 준비 상태이며 의미적 완전성 통과가 아니다. `run`이 별도 읽기 전용 명세 검토를 거쳐 개발·검증·독립 코드 검토를 실행한다. `review-spec <id>`로 명세만 먼저 검토할 수도 있다. `VERIFIED`는 이 실행 경로에서 해당 코드 지문의 검증을 통과한 상태이며 병합·배포와 다르다.

검증 `argv`는 셸 문자열이 아닌 배열이다. 명령은 workspace를 읽고 별도 scratch에만 쓸 수 있다. 빌드 산출물이 소스에 쓰이는 도구는 scratch로 출력 경로를 지정하거나 별도 로컬 검사로 구성한다. 테스트가 파일을 고쳐 통과시키는 것을 허용하지 않는다. `verification_files`는 변경되면 검증을 무효화할 **이미 존재하는** 테스트/설정 파일이다. 새로 작성하는 테스트를 기존 기준과 혼동하지 않는다.

## 상태·중단·사용자 피드백

```bash
"$HARNESS" --workspace "$WORKSPACE" status "$WORK_ID"
"$HARNESS" --workspace "$WORKSPACE" show "$WORK_ID"
"$HARNESS" --workspace "$WORKSPACE" events "$WORK_ID"
"$HARNESS" --workspace "$WORKSPACE" cancel "$WORK_ID"
# 취소는 최종 상태다. 장애/환경 문제를 해결한 중단 작업에는 resume을 사용한다.
"$HARNESS" --workspace "$WORKSPACE" resume "$WORK_ID"

"$HARNESS" --workspace "$WORKSPACE" feedback "$WORK_ID" \
  --message '요구한 오류 화면이 생략되었습니다.' --category unclassified \
  --evidence /absolute/path/to/observation.txt
```

취소·실패 시 제품 파일은 보존하며 자동 rollback하지 않는다. 재작업 한도 소진은 성공이 아니다. 환경 거절·미충족 요구·코드 실패를 구분해 원인을 설명한다. `show`와 로그에는 요청·코드 관찰이 포함될 수 있으므로 필요한 부분만 사용자에게 제시한다. `feedback`의 category는 원인 가설이며 자동으로 하네스 결함을 확정하지 않는다. 근거 파일의 경로·지문을 남기고 내용을 자동 복제하거나 외부로 게시하지 않는다.

## 요구사항 변경

`change`는 원문을 삭제하지 않고 후속 사용자 메시지와 새 계약 버전을 추가한다. 운영자는 실제 대화에서 이미 받은 권한을 사용하며 추가 확인을 관성적으로 만들지 않는다. 요구사항 삭제·검증 약화·중요 정책 변경에 사용자 결정이 없다면 변경하지 않는다.

```json
{
  "source": "실제 사용자 메시지를 찾을 수 있는 대화/메시지 참조",
  "message": "실제 사용자 메시지 원문",
  "old_hash": "status의 현재 contract_hash",
  "new_hash": "새 계약의 check-contract 출력 contract_hash"
}
```

```bash
"$HARNESS" --workspace "$WORKSPACE" change "$WORK_ID" \
  --contract "$INPUTS/contract-v2.json" --receipt "$INPUTS/scope-receipt-v2.json"
```

새 계약을 `check-contract`로 확인할 때는 최초 원문과 후속 메시지를 함께 담은 파일을 `--request`로 준다. 저장된 최초 원문은 변경하지 않는다. 변경은 이전 명세 검토·구현 PASS를 무효화한다. 제어 런타임이 업그레이드된 기존 작업은 새 작업으로 이어받으며 기존 검증을 승계하지 않는다. 동결 테스트가 이미 변경된 경우에는 원인을 정리하고 원래 기준을 복구하거나 새 작업을 만든다.

이 receipt는 운영자가 실제 대화를 근거로 기록하는 값이다. 파일만으로 사용자 신원을 인증하지 않는다. 샌드박스 안 개발자는 상태 파일을 쓸 수 없지만 같은 계정의 다른 비제한 프로그램까지 막는 권한 서버는 아니다.

## 이번 변경 이후 평가

이번에는 문법/import/JSON·TOML/도움말 연결만 확인했다. 실제 모델·검증 명령·중단/재개·샌드박스 프로브는 실행하지 않았다. 첫 개발 작업에서 사용자 체감과 실행 로그를 함께 보고 구체적으로 수정한다. 실행기 없이 처리한 native 대화까지 자동 감시한다고 보고하지 않는다.
