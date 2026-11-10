# F2/F3 수정 보고 (재검증 기록·승인 버전 연결)

작성: 2026-11-11 KST. 작성자: DeepSeek 구현 워커(`hive`/`deepseek-ai/deepseek-v4.1-flash-1017`,
추론 강도 `max`, 프로필 `dsh-tui`). 하위 워커 없음.
상태: **F2/F3 코드 수정 + 회귀 검사 통과. 실제 모델·API-Football 호출 0회. 편집 종료(§8).**

이 보고는 독립 검토 [r1-boundary-review.md](r1-boundary-review.md)의 **F2·F3만** 다룬다.
F1(R1 판단 문장의 축약 전제)은 이 작업 범위가 아니며 별도 워커 소유다. MP-09 S1 구현은
`f97f5cd`의 상태를 그대로 입력으로 썼고 다시 구현하지 않았다.

## 0. 한 줄 요약

재검증(`revalidate_section_from_stored_response`)이 **덜어낸 사실·사유를 문장 목록으로
저장**하고 **버전이 붙은 R1 검증 결과 행과 provenance**를 남기게 했고, 승인
(`approve_section_version`)이 **검토한 섹션 결과 행이 실제로 남긴 구성**을 쓰게 했다.
그래서 최신 후보 본문을 승인하면 승인 기록이 `section_form@dff5ef9da8f20f8a`로 남고
곧바로 SUPERSEDED가 되지 않는다. 옛 본문·옛 승인·현재 후보 계산은 그대로 분리했다.

## 1. 검토 지적과 수정 대응

| 지적 | 검토가 지목한 지점 | 실제 원인(내가 확인) | 수정 |
|---|---|---|---|
| **F2-1** 섹션 진단이 글자 배열로 저장 | `sections.py:868` 재검증의 `diagnostics=(...)` | 괄호 안 문자열 연결에 **튜플 쉼표가 없어** `str`이 되고, `store.save_section_result`의 `[str(item) for item in diagnostics]`가 글자마다 펼침 | `_section_revalidation_diagnostics(...)`가 **튜플**을 돌려주고, 문장마다 한 항목으로 저장 |
| **F2-2** 덜어낸 사실·사유가 실행 기록에 남지 않음 | `sections.py` 재검증 경로가 `validated.diagnostics`를 메모리에만 둠 | 재검증이 모듈 결과 행을 쓰지 않아 R1 행이 옛 버전에 머묾 | 재검증이 **새 R1 결과 행**(버전 올라간 행)을 저장하고 검증 진단을 그 행에 남김 |
| **F2-3** 검증 결과 provenance 없음 | (검토 지적의 직접 요구) | 어느 원문을 어떤 구현으로 다시 해석했는지 기록 없음 | `provenance`(원문 아티팩트·시도·원본 결과·원문 프롬프트/구현·검증 구현)를 R1 결과 payload에 남김 |
| **F3** 승인 버전이 검토 본문과 다름 | `approvals.py:408` `_constituents_from_results(...)` | 승인 버전을 **실행의 저장 모듈 행**에서 다시 계산 → 재검증은 모듈 행을 쓰지 않으므로 옛 버전(`@bf3b…`/`@7a18…`)이 남음 | 승인이 **검토한 섹션 결과 행이 남긴 구성(manifest)** 을 우선 사용하고 스탬프도 그 행의 값을 씀 |

## 2. 정확한 소스 변경

수정 파일(내 소유): `app/preview/sections.py`, `app/preview/approvals.py`,
`app/preview/modules/__init__.py`(F1 인계 뒤 R1 구현 버전 등록), 공유 버전 검사
`tests/preview/test_workflow_version.py`(고정 문자열 → 실제 상수 대조).
신규 검사: `tests/preview/test_f2_f3_revalidation_approval.py` (7건).
스키마 변경·마이그레이션·DDL **없음**. 기존 표·열만 사용했다.

### 2.1 `app/preview/sections.py` — 재검증이 기록을 남긴다

- `revalidate_section_from_stored_response`가 새 R1 결과 행과 새 `compose_body` 결과 행을
  만든다. 두 행은 **새 모듈 실행**(순번 이어감)에 속하므로 옛 행을 고치지 않는다.
