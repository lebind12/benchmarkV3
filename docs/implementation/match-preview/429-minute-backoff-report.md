# 429 분 단위 재시도와 매체 전망 실패 사유 (RB-IMPL)

작성 2026-11-19. 실행 주체: DeepSeek 구현 워커(task_6916d91024c4 / ctx_95655c4520b8).
세션 모델 `deepseek-ai/deepseek-v4.1-flash-1017`, provider `hive`, 추론 강도 `high`.
하위 워커 0, root `Plans.md` 편집 0. 명세: `docs/superpowers/plans/2026-11-19-429-minute-backoff.md`.

## 결론

429 전용 재시도를 **60/300/600초 고정 구간, 최초 포함 최대 4회 전송**으로 구현했고,
다른 오류·내용 재생성 상한은 그대로 뒀다. SDK 오류 본문(`details`/`response`)과
RetryInfo·Retry-After를 실제로 읽고, attempt 시각을 실제 시계로 남기며, 매체 전망 실패
사유를 "기사 근거 없음"으로 단정하지 않게 고쳤다.

## 1. 착수 확인

- HEAD `f6c7876`(제품 `7a3804a`, 테스트 `3e23207`), 워크트리 미커밋은 root 소유
  `collection-home-e2e-report.md` 1건뿐이며 **건드리지 않았다**(stash·커밋 0).
- AP-LIVE 관측은 종료했다(추가 AP 조회·POST 0회). 같은 세션에서 편집 소유를 이어받았다.

## 2. 변경

### 2-1. 429 대기 구간과 전송 상한 (`app/preview/retry.py`)

- `RATE_LIMIT_WAIT_SECONDS = (60, 300, 600)`, `RATE_LIMIT_MAX_SENDS = 4` 추가.
- `rate_limit_wait_seconds()`: 구간을 **고정**으로 돌려주고 jitter로 단축하지 않는다.
  공급자의 유효 안내가 더 길면 `max(구간, 안내)`로 **최소 대기**만 올린다.
  구간을 다 쓴 뒤에는 마지막 값(600초)을 유지한다(무한 증가 없음).
- `RunBudget.rate_limited_by_module` 카운터와 `note_rate_limited()`/`rate_limit_sends()`
  추가. **429로 끝난 전송 수**가 근거다.
- `can_attempt`: 모듈 상한 경로와 legacy `attempts_per_call` 경로 **둘 다**에서, 429 이력이
  있으면 상한을 최대 `RATE_LIMIT_MAX_SENDS`까지 연다. 다른 오류·내용 재생성은 기존 값.
- `effective_model_requests`: 429로 열린 몫만 합계에 더한다(모듈 상한만 열고 전체 상한이
  막는 두 번째 병목을 만들지 않는다).

### 2-2. 재시도 루프 (`app/preview/provider.py`)

- 429(`http_status == 429` 또는 `error_class == rate_limited`)면
  `rate_limit_wait_seconds()`를, 그 밖의 오류는 기존 `bounded_wait_seconds()`를 쓴다.
- 루프 머리의 `ordinal >= attempt_limit` 검사와 재시도 직전 검사 모두 429에 한해
  `RATE_LIMIT_MAX_SENDS`까지 허용한다. **중첩 루프는 만들지 않았다**(루프는 하나).

### 2-3. SDK 오류 본문·재시도 안내 (`provider.GoogleGenAIHttpTransport.send`)

- 기존 코드는 `getattr(exc, "response_json", None)`을 읽었는데, 설치된 google-genai
  3.0 `errors.APIError`는 `details`(본문)와 `response`(HTTP)만 갖고 `response_json`이
  **없다**(`inspect`로 확인). 그래서 오류 본문·RetryInfo가 버려지고 있었다.
- `_api_error_payload()`: `details` → `response.json()` 순으로 실제 본문을 꺼낸다.
- `_retry_after_from_response()`: `Retry-After` 헤더(숫자 초)를 읽는다.
- `_api_error_message()`: 본문의 `error.message`를 우선한다.
- 비밀값은 담지 않는다(기존 redaction 경로 그대로).

### 2-4. 실제 호출 시각 (`bundle_sections._call_model`, `provider.execute_request`)

- `bundle_sections`는 예산 판정용 `now=lambda: moment`를 **그대로** 두고,
  `timestamp_clock=_wall_clock`을 추가로 넘긴다.
- `execute_request`는 `stamps = timestamp_clock or now`로 attempt의 `started_at`/`finished_at`
  만 실제 시계에서 읽는다. **예산·기한 판정의 시간축은 바꾸지 않았다**(그렇게 바꾸면
  기존 검사들이 실행 기한 판정으로 깨졌고, 실제로 한 번 깨뜨려 되돌렸다).

### 2-5. 매체 전망 실패 사유 (`bundle_sections._outlook_section`)

본문이 비었을 때 세 갈래로 구분한다.

