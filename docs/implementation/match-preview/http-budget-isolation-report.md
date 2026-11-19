# 프리뷰 HTTP 로직별 보호 몫 (HB-IMPL)

작성 2026-11-19. DeepSeek 구현 워커(task_f3a9ab597313 / ctx_e6344f96097c).
세션 모델 `deepseek-ai/deepseek-v4.1-flash-1017`·`hive`·`high`. 하위 워커 0.
명세 `docs/superpowers/specs/2026-11-19-preview-http-budget-design.md`,
계획 `docs/superpowers/plans/2026-11-19-preview-http-budget.md`.

## 결론

사용자 확정(기사·배당 **각 10**, 공유 **10**, 총 **30**)을 기존 `RunBudget`에 연결했다.
기사가 자기 몫 20회를 다 써도 배당 10회가 남고, 반대 순서도 같다. 총 30을 넘는 전송은
시작하지 않는다. **단순 전역 30 상한으로 올리지 않았다.** AI 정책(모듈 3회, 429
60/300/600·최대 4)과 배당 read-once는 **불변**이다.

## 1. 변경 전 결함 재현 (수정 전 실측)

기존 단일 `api_requests=24` 예산에서:

```
articles charged before block: 24
ODDS allowed: False | reason: API 요청 예산(24회)을 모두 사용했습니다.
```

→ 기사 수집이 예산을 전부 먹으면 **배당이 0회**가 된다. 사용자 영향: 배당 섹션이
비고(2026-11-19 Chelsea 실행에서 실제 관측), 기사 자료량에 따라 배당 표시가 사라진다.

## 2. 변경 (최소)

### 2-1. `app/preview/retry.py` — 보호 몫의 단일 소유자

- 상수: `HTTP_LOCAL_SHARE=10`, `HTTP_SHARED_SHARE=10`, `HTTP_TOTAL_LIMIT=30`,
  소유자 `articles`/`odds`.
- 필드: `http_used_by_owner`, `http_shared_used`, `http_owner_quotas`.
- 판정: `http_remaining(owner)`은 **자기 보호 잔여 + 공유 잔여**와 **총 상한 잔여** 중
  작은 값. 다른 소유자의 보호 몫을 침범하지 않는다.
- 예약/차감/반환: `http_reserve` / `http_charge` / `http_release`. 셋 다 **같은 `lock`**
  아래에서 `_http_consume`으로 총·소유자·공유 값을 **한 곳에서** 갱신한다.
  `http_release`는 **그 소유자 사용량에서만** 줄인다(다른 로직 몫을 늘리지 않는다).
- `for_generation`이 `http_owner_quotas=True`. **legacy `for_run`은 기존 24 단일 상한
  그대로**(`False`)라 legacy 경로가 새 정책에 잘못 들어가지 않는다.
- `snapshot()`에 `http_owner_quotas`, `http_total_limit`, `http_shared_used`,
  `http_owners{used, local_share, local_left, shared_used}` 추가 → 사용량을 설명할 수 있다.

### 2-2. `app/preview/retrieval.py` — 기사 HTTP 소유자 표기

기사 수집의 4개 판단 지점을 `owner=articles`로 통일: 사전 확인(`http_remaining`),
홉 게이트(`http_charge`), 예약(`http_reserve`), 반환 3곳(`http_release`).
`network_usage`의 `limit`/`remaining`도 같은 기준으로 보고한다.

### 2-3. `app/preview/bundle_pipeline.py` — 배당 HTTP 소유자 표기

제공자 배당 읽기의 `can_attempt`/`charge`를 `http_charge(owner=odds)`로 대체.
read-once guard 확인이 **차감보다 먼저**인 순서는 그대로다(보내지 않은 전송을 세지 않음).

`provider.py`는 **변경하지 않았다**(API 경계에서 소유 분류가 필요하지 않았다).

## 3. 변경 후 동작 (대표 실측)

```
articles used: 20 | odds remaining: 10
odds used: 10 | total: 30
reverse: odds used: 20 | articles remaining: 10
reverse: articles used: 10 | total: 30
```

