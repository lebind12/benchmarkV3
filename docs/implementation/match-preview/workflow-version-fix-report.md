# 워크플로우 버전 계산 수정 보고 (승인 단위 버전 결함)

**고친 것.** `runner.section_workflow_version`이 구성 모듈마다 `prompt_version=""`,
`implementation_version=""`인 자리표시자를 넣어 버전을 계산했다. 그래서 R1이
`mp05-form-2`/`mp05-form-prompt-2`로, R2가 `mp06-r2-2`/`mp06-r2-prompt-2`로, 조립이
`mp05-compose-2`로 바뀌어도 `section_form` 버전은 `@9f0d2e9bcb33c26d`에 머물렀다.
**결과 의미를 바꾸는 변경이 승인 단위 버전을 바꾸지 못한 것**이 결함이다.

**한 줄 결론.** 구성 버전을 만드는 **단일 원천**(`app/preview/version_manifest.py`)을 두고,
실행과 승인 후보가 모두 그 원천을 쓴다. 실제 실행 단계(자료 준비 D0 · 조사 모듈 · 본문
조립 compose_body)의 **실제 버전 상수**로 계산하므로, 의미가 바뀌면 버전이 바뀐다.
저장된 옛 결과는 옛 버전을 그대로 보존했고, 새 후보만 새 버전으로 추가했다.

## 1. 실행 환경

| 항목 | 값 |
|---|---|
| 에이전트 모델 | hive / `deepseek-ai/deepseek-v4.1-flash-1017`, `reasoningEffort=max` |
| 프로필 | `dsh-tui` |
| 모델 호출 / API-Football 호출 | **0회 / 0회** (`vertex` 시도 총계 3건 그대로) |
| 승인 행 | **0건** (에이전트가 만들지 않음) |

## 2. 원인 (확인한 코드 경로)

```
runner.section_workflow_version(workflow)
  → ConstituentVersion(module_id, prompt_version="", implementation_version="",
                       contract_version=MODULE_INPUT_VERSION)   ← 자리표시자
  → approvals.release_version(...)  → sha256(...)[:16]
```

`release_version`은 버전 축을 그대로 해시한다. 자리표시자를 넣으면 축이 상수가 되어
모듈 버전을 올려도 해시가 변하지 않는다. 실측으로 확인했다.

| 계산 | 값 |
|---|---|
| 자리표시자(수정 전 실행 기록) | `section_form@9f0d2e9bcb33c26d` |
| 실제 구성(수정 후) | `section_form@dff5ef9da8f20f8a` |

## 3. 수정 (최소)

### 3.1 단일 버전 원천

새 파일 `app/preview/version_manifest.py`가 구성 목록을 만든다.

- 조사 모듈: `modules.module_versions()`가 소유한 **(구현, 프롬프트)** — 모듈 파일의
  자기 상수를 그대로 쓴다. 여기에 문자열을 복사하지 않는다.
- 자료 준비(D0): `sections.STORED_DATA_IMPLEMENTATION_VERSION`
- 본문 조립: 섹션별 상수(`FORM_COMPOSE_IMPLEMENTATION_VERSION`,
  `availability.COMPOSE_IMPLEMENTATION_VERSION`, `OUTLOOK_COMPOSE_IMPLEMENTATION_VERSION`)
- 계약 버전: 실제 `CONTRACT_VERSION`

값은 **코드 상수에서만** 온다. 프로세스 상태·현재 시각·경기 ID·무작위 해시·Git HEAD를
쓰지 않는다. 표시 문구만 바뀌는 변경은 이 축에 영향을 주지 않는다.

### 3.2 실행과 승인이 같은 원천을 쓴다

| 지점 | 수정 |
|---|---|
| `runner.section_workflow_version` | `version_manifest.constituents_for_workflow()` 사용 |
| `approvals._current_constituents` | 같은 함수 사용(저장 결과 역산 중단) |
| `approvals._constituents_from_results` | 같은 모듈 집합을 쓰되, 저장된 실행 값이 있으면 그 값을 우선 |

즉 **지금 코드로 실행하면 남을 버전**과 **승인 후보가 보여주는 버전**이 같은 계산이다.
검증: `section_form`·`section_availability`·`section_outlook` 셋 다 실행/승인 값 일치.

### 3.3 재검증 후보는 현재 버전으로

`revalidate_section_from_stored_response`가 이전 섹션 결과의 `workflow_version`을
물려받던 것을 고쳤다. 새 후보는 `version_manifest.workflow_version_of()`로 계산한
**현재 구성 버전**을 단다. 옛 실행 버전을 새 코드 결과에 붙이지 않는다.
(`recompose_section_body`는 옛 실행 본문만 다시 조립하는 경로라 기존대로 둔다.)

## 4. 검증 (대표 사례만)

`.venv/bin/python -m pytest tests/preview/test_workflow_version.py tests/preview/test_section_approvals.py tests/preview/test_form_module.py tests/preview/test_module_runner.py tests/preview/test_availability_module.py tests/preview/test_outlook_module.py -q`
→ **95 passed**

새 파일 `tests/preview/test_workflow_version.py`의 4건:

