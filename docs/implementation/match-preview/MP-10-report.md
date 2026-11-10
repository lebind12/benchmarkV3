# MP-10 전체 프리뷰 통합·재개 보고

작성: 2026-11-11 04:30 KST. 작성자: DeepSeek 구현 워커
(`hive` / `deepseek-ai/deepseek-v4.1-flash-1017`, 추론 강도 `max`, 프로필 `dsh-tui`). 하위 워커 없음.
커밋: `3c8a479`, `a45599c`, `de4bf00`. 상태: **기반·이름·R1/R4 분리 통합 완료.**

## 1. 한 줄 결과

전체 프리뷰가 **LangGraph 그래프**로 D0→(R1‖R2‖R3‖R4)→V0→S1→V1을 실제로 돌고, 작업 상태를
`preview_dev.preview_pipeline_runs`에 남겨 **재개**가 성공한 조사를 다시 호출하지 않습니다.
정상 경로 모델 호출은 **5회**(조사 4 + 종합 1, 총 상한 8), 갈래는 실제로 동시에 돌며,
예산은 **하나**입니다. 모델·API-Football 전송은 **0회**(기록 transport만 사용)입니다.

R1은 **경기력 전용**이고, 주목 선수 선정은 새 **R4/`section_players`** 가 맡습니다. 화면에는
`selected_player`(선정 선수)와 `selection_reason`(선정 이유)이 분리돼 나옵니다. 팀·선수
표시 이름은 DB의 한국어 값을 씁니다(§7).

## 2. 무엇을 만들었나

| 파일 | 역할 |
|---|---|
| `app/preview/pipeline.py` | 그래프 조립, 노드 어댑터, `start_preview_run`/`resume_preview_run`/`rerun_module`/`resynthesize_preview`/`rerun_preview` |
| `app/preview/jobs.py` | 작업 소유(임차)·울타리 토큰·중복 방지 키·진행/예산 저장 |
| `app/preview/checkpoints.py` | 공식 `PostgresSaver`를 `preview_dev`로 한정하는 어댑터 |
| `app/preview/models.py` | `PreviewPipelineRun` 표 추가 |
| `alembic/versions/0005_pipeline_runs.py` | 개발 스키마 전용 마이그레이션(공용 체인에서 실행 시 거부) |
| `app/preview/retry.py` | `RunBudget.restore/persistable`, 예산 잠금, `ConcurrencyLimiter` |
| `app/preview/runner.py` | `run_module(..., state=...)` — 앞 단계 산출(D0)을 노드에 전달 |
| `app/api/v1/preview_admin.py` | `POST /runs`, `/runs/{id}/resume`, `/module-reruns`, `/synthesis-runs`, `GET /admission` |
| `tests/preview/test_pipeline.py`, `test_resume.py` | 대표 사례 20건 |

기존 R1/R2/R3/S1 구현은 **입력으로만** 썼습니다. 문장 생성·근거 판정 규칙을 이 작업에서
다시 만들거나 넓히지 않았습니다.

## 3. 예산·동시성

| 항목 | 값 | 확인 |
|---|---|---|
| 정상 모델 호출 | 조사 4(R1·R2·R3·R4) + 종합 1 = **5** | `NORMAL_MODEL_CALLS` |
| 모델 요청 상한 | 8(재시도 포함) | `MODEL_REQUEST_BUDGET` |
| 논리 호출 시도 상한 | 3 | `MAX_ATTEMPTS_PER_CALL` |
| API 요청 상한 | 24 | `API_REQUEST_BUDGET` |
| 모델/API 동시 | 2 / 2 | `ConcurrencyLimiter` |
| 기한 | 1800초 | `RUN_DEADLINE_SECONDS` |
| 요청 상한 | 모델 300초 / API 30초 | 기존 값 유지 |

- 갈래 셋이 **같은 `RunBudget` 하나**를 씁니다. 갈래마다 예산을 새로 만들지 않습니다.
- 판정과 차감을 한 잠금 안에서 처리합니다. 동시에 통과 판정을 받고 함께 차감해 상한을
  넘기는 일을 막습니다.