- 섹션 결과의 `result_ids`/`module_execution_ids`가 **이번 재검증이 만든 행**을 가리킨다.
- R1 결과 payload에 다음을 남긴다.
  - `payload`: 새 규칙으로 다시 해석한 조사 payload
  - `diagnostics`: 제외 사유 + 덜어낸 사실 + 내려놓은 전제 + 불확실성 (문장 목록)
  - `provenance`: 아래 §4의 분리 기록
  - `manifest` / `workflow_version`: 이 후보를 만든 구성 집합과 그 스탬프
- `_revalidation_diagnostics()`가 `validated.diagnostics`·`dropped_facts`·
  `unasserted_premises`·`uncertainties`를 **중복 없이 한 문장씩** 모은다.
- `_section_revalidation_diagnostics()`가 재검증 사실 문장 + 위 사유들을 **튜플**로 준다
  (F2의 직접 원인 제거).
- `_next_execution_ordinal()`, `_fixture_from_payload()` 보조 함수 추가.

### 2.2 `app/preview/approvals.py` — 승인이 검토 본문에 붙는다

- `_reviewed_constituents(workflow, section_row, rows)` 추가.
  - 검토한 섹션 결과가 **자기 manifest를 남겼으면**(재검증 후보) 그 구성을 그대로 쓴다.
  - 남기지 않은 예전 결과는 그 결과가 **실제로 가리키는 모듈 행**에서 계산한다.
- `_stored_payload()`: 저장 행 payload가 `ModuleResult.to_dict()`로 한 겹 감싸인 것을 푼다.
- `approve_section_version`은 위 결과를 쓰고, 자기 manifest가 있는 경우 **버전도 그 행의
  스탬프**를 쓴다. 현재 코드로 다시 계산해 다른 버전을 적지 않는다.
- 쓰이지 않게 된 `_constituents_from_results`는 삭제했다(호출자 0).

## 3. 대표 확인 (실행한 명령과 결과)

```sh
# 이 작업의 회귀 검사 (전용 loopback DB preview_f2f3_test)
.venv/bin/python -m pytest tests/preview/test_f2_f3_revalidation_approval.py -q
#   7 passed

# 영향을 받는 연결 경로 (승인·버전·검사·표현)
PREVIEW_TEST_DATABASE_URL=...preview_mp05_test \
.venv/bin/python -m pytest tests/preview/test_module_runner.py tests/preview/test_workflow_version.py \
  tests/preview/test_section_approvals.py tests/preview/test_run_store.py -q
#   34 passed
PREVIEW_TEST_DATABASE_URL=...preview_mp05_test \
.venv/bin/python -m pytest tests/preview/test_inspection_api.py tests/preview/test_presentation.py -q
#   30 passed
```

수정 전 같은 회귀 검사(소스 변경 전)는 **5 failed / 2 passed**였고, 대표 실패 문구는 검토
보고와 같은 형태다.

```text
# F2 (수정 전 실측)
AssertionError: 진단이 글자 배열로 저장됐다: ['저', '장', '된', ' ', '원', '문', ' ', '응', '답', '을']

# F3 (수정 전 실측)
AssertionError: assert 'mp05-form-1-nomime-1' != 'mp05-form-1-nomime-1'
  where ConstituentVersion(module_id='R1', implementation_version='mp05-form-1-nomime-1', ...)
```

## 4. 진단·승인 기록의 before/after

### 4.1 진단 (F2)

| | 수정 전 | 수정 후 |
|---|---|---|
| 저장 형태 | 문자열 1건이 글자로 펼쳐짐: `["저","장","된"," ",...]` | 문장 목록: `["저장된 원문 응답을 새 사실/판단 검증 규칙으로 다시 해석했습니다(외부 호출 0회). …", "관전 포인트 1: 확인되지 않은 사실 조각 1개를 덜어냈습니다: …", ...]` |
| 덜어낸 사실 사유 | 실행 기록에 없음 | R1 결과 행 `diagnostics` + 섹션 결과 `diagnostics`에 남음 |
| 검증 결과 행 | 없음(옛 R1 행만) | 새 R1 행(새 모듈 실행·버전) + provenance |

### 4.2 승인 버전 (F3)

검토 보고 §2.2의 실측 표를 같은 입력으로 재계산해 확인했다.

