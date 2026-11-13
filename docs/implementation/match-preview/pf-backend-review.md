# PF-R-B — PF-B 백엔드 변경 독립 검토

작성: 2026-11-12 KST. 역할: PF-R의 backend 담당 독립 검토자(읽기 전용).
실제 모델 `deepseek-ai/deepseek-v4.1-flash-1017`(dsh-tui, Max 유지).
검토 범위: PF-B 변경 6파일 + 계획·구현 보고서. frontend는 다른 독립 검토자 소유이므로 제외.
이 문서 외의 제품·테스트·저장 결과·DB·설정은 수정하지 않았다.

> **개정 이력(중요).** 1차 검토(21:0x) 후 **다른 세션이 제품 코드를 수정**했다
> (`sources/provider_odds.py` 21:11·21:14, `bundle_pipeline.py` 21:13·21:17,
> `modules/bundle_sections.py` 21:15, `version_manifest.py`, `tests/preview/test_bundle_review_fixes.py` 21:17
> — 이 워커가 아니다. 상세는 `docs/implementation/match-preview/pf-odds-fix-report.md`, 후속2).
> 그래서 이 문서는 1차 판정을 그대로 두지 않고, **현재 작업 트리 기준으로 다시 읽고 재검증한
> 결과**로 개정했다. 1차에 차단으로 본 두 항목(배당 보충 호출 조건, `/odds` 해석 예외 전파)은
> **현재 코드에서 이미 고쳐져 있고 회귀 테스트도 함께 들어왔다.** 아래 §3.4·§3.6·§4.1·§5·§6이
> 그 재검증 근거다.
>
> **2차 확인(2026-11-14 01:5x, 이 워커).** 그 뒤 제품이 또 바뀌어 아래 문장 중 일부가
> **더 이상 사실이 아니다.** 이 검토 문서(11-12 21:25) 이후 수정: `sources/provider_odds.py`
> 11-12 21:33, `bundle_pipeline.py` 11-12 22:24, `section_structured.py` 11-12 22:54,
> `version_manifest.py` **11-13 05:30**. 그래서 **원 판정 문장은 지우지 않고**
> ("과거판정 덮어쓰기 금지" 지시 준수) §4.2에 현재 값과 차이를 따로 적는다. 요약:
>
> - 배당 **채택 정책이 v1(6시간 신선도) → v2(업체별 최신 갱신값 채택)** 로 바뀌어,
>   `PROVIDER_ODDS_IMPLEMENTATION_VERSION`이 `mp11-provider-odds-1` → **`mp11-provider-odds-2`**다.
> - 그래서 아래 §1의 "6시간 규칙 때문에 0행"과 워크플로우 버전 문자열(`section_odds@08ed203a…`,
>   `section_availability@643296ca…` 등)은 **현재 값이 아니다**. 현재는 `section_odds@49923b1c5dcb467a` 등.
> - 이 검토의 **판정(차단 없음, 참고 항목)은 바뀌지 않는다.** 코드 경로·범위 제한·null 규칙은 그대로다.

## 1. 결론 (현재 작업 트리 기준)

**차단 없음.** 1차 검토에서 차단으로 본 두 항목은 1차 보고 후 다른 세션이 수정했고,
이 워커가 현재 코드로 **재검증해 닫힌 것을 확인**했다. 나머지 참고 항목은 표시 결과를 바꾸지 않는다.

닫힌 차단 항목(1차 → 현재):

1. **배당 보충 호출 조건**(1차 차단) → `provider_odds.has_remaining_slots()`
   (`provider_odds.py:96`)로 바뀌어 **공개 표 채택 업체가 3개 미만이면** 제공자를 읽는다.
   두 호출 지점(`bundle_pipeline.py:1073` 생성, `:2394` 재생성)이 같은 판정을 쓴다.
   재검증: 공개 0/1/2행 → `has_remaining_slots=True`, 3행 → `False`. 같은 업체 중복 1행으로 셈,
   값이 불완전한 줄은 세지 않음. 즉 계획의 "남는 자리를 채워 최대 3행"이 이제 실제로 실행된다.
2. **`/odds` 해석 예외 전파**(1차 참고·권고) → `read_provider_odds`가
   `parse_envelope`/`parse_odds`의 `ApiFootballError`·`WrongFixture`를 **사유로 흡수**한다
   (`provider_odds.py:306`, `:328`, `:334`). 재검증: bookmakers 객체 형태·다른 경기·잘못된
   시각 3종 모두 예외 없이 `sent=1·available=false` + 사유로 돌아왔다.
   내부 버그까지 삼키지 않도록 `ApiFootballError` 계열만 잡는 경계도 적절하다.

동시에 **계획이 요구한 "실행당 1회"도 실제로 강제**하게 됐다: `ReadOnceGuard`
(`provider_odds.py:105`) + `read_provider_odds_once`(`:364`)로 병렬 갈래가 동시에 도달해도
실제 요청은 하나다. 재검증: 같은 guard로 두 번 호출 → 첫 회만 시도(`sent=0`, 키 없음),
두 번째는 "이미 한 번 시도" 사유로 요청 0회.