실제 `collect_with_bodies` 경로(후보 25개, 정상 응답 대역):

```
article hops charged: 20 | total: 20
usable sources: 1
odds remaining: 10
odds charged after articles: True | total: 21
```

→ **실제 wiring**에서도 기사는 20에서 멈추고 배당 몫이 보존된다.

## 4. 직접 검사

`/Users/woolee/benchmark/.venv/bin/python -m pytest tests/preview/test_retry_budget.py
tests/preview/test_bundle_retrieval.py tests/preview/test_bundle_pipeline.py -q`
→ **74 passed, 1 skipped**. 로컬 `127.0.0.1:55432/preview_mp01_test`(`_dbguard`),
동시 pytest 없음 확인 후 1회 실행. `provider.py`를 바꾸지 않아 `test_provider.py`는
추가 실행하지 않았다. 기존 전체60/CF58은 관성 반복하지 않았다.

대표 검사:

- `test_articles_exhausting_their_share_leaves_ten_for_odds` — 기사 20 후 배당 10 확보.
- `test_reverse_order_reserves_ten_for_articles` — 반대 순서 동일 보장.
- `test_thirty_first_http_hop_is_blocked_and_reason_names_the_limit` — 31번째 차단.
- `test_http_release_returns_only_the_owner_share` — 반환이 다른 로직 몫을 늘리지 않음.
- `test_legacy_run_budget_keeps_the_single_api_cap` — legacy는 24 유지.
- `test_article_collection_caps_at_its_share_and_leaves_odds_share` — 실제 수집 경로.
- `test_provider_odds_uses_its_own_share_after_articles_are_exhausted` — 실제 배당 경로.

## 5. 보존 확인

- AI 정책 불변: `RATE_LIMIT_WAIT_SECONDS=(60,300,600)`, `RATE_LIMIT_MAX_SENDS=4`,
  `MODULE_SEND_CAP=3`, `MAX_ATTEMPTS_PER_CALL=3`. 모델 전송은 `charge`로 별도 집계.
- 배당 read-once 유지, 새 재시도·페이지 요청·새 API 호출 **추가 0**.
- 프롬프트·모델·정본계약·DB권한·legacy 24 정책 변경 0.

## 6. 미검증 / 다음 단계

- **실서버·실수집·실모델 0회.** 이번 단위는 구현·직접검사까지이며 서버 재기동·재수집은
  HB-LIVE 배정 몫이다. 두 경기 5섹션 E2E도 아직 미확인이다.
- **과거 City 첫 예외는 여전히 미확정**이다. 이번 수정은 HTTP 로직 간 간섭만 해결하며,
  그 실패의 원인 해결로 부르지 않는다(그 실패는 collection 단계였다).
- 공급자에 자료가 없는 경우까지 성공을 보장하는 정책은 아니다(명세 그대로).

## 7. 상태

- 변경 파일: `app/preview/retry.py`, `app/preview/retrieval.py`,
  `app/preview/bundle_pipeline.py`, `tests/preview/test_retry_budget.py`,
  `tests/preview/test_bundle_retrieval.py`, `tests/preview/test_bundle_pipeline.py`,
  이 보고서(untracked).
- root `collection-home-e2e-report.md`·Plans 미접촉, backup ref `79a5418` 보존,
  staged RB6 + 보완 unstaged 유지. reset/stash/stage/commit/push **0**.
- 운영 DB 쓰기·권한 변경·서버 재시작 **0**. 두 경기 5섹션 홈 정상 전 커밋 금지 유지.

## 8. HB-REVIEW 지적 보완 (2026-11-19)

독립검토 `/tmp/hb-review.md`의 **원지적 1건만** 수정했다. 참고 3건은 확대하지 않고
아래 8-3에 후속 참고로 보존한다.

### 8-1. 지적: 소유자 생략·오타 경로가 보호 몫을 우회

수정 전 실측(현재 코드):