| 상황 | 사유 |
|---|---|
| 모델 호출 실패(`call.text is None`) | "외부 매체 전망 모델 호출이 성공하지 않아 …" + 실제 stopped_reason |
| 입력 자료 자체가 없음 | "수집 기사 본문과 검색 자료가 모두 없어 … 요청을 보내지 않았습니다" |
| 정상 응답에 채택 항목 없음 | "모델 응답에 채택 가능한 외부 매체 전망 항목이 없어 …" |

이전에는 세 경우 모두 "수집 기사에서 확인된 외부 매체 전망이 없어"였다. 실제 R3는
429로 소진됐고 입력은 3출처/7구간·검색 8건 8071자였으므로 그 문구는 오표기였다.

## 3. 직접 검증

로컬 전용(`127.0.0.1:55432/preview_mp01_test`)이며 `_dbguard`가 루프백·`*_test`를 먼저
검사한다. 운영 DB 초기화·fixture 없음, 동시 pytest 없음.

구분: **정적 정의 수**(`def test_` 개수)와 **실행 결과**(pytest 출력)는 다른 값이다.
아래 표의 실행 결과는 이번 RB-FIX 시점에 3파일을 1회 실행한 출력이다.

| 파일 | 정적 정의 수(고정 `79a5418`) | 실행 결과 |
|---|---|---|
| `tests/preview/test_provider.py` | 21 → **23**(RB-FIX 신규 2) | 23 passed |
| `tests/preview/test_retry_budget.py` | **20** | 20 passed |
| `tests/preview/test_bundle_sections.py` | 17 | 17 passed |
| **합산** | **60** | **60 passed** (6.9초) |

정정 이력: 앞선 판에 `test_retry_budget.py`를 **19 passed**, 합산을 **57 passed**로 적었으나
정적 정의 수가 20건이고 실행도 20 passed여서 **두 수치 모두 오기**였다(독립검토 지적).
RB 이전 시점의 합산은 58(21+20+17)이 맞다.

수용 기준별 대표 검사:

1. `test_429_exhaustion_uses_60_300_600_and_allows_fourth_send` — 429 4회에서
   `slept == [60.0, 300.0, 600.0]`, `transport.calls == 4`.
2. `test_non_429_errors_keep_the_three_attempt_cap` — 503 반복은 **3회**에서 멈춘다
   (일괄 증가 없음). `test_sdk_api_error_keeps_body_and_retry_hint` — SDK 오류의
   `details`/`RetryInfo`(180초)·`Retry-After`(120초) 보존.
3. `test_attempt_timestamps_come_from_the_timestamp_clock` — 두 시도의 시작 시각이 서로
   다르고 고정 예산 시각과도 다르다.
4. `test_outlook_transport_failure_is_not_reported_as_missing_articles` /
   `test_outlook_empty_forecasts_from_successful_response_are_distinguished` — 호출 실패와
   정상 응답의 빈 전망을 구분한다.
5. 코드 확인: 요청별 타임아웃은 `MODEL_TIMEOUT_SECONDS=300`/`API_TIMEOUT_SECONDS=30`,
   수집 실행은 백그라운드 스레드(`threading.Thread`)로 돌고 Vite 프록시는
   `timeout: 0`이라 16분 대기가 HTTP 응답을 끊지 않는다. 새 큐·인프라는 만들지 않았다.

### 기존 검사 조정(사유 포함)

- `test_429_then_success_two_attempts`: 429 첫 대기가 3초 → **60초**로 바뀐 계약을 반영
  (`wait_ms` 3000 → 60000). Retry-After가 짧아도 구간을 깎지 않는다는 새 정책의 직접 증거다.
- `tests/preview/test_bundle_sections.py`에 autouse `_no_real_sleep` 픽스처 추가: 429 구간이
  분 단위가 되어 그 파일의 429 재현 검사가 실제로 16분을 자게 됐다. 검사 대상은 **정책**이지
  실대기가 아니므로 대기를 건너뛰고, 대기 값 검증은 provider 검사가 담당한다.

## 4. 미검증 / 남은 제약

- **실제 16분 대기와 실모델 429 재현은 하지 않았다**(명세 제외). 실서버 반영·실행 확인은
  별도 단계다. 이 구현 완료를 실서버 적용으로 주장하지 않는다.
- 대기 중 **취소**는 기존처럼 대기가 끝난 뒤 다음 시도에서 관측된다(대기를 깨우는 취소
  신호는 이번 범위에 없다). 현재 실행을 막는 충돌은 아니지만 남는 제약으로 기록한다.
- `bounded_wait_seconds`의 60초 상한은 **429 아닌 오류**에 그대로 남아 있다(의도).
- SDK 오류 본문 보존은 단위 검사(모의 APIError)로만 확인했고, 실제 Vertex 429 응답의
  RetryInfo 존재 여부는 이번에 호출하지 않아 미확인이다.
- **검사 간헐 실패(내 변경과 무관, 보고에 남김).** 반복 실행 중 `preview_mp01_test`의
  `DROP SCHEMA ... CASCADE`가 `lock_timeout(10s)`으로 실패하는 경우가 있었다. 원인은
  코드가 아니라 **같은 테스트 DB에 남은 다른 세션**(`idle in transaction`)과 겹친 실행이었다
  (변경을 stash한 기준선에서도 동일하게 발생). 동시 pytest를 만들지 않고 세션이 정리된 뒤
  연속 4회는 58 passed로 안정적이었다. 간헐 실패는 제품 회귀로 보지 않는다.

