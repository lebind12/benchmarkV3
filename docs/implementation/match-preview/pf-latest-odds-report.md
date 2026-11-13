# PF-B 3차 — 최신 실제 배당 채택(신선도 제약 해제)

작성: 2026-11-12 KST. 담당: DeepSeek 구현 워커(PF-B 3차). 실제 모델 `deepseek-ai/deepseek-v4.1-flash-1017`(dsh-tui, Max 유지).
사용자 지시: "배당은 6시간 이전이라도 그때 당시의 최신 배당을 가져오도록 해야 한다."
범위: `sources/provider_odds.py`(+ 기존 odds 채택 경로의 표시 문구), `version_manifest.py`(기존 경유), 대표 검사. 한국어 이름/프론트/Plans/키/서버/DB/모델/실제 HTTP **변경·호출 0회**.

## 1. 무엇이 문제였나

이전 경로는 `api.odds_freshness`(6시간)를 통과하지 못한 줄을 **버려서** 진단만 남겼다.
실제 사용자 run `d96fe824…`의 저장 결과도 `structured.odds: []`, 품질 `insufficient`이고 진단이 이랬다.

```
William Hill: 수집 시점 기준 95.5시간 지난 배당이라 채택하지 않았습니다(기준 6시간).
Bet365: 수집 시점 기준 95.5시간 지난 배당이라 채택하지 않았습니다(기준 6시간).
```

제공자에는 실제 값이 **9개 업체 1X2**로 있었고 `update`는 `2026-11-08T12:52:18Z`였다. 값이 없어서가 아니라 **오래됐다는 이유로 버린 것**이 원인이었다.

## 2. 수정(사용자 확정 정책)

`provider_odds._quotes_from_records`에서 **신선도 거부를 제거**하고 "그 경기·그 업체의 가장 최근 실제 갱신값 채택"으로 바꿨다.

| 규칙 | 구현 |
|---|---|
| 오래돼도 채택 | `odds_freshness` 호출 제거. 값 자체(홈/무/원정 3개 + 숫자 검증)가 유효하면 채택 |
| 업체별 최신 선택 | 같은 업체 레코드가 여러 개면 `updated_at`이 **가장 최근**인 줄 사용(`_recency_rank`) |
| 시각 미상 처리 | 갱신 시각 없는 줄은 최신이라고 주장하지 않는다(이미 고른 줄을 밀어내지 않음). 단 **값은 채택**한다 |
| 원시 시각 보존 | `observed_at`은 제공자가 준 갱신 시각 **그대로**. `collected_at`으로 바꾸지 않는다 |
| 날짜 미상 | `observed_at = None`(기존 nullable 계약). "신선함"을 만들지 않음 |
| 보존 항목 | 공개 표 우선 / 서로 다른 업체 최대 3행 / 제공자 GET 1회 / 지원 시장·fixture 일치·숫자 검증 |

`odds_freshness`(공용 함수)는 **건드리지 않았다**. 다른 경로(D0 수집·outlook)는 자기 정책을 그대로 쓴다.

### 표시 문구 2건 정정

제공자 줄이 실리는데 "공개 사이트의 …"라고 적으면 사실과 다르다.
- 본문 머리: `"정규시간 1X2 소수점 배당입니다. 기준 시각은 제공된 갱신 시각입니다."`
- 출처 note: `"모델 없이 공개 표·제공자 배당을 정규화한 값입니다."`

## 3. 변경 파일

- `app/preview/sources/provider_odds.py` — 채택 정책·업체별 최신 선택·원시 시각 보존, `PROVIDER_ODDS_IMPLEMENTATION_VERSION` 1→2, 사유 문구 정정
- `app/preview/modules/bundle_sections.py` — 배당 본문 머리·출처 note 문구 2건(의미 있는 출처 표기)
- `tests/preview/test_bundle_review_fixes.py` — 대표 검사 3건 추가 + 버전 단언 갱신

## 4. 새 버전 (승인 축)

| 워크플로우 | 이전 | 이후 |
|---|---|---|
| `section_odds` | `section_odds@08ed203a23b234b5` | **`section_odds@49923b1c5dcb467a`** |
| `section_availability` | `section_availability@643296ca23b42faf` | 동일(불변) |
| `section_players` | `section_players@f29a3253194f31b1` | 동일(불변) |
| `section_ai_forecast` | `section_ai_forecast@8d4f5288197089fe` | 동일(불변) |

`section_odds`의 `compose_body` 구현 버전이 `mp11-provider-odds-1` → **`mp11-provider-odds-2`**로 올라가 버전이 파생됐다. 기존 저장 run·승인 근거는 덮어쓰지 않았다(아래 6절 실측).

