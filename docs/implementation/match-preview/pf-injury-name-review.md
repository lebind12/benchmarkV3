# PF-B-NAMES 독립 검토 — 한국어 부상 이름의 ID/사진 연결

작성: 2026-11-12 KST. 담당: **별도 DeepSeek 읽기 전용 검토 세션**(Orca `dsh-tui`, 실제 세션 모델
`deepseek-ai/deepseek-v4.1-flash-1017`, 사용자 설정 추론 강도 Max 유지). 이 세션은 **backend
구현자와 다른 세션**이며 구현 워커가 아니다.

검토 입력: [pf-injury-korean-name-report.md](pf-injury-korean-name-report.md)(PF-B 2차 구현 보고).
검토 범위: `app/preview/localized_names.py`의 한국어 정확 일치 규칙과
`tests/preview/test_bundle_review_fixes.py`의 한글/영문/부분이름 대표 3검사 **뿐**이다.
그 밖의 backend 지적·배당·프론트엔드는 보지 않았고 평가하지 않았다.

이 세션이 저장소에 쓴 파일은 **이 보고서 1개**다. 제품·테스트·`Plans.md`·설정 편집 **0건**,
파일 쓰기 0, 새 재현 스크립트 0, 전체 검사 0, 서버·DB·HTTP·브라우저 호출 0, 커밋 0, 하위 워커 0.
`pytest`는 실행하지 않았다(아래 §3 근거).

## 0. 결론

**차단 없음.** 수용 기준 5개가 코드와 독립 실행으로 확인됐다.

| 수용 기준 | 판정 | 근거 |
|---|---|---|
| 한글 `마크 게히`/`조슈아 킹` → 같은 경기 DB 내부 ID | **충족** | 정확 일치 등급 0이 `name_ko`/`short_name_ko`와 비교(`localized_names.py` 508~516행). 독립 probe에서 `549` 확인 |
| → 검증 외부 ID → 주목 선수와 동일 media 사진 | **충족** | `67971`(게히)·`389315`(킹)가 기존 주목 선수와 같은 외부 ID. 기존 문서·증거와 일치(§2-2) |
| 기존 영어 입력 유지 | **충족** | 영어 분기(등급 1~5) 무변경. `Marc Guéhi` → `549` probe 확인 |
| 애매·부분 이름 추정 금지 | **충족** | `게히`·`킹` → `None`. 동명이인 동률 → `AMBIGUOUS`(§2-4) |
| 저장 원문 무변경 | **충족** | diff가 `_match_rank` 읽기 비교만 추가(+17행). 쓰기 경로 없음(§2-1) |
| 작성/읽기가 같은 resolver | **충족** | 두 경로 모두 `DisplayNames.resolve_player`에 도달(§2-5) |

## 1. 확인한 파일

| 파일 | 내용 |
|---|---|
| `app/preview/localized_names.py` | 추적 중 파일, `git diff` = **+17행 / -0행**(§2-1) |
| `tests/preview/test_bundle_review_fixes.py` | 현재 미추적 파일. 대표 3검사 1126~1200행 |

검토 시점 이후 이 세션은 두 파일을 **쓰지 않았다**. backend 구현자가 같은 test 파일의 배당 부분을
수정할 수 있는 상태이므로 파일 쓰기·재현 스크립트 생성은 하지 않았다.

## 2. 수용 기준별 대조

### 2-1. 변경이 최소이고 저장 원문을 건드리지 않는가

```
git diff -- app/preview/localized_names.py
→ 1 file changed, 17 insertions(+), 0 deletions(-)
```

추가된 것은 두 곳뿐이다. ①`_match_rank` docstring에 등급 0 설명 ②한국어 정확 일치 분기.

```python
if tokens and _has_korean(str(row.name_ko or "") + str(row.short_name_ko or "")):
    for korean in (row.name_ko, row.short_name_ko):
        if korean and _tokens(korean) == tokens:
            return 0
```

- 읽기 비교만 한다. 저장 payload·DB·본문 문자열을 쓰거나 바꾸는 코드가 없다.
- 새 문자열·번역·음차·ID 하드코딩이 없다(`마크 게히`·`549` 같은 값이 코드에 없다).
- **NFKD 함정을 정확히 피했다.** `normalize_name`이 음절을 자모로 분해하므로(독립 확인:
  `_tokens('마크 게히')` → `('마크', '게히')`), 한국어 여부는 **원문**(`row.name_ko`)으로
  판정하고 동등성만 정규화 토큰으로 본다. 보고 §1의 서술과 코드가 일치한다.