**PF-KEY 후속 근거(별도 워커).** 키 부재 전제는 해소됐다
(`pf-key-report.md`: 기존 Koyeb secret 재사용 → `/odds` 1회 HTTP 200, 북메이커 9곳,
pre-match 1X2 9행, 경기 id 일치). 다만 레코드 `update`가 `2026-11-08T12:52:18Z`(94.2시간 전)이고
업체별 `book.update`가 없어 `odds_freshness`(`ODDS_FRESH_HOURS=6`)가 **9행 전부를 거부**했고
`sent=1·available=false·quotes=0`이다. 즉 실제 배당 0행의 원인은 코드가 아니라
**제공자 자료의 신선도 + 기존 6시간 채택 규칙**이며, 기준 완화는 정책 승인 사항이다.
이 검토는 신선도 규칙의 타당성을 판정하지 않는다.

| 구분 | 건수 | 항목 |
|---|---|---|
| 요구사항 위반 | 0 | (1차 차단 2건은 현재 코드에서 닫힘 — 위 1·2) |
| 참고(정책 판단 필요) | 1 | 6시간 신선도 규칙 때문에 실제 배당 표시가 여전히 0행 |
| 참고(기존 경로 미해결) | 2 | 저장 payload 충돌 ID가 있는 과거 저장본은 다른 선수 사진 / `team_id` 출처 미검증 |
| 참고(정직성·표시) | 2 | 제공자 줄도 "공개 사이트" 문구로 표시 / 전송 장부에 `/odds` 미기록·미전송 차감 |
| 정상 확인 | — | 부상 이름→ID·사진 연결, 범위 제한, 기존 payload 무변경, GET 무호출, 모델 0회, 비밀값 비노출 |

## 2. 검토한 파일과 실제 경로

계획·보고서가 적은 경로와 실제 경로가 **2건 달랐다**(검토 시 정정).

| 보고서·과제 표기 | 실제 경로 |
|---|---|
| `app/preview/modules/section_structured.py` | `app/preview/section_structured.py` (modules 아님) |
| `app/preview/modules/bundle_pipeline.py` | `app/preview/bundle_pipeline.py` (modules 아님) |

나머지 4개는 표기와 일치: `app/preview/modules/bundle_sections.py`,
`app/preview/sources/provider_odds.py`(신규), `app/api/v1/preview_admin.py`,
`tests/preview/test_bundle_review_fixes.py`.

읽기 전용 확인: 위 6파일 + `section_preview.py`, `display_names.py`, `localized_names.py`,
`retry.py`, `information_bundle.py`, `contracts.py`, `store.py`, `sources/api_football.py`,
`version_manifest.py`, `approvals.py`, `registry.py`, `frontend/src/lib/api/previewView.ts`,
`frontend/src/features/match-preview/sectionStructured.ts`.
DB 쓰기·외부 HTTP·키 조회·서버 재기동·제품 편집은 하지 않았다.

## 3. 수용 기준별 확인

### 3.1 이름만 있는 저장본에서 한글명/외부ID/사진 연결 — 확인

- `bundle_sections._verified_injury_player()`(`bundle_sections.py:1684`)는 모델이 적은 **이름**만
  `resolver.resolve_player(name, team_hint=..., scope_team_ids=...)`로 확인하고, 모델이 적은 숫자는
  신뢰 ID로 쓰지 않는다(`id_is_hint` 미사용). 확인 결과는 `(player_id, display_name)`뿐이다.
- 범위는 `_scope_team_ids()`(`bundle_sections.py:1263`)가 만든 **이 경기 두 팀 내부 ID**로 고정된다.
  호출은 `bundle_sections.py:1984`에서 `fixture_values`로만 만들어진다.
- 모델 숫자와 확인 ID가 다르면 ID를 비우고 진단을 남긴다(`bundle_sections.py:1792-1800`).
  확인되지 않으면 ID 없이 이름만 남긴다(`:1809-1822`).
- 저장 payload에 `player_id`/`team_id`를 함께 남긴다(`bundle_sections.py:1993-2013`).
- 기존 저장본(이름만 있음)은 `section_structured._injuries()`(`section_structured.py:344-354`)가
  재읽기에서 ID·외부 ID·사진을 채운다. 저장 원문은 건드리지 않는다(투영만).
- 실제 재현(읽기 전용, 이 워커 로컬 합성 인덱스): 중첩 payload
  `{"payload": {"structured": {"injuries": [...]}}}`(저장 형태)에 대해
  `마크 게히 / player_id 549 / external_player_id 67971 / team_external_id 50 /
  photo_url https://media.api-sports.io/football/players/67971.png`가 채워졌다.
- 부분 표기(`Guehi`, `Guéhi`, `Marc Guehi`, `M. Guéhi`, `Cairney`)도 같은 ID로 확인됐다.
  범위 밖/모호한 이름에 ID를 만들지 않는 규칙은 기존 해석기(`localized_names.py:789-819`)에 있다.

