# PF-B 후속 수정 — 배당 보완 조건·1회 제한·파서 경계·버전 축

작성: 2026-11-12 KST. 담당: DeepSeek 구현 워커(PF-B 후속 2). 실제 모델 `deepseek-ai/deepseek-v4.1-flash-1017`(dsh-tui, Max 유지).
범위: 지적된 backend 3개 항목만. frontend·키·DB·서버·모델·실제 HTTP 호출 0회.

## 1. A — 남는 자리(채택 업체 3개 미만)가 있을 때 보완

**수정 전**: 공개 표가 **0행일 때만** `/odds`를 호출했다(`not adopted_odds_quotes`). 공개 표가 1~2행이면 남는 자리가 있어도 보완하지 않았다.

**수정 후**: `provider_odds.has_remaining_slots(market)` = `adopted_site_count(market) < 3`.
- `adopted_site_count`는 **정규시간 1X2 세 값이 모두 있는** 줄의 **서로 다른 업체**만 센다(같은 업체 중복은 1).
- 생성 노드(`_section_node`)와 **배당 재생성**(`run_section_regeneration`) 둘 다 같은 판정을 쓴다.
- 사이트 우선·최대 3개 고유 업체·호출 최대 1회는 그대로 유지된다.
  - 병합: `market_with_provider_quote`가 공개 표를 앞에 두고 남는 자리만 채운다.
  - 1회: `ReadOnceGuard`(실행당 1회 표시) + `read_provider_odds_once`.

**예산 차감 순서도 고쳤다.** 1회 제한을 **예산 판정·차감보다 먼저** 본다. 이미 읽은 실행이면 요청도, 사용량 차감도 하지 않는다(보내지 않은 전송을 사용량으로 세지 않음).

## 2. B — 결과 의미를 바꾸는 공급 경로를 버전 축에 반영

**버전 전후**

| 워크플로우 | 수정 전 | 수정 후 |
|---|---|---|
| `section_odds` | `section_odds@61e09b66690638fb` | `section_odds@08ed203a23b234b5` |
| `section_availability` | `section_availability@643296ca23b42faf` | `section_availability@643296ca23b42faf` (변경 없음) |
| `section_players` | `section_players@f29a3253194f31b1` | `section_players@f29a3253194f31b1` (변경 없음) |
| `section_ai_forecast` | `section_ai_forecast@8d4f5288197089fe` | `section_ai_forecast@8d4f5288197089fe` (변경 없음) |

**어떻게 넣었나(기존 등록 방식 재사용)**

- 배당 공급 경로가 **자기 버전 상수**를 소유한다: `provider_odds.PROVIDER_ODDS_IMPLEMENTATION_VERSION = "mp11-provider-odds-1"`.
- `version_manifest._compose_manifest("section_odds")`가 그 값을 돌려준다. 기존 `_compose_manifest`는 이미 섹션별 조립 버전을 돌려주는 자리이고, `constituents_for_workflow` → `release_version`이 그대로 승인 버전 계산에 넣는다. 새 등록부·새 표를 만들지 않았다.
- **공용 축(`bundle_sections.IMPLEMENTATION_VERSION`)은 올리지 않았다.** 그 값은 다섯 섹션 전체의 축이라, 올리면 배당과 무관한 네 섹션(`section_players`·`section_availability`·`section_outlook`·`section_ai_forecast`)의 승인 버전까지 바뀌어 불필요한 재승인을 만든다. 코드에 그 이유를 주석으로 남겼다.
- 과거 승인·실행·원문은 건드리지 않았고 **승인을 자동 부여하지 않았다**. 저장본의 기존 버전은 그대로 남아 있다(§5 실측).

## 3. — 제공자 파서 예외 경계(선택 배당이 전체 생성을 터뜨리지 않게)

`read_provider_odds`에서 **기존 명시 예외만** 잡는다.

