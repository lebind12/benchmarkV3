# PF-R-FIX — 배당 보완 조건·1회 제한·파서 경계·버전 축 **수정 확인**

작성: 2026-11-12 KST. 담당: DeepSeek 독립 검토 워커(PF-R-FIX). 실제 모델 `deepseek-ai/deepseek-v4.1-flash-1017`(dsh-tui, Max 유지).
범위: 지시된 3항목만. 전체 재검토 없음(기존 전체 검토: `pf-backend-review.md`). 입력: `pf-odds-fix-report.md` + 변경 5파일. 제품·테스트·키·DB·서버·외부 HTTP·모델 호출·새 재현 스크립트 0. 과거 참고 항목(충돌 ID·팀 ID·장부·키 없는 예산·일반 타입 오류)은 재개하지 않았다.

## 판정 요약

| # | 확인 항목 | 판정 |
|---|---|---|
| 1 | 생성·재생성 모두 "공개 채택업체 3개 미만"일 때 provider 1회, 사이트 우선 최대 3고유업체, 공개 3개면 호출 0 | **충족** |
| 2 | 배당만 새 구현 버전 축, 기존 승인·저장본·다른 섹션 버전 보존 | **충족(축 분리)** — 단, 보고서의 해시 `08ed203a23b234b5`는 현재 트리 값이 아니다(아래 §2) |
| 3 | 기존 명시 provider 파서 예외만 선택배당 미제공 처리, 내부 예외 은폐 0 | **충족** |

## 1. 보완 조건·상한·1회 — 충족

- 판정 단일 함수: `provider_odds.adopted_site_count()`/`has_remaining_slots()`가 `채택 업체 < 3`을 본다(`provider_odds.py:66-102`). 정규시간 1X2 세 값이 모두 있는 줄만, 업체명은 `casefold()` 중복 제거.
- 호출 지점 2곳이 **같은 판정·같은 헬퍼**를 쓴다: 생성 노드 `_section_node`(`bundle_pipeline.py:1073`)와 재생성 `run_section_regeneration`(`:2394`) → 둘 다 `_provider_odds_for()`(`:721`). 재생성이 순서를 따로 구현하지 않는다.
- 공개 3개면 `has_remaining_slots`가 `False`라 `_provider_odds_for` 진입 전에 끝난다 → 요청 0, 예산 차감 0.
- 사이트 우선·최대 3고유업체: `_odds_section`이 채택 공개 행을 먼저 채우고, 제공자 줄은 `taken`(업체 casefold) 중복을 건너뛰며 `len(rows) >= 3`에서 멈춘다(`bundle_sections.py:2352-2385`). 공개 값이 0행이면 제공자 줄로만 채운다.
- 1회 제한: `ReadOnceGuard.claim()`을 **예산 판정·차감보다 먼저** 본다(`bundle_pipeline.py:747-770`) → 두 번째 도달은 요청도, `api_used` 차감도 없다(1차 검토 참고 A의 "보내지 않은 전송을 사용량으로 세는" 문제가 이 경로에서 해소). 생성은 실행 단위 `plan.provider_odds_guard`(`:1607`), 재생성은 실행마다 새 표시(`:2401`) → 실행당 1회.
- 참고(비차단): `market_with_provider_quote()`는 `public_quote_limit=1` 기본값이지만 **제품 경로에서 호출되지 않는다**(정의·검사에만 존재). 제품 병합은 위 `_odds_section` 코드다.

## 2. 버전 축 — 축 분리는 충족, **보고서 해시는 현재 트리와 다르다**

