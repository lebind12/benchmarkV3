# 원문 응답 탭 결함 수정 보고 (시도↔모듈 실행 연결 + 전체 응답 표시)

작성: 2026-11-11 06:35 KST. 담당: DeepSeek 구현 워커
(`hive` / `deepseek-ai/deepseek-v4.1-flash-1017`, `max`, 프로필 `dsh-tui`). 하위 워커 없음.
상태: **수정·검증 완료. 유료 호출 0회. 편집 종료(§8).**

## 1. 한 줄 결과

사용자가 본 "이전에 첨부한 내용밖에 안 보인다"는 것은 **두 개의 실제 결함**이었습니다.

1. **선수 패널의 '원문 응답'이 모델 JSON만 보여줬습니다.** 그건 원문이 아니라 모델이
   생성한 선수 선정 JSON입니다.
2. **Google API 전체 응답이 아예 보이지 않았습니다.** R4가 보낸 시도가
   `module_execution_id=NULL`로 저장되어, 공통 '응답' 탭이 그 모듈에서 원문을 찾지
   못했습니다(저장 실행에서 R4 `attempt_count=0`).

둘 다 고쳤고, **이미 저장된 두 실행**(`22e1a19e`, `6176a8c6`)도 이제 전체 응답을
보여 줍니다. 저장 행은 고치지 않았습니다(읽기 투영만).

## 2. 결함 1 — 시도가 모듈 실행에 붙지 않던 문제 (앞으로 보내는 호출)

**원인.** 노드 문맥에는 `module_execution_id`가 있었지만, 노드가 쓰는 **실행 문맥**
(`ctx.context`)에는 없었습니다. R4는 `context.module_execution_id`를 읽어 시도를
기록하므로 `NULL`이 저장됐습니다.

| 파일 | 수정 |
|---|---|
| `app/preview/runner.py` | `_run_node`가 실행 문맥에도 이번 모듈 실행 ID를 넣는다(`replace(ctx.context, module_execution_id=execution.id)`) |
| `app/preview/modules/players.py` | R4 노드가 `ctx.context`를 그대로 넘기던 것을, 실행 ID를 넣은 문맥으로 넘기게 수정 |

R1/R2/S1은 이미 각자 실행 ID를 넘기고 있어 정상이었고, R4만 빠져 있었습니다. 공유
runner를 고쳐 **모든 모듈**이 같은 문맥을 받게 했습니다.

**검증**(기록 transport, 유료 호출 0): 새 실행에서 시도 5건이 **모두**
`module_execution_id`와 `response_artifact_id`를 가집니다.

## 3. 결함 2 — 이미 저장된 실행도 전체 응답을 볼 수 있게 (읽기 투영)

저장된 행은 고치지 않고 **읽을 때** 연결합니다(`app/preview/store.py`).

- 시도의 `module_execution_id`가 비어 있으면, **같은 실행에 그 모듈의 실행이 정확히
  하나일 때만** 그 실행에 붙여 보여 줍니다.
- 모듈 실행이 둘 이상이면 **임의로 고르지 않고**, 실행 단위 `unassigned_attempts`로
  따로 노출합니다(정직한 라벨).
- `attempt_count`가 0으로 남아 있던 옛 행은 실제로 붙은 시도 수로 표시합니다(읽기 보정).

**실제 저장 실행으로 확인**(읽기 전용):

| 실행 | R4 attempt_count | 응답 탭 | 원문 artifact | candidates | grounding |
|---|---|---|---|---|---|
| `6176a8c6` (이전 성공) | **1** | 사용 가능 | `d3ef5acb…` | 있음 | chunks 8 / supports 9 / queries 14 |
| `22e1a19e` (최신) | **1** | 사용 가능 | `740db1a0…` | 있음 | chunks 0 / supports 0 / queries 8 |