```
A) None allowed: (True, None) -> used: 1
B) rogue used: 20 | shared_used field: 0
   articles after rogue: 10 | odds remaining: 0   ← 배당 완전 고갈
```

- `owner=None`이 조용히 legacy 24 기준으로 통과해 **두 로직의 보호 몫을 함께 잠식**했다.
- `HTTP_OWNERS`에 없는 이름(`rogue`)은 **없는 보호 몫 10**을 새로 받고, 공유 소진을
  `http_shared_used`에 집계하지 않아 실제 로직(배당)을 0회로 굶겼다.

### 8-2. 수정 (경계 한 곳)

- `_http_owner_is_known(owner)`: 보호 몫이 켜진 실행에서 `articles`/`odds`만 유효.
- `_http_owner_allowance`: 유효하지 않은 소유자는 **몫 0**.
- `http_charge`: 유효하지 않으면 `False` + 사유(`http_unknown_owner_reason`)를 돌려준다.
- `http_reserve`: 유효하지 않으면 **0**(예약 불성립).
- **legacy(`for_run`, `http_owner_quotas=False`)는 종전대로** 소유자 개념 없이 동작한다.

수정 후 실측:

```
None charge: (False, 'HTTP 요청 소유자가 지정되지 않았거나 등록되지 않아 전송하지 않았습니다: None (허용: articles, odds)')
None reserve: 0
rogue charge: (False, ... 'rogue' (허용: articles, odds))
rogue reserve: 0
after rejections total: 0 | shared: 0
articles remaining: 20 | odds: 20
```

유효 경로·legacy 보존 확인:

```
valid path: articles 20 odds 10 total 30
legacy quotas: False
legacy None charge: (True, None)   ← legacy 기존 동작 유지
legacy reserve None: 3
```

### 8-3. 참고 3건 — 이번에 고치지 않음(후속 참고로 보존)

1. `snapshot()`의 옛 필드 `api_remaining`이 여전히 24 기준이다. 새 `http_total_limit`(30)
   및 `http_owners`는 정확하고, 이 옛 필드를 읽는 제품·UI 소비자는 현재 없다(차단 아님).
2. `http_shared_used`는 `_http_consume`에서만 재계산되어 `http_release` 뒤에는 갱신되지
   않는다. 현 지원 경로는 두 HTTP 클라이언트 모두 `supports_hop_gate=True`라 release가
   실질 no-op이어서 드러나지 않는다(`http_owners[*].shared_used`는 정확).
3. `http_used_by_owner`·`http_shared_used`·`http_owner_quotas`가 `persistable()`/`restore()`
   에 없다. 복원을 쓰는 것은 legacy `pipeline.py`(`for_run`)뿐이고 bundle 생성 경로에는
   `restore` 호출이 없어 명세의 "현재 지원 경로가 있다면 유지" 조건에 해당하지 않는다.
   복원을 도입할 때 함께 넣어야 한다.

### 8-4. 검사

`pytest tests/preview/test_retry_budget.py -q` → **26 passed**(1회).

대표 검사 `test_unknown_or_missing_http_owner_is_refused_without_changing_counters`:
`None`·`rogue`·`Articles`·`""` 네 입력 모두 차감·예약에서 거부되고, 총량·공유·소유량·
잔량이 **전혀 변하지 않으며**, 유효 소유자는 정상 동작함을 확인한다.
**수정 전 코드로 되돌리면 이 검사가 실패**함을 변이로 확인했다(검사가 실제로 경계를 본다).

기존 74+1 전체 재실행·전체 회귀·실호출은 하지 않았다(지시대로 `test_retry_budget.py` 1회).

### 8-5. 이번 보완의 파일·해시

- `app/preview/retry.py` — sha256 `4ba655585c8941a2…`
- `tests/preview/test_retry_budget.py` — sha256 `5b9ebe41c8f5fd73…`
- 이 보고서
- `retrieval.py`·`bundle_pipeline.py`·`provider.py`는 **추가 변경 0**.