### 3.2 명백히 다른 선수 사진 거부 — 신규 생성 경로는 확인, 기존 저장본은 미해결

- 새 생성 경로: 모델 ID가 이름 확인 결과와 다르면 ID를 비운다(3.1). 재현 확인.
- **한계 1(기존 저장본)**: 이미 `player_id`가 **틀린 값으로 저장된** 과거 payload는 이름으로
  다시 확인하지 않는다. `section_structured.py:338-339`가 저장 ID로 외부 ID를 먼저 만들고,
  `:355-362`는 이름 확인이 **같은 ID일 때만** 표시 이름을 바꾼다.
  재현: 저장 payload `{"player_name": "Marc Guéhi", "player_id": 533}` →
  `photo_url .../players/1100.png`(홀란드 사진)가 그대로 나왔다.
  이번 저장본(`6c2ce4c2…`)은 세 선수 모두 `player_id: null`이므로 이 경우에 해당하지 않는다.
  보고서 §7-2도 "새로 생성하지 않으므로 저장 payload에는 ID가 남지 않는다"고만 적고,
  **틀린 ID가 이미 저장된 경우**는 다루지 않는다.
- **한계 2(team_id 출처)**: `_injury_rows`는 모델이 적은 `team_id`를 검증 없이 저장한다
  (`bundle_sections.py:1814-1816`). 계획·프롬프트(`bundle_availability.md:27`)는 팀 ID를 내부 ID로
  제시하지만, 모델이 외부 ID(50)를 적으면 그 값이 내부 ID 공간으로 들어간다.
  재현: 내부 id 50번 팀이 실제로 존재하는 인덱스에서 `team_external_id`가 **999**(다른 팀)로 나왔다.
  현재 frontend는 부상 행의 `team_external_id`를 좌우 판정에 쓰므로(`previewView.ts:365-380`)
  이 경우 다른 팀 배지·좌우가 될 수 있다. 이번 저장본은 `team_id`가 null이라 발생하지 않았다.

두 한계 모두 **PF-B 이전부터 있던 저장 데이터 형태**에 대한 것이고, 이번 변경이 만든 회귀가 아니다.
현재 사용자 증상(사진 없음)을 고치는 방향과 충돌하지도 않는다.

### 3.3 기존 payload 무변경 — 확인

- 수정은 조회 시점 투영에만 있다. `preview_admin.get_section_results`(`preview_admin.py:1142-1197`)는
  `store.list_section_results`(읽기)와 `detail.results`(읽기)만 쓰고 저장 행을 갱신하지 않는다.
- `structured_row_from_section_result`는 `{**row, **structured}`로 **응답 사본**만 만든다
  (`section_structured.py:503-523`). 저장 테이블 갱신·마이그레이션·백필 없음.
- 이 요청에서 DB에 쓴 것이 없다(이 검토는 DB에 접속하지 않았다. 근거는 코드 경로).

### 3.4 배당: 사이트 실제 1X2 우선 + API-Football 서로 다른 북메이커 최대 3행 — 확인

확인된 것:

- `/odds` **한 번** 읽기: `provider_odds.read_provider_odds`가 `client.get("/odds", fixture=...)`를
  한 번만 부르고 `max_retries=1`이다(`provider_odds.py:207`, `:201`). 신규 테스트가
  `client.calls == [("/odds", {"fixture": 1557474})]`를 고정한다.
- **서로 다른 북메이커 최대 3행**: `_quotes_from_records`가 같은 업체를 접고 3행에서 멈춘다
  (`provider_odds.py:139-157`). 재현: 4업체 응답 → 3행(`Bet365/Unibet/William Hill`).
- **공개 표 우선 병합 로직 자체는 옳다**: `market_with_provider_quote`(`provider_odds.py:255`)와
  `_odds_section`(`bundle_sections.py:2348-2380`)은 공개 표 값을 먼저 두고 남는 자리만 채운다.
  재현: 공개 2행 + 제공자 2행 → 3행(`Site0, Site1, Bet365`), 공개 값 유지.
- 정규시간 1X2가 아닌 시장·라이브 시장 제외는 기존 `parse_odds`/`_is_pre_match_market`
  (`sources/api_football.py:611-683`)를 그대로 쓴다. `/predictions` 미사용 확인(import 없음).
- 값이 없으면 빈 표 + 사유다(합성값 없음). 재현: 제공자 없음 → `structured["odds"] == []`,
  quality `INSUFFICIENT`.

계획 대조 — **1차 위반은 닫혔고, 현재는 계획과 일치**:

- **호출 조건이 "남는 자리"로 바뀌었다**: `provider_odds.has_remaining_slots(bundle.odds)`
  (`provider_odds.py:96`)가 참일 때, 즉 **공개 표에서 채택된 서로 다른 업체가 3개 미만**일 때
  제공자를 읽는다(`bundle_pipeline.py:1073` 생성, `:2394` 재생성). 1차 검토 시점의 조건은
  "공개 채택값 0행일 때만"이어서 공개 1~2행 경기에서 보완이 실행되지 않았다(그때 차단으로 보고).
  재검증: 공개 0행→True, 1행→True, 2행→True, 3행→False. 같은 업체 중복은 1행으로 세고,
  세 값이 다 있지 않은 줄은 세지 않는다. 실행 없이 순수 판정 함수로 확인했다.
