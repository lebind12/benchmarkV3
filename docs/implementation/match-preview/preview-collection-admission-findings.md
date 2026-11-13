# PC-LIVE 승인 판정 불일치 조사 (읽기 전용)

작성: DeepSeek 조사 워커, 2026-11-13 05:26 KST. 모델 `deepseek-ai/deepseek-v4.1-flash-1017`, 추론 강도 `max`.
성격: **읽기 조사**다. 제품·검사·설정 파일을 수정하지 않았고, 인라인 Python 실행·테스트·
실제 DB/API/모델·서버·승인 POST도 하지 않았다. 편집한 파일은 이 보고서 하나다.

표기 구분: **[확인]** 코드/파일에서 직접 읽은 사실, **[추론]** 확인 사실에서 이어지는 해석,
**[미확인]** 이번에 실행·조회하지 않아 모르는 것.

입력: 조정자가 관측한 05:20~05:22 KST 실측(아래 "관측" 절)과 현재 소스.

## 조정자 관측(요약, 실측값)

- API PID13279는 새 경로 미반영, `preview-test`가 openapi에 없음. 개발 런처
  `scripts/run_benchmark_dev.sh`의 `HOME_PREVIEW_ENABLED` 기본값은 `false`.
- target13 활성·EPL2026·상세/선수/순위 true·`fixture_limit=null`. 두 경기 모두 NS,
  `2026-11-21T15:00:00Z`.
- `GET /api/v1/admin/preview/admission`: `ready=false`,
  `missing_approval=[section_form, section_availability, section_outlook, section_players, section_synthesis]`,
  `stale_approval=[]`.
- `GET approvals`: `section_odds`만 active. `availability/outlook/players/ai_forecast`는
  `pinned_approval`이 있고 `superseded`. `section_form/synthesis`에는 승인 기록이 없다.
- pinned 4건과 current_constituents가 모듈 `contract_version`에서 다름:
  승인 근거는 `mp04-section-result-1`, 현재 manifest는 `mp02-1`. 표시되는
  `implementation_version`/`prompt_version`은 동일했다.

---

## 질문 1. 수집 승인 판정이 실제 생성 섹션 집합과 일치하는가

**불일치한다. [확인]**

- 승인 판정은 `app/preview/pipeline.py:185-187`의 `required_workflows()`를 쓴다. 이 함수는
  `SECTION_WORKFLOW_IDS + (synthesis.SECTION_WORKFLOW_ID,)`를 돌려준다.
- `SECTION_WORKFLOW_IDS`(`app/preview/pipeline.py:97-102`)는
  `section_form, section_availability, section_outlook, section_players`다.
  여기에 `section_synthesis`가 더해진다. 그래서 판정 대상은 5개이고 form·synthesis가 포함된다.
- 실제 공통 생성 서비스(`match_preview.generate_match_preview` →
  `bundle_pipeline.run_bundle_pipeline`)가 만드는 섹션은
  `bundle_contract.SECTION_IDS`(`app/preview/information_bundle.py:238-244`)다:
  `players, availability, outlook, odds, ai_forecast`. **form·synthesis가 없고 odds가 있다.**
- `admission_state()`는 `required_workflows()`만 순회한다
  (`app/preview/pipeline.py:190-215`). 따라서 실제로 만들지 않는 `section_form`,
  `section_synthesis`의 승인이 없다는 이유로 `ready=false`가 된다. 관측된
  `missing_approval` 5건 중 2건이 이 경우다.
- 반대로 실제로 만드는 `section_odds`는 판정 대상이 아니다. 관측에서 odds만 active인데도
  판정에 반영되지 않았다.

**호출 근거(어디서 이 판정을 쓰는가) [확인]**

`required_workflows`/`admission_state`의 소비자는 셋뿐이다.

