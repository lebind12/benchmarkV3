# PF-R-CALLS — 호출 수 표시 수정 **한정 독립 확인**

작성: 2026-11-12 KST. 담당: DeepSeek 독립 검토 워커(PF-R-CALLS). 실제 모델 `deepseek-ai/deepseek-v4.1-flash-1017`(dsh-tui, Max 유지).
범위: 두 차례 정정된 지적(W-2/W-3)만. 입력 `pf-refresh-call-report.md`, `pf-reuse-ui-report.md` §8, 현 코드. 디자인 워커가 소유한 `MatchPreviewBody`/css/`previewView`는 검토 제외.

## 판정: **위반 없음 — 충족**

| 지적 | 판정 | 근거 |
|---|---|---|
| W-3: `expected_model_calls`가 계획을 따라야 | 충족 | `expected_model_calls=len(participating_module_ids)`(`bundle_pipeline.py:2557`). 그 계획은 첫 전송 전 확정된 지역 변수(`:2200`)이며 다른 곳에서 재계산하지 않는다 |
| reuse는 실제 모델 0 | 충족 | `section_odds`의 `LOGICAL_CALL_IDS` 값이 `None`이라 `regeneration_logical_call_ids('section_odds', reuse) == ()`(직접 실행으로 확인). refresh 조사는 `source_mode == "refresh"` 분기에서만 일어난다(`:2028`,`:2239`). 따라서 계획 0 = 실제 0 |
| odds refresh는 `discovery_outlook` 계획 1 | 충족 | 직접 실행 결과 `section_odds` refresh = `('discovery_outlook',)` len 1. `regeneration_discovery_group`이 odds/outlook을 `GROUP_OUTLOOK`으로 보낸다(`:2006-2007`) |
| refresh에서 `no_model_call` false | 충족 | API는 반환에서만 파생한다: `no_model_call=outcome.expected_model_calls == 0`(`preview_admin.py:899`). 기대 1 → false. 정적 `_SECTION_MODEL_CALLS`(`:713-724`)는 **옛 경로 분기(970행)** 전용이며, `section_odds`는 `implemented_section_ids()`에 없어(`('section_form','section_availability','section_outlook','section_players','section_synthesis')`) live 옛 경로에 도달하지 못한다 → 보고서 §7-2 주장과 일치 |
| `external_calls` = 실제 모델 전송, 배당 API 전체 전송과 혼동 금지 | 충족 | `external_calls=int(budget.model_used)`(`:2546`)이고 `charge()`는 `RequestClass.API`면 `api_used`, 아니면 `model_used`를 올린다(`retry.py:563-566`). 배당 provider GET은 `RequestClass.API`로 차감되므로 `model_used`에 섞이지 않는다. 화면도 "모델 전송 n회"로만 적고(`SectionRegenerationPanel.vue:221-226`) 배당 reuse 결과에는 "실제 배당 API 전송 수는 이 화면에서 확인하지 않습니다"를 덧붙인다(`:230-237`) |
| 문구가 실행 방식별로 갈라짐 | 충족 | refresh 안내: "자료 검색 모델 호출…배당 본문 작성 자체는 모델을 쓰지 않지만, 조사 단계의 모델 호출은 발생합니다"(`:99-105`). reuse 안내: "이 재사용 경로는 모델 호출이 0회"(`:317-319`) — 방식 한정 표현. `PreviewPanel.vue`는 모델 0회를 단정하지 않고 두 경우를 병기(`:721-731`) |

## 계약 정합(직접 계산)

| 섹션 | 모드 | 계획 | expected | 비고 |
|---|---|---|---|---|
| section_odds | reuse | `()` | 0 | 실제 0 |
| section_odds | refresh | `('discovery_outlook',)` | 1 | 실제 ≥1 |
| section_players | reuse / refresh | 1 / 2 | 1 / 2 | 보고서 §3 표와 일치 |
| section_ai_forecast | reuse / refresh | 1 / 2 | 1 / 2 | 일치 |

## 검사 근거(재사용, 새 실행 0)

- 신규 대표 1건이 4가지를 한 번에 고정한다: 계획 전제(`()`, `('discovery_outlook',)`) → reuse `expected 0`·`external 0`·`transport.calls == []` → refresh `expected 1`·`external >= 1`·전송 `['discovery_outlook']` → 관리자 라우트 reuse `no_model_call=true`/refresh `false`(`test_bundle_integration.py:1917-2054`). 헬퍼 `_recording_transport_for`·`_patch_admin_route`·`_store_context_run` 실재 확인.
- 기존 직접 검사도 실재: `test_odds_section_expects_zero_model_calls`(정적 표 값 0/1/1), `test_regeneration_budget_covers_the_modules_that_refresh_actually_runs`, `test_bundle_section_regeneration_uses_the_stored_bundle...`, `test_live_regeneration_returns_the_saved_result...`.
- 프론트 대표 2건이 표와 일치: reuse(`no_model_call=true`,`external_calls=0`) → "모델 호출 없이 처리됐습니다"+"모델 전송 0회", refresh(`false`,`1`) → "모델 호출 없이" **없음**+"모델 전송 1회"(`SectionRegenerationPanel.test.ts:207-277`). 안내 문구 단언도 존재(`:190`,`:201`).
- 보고된 backend 5 pass / frontend 13 pass는 **재실행하지 않고** 위 코드·검사 내용 대조로 확인했다. 파일 mtime(backend 22:24, 프론트 22:21~22:23, 보고서 22:24~22:25)이 보고 이후 그대로라 증거가 현재 트리에 그대로 적용된다.

## 남은 필수

1. **root 실제 화면 확인 1회** — 서버는 22:37 재기동됐다(Plans.md). odds **refresh**는 실제 모델 1회가 나가므로 실행은 root 판단이다. 이 워커는 실행하지 않았다.
2. 그 밖에 이번 지적에 대한 미수정 항목은 없다. 새 후보·범용 개선은 만들지 않았다.

## 실행하지 않은 것

추가 pytest·vitest·typecheck·실제 HTTP·모델·DB·브라우저·서버·새 재현 스크립트 **0**. 제품·테스트 편집 0. 전체 재검토·참고 확대 0.

READ-ONLY CONFIRMED
EDITING STOPPED