- **실행당 1회 강제**: `ReadOnceGuard`(`provider_odds.py:105`)와
  `read_provider_odds_once`(`:364`)가 실제 요청을 1회로 제한한다. 생성 실행은
  `_Plan.provider_odds_guard`(`bundle_pipeline.py:584`, `:1608`)로 guard를 공유하고,
  배당 노드는 guard가 이미 소비됐으면 **요청 없이** 사유만 만든다(`:1069-1078`).
  재검증: 같은 guard로 두 번 호출 → 두 번째는 요청 0회 + "이미 한 번 시도" 사유.
- **공개 표 우선 순서 유지**: 병합 함수(`provider_odds.py:255` 수준)와 `_odds_section`
  (`bundle_sections.py:2352-2385`)은 공개 표 줄을 먼저 두고 제공자 줄을 뒤에 붙이며 3행에서 멈춘다.
  재검증: 공개 1행(Pinnacle) + 제공자 2행(Bet365·Unibet) → 표시 3행, 공개 값이 첫 행.
- **실제 `/odds` 읽기 결과(PF-KEY 후속 §4 반영, 별도 워커 근거)**: 키 연결 후 1회 실제 호출은
  HTTP 200, 응답 1건, 북메이커 9곳, pre-match 1X2 9행, `fixture.id` 일치였다. 그런데 레코드
  `update`가 `2026-11-08T12:52:18Z`(94.2시간 전)이고 업체별 `book.update`가 없어
  `odds_freshness`(`ODDS_FRESH_HOURS=6`)가 **9행 전부를 거부**했고 `sent=1·available=false·quotes=0`이다.
  원인은 PF-B 코드가 아니라 **제공자 자료의 신선도 + 기존 6시간 채택 규칙**이며, 그 규칙은
  이번 변경이 건드리지 않았다(`sources/api_football.py:589`, `:791-804`). 6시간 기준 완화는
  정책 변경이라 PF-B 범위 밖이다. 이 검토는 신선도 규칙의 타당성 자체를 판정하지 않는다.
- 참고(표시 정직성): 제공자에서 온 행도 본문 첫 줄이 "**공개 사이트의** 정규시간 1X2 소수점
  배당입니다"이고 출처 note도 "모델 없이 공개 자료에서 정규화한 값입니다"다
  (`bundle_sections.py:2391`, `:2414`). 재현: 공개 1행 + 제공자 2행 → 3행 모두 같은 문구 아래
  표시되고, 행 dict에도 출처 구분 키가 없다. 값은 실제 값이므로 거짓 수치는 아니지만
  **출처 표기가 부정확**하다. 사용자에게 보이는 문장이므로 후속 후보로 남긴다(차단 아님).

### 3.5 명시 생성/재생성에만 HTTP, GET에서 0 — 확인

- 호출 지점은 3곳뿐이다: `bundle_pipeline.py:1073`(생성 노드), `:2394`(재생성),
  `:771`(`_provider_odds_for` 본문의 실제 읽기). 그 외 호출 없음(전수 grep).
- GET 경로(`/runs/{id}/section-results`, `/runs/{id}/preview`, `/information-bundle`)는
  `provider_odds`를 **넘기지 않는다**. `_odds_section`의 `provider_odds` 기본값은 `None`이고,
  `preview_admin.py`·`section_preview.py`·`information_bundle.py`에 `read_provider_odds` 참조가 없다.
- 생성/재생성 노드도 `has_remaining_slots(...)`가 참이고 예산이 있을 때만 전송한다
  (`:1064-1081`, `:2391-2412`). 저장 결과를 다시 여는 것만으로 외부 호출이 생기지 않는다.
- 이번 검토 실행에서 나간 외부 HTTP는 0회다(테스트는 대역 클라이언트 사용).

### 3.6 모델 호출 0 / 예산·비밀값 보호 — 확인(단, 두 가지 참고)

- 배당 섹션은 모델을 부르지 않는다. `_odds_section`은 `transport`를 쓰지 않고
  `external_calls=0`으로 남긴다(`bundle_sections.py:2445` 근방). 섹션 등록부도 `section_odds`의
  모듈을 `D0`만 둔다(`registry.py:303`) → 모델 호출 축에 배당이 없다.
- 예산: `_provider_odds_for`가 `can_attempt(..., RequestClass.API)` → `charge` 순서로 처리하고,
  예산이 없으면 전송 0 + 사유다(`bundle_pipeline.py:740-757`). 재생성도 같다(`:2395-2412`).
- 비밀값: `_api_key()`는 설정·환경변수에서 **존재 여부만** 다루고, 값은 사유·진단에 넣지 않는다
  (`provider_odds.py:157-174`). 실패 사유는 `type(exc).__name__`만 쓴다.
  재현: 키 없음 → 사유에 "API-Football 키가 설정되지 않아…"만 있고 값은 없다.