## EDITING STOPPED

수정 파일: `app/preview/retry.py`, `app/preview/provider.py`,
`app/preview/modules/bundle_sections.py`, `tests/preview/test_provider.py`,
`tests/preview/test_bundle_sections.py`, 이 보고서. 제품 프롬프트·모델·버전·UI 변경 0,
승인·수집 POST·실모델·운영 DB 쓰기·서버 재기동 0회. root 미커밋 문서와 `Plans.md` 보존.

## 5. RB-FIX 독립검토 지적 보완 (2026-11-19)

독립검토 `/tmp/rb-review.md`의 지적 중 **D1·R1·보고서 수치 오기** 3건만 보완했다.
참고 개선 3건은 지시대로 확대하지 않았다. **커밋 금지 조건 유지**(작업트리 diff로 인계).

### 5-1. D1 — 혼합 흐름에서 4번째 전송이 막히던 경계

이전 판정은 `429로 끝난 수 >= 전송수 - 1`을 요구해, `429 → 503 → 429`처럼 중간에 다른
오류가 끼면 3번째에서 막혔다(대기 600초 구간에 도달 불가).

- 원인: 판정 근거가 "429 누적 수"였고, 직전 실패의 성격을 보지 않았다.
- 수정: `RunBudget.last_was_rate_limited`를 두고 **직전 실패가 429일 때만** 4번째를 연다.
  `note_rate_limited()`가 True, `note_non_rate_limit_failure()`가 False를 기록한다.
- 적용 지점 3곳을 같은 규칙으로 맞췄다: `can_attempt`(모듈 상한 경로),
  `can_attempt`(legacy `attempts_per_call` 경로), `provider`의 `loop_ceiling`, 그리고
  `effective_model_requests`의 추가 몫 계산.
- **늘이지 않은 것**: 429가 아닌 오류만 반복하면 기존 3회(`attempt_limit`) 그대로이고,
  3번째가 비429로 끝나면 4번째를 열지 않는다. 최대값은 `RATE_LIMIT_MAX_SENDS=4`를 넘지 않는다.
- 대기 구간은 지시대로 **시도 서수 기준** 60/300/600을 유지한다. 혼합 흐름에서 비429
  시도의 대기는 기존 `bounded_wait_seconds`(짧은 지수 대기) 정책 그대로다.

검증: `test_mixed_429_and_other_errors_still_reach_four_sends`(429→503→429→429에서 4전송,
`slept == [60.0, <60, 600.0]`), `test_non_429_failure_after_429_does_not_open_a_fourth_send`
(429 뒤 503 반복은 3전송에서 정지).

### 5-2. R1 — R3 소진 사유에 429가 문구로 드러나지 않던 문제

`provider`의 소진 문구가 `시도 상한(N회)에 도달했습니다`뿐이라, 429 소진인지 다른 오류인지
문구만으로 알 수 없었다.

- 수정: 소진 사유에 **마지막 실패의 실제 상태·분류**를 덧붙인다.
  `… 도달했습니다(마지막 실패: HTTP 429 rate_limited).`
- 비밀 원문·오류 본문은 넣지 않는다(상태 코드와 분류 이름만).
- 기존 검사 `test_outlook_transport_failure_is_not_reported_as_missing_articles`에
  `429`·`rate_limited` 단언을 추가해 회귀를 고정했다.

### 5-3. 보고서 수치 정정

§3 표의 `test_retry_budget.py 19 passed`와 합산 `57 passed`가 오기였다(정적 정의 20건,
실행도 20 passed). 정적 정의 수와 실행 결과를 **분리한 표**로 고쳤고, 정정 이력을 남겼다.
RB-FIX 후 합산은 60 passed다.

### 5-4. 직접 검사 (1회)

`pytest tests/preview/test_provider.py tests/preview/test_retry_budget.py tests/preview/test_bundle_sections.py -q`
→ **60 passed** (6.9초). 로컬 `127.0.0.1:55432/preview_mp01_test`, `_dbguard` 통과,
실행 전 동시 pytest 0·테스트 DB 다른 세션 0을 확인했다. 전체 회귀·연속 반복·새 변이는 하지 않았다.

## EDITING STOPPED (RB-FIX)

수정 파일: `app/preview/retry.py`, `app/preview/provider.py`,
`tests/preview/test_provider.py`, `tests/preview/test_bundle_sections.py`, 이 보고서.
(`app/preview/modules/bundle_sections.py`는 R1 문구가 이미 있어 이번에 추가 변경 없음.)

**커밋·push 0.** 사용자 종료 조건에 따라 모든 변경은 **staged(기존 RB 6파일) + 이번 수정**으로
작업트리에만 남긴다. root `collection-home-e2e-report.md`·`Plans.md`는 건드리지 않았고
stash도 하지 않았다. 서버 재시작·수집·실모델·운영 DB 쓰기 0회.