### 2-2. 한글 이름 → 내부 ID → 외부 ID → 사진

독립 probe(저장소 코드만 import, DB·네트워크 0):

```
'마크 게히'  → player_id 549
'Marc Guéhi' → player_id 549
```

외부 ID·사진 값 `67971`/`389315`는 이 세션이 만든 값이 아니라 **기존 문서·증거에서 이미 확인된
값**과 대조했다.

| 근거 출처 | 값 |
|---|---|
| `home-preview-mock-brief.md` 31·34행 | 조슈아 킹 `139`/`389315`, 마크 게히 `549`/`67971` |
| `home-preview-mock-report.md` 84행 | 사진 URL 규칙과 `389315`·`67971` |
| `pf-backend-report.md` 39·115행 | `Marc Guéhi 549/67971`, 기존 run 3명 photo 3건 |

즉 보고 §5의 표는 **기존에 수용된 주목 선수 카드의 외부 ID와 같은 값**이며, 새 ID를 만들지 않았다.
`조슈아 킹 389315`가 주목 선수 카드와 동일하다는 보고 §5의 진술도 위 근거와 모순이 없다.

### 2-3. 기존 영어 입력 유지

영어 분기(등급 1~5)는 `git diff`에서 **한 줄도 바뀌지 않았다**. 한국어 분기는
`_has_korean(저장된 name_ko/short_name_ko)`가 참일 때만 진입하므로, DB 한국어 값이 없는 로스터에서는
기존 경로가 그대로다. 독립 probe로 `Marc Guéhi → 549`를 확인했다.

### 2-4. 애매·부분 이름 추정 금지

독립 probe(코드 직접 호출):

| 입력 | 결과 |
|---|---|
| `게히` | 일치 없음(`None`) — 부분 표기로 ID를 만들지 않음 |
| `킹` | 일치 없음 |
| `마크게히`(공백 없음) | 일치 없음 — 음절 부분 일치를 흡수하지 않음 |
| `마크  게히`(공백 2개) | `549` — 공백 정규화만 흡수(표기 차이) |
| 한국어 값이 없는 로스터에 `마크 게히` | `None` — 영어 표기로 되돌아가 추정하지 않음 |
| 다른 선수의 한국어 값과만 같은 입력 | 해당 선수로 붙지 않음 |

동명이인 처리도 확인했다. 같은 `name_ko`(김 철수)를 가진 두 선수를 두면 범위 조회는
`AMBIGUOUS`로 **ID를 만들지 않고**, 팀 힌트가 있을 때만 그 팀 로스터로 좁혀 1명을 고른다.
이는 기존 `resolve_player`의 동률 규칙(정확히 1명일 때만 채택)을 그대로 쓰는 결과이며 새 추정을
추가하지 않는다. 읽기 경로의 `StructuredIdContext`도 후보가 둘 이상이면 `None`을 돌려준다.

### 2-5. 작성·읽기가 같은 resolver를 쓰는가

두 경로가 **같은 클래스의 `resolve_player`** 에 도달함을 코드로 확인했다.

| 경로 | 호출 사슬 |
|---|---|
| 작성 | `bundle_sections._verified_injury_player` → `resolver.resolve_player(...)` → `sections._ResolverHandle.resolve_player` → `localized_names.DisplayNames.resolve_player` → `_match_rank` |
| 읽기 | `preview_admin.get_section_results` → `StructuredIdContext(player_by_name)` → `self._names.resolve_player(...)` → `DisplayNames.resolve_player` → `_match_rank` |

- 작성 경로의 `resolver`는 `bundle_pipeline._open_name_resolver` → `sections._name_resolver` →
  `_ResolverHandle`이며, 그 내부가 `DisplayNames(load_name_index(...))`다(`sections.py` 1184~1199행).
- 읽기 경로의 `names`는 `_display_names_for` → `open_display_names` → `DisplayNameBridge.names`
  (동일 `DisplayNames`)이며, 범위는 이 경기 두 팀으로 한정된다(`preview_admin.py` 1162~1166행).
- 즉 **한 곳(`_match_rank`) 수정이 두 경로를 동시에 고친다**는 보고 §2의 주장은 코드와 일치한다.
  다른 파일을 고치지 않은 것도 이 구조상 타당하다.

## 3. 보고된 검사 증거의 취급