- **참고 A(예산 정직성) — 부분 해소**: 1회 제한이 **예산 판정·차감보다 먼저**로 옮겨져, 같은 실행의
  두 번째 호출은 요청도 예산 차감도 하지 않는다. 재검증: 키 없음 상태에서 같은 guard로 두 번 호출 →
  `sent=0`/`sent=0`, **`api_used=1`**(1차 검토에서는 2였다). 예산 0이면 `api_used=0`이고 guard는
  소비된 채 남는다. 남은 부분은 **키 미설정**으로 실제 전송이 0회인데도 1회가 차감되는 점이다
  (전송 전에 `charge()`를 먼저 하기 때문). 이번 후속 보고도 "키 없는 예산 차감"은 범위 밖으로
  남겼다고 밝혔다. 배당 표시 결과는 바뀌지 않는다.
- **참고 B(전송 감사)**: `/odds` 전송은 `store.append_attempt`/전송 장부에 남지 않는다
  (`provider.py`·`data.py`만 장부를 쓴다). 그래서 실행 상세의 `send_ledger`는 이 API 호출을
  세지 않는다. `external_calls=0`은 모델 축 값으로 의도된 것이지만, 결과적으로 `/odds` 실제
  전송은 화면 어디에도 "n회"로 드러나지 않고 예산 스냅샷의 `api_used`로만 남는다.

## 4. 보고서 주장과 실제 코드 대조

| 보고서 주장 | 확인 결과 |
|---|---|
| §2 "모델 숫자는 신뢰 ID로 쓰지 않는다" | 사실. `_verified_injury_player`는 이름만 확인하고 `id_is_hint`를 쓰지 않는다 |
| §2 "이름과 다른 ID면 비운다" | 사실(재현) — 단 **새로 만드는 행**에 한정 |
| §2 "기존 저장본도 재읽기에서 ID·외부ID·사진을 얻는다" | 사실(중첩 payload 재현). 단 저장 payload에 틀린 ID가 있으면 그 ID가 이긴다(3.2) |
| §3 "공개 표 1행 먼저, 남는 자리만 제공자" | **사실(재검증).** 1차 검토 시점에는 호출 지점이 공개 0행일 때만이라 위반이었으나, 현재는 `has_remaining_slots()`로 공개 업체 3개 미만일 때 읽는다(3.4) |
| §3 "GET 경로에 넣지 않았다" | 사실(전수 확인) |
| §3 "예산 없으면 전송 0 + 사유" | 사실. 다만 전송하지 않아도 예산은 차감된다(참고 A) |
| §3 "키 없음 → sent=0, 실제 읽기 0회" | **이 정정 이후 사실이 아니다.** PF-KEY 후속 §4에서 키 연결 후 실제 1회 읽기 HTTP 200·9행을 확인했고, 신선도 6시간 규칙이 9행을 전부 거부해 `sent=1·quotes=0`이다(3.4) |
| §3 "`OPTIONAL_BUILDER_PARAMS`로 기존 대역 보호" | 사실(`bundle_pipeline.py:601`, `:632-641`). 필수 인자 계약은 그대로 강제 |
| §3 "실행당 1회" | 1차에는 코드에 없었고 가드 도입 후 사실이 됐다(3.4). 재검증 완료 |
| §5 검사 수치 19/152/45/109 | 수치를 근거로 쓰지 않았다(구현자 정정 요청 대상). 이 검토는 대표 3파일만 1회 실행 |
| §7-3 "PF-F 추가 필드 없음, `team_external_id`가 실린다" | 사실. 단 3.2 한계 2 때문에 값의 출처 보증은 없다 |

### 4.1 PF-B 후속2 보고(`pf-odds-fix-report.md`) 대조 — 전 항목 사실 확인

다른 세션이 남긴 후속2 보고의 주장을 현재 코드·실행으로 대조했다(모두 사실).

| 후속2 주장 | 확인 결과 |
|---|---|
| `has_remaining_slots` = 채택 서로다른 업체 < 3 | 사실. 0/1/2행 True, 3행 False, 중복 업체 1로 셈, 불완전 행 제외(재현) |
| 생성·재생성 **둘 다 같은 판정** | 사실. `bundle_pipeline.py:1073`·`:2394` 모두 `has_remaining_slots` |
| 사이트 우선·최대 3 고유 업체 유지 | 사실(공개1+제공자2 → 3행, 공개 값이 앞) |
| 실행당 1회(`ReadOnceGuard`) | 사실. 같은 guard 두 번째 호출 `sent=0`, `client.calls` 1회 |
| 1회 제한을 **예산 판정·차감보다 먼저** | 사실. `bundle_pipeline.py:749-758`(guard 판정) → `:759-`(예산 판정·차감). 재검증 `api_used=1`(이중 호출에도 1) |
| `PROVIDER_ODDS_IMPLEMENTATION_VERSION`이 승인 축에 들어감 | 사실. `version_manifest.py:126`, `section_odds@08ed203a23b234b5` |
| 다른 네 섹션 버전 불변 | 사실. `section_availability@643296ca…`, `section_players@f29a3253…`, `section_ai_forecast@8d4f5288…` 확인 |
| 공용 축 `bundle_sections.IMPLEMENTATION_VERSION` 미변경 | 사실. 여전히 `mp11-bundle-sections-7`, 주석으로 이유 설명 |
| `WrongFixture`를 `ApiFootballError`보다 먼저 잡음 | 사실. `parse_odds` 구간 except 순서 `WrongFixture` → `ApiFootballError` |
| 전송 실패는 기존 동작 유지 | 사실. `TimeoutError` 대역 → `sent=1`·`available=False`·사유에 예외 이름 |
| 출력 계약 불변(`mp11-odds-output-1`) | 사실. `registry.get_section_workflow("section_odds").output_contract_version` 확인 |
| 대표 검사 30 passed | 사실. `test_bundle_review_fixes.py`+`test_workflow_version.py` 1회 실행 → 30 passed |
| 과거 저장 행 무변경 | 코드 경로상 사실(조회·버전 계산만 하고 저장 행을 갱신하지 않음). DB는 이 워커가 열지 않았다 |