D0도 `raw_response` artifact를 가지므로 **첫 번째 raw_response를 고르지 않고**, 그 시도가
기록한 `response_artifact_id`를 정확히 씁니다. 원문 안의 `candidates[].content.parts[].text`와
`grounding_metadata`가 그대로 보존됩니다.

## 4. 결함 3 — 라벨이 두 가지를 섞던 문제

| 위치 | 이전 | 이후 |
|---|---|---|
| 선수 패널 접이식 | `원문 응답(데이터로만 표시)` | **모델이 생성한 JSON (선수 선정 결과)** + "전체 응답은 같은 화면의 **응답** 탭" 안내 |
| 공통 응답 탭 | `수신 원문 (비밀값 제거)` | **Google API 전체 응답 (비밀값 제거 · 메타데이터 포함)** + candidates/grounding/usage 포함 설명 |

이제 사용자가 "모델이 만든 JSON"과 "Google이 준 전체 응답"을 혼동하지 않습니다.

## 5. 보안·정직성

- 저장된 전체 응답은 이미 artifact 계층에서 **비밀값 제거**를 거쳤고(`redacted: true`),
  `sdk_http_response`에는 인증 헤더가 없습니다(alt-svc·content-type·date·request-id 등만).
- 없는 필드는 지어내지 않습니다. 최신 실행은 chunks/supports가 **실제로 0**이며 그대로
  드러납니다.
- 최신 실행의 `quality=insufficient`(본문 비어 있음)는 **그대로**입니다. 사용자는 보기를
  요청했고, 이 작업은 재생성하지 않았습니다.

## 6. 검증 (유료 호출 0회)

```sh
PREVIEW_TEST_DATABASE_URL=...preview_mp10_test \
  .venv/bin/python -m pytest tests/preview/test_run_store.py \
    tests/preview/test_inspection_api.py tests/preview/test_pipeline.py -q   # 40 passed

# 새 대표 검사 2건 포함
.venv/bin/python -m pytest tests/preview/test_pipeline.py -q                  # 18 passed

npm --prefix frontend run type-check                                          # clean
npx vitest run RunInspector.test.ts R4PanelAndBody.test.ts                    # 12 passed
```

새 대표 검사 2건:
1. `test_sent_attempt_is_linked_to_its_module_execution` — 보낸 시도가 자기 모듈 실행과
   원문 artifact를 가진다.
2. `test_legacy_unlinked_attempt_is_attached_by_unique_module` — 실행 ID가 빈 옛 시도는
   유일할 때 붙고, 모듈 실행이 둘이 되면 미배정으로 노출된다.

## 7. 화면에서 보는 곳 (한국어 경로)

1. <http://127.0.0.1:5173/admin/runs?run=22e1a19e-52df-4774-a1b1-1de9f892a840>
2. 실행 검사 화면에서 **모듈 목록의 `R4` (주목 선수 선정)** 선택
3. 아래 **노드·모듈 진단 정보** 접이식을 펼침
4. **응답** 탭 → **Google API 전체 응답 (비밀값 제거 · 메타데이터 포함)**
   - 선수 패널 안의 `모델이 생성한 JSON`은 모델이 만든 선수 선정 JSON입니다(별개).

## 8. 편집 종료

변경 파일: `app/preview/runner.py`, `app/preview/modules/players.py`,
`app/preview/store.py`, `app/preview/contracts.py`,
`frontend/src/features/match-preview/panels/PlayersPanel.vue`,
`frontend/src/features/match-preview/ModuleResultPanel.vue`,
`tests/preview/test_pipeline.py`, 이 보고서.

스키마·마이그레이션·백필 없음. 승인 0 유지, 기존 행·버전·원문·본문 무변경.
`Plans.md`·정책·환경·dist·808 삭제 무변경, `git add -A` 미사용.

**backend 8000 재시작 1회가 필요합니다**(조정자 수행, 제가 하지 않았습니다). 저장된 행을
읽는 투영과 라벨이 새 코드에 들어 있기 때문입니다.

여기서 편집을 멈춥니다.
