# PF-R-LATEST — 최신 실제 배당 채택 정책 **한정 확인**

작성: 2026-11-12 KST. 담당: DeepSeek 독립 검토 워커(PF-R-LATEST). 실제 모델 `deepseek-ai/deepseek-v4.1-flash-1017`(dsh-tui, Max 유지).
범위: 지시된 항목만. 입력 `pf-latest-odds-report.md`. 공개 우선 3업체·1회 호출·예외 경계는 **재검토 0**(PF-R-FIX에서 확인 완료). 추가 pytest·DB·HTTP·서버·제품 편집·새 재현 코드 0.

## 판정: **차단 없음**

| 확인 | 판정 | 근거 |
|---|---|---|
| 오래된 값도 채택(신선도 거부 제거) | 충족 | `_quotes_from_records`에 `api.odds_freshness` 호출이 **없다**(`provider_odds.py:213-288`). 값 3개 존재·숫자 검증만 통과하면 채택 |
| 업체별 최신 갱신 선택 | 충족 | 업체 `casefold()` 키로 `best`/`order` 유지, `_recency_rank`(=`updated_at.timestamp()`)가 더 크면 교체(`:236-259`). 순서는 첫 등장 유지 → 최대 3행 상한 유지 |
| 원시 `observed_at` 보존 | 충족 | `observed_at=record.updated_at`(`:264`). `collected_at`으로 대체하는 대입 없음(`collected_at`은 이 함수에서 **사용되지 않음**) |
| 시각 미상 → null | 충족 | `updated_at is None`이면 `observed_at=None` + note에 "갱신 시각은 제공되지 않았습니다"(`:262-277`) |
| 배당 문구 2건 | 충족 | 본문 머리 `"…기준 시각은 제공된 갱신 시각입니다."`(`bundle_sections.py:2393`), 출처 note `"모델 없이 공개 표·제공자 배당을 정규화한 값입니다."`(`:2416`). 옛 "공개 사이트" 표기는 잔존 0 |
| `mp11-provider-odds-2` / `section_odds@49923b1c5dcb467a` | 충족 | 직접 계산 일치. 구성은 `D0=mp05-stored-d0-1`, `compose_body=mp11-provider-odds-2`. `section_players@f29a3253…`·`section_availability@643296ca…`·`section_ai_forecast@8d4f5288…` 불변 |

## 확인 과정에서 본 것(모두 비차단)

1. **시각 비교 안전**: `_recency_rank`는 naive/aware 혼합 시 예외 위험이 있는데, 값을 만드는 `api._dt`가 naive를 UTC로 정규화하므로(`api_football.py:356-365`) 실제 비교는 전부 aware다. "최신 선택"에서 naive 비교 버그 없음.
2. **다른 경로의 6시간 규칙은 그대로**: `odds_freshness`는 삭제되지 않았고 D0 `data.py:1217-1220`·`outlook.py:683`이 계속 쓴다. 배당 섹션이 보는 공개 표 경로(`retrieval._to_odds_market`, `:1037-1075`)에는 신선도 필터가 없어 화면 값이 다시 걸러지지 않는다 — 즉 "오래돼도 표시"가 표시 경로 전체에서 성립한다.
3. **문구 정밀도(참고)**: 머리 문구의 "제공된 갱신 시각"은 제공자 줄에는 정확하지만, 공개 표 줄의 `observed_at`은 수집 시각(`parse_odds_table(observed_at=source.collected_at)`)이다. 실제 run `493ef4a9`는 제공자 3행만 실려 문제가 드러나지 않았다. 차단 아님.
4. **미사용 인자(참고)**: `_quotes_from_records(..., collected_at=...)`는 이제 쓰이지 않는다. 호출부 계약을 깨지 않으려 남긴 것으로 보이며 동작 결함은 아니다.

## 검사 증거(재실행 없음)

- 지시대로 새 pytest를 돌리지 않았다. **이 세션이 앞서 같은 두 파일을 1회 실행한 결과 36 passed**(21:39:51)를 재사용한다.
- 그 실행 시점보다 **파일 mtime이 모두 이르다**: `provider_odds.py` 21:33:45, `bundle_sections.py` 21:35:41, `test_bundle_review_fixes.py` 21:34:14, `version_manifest.py` 21:14:56 → 이후 코드 변경 없음 → 36 passed가 현재 트리에 그대로 적용된다.
- root의 실제 확인(Plans.md): run `493ef4a9-0e14-4436-8a97-d6de7ce034a7`, 결과 `f6cc06ca…`, `section_odds@49923b1c5dcb467a`, succeeded/ready, William Hill 1.4/4.8/6.5 · Bet365 1.44/4.75/6.25 · Marathonbet 1.46/4.9/6.5, 모두 `observedAt=2026-11-08T12:52:18+00:00`. 이 검토는 그 기록을 **인용**하며 DB를 새로 조회하지 않았다.

## 남은 것

없음(이 확인 범위). 배당 화면 캡처·기준 시각 KST 표시 개선·프론트 작업은 다른 워커/root 범위다.

READ-ONLY CONFIRMED — 제품·테스트·DB·설정을 수정하지 않았다.

## 재확인 (2026-11-14 01:50 KST, 같은 세션) — 근거 재사용, 새 실행 0

메시지 지시대로 새 검사를 실행하지 않고, 현재 트리에서 수용 항목만 다시 대조했다.

| 항목 | 현재 상태 |
|---|---|
| 94h 지난 실제형태 값 채택 | 충족 — `_quotes_from_records` 안 `odds_freshness` 호출 0건(`provider_odds.py:213-300`) |
| 업체별 최신 선택 | 충족 — `_recency_rank` 사용(`:189,249,253`) |
| 원시 관측시각 유지 | 충족 — `observed = record.updated_at`, `observed_at=observed`(`:264,271`) |
| 시각 미상 null | 충족 (코드 무변경, 기존 검사 `test_unknown_update_time_is_adopted_without_faking_freshness` 존재) |
| 공개우선 3업체 / 실행당 1회 | 충족 — `has_remaining_slots`(`:100`), `ReadOnceGuard`(`:109`), `read_provider_odds_once`(`:409`) |
| 배당 문구 2곳 | 충족 (`bundle_sections.py:2393,2416` 원문 일치) |
| `mp11-provider-odds-2` / `section_odds@49923b1c5dcb467a` | 충족 — 직접 재계산 일치 |
| 다른 섹션 버전 불변 | **불변 아님(신규 드리프트)** — 아래 참고 |

**신규 드리프트(비차단, 이번 범위 밖)**: `version_manifest.py`가 2026-11-13 05:30에 바뀌어 bundle 워크플로우의 **계약 축**을 `CONTRACT_VERSION`(`mp02-1`)에서 `SECTION_RESULT_CONTRACT_VERSION`(`mp04-section-result-1`)로 교체했다. 그래서 다른 네 섹션 버전이 함께 이동했다(`section_players@174a98077f78af37`, `section_availability@7dc7fec4ec7919ac`, `section_outlook@ad49f4e4058f7bbb`, `section_ai_forecast@c186f27356d4bb80`). `section_odds@49923b1c5dcb467a`는 그대로다. 이 변경은 배당 작업이 아니므로 위 "불변" 판정은 **작성 시점 값**으로만 유효하다. `tests/preview/test_bundle_review_fixes.py:1083-1086`이 `section_availability@643296ca23b42faf`를 문자열로 고정하고 있어 지금 코드에서는 그 단언이 맞지 않는다(미실행, 값 대조만). 수정은 이 검토 범위가 아니다.