후속2가 **스스로 범위 밖으로 남긴 항목**(잘못된 ID/팀 ID, 전송 장부 확대, 키 없는 예산 차감)은
이 검토의 참고 1·2·4·5와 일치한다. 즉 남은 참고는 구현자가 인지하고 있고, 이번 수정에서
의도적으로 제외됐다.

버전 집합(계획의 "결과 의미를 바꾸는 변경은 새 버전") — **현재 코드 기준으로 확인**:
PF-B가 결과 의미를 바꾼 것은 ①부상 행의 ID·표시 이름 해석 ②배당 섹션에 제공자 줄이 붙는 경로다.
`bundle_sections.IMPLEMENTATION_VERSION`은 `mp11-bundle-sections-7`이고, 그 주석은 **다른 변경
(잘린 응답 수용 기준)**을 근거로 이미 올라간 값이라 PF-B가 다시 올리지 않았다. 대신 배당 축은
`provider_odds.PROVIDER_ODDS_IMPLEMENTATION_VERSION = "mp11-provider-odds-1"`이라는 **별도 축**을
두고 `version_manifest._compose_manifest("section_odds")`가 그것을 쓴다(`version_manifest.py:120-127`).
그래서 현재 워크플로우 버전은 `section_odds@08ed203a23b234b5`(구성: D0 + `mp11-provider-odds-1`)로,
1차 검토 시점의 `section_odds@61e09b66690638fb`와 **다르다** → 배당 승인 축이 실제로 이동했다.
`section_availability@643296ca23b42faf`(R2·`mp11-bundle-sections-7` 포함)는 그대로다.
사용자가 어느 버전을 승인했는지, 재승인이 필요한지는 조정자·사용자 소유이므로 이 워커는 판정하지
않는다. 다만 "한 섹션만의 변경으로 네 섹션 승인 버전을 흔들지 않는다"는 의도는 코드 주석과 일치한다.
(단 위 수치는 **21:2x 시점**이며, 이후 변경으로 현재는 §4.2 값이다.)

### 4.2 2차 확인 — 그 뒤 바뀐 것(2026-11-14 01:5x 현재 트리)

위 §1·§3.4·§4의 문장 중 **더 이상 사실이 아닌 것**과 현재 값을 적는다. 근거는 현재 코드와
이 워커의 1회 실행이다(새 검사·재현 도구 작성 없음, DB·HTTP·모델 0).

| 항목 | 위 문서(21:2x) | 현재(01:5x) | 확인 방법 |
|---|---|---|---|
| 배당 채택 정책 | 제공자 6시간 신선도(`odds_freshness`)로 9행 전부 거부 → 0행 | **업체별 가장 최근 실제 갱신값을 채택**(오래돼도 버림). `_quotes_from_records`가 업체별 `updated_at` 최신을 고르고 `observed_at`은 제공자 원시 시각 유지 | 코드(`provider_odds.py:213-283`) + 재현: 94.2시간 지난 레코드 → `quotes 1건`, `observed_at == 원시 시각`(True), 진단 0 |
| 버전 상수 | `mp11-provider-odds-1` | **`mp11-provider-odds-2`** (주석에 v2 채택 정책 변경 근거 기재) | `provider_odds.py:61` |
| `section_odds` 버전 | `08ed203a23b234b5` | **`49923b1c5dcb467a`** | `version_manifest.workflow_version_of("section_odds")` |
| 다른 섹션 버전 | `643296ca…`·`f29a3253…`·`8d4f5288…` | **`7dc7fec4…`(availability)·`174a9807…`(players)·`c186f273…`(forecast)** | 같은 함수 1회 실행 |
| 계약 축 | 전역 `CONTRACT_VERSION`(`mp02-1`) | bundle 워크플로우는 **`SECTION_RESULT_CONTRACT_VERSION`(`mp04-section-result-1`)** 을 쓴다(저장 시 쓰는 축과 일치시킴) | `version_manifest.py:163-172` |