## 5. 검사 명령과 결과(대표만)

```
./.venv/bin/python -m pytest tests/preview/test_bundle_review_fixes.py tests/preview/test_workflow_version.py -q
  36 passed
```

추가한 대표 검사:

| 검사 | 확인 |
|---|---|
| `test_stale_provider_quote_is_adopted_with_raw_observed_time` | 실제 시각(2026-11-08T12:52:18Z)·94시간 경과 → 채택, `observed_at` 원시값 유지(수집 시각 아님) |
| `test_same_bookmaker_chooses_most_recent_update` | 같은 업체 2건 → 최신 갱신값 선택, 업체당 1행 |
| `test_unknown_update_time_is_adopted_without_faking_freshness` | 시각 미상 → 채택하되 `observed_at=None` |

기존 검사 유지 확인: 공개 우선 3업체 병합(`test_public_one_row_plus_provider_two_rows_keeps_site_first_three`), 공개 3개면 호출 0(`test_public_three_rows_means_no_provider_call`), 1회 제한(`test_read_once_guard_blocks_the_second_request`) 모두 통과.

**실제 응답 모양 재현(네트워크 0회, 대역 클라이언트)**: 9업체·`update 2026-11-08T12:52:18Z` → `sent=1`, `available=True`, 업체 3행(William Hill·Bet365·Marathonbet) 모두 `observed_at = 2026-11-08 12:52:18+00:00`.

## 6. 기존 저장 run 보존 확인(READONLY)

run `d96fe824-bc38-4402-bb2c-9f16fdee4b3b`의 `section_odds` 행은 그대로다.
`workflow_version = section_odds@08ed203a23b234b5`(옛 버전), 품질 `insufficient`, `structured.odds: []`.
즉 **버전만 새로 계산**되고 기존 행은 덮어쓰지 않는다.

## 7. 인계 — root가 실행할 재생성 경로(모델 0회)

**API 요청 계약**

```
POST /api/v1/admin/preview/section-runs
Content-Type: application/json
(인증: 기존 관리자 JWT 세션 — 새 키·새 권한 없음)

{
  "workflow_id": "section_odds",
  "mode": "live",
  "source_mode": "reuse",
  "base_run_id": "d96fe824-bc38-4402-bb2c-9f16fdee4b3b"
}
```

- `source_mode="reuse"`는 **저장된 정보 원문 묶음을 그대로** 쓰므로 조사·검색·수집 호출이 0회다.
- `section_odds`는 모델 호출이 없으므로(`_expected_section_model_calls("section_odds") == 0`) 이 실행의 모델 전송은 **0회**다.
- 제공자 `/odds` GET은 새 `bundle_pipeline._provider_odds_for`가 **실행당 1회**만 보낸다(공개 표 채택 업체가 3개 미만일 때만).
- 응답은 기존 `SectionRunResponse`이며 `run_id`로 저장 결과를 다시 연다.

**결과 선택 경로(관리자 화면이 보는 순서)**

1. `GET /api/v1/admin/preview/runs/{new_run_id}/preview` — 독자용 본문(배당 섹션 포함).
2. `GET /api/v1/admin/preview/runs/{new_run_id}/section-results` — 섹션 행 + `structured`.
   `section_odds`의 `structured.odds[]`가 `bookmaker · observedAt · home · draw · away`로 내려간다.
3. `GET /api/v1/admin/preview/runs/{new_run_id}/information-bundle` — 저장 묶음(배당 포함).
4. 최종 전망을 다시 만들 필요가 있으면 기존 구성본 경로(`selected_result_ids`)로 이 배당 결과를 선택한다. **이번 작업에서는 실행하지 않는다.**

`observedAt`은 frontend가 이미 소비하는 필드다(`section_structured._odds` → `structured.odds[].observedAt`). 값은 제공자 원시 갱신 시각이며, 시각 미상이면 `null`이다.

## 8. 남은 일

1. **root 1회 재기동**: 현재 8000 프로세스는 수정 전 코드다.
2. 재기동 후 위 §7 요청 1회 → 새 `section_odds` 버전(`49923b1c…`)으로 실제 배당 3행이 저장되는지 확인 → 관리자 화면에서 표·기준 시각 표시 확인.
3. 프론트에서 기준 시각을 "KST"로 바꿔 보여주는 표시 개선은 별도 범위다(이번 작업은 서버 값 보존까지).
4. 배당 섹션 머리 문구가 바뀌었으므로, 화면 캡처로 문구 확인은 root의 실제 화면 확인 단계에서 한다.

EDITING STOPPED