| 대상 | 승인 시 기록되는 버전 |
|---|---|
| 수정 전, 기준 `6e59041a` v5 (옛 모듈 행 계산) | `section_form@bf3b6e2ba968e123` |
| 수정 전, 후보 `7c0af3c0` v4 (옛 모듈 행 계산) | `section_form@7a18bceabdf61629` |
| **수정 후, 검토한 최신 후보 본문 승인** | **그 섹션 결과 행이 가진 스탬프 그대로**(아래 최종 manifest) |

수정 후에는 승인 직후 `section_approval_status`가 **APPROVED**이고, 옛 본문을 승인하면
그 본문의 옛 버전이 남아 **SUPERSEDED**로 표시된다(의도한 구분 유지).

F1 인계 뒤 등록한 R1 구현 버전(`mp05-form-3`, 프롬프트는 `mp05-form-prompt-2` 유지)으로
 현재 manifest를 다시 유도한 값은 다음과 같다. 해시는 코드에 적지 않고
`version_manifest.workflow_version_of("section_form")`로 계산해 확인했다.

```text
section_form@3721e7df4a7f6a61
  D0          prompt=""                  impl="mp05-stored-d0-1"
  R1          prompt="mp05-form-prompt-2" impl="mp05-form-3"
  compose_body prompt=""                  impl="mp05-compose-2"
```

## 5. provenance 한계와 정직성 구분

- **원문 생성과 재검증은 다르다.** 원문 문장은 **옛 프롬프트**가 만들었고, 채택/제외 판정과
  본문 조립은 **지금 구현**이 했다. 그래서 R1 결과 행의 `prompt_version`에는 **원문을 만든
  옛 프롬프트**를, `implementation_version`에는 **지금 검증 구현**을 적었다. 새 프롬프트를
  보낸 것처럼 바꾸어 적지 않았다.
- `provenance.kind = "revalidated_from_stored_response"`, `external_calls = 0`,
  `source_artifact_id`/`source_attempt_id`/`source_result_id`로 **어느 원문을** 다시
  해석했는지 가리킨다.
- 재검증 후보의 **섹션 스탬프는 현재 코드 구성**이다. 그 본문을 실제로 만든 검증·조립
  구현이 현재 코드이기 때문이다. 원문 프롬프트가 옛 값이라는 사실은 위 R1 행과
  provenance에 남긴다. 즉 "본문을 만든 현재 구성"과 "원문을 만든 옛 프롬프트"를 한 값에
  섞지 않는다.
- **한계:** 재검증은 새 모델 응답이 아니므로 원문 프롬프트 버전을 현재 값으로 올릴 수
  없다. 승인 기록은 본문 기준 구성(현재 코드)을 가리키고, 원문 프롬프트 이력은 R1 행에
  남는다. 이 둘을 한 필드로 합치지 않았다.

## 6. 스키마·데이터 경계

- 새 표·열·마이그레이션 **없음**. 기존 `preview_results`(R1·compose 행),
  `preview_section_results`(result_ids·diagnostics), `preview_write_audit`만 사용했다.
- 옛 본문·옛 원문·옛 승인 행은 **수정·삭제하지 않았다**(backfill 없음).
- 승인 행은 **전용 loopback DB `preview_f2f3_test`** 에서만 만들었다. 실제/공용 DB에
  승인 행을 만들지 않았다. 검사 픽스처는 `public` 스키마를 만들거나 지우지 않고
  `preview_dev` 스키마만 준비한다.

## 7. 하지 않은 것 / 남은 것

- **F1 미수정.** R1 판단 문장의 축약 전제(form.py)는 이 작업 범위가 아니다.
  `app/preview/modules/form.py`·`form.md`·직접 `compose.py`·`test_form_module.py`는
  F1 소유이며 이 커밋에 넣지 않았다.
- **R3 시계 관련 기존 실패는 그대로.** `tests/preview/test_outlook_module.py`의 실패는
  `45b442a`에서도 동일하며 R3 소유 파일이다. 이번 범위에서 고치거나 확장하지 않았다.
  **기존 gap으로 기록**한다.
- **서버 재시작 필요.** 실행 중인 `127.0.0.1:8000` 백엔드는 수정 전 코드를 싣고 있다.
  전용 스크립트로 **1회 재시작**이 필요하며, 내가 8000/5173을 건드리지 않았다.
- live S1/MP-10/새 API 범위는 열지 않았다.

## 8. 편집 종료

F2/F3 파일 편집을 멈춘다. 추가 지시가 있으면 조정자가 새 작업으로 배정해야 한다.