**왜 네 섹션 버전까지 함께 움직였나.** `constituents_for_workflow`가 bundle 워크플로우의 계약 축을
전역 `mp02-1`에서 저장 축 `mp04-section-result-1`로 바꾼 결과다. 코드 주석의 의도는 "승인이 늘
stale로 보이는 것"을 막는 것이고, 그 자체는 수용 범위 밖 변경이라 이 검토는 **판정하지 않는다**.
다만 위 §4의 "네 섹션 버전 불변"은 이 변경 이후 사실이 아니다.

**판정은 그대로다.** 차단 0. 배당 채택 정책 변경은 사용자 지시(2026-11-12)에 따른 별도 v2이며,
이 검토의 수용 기준(공개 표 우선 순서·최대 3 고유 업체·실행당 1회·GET 무호출·모델 0회)은
현재 코드에서도 유지된다(`has_remaining_slots`·`ReadOnceGuard`·`read_provider_odds` 경로 불변,
guard가 여전히 예산 차감보다 앞: `bundle_pipeline.py:749-772`, 재검증 `api_used=1`).

**줄 번호가 이동했다.** v2 코드가 `provider_odds.py`에 추가되면서 위 §1·§3.4·§4.1에 적은
`provider_odds.py` 줄 번호는 현재 코드와 어긋난다. 현재 값은 `has_remaining_slots` :100,
`ReadOnceGuard` :109, `read_provider_odds` :290, `read_provider_odds_once` :409,
예외 경계 :349(봉투)·:371(`WrongFixture`)·:377(`ApiFootballError`)다. 함수·동작은 같다.

**참고 8은 해소됐다.** 위 §6-8 "6시간 신선도 규칙으로 실제 배당 0행"은 v2에서 채택되므로 더 이상
현재 동작이 아니다. 대신 새 참고: 실제 `/odds` 9행이 이제 **채택되어 표시될 수 있으므로**,
화면에 나가는 배당의 기준 시각(4일 전)이 사용자에게 그대로 보이는지가 확인 대상이다.
이 검토는 화면을 보지 않았다(§6-5 재기동 필요와 같은 이유).

## 5. 실행한 검사(단위 1회, 대표만)

```
# 1차 검토(수정 전 코드)
./.venv/bin/python -m pytest tests/preview/test_bundle_review_fixes.py -q      -> 19 passed
./.venv/bin/python -m pytest tests/preview/test_bundle_sections.py -q          -> 15 passed
./.venv/bin/python -m pytest tests/preview/test_bundle_pipeline.py -q          -> 16 passed, 1 skipped
# 세 파일 묶음 1회                                                             -> 50 passed, 1 skipped

# 수정 반영 후 재확인(같은 대표 파일, 1회)
./.venv/bin/python -m pytest tests/preview/test_bundle_review_fixes.py -q      -> 19 passed
./.venv/bin/python -m pytest tests/preview/test_bundle_pipeline.py tests/preview/test_bundle_sections.py -q
                                                                               -> 31 passed, 1 skipped
```

새 테스트·재현 스크립트는 **이 워커가** 저장소에 만들지 않았고, 재현은 `python -` 임시 실행으로만 했다.
전체 회귀·가상환경 조합·미지원 입력 탐색은 하지 않았다(지시 범위).

**수정 후 추가된 테스트(다른 세션, 이 워커 아님)**: `tests/preview/test_bundle_review_fixes.py`가
19 → **26건**으로 늘었고 다음을 직접 고정한다.

- `test_remaining_slots_is_true_below_three_adopted_sites` — 0/1/2행 True, 3행 False
- `test_public_one_row_plus_provider_two_rows_keeps_site_first_three` — 공개 1행 + 제공자 2행 = 3행
- `test_public_three_rows_means_no_provider_call` — 3행이면 보완 호출 없음
- `test_read_once_guard_blocks_the_second_request` — 두 번째 요청 0회·`sent=0`
- `test_wrong_fixture_parse_error_becomes_missing_odds_not_a_crash`, `test_malformed_odds_envelope_becomes_missing_odds` — 예외 흡수
- `test_odds_workflow_version_changed_and_others_kept` — 배당 버전 이동·다른 섹션 불변

이 워커가 재실행한 결과 **26 passed**(수정 전 19 passed와 같은 파일). 즉 1차 검토에서 지적한 두 항목과
버전 축이 **회귀 테스트로 고정**됐다. 검토자 재현(임시 실행)과 저장소 테스트가 같은 결론을 낸다.

**남은 검사 한계**: 위 26건은 이 워커가 작성한 것이 아니며, 이 검토는 그 내용이 지적 사항과
일치하는지만 확인했다. 전체 스위트·통합 회귀는 지시대로 실행하지 않았다.

## 6. 재현 결함 / 참고 정리

**재현 결함(이번 변경이 만든 회귀 아님, 현재 증상 영향 없음)**

1. 기존 저장 payload에 이름과 다른 `player_id`가 이미 있으면 그 ID로 사진을 만든다
   (`section_structured.py:338`, `:355-362`). 현재 저장본은 해당 없음.