- 실제 전송·재시도·시도 기록은 기존 `provider.execute_request` 하나가 그대로 소유합니다.
  노드나 SDK에서 재시도를 겹쳐 켜지 않았습니다.

## 4. 재개·중복·울타리

| 동작 | 결과 |
|---|---|
| 진행 중 같은 경기·버전 조합 요청 | 기존 실행에 **붙음**(새 호출 0) |
| `explicit_rerun` | 새 실행 ID, 옛 실행 보존, `rerun_of_run_id` 기록 |
| 재개 | 저장된 **남은 예산**으로 미완료 단계만. 성공한 조사는 재호출 안 함 |
| 오래된 실행자의 진행 저장 | 거부(`fencing_token` 불일치) |
| 오래된 실행자의 종료 확정 | 거부 |
| 한 갈래 실패 | 성공한 다른 갈래 결과 유지 |
| 전송 후 응답 미보존 | `unknown`으로 저장, 성공으로 세지 않음 |

재개 검사에서 실제로 확인한 것: 첫 실행이 남긴 성공 R1 결과는 재개 때 **다시 호출되지
않고**(`R1-form` 호출 없음), 실패했던 갈래만 남은 예산으로 다시 시도합니다.

## 5. 승인 게이트

- 기본(`admission=approved`)은 **필요한 섹션이 모두 승인**되어 있고 **승인된 버전이 지금
  코드 구성과 같아야** 실행합니다. 아니면 `409`와 함께 빠진 섹션·현재/승인 버전을 돌려주고,
  정상 완료로 표시하지 않습니다.
- `admission=admin_preview`는 승인 없이 실행되지만 응답·기록 라벨이 "승인 근거 아님"입니다.
- 승인 행은 이 작업에서 **만들지 않습니다**(검사에서 0건 확인). 공개 엔드포인트도 열지 않았습니다.

## 6. 검증 (실제 실행한 것)

```sh
# 이 작업의 전용 loopback DB (preview_mp10_test)
.venv/bin/python -m pytest tests/preview/test_pipeline.py tests/preview/test_resume.py -q
#   22 passed

# R1 모듈(분리 후)
.venv/bin/python -m pytest tests/preview/test_form_module.py -q
#   21 passed

# 영향을 받는 연결 경로
.venv/bin/python -m pytest tests/preview/test_form_module.py tests/preview/test_synthesis.py \
  tests/preview/test_presentation.py tests/preview/test_section_approvals.py \
  tests/preview/test_workflow_version.py tests/preview/test_module_runner.py \
  tests/preview/test_retry_budget.py tests/preview/test_f2_f3_revalidation_approval.py \
  tests/preview/test_run_store.py tests/preview/test_inspection_api.py \
  tests/preview/test_localized_names.py -q
#   148 passed

npm --prefix frontend run type-check     # clean
```

측정된 값: 정상 경로 전송 **5회**(`R1-form`, `section_availability/research-r2`,
`R3-outlook`, `section_players/research-r4`, `section_synthesis/research-s1`), 갈래 전송 구간
**겹침 확인**, 예산 `model_used=5`, `model_remaining=3`.

> 중간 단계의 4회 측정은 R4가 붙기 전(조사 3 + 종합 1) 경로의 값입니다. R4 통합 후 목표인
> **조사 4 + 종합 1 = 5회**와 섞지 않습니다.

부수 확인: 이 기록 입력에서 `section_form`·`section_players`·`section_synthesis`는 본문이
만들어졌고, `section_availability`·`section_outlook`은 **근거가 없어 본문을 만들지
않았습니다**. 저장 자료에 부상·배당 자료가 없기 때문이며, 선택 항목 누락만으로 실행 전체를
실패로 만들지 않는 기존 기준과 같습니다. `section_players` 본문은 `선정 선수:`/`선정 이유:`
를 분리해 냅니다.

## 7. 스키마·DB 경계