| 검사 | 확인 내용 |
|---|---|
| `test_manifest_uses_real_versions_not_placeholders` | 구성에 D0·R1·compose_body가 모두 있고, R1의 프롬프트/구현 버전이 실제 값이다(빈 문자열 아님) |
| `test_same_manifest_is_stable_and_shared_by_execution_and_approval` | 같은 코드면 실행/승인 버전이 같고 안정적이다 |
| `test_semantic_version_change_alters_candidate` | R1 프롬프트·R1 구현·조립 구현·D0 구현·출력 계약 중 **하나만** 바뀌어도 후보 버전이 바뀐다 |
| `test_old_result_versions_do_not_become_the_current_candidate` | 옛 실행 버전은 현재 후보와 다르고, 현재 후보를 덮어쓰지 않는다 |

추가로 실행 경로 검사(`test_form_section_workflow_runs_with_live_style_implementations`)에
**저장된 `workflow_version`이 실제 구성으로 계산한 값과 같은지**를 넣었다.
이 검사는 자리표시자 동작으로 되돌리면 실제로 실패하는 것을 확인했다.

```
자리표시자로 임시 되돌림 → AssertionError:
  assert 'section_form...d2e9bcb33c26d' == 'section_form...5ef9da8f20f8a'
수정 복구 → 1 passed
```

`test_module_runner.py`의 승인 경로 검사도 고쳤다. 기존 검사는 구성이 `["D0","R1"]`이라고
단정했는데, 본문 조립은 **실제로 실행되는 결과 축**이므로 구성에 포함되는 것이 맞다.
이 검사는 이제 (a) 구성이 `D0·R1·compose_body`이고 (b) 승인 기록이 그 실행의 실제
버전(`test-*`)을 가리키며 (c) 테스트용 옛 버전 결과를 승인했을 때 현황이 `SUPERSEDED`로
보여 **새 버전 확인을 요구**하는 것까지 확인한다.

전체 296건·프론트엔드 빌드·브라우저 검사는 백엔드 로직 변경이라 실행하지 않았다.

## 5. 저장 결과: 옛 이력 보존 + 새 후보

| 실행 | 버전 이력 | 비고 |
|---|---|---|
| baseline `6e59041a` | v1~v4 `@9f0d2e9bcb33c26d` (502/454/442/885자) | **옛 기록 그대로** |
| | **v5 `@dff5ef9da8f20f8a`** 885자 | 새 후보(현재 구성) |
| candidate `7c0af3c0` | v1~v3 `@9f0d2e9bcb33c26d` (528/455/878자) | **옛 기록 그대로** |
| | **v4 `@dff5ef9da8f20f8a`** 878자 | 새 후보(현재 구성) |

- 옛 `@9f0d2e9bcb33c26d` 행은 **다시 쓰지 않았다**. 일괄 backfill도 하지 않았다.
- 본문 외부 호출 **0회**: 저장된 원문 응답과 저장된 D0 사실만 다시 검증·조립했다.
- fact/judgment 개선은 그대로 유지된다: baseline **관전 2 / 선수 3**, candidate
  **관전 3 / 선수 3**. (수치는 재조립 후에도 동일하며, 없는 값을 만들어 채우지 않았다.)

## 6. 바꾼 경로

| 경로 | 내용 |
|---|---|
| `app/preview/version_manifest.py` | **신규** 구성 버전 단일 원천 |
| `app/preview/runner.py` | 자리표시자 → 원천 사용 |
| `app/preview/approvals.py` | 현재 구성·실행 구성 모두 원천 기준 |
| `app/preview/sections.py` | D0/아웃룩 조립 버전 상수화, 재검증 후보가 현재 버전 사용 |
| `tests/preview/test_workflow_version.py` | **신규** 대표 4건 |
| `tests/preview/test_form_module.py` | 실행 버전이 실제 구성값인지 확인 |
| `tests/preview/test_module_runner.py` | 승인 구성/버전 기대값 정정 |
| `docs/implementation/match-preview/workflow-version-fix-report.md` | 이 보고 |
| `docs/implementation/match-preview/evidence/workflow-version/evidence.json` | 전/후 버전·구성·이력 증거 |

스키마·마이그레이션 변경 **없음**. 기존 승인 표의 버전 메타데이터로 충분했다.

## 7. 남은 한계 (정직하게)

1. **옛 실행의 버전은 여전히 `@9f0d2e9bcb33c26d`다.** 그것이 그 실행의 역사다. 지금
   그 옛 결과를 승인하면 승인 현황은 `SUPERSEDED`로 보여 새 버전 확인을 요구한다
   (검사로 고정). 옛 행을 새 버전으로 바꾸지 않았다.
2. **`compose_body`가 구성에 정식으로 들어왔다.** 이전 승인 기록(있다면)은 `D0·R1`만
   담고 있었을 수 있다. 현재는 승인 0건이라 실제 영향은 없지만, 그런 기록이 생기면
   버전이 달라 보이는 것이 정상 동작이다(구성이 늘었으므로).
3. **`recompose_section_body`는 옛 버전을 유지한다.** 그 경로는 "옛 실행 본문을 다시
   조립"하는 것이지 새 검증이 아니므로 실행 정체성을 바꾸지 않았다.
4. **백엔드 8000 재시작이 필요하다.** 이 변경은 런타임 코드다. 재시작 전에는 실행
   기록·승인 후보가 새 버전으로 바뀌지 않는다. 재시작은 조정자가 결정한다(내가
   건드리지 않았고, 8000·5173 모두 정상 응답).
5. 프론트엔드 변경 없음 → 5173 재시작 불필요.