2. 부상 행의 `team_id`가 내부/외부 ID 공간 검증 없이 저장되고, 투영에서 다른 팀 배지가 될 수 있다
   (`bundle_sections.py:1814`, 재현 시 999). 현재 저장본은 `team_id` null.

**참고 개선(차단 아님)**

3. ~~제공자 보충 호출 조건~~ → **수정됨**(`has_remaining_slots`). 3.4 참고.
4. **키 미설정 시 전송 0회인데 `api_used` 1 차감**(참고 A). 중복 호출로 인한 이중 차감은
   수정됐다(`ReadOnceGuard`가 차감보다 앞). 남은 것은 "보내기 전에 차감" 순서 하나다.
5. `/odds` 전송이 전송 장부에 남지 않는다(참고 B).
6. ~~`/odds` 해석 예외 전파~~ → **수정됨**(`ApiFootballError`/`WrongFixture` 흡수, 재검증 3종 통과).
7. **제공자 행의 출처 표기가 부정확**(3.4). 제공자에서 온 줄도 "공개 사이트의…" 문구·"공개 자료에서
   정규화한 값" note로 표시된다. 값은 실제 값이라 거짓 수치는 아니지만 출처 문장이 틀렸다.
8. **6시간 신선도 규칙으로 실제 배당 0행**(3.4). 키·연결·코드는 정상이고 제공자 값이 4일 전이다.
   사용자에게 실제 배당이 보이지 않는 직접 원인이므로, PF-UI 화면 확인 시 "연결 실패"가 아니라
   "자료 신선도 미달"로 표시되는지 확인이 필요하다. 신선도 기준 변경은 정책 승인 사항이다.
9. ~~새 판정 함수·가드의 저장소 테스트 부재~~ → **해소**. 26건으로 늘어난
   `test_bundle_review_fixes.py`가 판정·가드·예외 흡수·버전 축을 고정한다(§5).

## 7. 차단 여부

**차단 없음.** 1차 검토에서 차단으로 본 두 항목은 1차 보고 후 다른 세션이 수정했고, 현재 코드로
재검증해 닫힌 것을 확인했다(§1, §3.4, §3.6). 수정분에는 회귀 테스트도 함께 들어왔다(§5, 26 passed).

- 부상 이름·사진(3.1, 3.2 신규 생성 경로), 기존 payload 무변경(3.3), GET 무호출(3.5),
  모델 0회·비밀값 비노출(3.6)은 근거로 확인했다. 사용자가 지적한 주 증상(부상 한글명·사진)은
  충족된다.
- 배당 보완은 `has_remaining_slots()`로 공개 업체 3개 미만일 때 읽고(공개 0/1/2행 True, 3행 False),
  `ReadOnceGuard`로 실행당 1회가 강제된다. 1회 제한을 **예산 차감보다 먼저** 판정하도록 순서도
  고쳐져, 중복 호출이 예산을 두 번 쓰지 않는다(`bundle_pipeline.py:749-758`).
  계획의 "공개 사이트 우선 + 남는 자리 보완(최대 3행)"과 일치한다.
- 배당의 0행 결과는 **키 연결·HTTP 200·9행 수신까지 확인된 상태**(PF-KEY 후속 §4)에서
  6시간 신선도 규칙이 4일 전 값을 거부한 것이다. 잘못된 배당을 표시하지 않는다는 점에서 정직하며,
  "부족한 것은 키가 아니라 최신 배당 자료"라는 보고서 정리에 동의한다. 이 부분은 차단 사유가 아니다.
- 남은 참고(1·2·4·5·7·8)는 현재 저장본 데이터에 해당하지 않거나, 표시 결과를 바꾸지 않거나,
  출처 문구·감사처럼 후속 개선 성격이다. 차단하지 않는다.
- **사용자 판단이 필요한 항목**: 8(6시간 신선도 기준). 기준을 유지하면 이 경기의 실제 배당은
  계속 빈 표이고, 완화하려면 정책 승인과 배당 섹션 재실행 1회(`POST /section-runs`,
  `workflow_id=section_odds`, `mode=live`, `source_mode=reuse`)가 필요하다. 실행·정책 결정은
  이 워커가 하지 않는다.
- **승인 버전 관점**: 배당 축이 `mp11-provider-odds-1`로 새로 생겨 `section_odds` 워크플로우 버전이
  `61e09b66690638fb` → `08ed203a23b234b5`로 이동했다. 이 섹션을 승인 근거로 쓸 경우 조정자가
  새 버전 기준으로 확인해야 한다(이 워커는 판정하지 않는다).
- **이 검토의 한계**: 이 워커는 읽기 전용이므로 새 테스트·재현 스크립트를 저장소에 만들지 않았다.
  수정분의 26건 테스트는 다른 세션이 작성한 것이고, 이 검토는 그것이 지적 사항과 맞는지 확인하고
  1회 실행(26 passed)한 것까지다. 전체 스위트·통합 회귀·실제 화면은 이 검토 범위가 아니다.

EDITING STOPPED