1. `app/api/v1/preview_admin.py:1932` — 실행 응답에 `state`로 첨부.
2. `app/api/v1/preview_admin.py:2059-2066` — `GET /admission` (관측이 호출한 경로).
3. `app/services/home_preview_collection.py:454-457` — 수집 종료 훅의 **생성 전 게이트**.

즉 수집 경로의 실제 차단은 3번이다. `bundle_pipeline.py`에는 `admission` 참조가 **0건**이므로
생성 엔진 자체는 이 판정을 하지 않는다. 차단은 순전히 수집 경계(`home_preview_collection`)가
`admission_state`를 호출해서 생긴다.

**최소 수정 위치 (제안만, 실행하지 않음)**

`app/preview/pipeline.py`에 bundle 섹션 집합으로 판정하는 함수를 **하나 추가**하고,
수집 경계의 호출만 그 함수로 바꾼다.

- 새 함수는 `bundle_contract.SECTION_IDS`(또는 `version_manifest.BUNDLE_WORKFLOW_IDS`)를
  순회해야 한다. 실제 생성 집합과 같은 출처를 써야 다시 어긋나지 않는다.
- `required_workflows()`와 기존 `admission_state()`는 **그대로 둔다**. 관리자 화면의
  "기본 전체 프리뷰" 의미와 옛 파이프라인 경로가 그것을 쓰고 있고, 이번 조사 범위에서
  그 의미를 바꿀 근거가 없다.
- 호출부 변경은 `home_preview_collection.py`의 한 곳.

**사용자 승인 의미에 미치는 영향**: 이 수정은 승인 행을 만들지도 바꾸지도 않는다. 다만
"무엇을 승인해야 준비된 것인가"라는 **판정 대상 집합**을 실제 생성물과 맞추는 일이다.
그래서 이미 받은 승인(맨시티 문서 저장 버전)의 효력은 그대로이고, 대신 `section_odds`
승인이 판정에 포함되기 시작한다.

**주의(중요) [확인]**: 이 수정만으로 `ready=true`가 되지는 않는다. 관측대로
availability/outlook/players 세 pinned 승인은 `superseded`이고, odds만 active다.
bundle 집합으로 바꿔도 `section_odds` 외 4개(players/availability/outlook/ai_forecast)는
여전히 `approved`가 아니다. 즉 질문 1의 수정은 "없는 것을 요구"하는 오류를 없애는 것이지
승인 부족 자체를 해소하지 않는다.

---

## 질문 2. pinned 승인의 contract_version 차이는 의미 변경인가

**같은 실행의 계약을 서로 다르게 계산한 것이다. 결과 의미 변경이 아니다. [추론]**

확인한 사실:

- 저장된 섹션·모듈 결과는 `SECTION_RESULT_CONTRACT_VERSION = "mp04-section-result-1"`로
  스탬프된다(`app/preview/contracts.py:35`). bundle 경로도 `ModuleInput`에 이 값을 넣는다
  (`app/preview/bundle_pipeline.py:452-473`).
- 승인 구성은 **저장 행에서** 읽는다: `_reviewed_constituents`가
  `row.contract_version or expected.contract_version`을 쓴다
  (`app/preview/approvals.py:203`). 그래서 승인 기록에는 `mp04-...`가 남았다.
- 현재 manifest는 모든 모듈 항목에 `CONTRACT_VERSION = "mp02-1"`을 넣는다
  (`app/preview/contracts.py:28`, `app/preview/version_manifest.py:161,174`).
  **모듈별 실제 계약이 아니라 전역 상수 하나를 쓴다.**
- 두 값은 서로 다른 축을 이름으로 갖는다. `mp02-1`은 원래 파이프라인 계약,
  `mp04-section-result-1`은 섹션 결과 축으로 **나중에 추가된 별도 상수**다
  (`contracts.py:33` 주석: "MP-04가 더한 축. 기존 값은 바꾸지 않고 새 이름만 추가한다").