- 축 분리 자체는 사실: 배당 섹션만 자기 공급 경로 버전을 소유하고(`provider_odds.PROVIDER_ODDS_IMPLEMENTATION_VERSION`), `version_manifest._compose_manifest("section_odds")`가 그 값을 `compose_body` 구현 버전으로 돌려준다(`version_manifest.py:120-127`). 공용 `bundle_sections.IMPLEMENTATION_VERSION`은 `mp11-bundle-sections-7`로 올리지 않았고, 그 이유가 주석으로 남아 있다(`bundle_sections.py:91-95`).
- **해시 대조**: `08ed203a23b234b5`는 구현 버전 `mp11-provider-odds-1` 조합에서 재현된다(직접 계산으로 일치 확인). 즉 보고서 작성 시점 값과 그 계산 근거는 맞다.
- **그러나 검토 시점 트리는 `mp11-provider-odds-2`**이고 워크플로우 버전은 `section_odds@49923b1c5dcb467a`다. 원인은 이 수정이 아니라 **동시 진행된 사용자 확정 정책 변경**(6시간 신선도 폐기·최신 실제값 채택, PF-B-LATEST)이다. 그래서 "새 축 = 08ed203a23b234b5"를 현재 값으로 인용하면 틀린다. 파일 mtime상 이 검토 도중(21:33) 바뀌었다.
- 다른 섹션 보존은 **측정값으로 충족**: `section_players@f29a3253194f31b1`, `section_availability@643296ca23b42faf`, `section_ai_forecast@8d4f5288197089fe`가 보고서 표와 일치하고, `section_outlook@ad49f4e4058f7bbb`도 그대로다. 배당 변경이 네 섹션 승인 버전을 흔들지 않았다.
- 기존 승인·저장본 보존(코드 확인, DB 미조회): 섹션 결과는 `store.save_section_result`가 **새 행 삽입 + version 증가**로만 남기고, 저장된 `workflow_version`을 갱신하는 경로가 없다(`store.py:546-604`). 승인은 기존 행을 지우지 않고 `active=False` + `supersedes_approval_id`로 이력 보존(`approvals.py:458-480`). 재조립 경로도 기존 `latest_section["workflow_version"]`을 그대로 쓴다(`sections.py:716`). 실행 undo는 그 실행 소유 행만 지운다(`store.py:1217-1266`). **DB 실측은 지시상 하지 않았으므로** "run 6c2ce4c2 행 무변경"은 보고서 주장 인용이며 이 검토가 새로 확인한 값이 아니다.

## 3. 파서 예외 경계 — 충족

- 파싱 구간에서 **기존 명시 예외만** 잡는다: `parse_envelope` → `api.ApiFootballError`(`provider_odds.py:346-353`), `parse_odds` → `api.WrongFixture`(더 구체적이라 먼저, `:369-375`) → `api.ApiFootballError`(`:376-382`). 셋 다 `ProviderOddsResult`(배당 미제공, `sent=1`)로 돌려 흐름이 계속된다.
- 그 밖의 예외는 잡지 않는다 → 내부 버그 은폐 0. 전송 실패만 기존 `except Exception`(예외 이름만 사유로) 경로로 남아 있고, 이는 수정 전 동작 그대로다(`:334-340`).
- 봉투 오류·다른 경기 응답 검사가 각각 이유 문구와 원문 진단을 남기며, 진단에 키 값은 없다(`_api_key`는 존재 여부만 다룬다).

## 4. 실행한 검사(지시대로 해당 두 파일 1회)

```
./.venv/bin/python -m pytest tests/preview/test_bundle_review_fixes.py tests/preview/test_workflow_version.py -q
  -> 33 passed   (21:32경, 1회차 / 검토 중 파일이 늘어난 뒤 재실행 1회: 36 passed)
```

- 보고서의 `30 passed`는 **그 시점 파일 구성(26+4)**과 일치한다. 이후 다른 세션이 한글 이름·신선도 채택 검사를 추가해 지금은 32+4=36건이다(이 수정의 회귀가 아니다).
- 검사 내용을 소스와 대조함: `test_remaining_slots_is_true_below_three_adopted_sites`(0/1/2행 True·3행 False), `test_public_one_row_plus_provider_two_rows_keeps_site_first_three`, `test_public_three_rows_means_no_provider_call`, `test_read_once_guard_blocks_the_second_request`, `test_wrong_fixture_…`, `test_malformed_odds_envelope_…`, `test_odds_workflow_version_changed_and_others_kept`가 §1~§3의 실제 코드 경로를 가리킨다(가상 입력 나열 없음).
- **검사 공백 2건(차단 아님, 사실 기록)**: ① `test_odds_workflow_version_changed_and_others_kept`는 해시를 문자열로 고정해 이번처럼 축 값이 바뀌면 함께 고쳐야 한다(현재 `49923b1c5dcb467a`로 갱신돼 있음). ② 생성·재생성 노드에서 `has_remaining_slots → _provider_odds_for`가 실제로 불리는지를 파이프라인 수준에서 고정하는 검사는 없다(`test_bundle_pipeline.py`·`test_bundle_sections.py`에 `provider_odds` 언급 0). 지시 범위상 새 검사는 만들지 않았다.

## 5. 남은 것

1. 배당 승인·화면 반영에는 root의 서버 재기동 1회와 배당 섹션 실행 1회가 필요하다(이 워커는 실행하지 않았다).
2. 보고서·Plans.md의 `08ed203a23b234b5` 표기는 **당시 값**으로만 유효하다. 현재 코드 기준 값은 `section_odds@49923b1c5dcb467a`(구현 `mp11-provider-odds-2`)이며, 승인 근거로 인용할 때는 실행 시점 `workflow_version`을 써야 한다.
3. 위 §4의 검사 공백 2건은 후속 후보일 뿐 이번 수정 확인의 차단 사유가 아니다.

READ-ONLY CONFIRMED — 이 검토는 제품 코드·테스트·DB를 수정하지 않았다.