| 예외 | 처리 |
|---|---|
| `api.WrongFixture` | `sent=1`, `available=False`, 사유 "다른 경기의 배당" + 원문 진단 |
| `api.ApiFootballError` (`parse_envelope` 봉투 모양 오류) | `sent=1`, `available=False`, 사유 "봉투 모양 오류" |
| `api.ApiFootballError` (`parse_odds` 해석 실패) | `sent=1`, `available=False`, 사유 "정규시간 1X2로 해석하지 못했습니다" |
| 전송 실패(기존 `except Exception`) | `sent=1`, 사유 + 예외 이름 (기존 동작 유지) |

- `WrongFixture`가 `ApiFootballError`의 하위형이므로 더 구체적인 예외를 먼저 잡는다.
- **내부 버그를 숨기지 않는다**: 파싱 구간에서 `ApiFootballError` 계열만 잡고, 그 밖의 예외는 그대로 올린다. 가상 입력을 나열하는 검사는 만들지 않았다.
- 결과는 모두 `ProviderOddsResult`(배당 미제공)로 돌아오므로 **전체 생성 흐름은 계속된다**.

## 4. 변경 파일

- `app/preview/sources/provider_odds.py` — `has_remaining_slots`/`adopted_site_count`/`ReadOnceGuard`/`read_provider_odds_once`, 파서 예외 경계, `PROVIDER_ODDS_IMPLEMENTATION_VERSION`
- `app/preview/bundle_pipeline.py` — 남는 자리 조건(생성·재생성), `_provider_odds_for(fixture, budget, moment, guard)`로 정리, 1회 제한을 예산 차감보다 먼저
- `app/preview/version_manifest.py` — `_compose_manifest("section_odds")`가 배당 경로 버전을 반환
- `app/preview/modules/bundle_sections.py` — 주석만(공용 버전 축을 올리지 않는 이유)
- `tests/preview/test_bundle_review_fixes.py` — 지적 항목 대표 검사 7건 추가

## 5. 검사 명령과 결과(대표만)

```
./.venv/bin/python -m pytest tests/preview/test_bundle_review_fixes.py tests/preview/test_workflow_version.py -q
  30 passed
```

추가된 대표 검사(지적 항목과 1:1):

| 검사 | 확인 |
|---|---|
| `test_remaining_slots_is_true_below_three_adopted_sites` | 0/1/2행은 남는 자리 있음, 3행은 없음 |
| `test_public_one_row_plus_provider_two_rows_keeps_site_first_three` | 공개1+제공자2 → 사이트 우선 3개 |
| `test_public_three_rows_means_no_provider_call` | 공개 3개면 제공자 호출 0 |
| `test_read_once_guard_blocks_the_second_request` | 두 번째 읽기 요청 0회 |
| `test_wrong_fixture_parse_error_becomes_missing_odds_not_a_crash` | `WrongFixture` → 배당 미제공 |
| `test_malformed_odds_envelope_becomes_missing_odds` | 봉투 오류 → 배당 미제공 |
| `test_odds_workflow_version_changed_and_others_kept` | 배당 버전만 변경·다른 섹션 불변 |

**과거 자료 무변경 확인(읽기 전용)**: run `6c2ce4c2…`의 저장 행 5건이 그대로다.
`section_odds` = `section_odds@61e09b66690638fb`(옛 버전), `section_availability` = `…@643296ca23b42faf`, 본문 길이·품질·`created_at` 모두 변경 없음.
즉 **버전 축만 새로 계산되고 기존 행은 덮어쓰지 않는다.**

## 6. 남은 문제 / 범위 밖

1. 저장본에 실제 배당을 채우려면 root가 최종 수정 후 **1회 재기동**하고, 배당 섹션을 1회 실행해야 한다. 실제 값은 여전히 제공자 신선도 기준에 달려 있다(직전 후속에서 94.2시간 초과 확인).
2. 이전에 후속으로 미뤄진 항목(잘못된 ID/팀ID·전송 장부 확대·키 없는 예산 차감)은 이번 작업에 넣지 않았다.
3. `section_odds`의 출력 계약 버전(`mp11-odds-output-1`)은 바꾸지 않았다. 출력 모양이 그대로이기 때문이다(공급 경로만 변경).

EDITING STOPPED