- 보고 §4의 `.venv/bin/python -m pytest tests/preview/test_bundle_review_fixes.py -q → 29 passed`
  와 `tests/preview/test_localized_names.py → 25 passed`를 **유효 근거로 재사용**했다. 대표 3검사의
  내용(1126~1200행)과 보고 §4의 표가 서로 맞고, 모순이나 누락을 발견하지 못했으므로 재실행하지 않았다.
- 현재 파일에는 `def test_`가 **32개**이고 skip/xfail/parametrize는 0건이다. 보고 시점(21:29) 이후
  파일 mtime이 21:34로 바뀌었으므로, 이 차이는 **다른 워커가 같은 파일에 배당 부분 검사를 추가로
  쓰고 있는 중**이라는 사실과 일치한다. 이번 검토 범위(대표 3검사)와 무관하므로 재실행·판정하지 않았다.
- 이 세션은 `pytest`를 실행하지 않았다(파일 쓰기·서버·DB 호출 금지, 그리고 동시 편집 중인 파일을
  검증 근거로 삼지 않기 위해). 대신 **순수 함수 단위 probe**(저장소 모듈 import만, DB·네트워크 0)로
  §2-2·§2-4의 동작을 독립 확인했다.

## 4. 지적 사항

**차단 항목 없음.** 아래는 참고이며 이번 수용을 막지 않는다.

### 4-1. [참고 · 이번 변경과 무관] 동명이인은 팀 힌트가 있을 때만 좁혀진다

같은 한국어 표기를 가진 두 선수가 같은 범위에 있으면, 팀 힌트가 없을 때는 `AMBIGUOUS`로 남는다
(의도된 안전 동작). 부상 행에는 저장 payload에 `team`이 있어 대부분 힌트가 있으므로 실사용에서는
좁혀진다. 힌트가 비어 있는 행만 ID가 비는데, 이는 **추정 금지** 기준에 맞는 결과다. 조치 불필요.

### 4-2. [참고 · 이번 변경과 무관] 짧은 한국어 이름의 부분 일치 위험은 늘지 않았다

한국어 분기는 **정확 일치**만 보므로 `게히`·`킹` 같은 2자 표기가 다른 선수에 붙지 않는다(§2-4).
본문 치환(`rewrite_body`) 쪽의 짧은 표기 규칙은 이번 변경 대상이 아니며 손대지 않았다.

### 4-3. [사실 확인] 보고 §6의 "서버 재기동 필요"는 이번 검토 범위 밖이다

보고 스스로 밝힌 대로 현재 8000 프로세스는 수정 전 코드다. 재기동·화면 확인은 root 담당이며,
이 검토는 코드와 순수 함수 동작까지만 판정했다.

## 5. 확인하지 못한 것

- **실제 화면**은 보지 않았다(브라우저 호출 0). 사진 렌더 확인은 root 담당이다.
- **DB 실조회**를 하지 않았다(호출 0). 보고 §5의 READONLY 조회 결과는 구현 워커의 증거를 재사용했다.
- 저장 payload 자체가 `player_id: null`로 남는 문제(보고 §6-2)는 재생성 없이는 바뀌지 않는다.
  이는 읽기 투영으로 화면을 고치는 현재 설계의 한계이며 이번 수용 기준 위반이 아니다.
- 배당·프론트엔드·다른 backend 지적은 지시대로 **검토하지 않았다**.

## 6. 실행 명령

```
# 읽기 (코드·보고·근거 대조)
git status --short app/preview/localized_names.py tests/preview/test_bundle_review_fixes.py
git diff -- app/preview/localized_names.py            # +17 / -0
grep -n "_match_rank\|_tokens\|_has_korean" app/preview/localized_names.py

# 순수 함수 probe (저장소 모듈 import만, DB·네트워크·파일 쓰기 0)
./.venv/bin/python - <<'PY'
# _match_rank / DisplayNames.resolve_player 직접 호출로 §2-2·§2-4 확인
PY
→ '마크 게히' → 549, 'Marc Guéhi' → 549
→ '게히' / '킹' / '마크게히' → None
→ 동명이인 두 명 + 힌트 없음 → AMBIGUOUS, 힌트 있음 → 1명
→ 한국어 값 없는 로스터에 '마크 게히' → None
```

`pytest` 전체 검사·새 재현 스크립트·서버·DB·HTTP·브라우저 호출은 **0회**다.

EDITING STOPPED