- 새 표는 `preview_dev.preview_pipeline_runs` **하나**입니다. `public` DDL은 0입니다.
- 마이그레이션은 `scripts/preview_dev_migrate.py`가 명시적으로 1회 적용합니다. 앱 시작 시
  자동 DDL은 없습니다.
- LangGraph 체크포인트는 공식 `PostgresSaver`를 `search_path=preview_dev`로 고정해 씁니다.
  실제로 `preview_dev`에만 `checkpoints`·`checkpoint_blobs`·`checkpoint_writes`·
  `checkpoint_migrations`가 생기고 `public`에는 **하나도 생기지 않음**을 확인했습니다.
- 기존 경기·계정 자료는 읽기 전용이고, 개발 연결 역할에 그 쓰기 권한이 없습니다.

## 8. R1/R4 분리와 이름 표시 (최신 사용자 요구)

| 항목 | 상태 |
|---|---|
| R1 경기력 전용화 | 완료. R1은 선수 선정을 만들지 않음(`include_players=False`) |
| R4 `section_players` 등록 | 완료. registry·modules/__init__·version_manifest·sections·pipeline·S1 입력 |
| 선정 표시 분리 | 완료. `selected_player` / `selection_reason` 별도 필드 |
| 공유 판정 API 보존 | 완료. R4는 `form.validate_response`를 기본값으로 그대로 사용 |
| 정상 예산 4+1 | 완료. 총 상한 8·동시 2 유지 |
| 한국어 표시 이름 | 완료(표시 경계). 저장 본문·승인 스탬프 불변 |
| 옛 결합 결과·승인 보존 | 완료. 옛 행·승인을 새 버전으로 덮지 않음 |

## 9. 아직 아닌 것 / 남은 일

- **API-Football 실시간 수집 미연결**(MP-03 잔여). D0는 저장 자료만 읽고, 전송 계층이
  없으면 그 사실을 진단·상태로 드러냅니다. 없는 성공을 만들지 않습니다.
- **전체 프리뷰 실호출 미검증.** 이 작업은 유료 호출 0회이며, 실제 live 실행은 별도 승인
  범위입니다.
- **런타임 반영 미확인.** 8000 백엔드는 아직 이전 코드를 싣고 있습니다. 재시작 뒤에 새
  라우트·한국어 표시가 실제 화면에 나오는지 확인해야 합니다(재시작은 조정자 1회).
- **R4 실제 생성 미검증.** R4는 기록 응답으로만 확인했습니다. 실제 모델 호출은 별도 승인
  범위입니다.
- **S1은 R4를 입력으로 받지만**, 옛 R1 결합 결과로 만든 과거 종합·승인은 그대로 옛 증거이며
  새 R4 결과로 다시 만든 것이 아닙니다.
- **MP-11 별도.** 최종 독립 검토·실연동 검증은 이 작업 범위가 아닙니다.

## 10. 소유 경로·커밋

- `3c8a479`(11경로): 그래프·작업상태·재개·예산·체크포인트·마이그레이션.
- `a45599c`: 전체 프리뷰 관리자 API(`preview_admin.py` +332 포함) **와** 한국어 표시 이름
  통합, 그리고 이름 담당 최종 인계 경로(해석기·검사·프로비저너·보고·증거). 이 커밋을
  "이름만"이라고 부르지 않습니다.
- `de4bf00`: R1 경기력 전용 분리 + R4 `section_players` 통합, 그리고 R4 담당 최종 인계
  경로(모듈·계약·프롬프트·패널·오프라인 예시·보고·증거).
- `git add -A`는 쓰지 않았습니다. 커밋마다 경로를 지정해 스테이징했습니다.
- 808건의 기존 삭제와 dirty 문서는 그대로입니다. `Plans.md`·정책 문서는 수정하지 않았습니다.
- 8000/5173은 재시작하지 않았습니다. 새 코드는 재시작 뒤에 로드됩니다.

증거: [evidence/mp10/](evidence/mp10/)