- `release_version`은 `workflow.output_contract_version`과 구성 요소 버전 문자열을 해시한다
  (`approvals.py:82-105`). 그래서 contract_version 한 축이 달라지면 버전 문자열이 달라지고
  상태가 `superseded`가 된다.

[추론] 즉 이 차이는 **결과를 실제로 만든 축(저장 행 = mp04)** 과 **지금 코드가 스스로
계산한 축(manifest = mp02)** 이 다르기 때문이다. 프롬프트·구현 버전이 동일하고
output_contract_version도 그대로라면, 같은 본문을 서로 다른 계약 이름으로 계산한 것이며
결과의 의미가 바뀌었다고 볼 근거는 이번 대조에서 없다. 다만 이것은 **추론**이며, 두 상수의
실제 계약 내용(diff)은 이번에 확인하지 않았다.

**현재 승인을 보존하면서 해결 가능한 최소 변경**

가장 작은 변경은 `version_manifest.constituents_for_workflow`가 모듈 항목의
`contract_version`을 **그 모듈이 실제로 산출/기록하는 축**에서 가져오게 하는 것이다. bundle
워크플로우는 `SECTION_RESULT_CONTRACT_VERSION`을 쓰고(`_bundle_manifest` 분기와 같은 경계),
옛 경로는 지금처럼 `CONTRACT_VERSION`을 유지한다. 그러면 승인 근거와 현재 계산이 같은 축을
비교하게 되어 기존 pinned 승인이 `superseded`로 남지 않는다.

- 파일은 `app/preview/version_manifest.py` **한 곳**이면 된다.
- 승인 행을 새로 만들거나 고치지 않는다. `approvals.py`·`contracts.py`도 건드릴 필요가 없다.

**주의 [확인]**: 이 변경은 `workflow_version_of()` 값(= 버전 문자열)을 바꾼다. 그래서
이미 저장된 `preview_section_approvals.version_hash`와 새 계산값이 달라질 수 있고,
`section_approval_status`가 새 버전을 후보로 보는 경계가 생긴다. 즉 "승인 보존"은
**행을 지우지 않는다**는 뜻이지 "버전이 자동으로 승인된다"는 뜻이 아니다. 실제로
`ready`가 되려면 관리자가 그 버전을 한 번 더 확인하는 절차가 필요할 수 있다. 이번 조사는
그 절차를 자동 승인으로 대체할 수 없다고 본다(사용자 승인 의미 보존).

---

## 질문 3. 새 시험 엔드포인트도 `home_preview_enabled=false`에서 훅이 생략되는가

**생략된다. [확인]**

- `app/services/management_runs.py`의 훅은 두 곳 모두 전역 플래그를 먼저 검사한다:
  - 정상 경로: `if settings.home_preview_enabled:` (`:616` 부근)
  - 상위 예외 경로: `if not preview_started and getattr(get_settings(), "home_preview_enabled", False):`
    (`:654` 부근)
- `start_preview_test_run`은 `start_run(..., test_scope=scope)`로 위임하고
  (`management_runs.py:443-460`), 시험 범위는 payload에 저장되지만 **플래그 검사에는
  관여하지 않는다**. `execute_run`은 `test_scope`를 측정·종료 훅에 전달할 뿐이다.
- 따라서 `HOME_PREVIEW_ENABLED=false`이면 시험 실행도 수집만 하고 **프리뷰 생성을
  호출하지 않는다**. 수집은 정상 종료되고 `home_preview` 키도 생기지 않는다.
- `worker_runs.py`도 같은 구조다(`:265`, `:293`). 다만 새 엔드포인트는 관리 경로를 쓰므로
  시험 요청과 직접 관련은 없다.
- 개발 런처의 기본값이 `false`라는 조정자 관측과 일치한다. **다만 실제 프로세스의 환경값은
  [미확인]이다**(이번에 프로세스 환경을 열지 않았다).

