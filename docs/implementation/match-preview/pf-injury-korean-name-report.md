# PF-B 2차 수정 — 한국어 이름만 저장된 부상 행의 ID/사진 연결

작성: 2026-11-12 KST. 담당: DeepSeek 구현 워커(PF-B 2차). 실제 모델 `deepseek-ai/deepseek-v4.1-flash-1017`(dsh-tui, Max 유지).
범위: 부상 사진 범위만. frontend·배당 코드·운영 DB·저장 payload·새 모델/HTTP/전체 생성 **변경·호출 0회**.

## 1. 재현과 원인

**재현(사용자 직접 생성 run `d96fe824-bc38-4402-bb2c-9f16fdee4b3b`)**
저장된 `section_availability.structured.injuries`가 `player_id: null`, `external_player_id: null`, `photo_url: null`로 내려왔다.
비교 대상 기존 run `6c2ce4c2…`는 세 선수 사진이 정상이었다.

**두 run의 저장 payload 차이(실측)**

| run | 저장 `player_name` | 결과 |
|---|---|---|
| `6c2ce4c2` | `Marc Guéhi`, `Antoine Semenyo`, `Tom Cairney` (영어) | ID·사진 정상 |
| `d96fe824` | `마크 게히`, `조슈아 킹` (**한국어**) | ID·사진 `null` |

즉 본문이 처음부터 한국어인 새 run에서만 실패했다.

**원인(코드, 결정적)**

`localized_names._match_rank`는 **영어 표기 규칙만** 있었다(DB `name` 일치·이름+성·머리글자+성·성 단독). 저장된 한국어 값(`name_ko`/`short_name_ko`)과 비교하는 규칙이 없어, 한국어 이름은 항상 `not_found`가 됐다.

그래서:
- `_verified_injury_player`(작성 경로)가 `None` → `player_id`를 저장하지 못했다.
- `StructuredIdContext.player_by_name`(읽기 투영)도 `None` → `external_player_id`·`photo_url`이 비었다.

**부수 함정(같이 고침)**: `normalize_name`이 NFKD 정규화를 하므로 한글 음절이 **자모로 분해**된다. 분해된 문자열에 음절 범위(`가~힣`) 검사를 하면 항상 거짓이라, "한국어일 때만 비교"하는 조건을 정규화 결과로 쓰면 동작하지 않는다. 실제로 첫 시도가 이 함정에 걸려 실패했고, 한국어 여부는 **저장된 원문**으로 판정하도록 고쳤다.

## 2. 수정(최소)

`app/preview/localized_names.py` — `_match_rank`에 **한국어 정확 일치 등급(0)** 을 추가했다.

- 비교 대상: `row.name_ko`, `row.short_name_ko`(DB에 저장된 값). 새 문자열·번역·음차를 만들지 않는다.
- 동등성: 정규화 토큰이 **완전히 같을 때만**(`_tokens(korean) == tokens`). 음절/자모 표기 차이만 흡수한다.
- 부분 일치 금지: `게히`, `킹` 같은 성 단독·부분 표기는 여전히 미해결이다(실측).
- 동명이인: 같은 한국어 값이 둘이면 기존 규칙대로 `ambiguous`로 남고 ID를 만들지 않는다(실측).

이 한 곳을 고치면 **작성 경로**(`bundle_sections._verified_injury_player` → `resolve_player`)과 **읽기 투영**(`section_structured.StructuredIdContext.player_by_name` → 같은 해석기)이 동시에 해결된다. 두 경로 모두 같은 해석기를 쓰기 때문이다. 그래서 다른 파일은 고치지 않았다.

## 3. 변경 파일

- `app/preview/localized_names.py` — `_match_rank`에 한국어 정확 일치 등급 추가(주석으로 NFKD 함정 기록)
- `tests/preview/test_bundle_review_fixes.py` — 대표 검사 3건 추가

하드코딩 문자열 없음(선수 이름·ID를 코드에 쓰지 않았다). 문자열 하드코딩/임의 사진/모호 매칭 추정/운영 DB·저장 payload 변경 없음.

## 4. 검사 명령과 결과

```
./.venv/bin/python -m pytest tests/preview/test_bundle_review_fixes.py -q
  29 passed
./.venv/bin/python -m pytest tests/preview/test_localized_names.py -q
  25 passed
```

추가한 대표 검사:

| 검사 | 확인 |
|---|---|
| `test_korean_only_injury_name_resolves_to_db_player_id` | 새 run 저장 모양(한국어·`player_id:null`) → `549/67971`·`139/389315` + 사진 URL 2건 |
| `test_english_only_injury_name_still_resolves_same_way` | 기존 run 저장 모양(영어) → 같은 ID·사진(회귀 없음), 표시 이름은 DB 한국어 값 |
| `test_partial_or_unknown_korean_name_is_not_guessed` | `게히`·`킹`·`없는 선수` → ID 없음(모호 매칭 금지) |

## 5. 두 실행의 photo 필드 결과(실제 READONLY 조회)

저장 원문은 **읽기만** 했고 쓰기·재생성은 하지 않았다.

| run | 선수 | player_id | external_player_id | photo_url |
|---|---|---|---|---|
| `6c2ce4c2`(기존) | 마크 게히 | 549 | 67971 | .../players/67971.png |
| `6c2ce4c2`(기존) | 앙투안 세메뉴 | 88 | 19281 | .../players/19281.png |
| `6c2ce4c2`(기존) | 톰 케어니 | 132 | 19025 | .../players/19025.png |
| `d96fe824`(새) | 마크 게히 | **549** | **67971** | **.../players/67971.png** |
| `d96fe824`(새) | 조슈아 킹 | **139** | **389315** | **.../players/389315.png** |

수정 전 새 run은 두 행 모두 `null`이었고, 수정 후 같은 저장 payload에서 ID·사진이 채워진다.
`조슈아 킹`의 외부 ID `389315`는 기존 주목 선수 카드가 정상 표시하던 것과 같은 값이다.

## 6. 남은 문제

1. **서버 재기동 필요**: 현재 8000 프로세스는 수정 전 코드로 떠 있다. root의 1회 재기동 후 위 투영이 화면에 반영된다(재기동은 이 워커 범위 밖).
2. **저장 payload 자체는 그대로다**: 새 run의 `structured.injuries[].player_id`는 여전히 `null`로 저장돼 있다. 화면 값은 읽기 투영에서 채워진다. 저장 payload를 고치려면 재생성이 필요하지만 지시 범위 밖이다.
3. 배당은 지시대로 재검사하지 않았다(새 버전 `08ed203a`·95.5h 미채택으로 정상 동작 확인된 상태).

EDITING STOPPED
