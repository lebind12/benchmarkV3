# PF-REFRESH-CALL — W-3 수정: `expected_model_calls`를 계획과 일치

작성: 2026-11-12 KST. 담당: DeepSeek 구현 워커(Orca `dsh-tui`, 실제 모델
`deepseek-ai/deepseek-v4.1-flash-1017`, 추론 강도 Max 유지).
역할 전환: 읽기 전용 검토 종료 후 **backend 구현**으로 수행.

## 1. 실제 원인 (root 소스 대조와 일치)

`run_section_regeneration`의 반환이 고정값이었다.

```python
# 수정 전 (app/preview/bundle_pipeline.py:2547)
expected_model_calls=(0 if section_id == bundle_contract.SECTION_ODDS else 1),
```

같은 함수는 이미 2200행에서 **첫 전송 전에** 계획을 확정해 두고 있었다.

```python
participating_module_ids = regeneration_logical_call_ids(section_id, source_mode=source_mode)
budget.module_ids = participating_module_ids
```

그런데 반환은 그 계획을 쓰지 않았다. 그래서 `section_odds` + `source_mode='refresh'`는
계획이 `('discovery_outlook',)`(조사 모델 1회)인데도 기대값이 **0**으로 나갔고,
`preview_admin` 899행 `no_model_call = (expected_model_calls == 0)`이 **true**가 되어
화면이 "모델 0회"로 표시했다. **원인은 표시가 아니라 반환값**이다.

## 2. 수정 (단일 지점, 최소)

```python
# 수정 후 (app/preview/bundle_pipeline.py:2548~2557)
external_calls=int(budget.model_used),
# **계획상** 모델 모듈 수. `budget.model_used`(external_calls)는 실제 전송 수이며
# 재시도를 포함하므로 둘은 다른 값이다.
expected_model_calls=len(participating_module_ids),
```

- 새 계산 체계·새 모듈·새 예산·모델 설정·승인 버전 변경 **없음**.
- 외부 모델 호출·배당 호출을 **추가하거나 삭제하지 않았다**(계획은 그대로, 보고 값만 계획을 따른다).
- `participating_module_ids`는 이 함수 안에서 이미 확정된 지역 변수다(다른 곳에서 재계산하지 않는다).

## 3. 계약 확인 (수정 후 실제 값)

| 섹션 | 모드 | 계획 | `expected_model_calls` | `external_calls` | API `no_model_call` |
|---|---|---|---|---|---|
| `section_odds` | reuse | `()` | **0** (유지) | 실제 0 | **true** (유지) |
| `section_odds` | **refresh** | `('discovery_outlook',)` | **1** (고침) | 실제 ≥1 | **false** (고침) |
| `section_players` | reuse | `('section_players',)` | 1 (유지) | 실제 1 | false |
| `section_players` | refresh | `('discovery_people','section_players')` | 2 (계획과 일치) | 실제 ≥1 | false |
| `section_ai_forecast` | reuse | `('section_ai_forecast',)` | 1 (유지) | 실제 1 | false |

계약 정의(이번 수정으로 코드가 따르게 된 의미):

- `expected_model_calls` = **계획상 모듈 수**(첫 전송 전 확정).
- `external_calls` = `budget.model_used` = **실제 모델 전송 수**(재시도 포함).
- API `no_model_call` = `expected_model_calls == 0`.

즉 두 값은 서로 다른 축이며, 재시도가 있으면 `external_calls`가 기대값보다 클 수 있다.

## 4. 변경 파일

- `app/preview/bundle_pipeline.py` — 반환 1줄 + 근거 주석(그 외 무변경)
- `tests/preview/test_bundle_integration.py` — 직접 대표 검사 1건 추가

`app/api/v1/preview_admin.py`는 **수정하지 않았다**. 이미
`expected_model_calls=outcome.expected_model_calls`(894행)와
`no_model_call=outcome.expected_model_calls == 0`(899행)으로 **반환값을 그대로 파생**하므로,
반환을 고치면 API 출력이 자동으로 맞는다(수정 전 코드에서 899행이 true를 만들던 것이 결함이었다).

## 5. 검사 명령과 결과

모델·HTTP 실제 호출 0. DB는 기존 `tests/preview` 가드(루프백 + `*_test` 이름)를 통과한 로컬만 사용했다.
전체 파일·전체 suite·새 재현 스크립트는 실행·작성하지 않았다.

```
# 신규 직접 대표 검사
./.venv/bin/python -m pytest tests/preview/test_bundle_integration.py \
  -k "odds_regeneration_reports_planned_modules" -q
  1 passed, 29 deselected

# 기존 직접 관련 검사(예산 계획·배당 0회 선언·reuse 재생성)
./.venv/bin/python -m pytest tests/preview/test_bundle_integration.py \
  -k "regeneration_budget_covers or odds_section_expects_zero or bundle_section_regeneration_uses_the_stored_bundle" -q
  3 passed, 27 deselected

# 다른 섹션 재생성 회귀 확인(기대값 변경 영향)
./.venv/bin/python -m pytest tests/preview/test_bundle_integration.py \
  -k "live_regeneration_returns_the_saved_result" -q
  1 passed, 29 deselected
```

**회귀 감지력 확인**: 수정을 옛 고정식으로 되돌리면 신규 검사가
`expected_model_calls` 0 vs 1에서 **실패**하고, 되돌리면 다시 통과한다(1 passed). 즉 이 검사는
이번 결함을 직접 잡는다.

## 6. 신규 검사가 확인하는 것

`test_odds_regeneration_reports_planned_modules_not_just_zero`

1. 계획 전제: odds reuse = `()`, odds refresh = `('discovery_outlook',)`.
2. **reuse**: `expected_model_calls == 0`, `external_calls == 0`, 기록 transport 호출 `[]`.
3. **refresh**: `expected_model_calls == 1`, `external_calls >= 1`, 실제 전송
   `['discovery_outlook']` (모델 대역이며 네트워크 없음).
4. **API 연결**: 관리자 라우트로 reuse → `expected_model_calls=0`·`no_model_call=true`,
   refresh → `expected_model_calls=1`·`no_model_call=false`.

실패하면 사용자에게 생기는 일: 배당 "재생성"이 실제로 모델을 불렀는지·과금됐는지를 화면으로
알 수 없게 된다(모델 0회로 잘못 표시).

## 7. 미해결 / 남은 일

1. **화면 문구는 이번 범위 밖**이다. backend 값이 이제 정확해졌으므로, `SectionRegenerationPanel`의
   배당 refresh 문구("모델을 부르지 않습니다")와 응답 처리 결과 문구가 그 값을 그대로 반영하면
   사실과 맞는다. 해당 문구는 **frontend 작업자 소유**이며 이번에 수정하지 않았다.
2. `preview_admin._SECTION_MODEL_CALLS`의 정적 값(`section_odds: 0`)은 **옛 경로**(`section-runs`의
   비-bundle 분기)에서만 쓰인다. 그 경로는 배당을 재생성하지 않으므로 이번 결함과 무관해 손대지 않았다.
3. **root**: 실제 `refresh` 실행 0 유지, 재기동만 담당. 이번 수정은 재기동 후 반영된다.
4. 재시도가 발생하면 `external_calls`가 `expected_model_calls`보다 커질 수 있다(정상이며 두 축이 다름).

EDITING STOPPED