**요청별 시험 의도로 작동하게 할 최소 위치**

두 훅 조건을 "정기 경로는 플래그 존중, 시험 요청은 요청 범위가 있으면 진행"으로 바꾼다.
최소 형태는 조건 하나를 추가하는 것이다.

```text
if settings.home_preview_enabled or test_scope is not None:
```

- 위치는 `management_runs.py`의 두 훅 지점(`:616`, `:654` 부근)뿐이다.
- `test_scope`는 이미 `execute_run` 스코프에 있고 payload에서 복원되므로 새 배선이 필요 없다.
- **정기 경로 보존 조건**: `test_scope`는 `start_preview_test_run`이 만든 실행에만 실린다.
  `start_run`의 기본값이 `None`이므로 일반 수집·정기 스케줄 실행에는 값이 없다. 그래서
  위 조건은 정기 경로의 동작을 바꾸지 않는다.
- 설정 파일·환경 변수는 열거나 바꾸지 않는다. 전역 플래그를 `true`로 켜는 방식은 정기
  경로까지 영향을 주므로 이 요구("정기 경로 보존")에 맞지 않는다.

**주의 [확인]**: 플래그를 우회해도 질문 1·2가 남아 있으면 생성 게이트에서 다시 막힌다.
`test_scope`가 있어도 `_admission`이 `not_ready`를 돌려주면 생성은 시작되지 않고
`approval_not_ready`로 건너뛴다. 그래서 세 질문은 **함께** 해결해야 실제 두 경기 생성에
도달한다.

---

## 수정 최소 파일 요약 (제안, 실행하지 않음)

| 질문 | 최소 파일 | 내용 |
|---|---|---|
| 1 | `app/preview/pipeline.py`, `app/services/home_preview_collection.py` | bundle 섹션 집합으로 판정하는 함수 추가 + 수집 경계의 호출 교체. 기존 `admission_state`/`required_workflows`는 보존 |
| 2 | `app/preview/version_manifest.py` | 모듈 `contract_version`을 bundle 경로에서 `SECTION_RESULT_CONTRACT_VERSION`으로 계산 |
| 3 | `app/services/management_runs.py` | 두 훅 조건에 `or test_scope is not None` 추가 |

**사용자 승인 의미 영향**: 세 변경 모두 승인 행을 자동 생성·변경하지 않는다. 질문 1·3은
"판정 경로"와 "훅 진입 조건"을 고치는 것이고, 질문 2는 비교 축을 맞추는 것이다. 다만 질문 2는
버전 문자열을 바꾸므로, 관리자가 그 버전을 확인하는 절차 없이 `ready`를 만들지 않는다.
새 승인을 자동 생성하는 제안은 하지 않는다.

## 미확인 사항

- [미확인] 실제 프로세스의 `HOME_PREVIEW_ENABLED` 값(조정자 관측은 런처 기본값과 dev 실행
  방식에 대한 것이며, 실행 중 프로세스 환경은 열지 않았다).
- [미확인] `mp02-1`과 `mp04-section-result-1`이 실제로 어떤 계약 차이를 담는지(diff). 이번에는
  두 상수가 서로 다른 축의 이름임만 확인했다.
- [미확인] 질문 2의 최소 변경 적용 후 `section_approval_status`가 각 승인에 대해 어떤 상태를
  낼지(실행 없이 확인 불가).
- [미확인] bundle 섹션 중 `section_odds`가 active 승인일 때 판정에 포함되면 실제로 `ready`에
  얼마나 가까워지는지(나머지 4개가 여전히 필요).

## 하지 않은 것

범용 승인 엔진 설계, 모든 경로 재설계, 새 테스트·재현 도구 구현, 실제 DB/API/모델 호출,
승인 POST, 설정·환경 변경. 같은 원인에 필요한 호출 계약까지만 읽고 종료한다.

`EDITING STOPPED`. 백그라운드 작업 0건.
