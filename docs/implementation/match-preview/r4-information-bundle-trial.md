# R4 정보 원문 묶음 시험 (브라우저 없는 수집 + 읽기 전용 DB → 한국어 프리뷰)

작성: 2026-11-11 KST. 성격: **실험용 프로토타입 한 건의 실제 관측 기록**이다. 제품 기본 경로 수정도, 섹션 워크플로우 승인도, 전체 확장 승인도 아니다. 이 문서의 성공은 "이 접근이 쓸 만한지"에 대한 근거 하나이며 "이제 제품에 연결해도 된다"는 뜻이 아니다.

## 판정 (먼저)

**되는 쪽으로 확인됐다.** 브라우저 없이 실제로 수집한 기사·통계·프로필 본문 4건과 읽기 전용 DB 스냅샷으로, Google `grounding_chunks`/`grounding_supports`가 전혀 없이도 한국어 R4 프리뷰 3명분(선정 선수·선정 이유 분리, 이름 전부 DB 한국어 값)을 만들었다.

**정정 — 실제 유료 Vertex 전송은 1회가 아니라 최소 2회다.** 이전 판본이 "1회"라고 적은 것은 틀렸다. 작업 전체를 세션 로그로 재구성한 결과, 서로 다른 두 프로세스가 각각 1회씩 전송했다.

- **1차 전송(유실)**: 2026-11-10T23:56:52Z 시작(`--phase collect` 실행). 수집 단계 가드가 없어 preflight·전송까지 진행됐고, 응답을 받은 뒤 후처리에서 `AttributeError`가 나 커밋 전에 예외가 전파됐다. 그 프로세스의 run·시도·원문 행이 **전부 롤백**되어 응답이 남지 않았다.
- **2차 전송(보존)**: 2026-11-11T00:17:33Z 시작(run `a32f3ed4`). 응답을 즉시 커밋하도록 고친 뒤 실행했고 아티팩트에 남았다.

두 전송 합계 사용량·비용은 **확정할 수 없다.** 1차 전송의 응답 원문이 롤백으로 사라졌기 때문이다. 다만 1차는 응답을 **받은 뒤** 실패했으므로 전송 자체는 성립했고, 제공자 과금은 발생했을 가능성이 높다.

네 가지를 분명히 해 둔다.

1. **이건 "기사 사실이 검증됐다"는 뜻이 아니다.** 수집 본문에 근거가 있는지만 봤고, 문장이 그 출처를 실제로 뒷받침하는지·시즌/대회 일치·기사와 DB의 충돌은 검사하지 않았다. 이 시험의 범위는 애초에 거기까지가 아니다(아래 "검증 범위" 참조).
2. **1차 전송의 결과는 아무도 보지 못했다.** 2차 전송의 응답도 최초에는 내 검증기 결함으로 세 항목이 전부 탈락했다. 같은 응답을 다시 사지 않고 고친 검증기로 재처리해 3명분을 얻었다. 지금 보이는 본문은 **2차 전송 응답의 오프라인 재처리 결과**다.
3. **수집 커버리지는 좁다.** 저장 후보 6개 중 실제 본문 확보 4건, 실패 2건(403 차단 1, JS 셸 1)이다. Fulham 기사 본문은 얻지 못했다.
4. **저장된 섹션 행에는 본문이 없다.** 이 문서와 증거 파일의 본문은 생성 파일이지 `preview_dev`의 섹션 결과 행이 아니다(아래 "본문은 어디에 있나" 참조).

## 시험한 결정

> 브라우저 없는 실제 본문 수집 + 읽기 전용 DB 자료로, Google `grounding_chunks`/`supports`나 기사↔DB 교차 검증 없이도 근거가 붙은 R4 프리뷰를 만들 수 있는가?

## 실행 환경 (실제 확인)

| 항목 | 관측값 | 근거 |
|---|---|---|
| 개발 모델 제공자 | `hive` | 세션 레코드 `model/selection` |
| 개발 모델 ID | `deepseek-ai/deepseek-v4.1-flash-1017` | 같은 레코드 |
| 추론 강도 | `max` | 같은 레코드 |
| DSH 프로필 | `dsh-tui` (`DSH_PROFILE_DIR=/Users/woolee/.dsh/profiles/dsh-tui`) | 환경변수 |
| 터미널 | `term_4c2ff03d-c0fa-4e01-b914-a46cb7a28328` | `ORCA_TERMINAL_HANDLE` |
| 제품 생성 모델 | `gemini-3.5-flash` / `global` | `~/.config/match-preview/model-live.env` 값 이름만 확인, 값 미출력 |

## 무엇을 그대로 쓰고 무엇을 바꿨나

| 경계 | 내용 |
|---|---|
| **그대로 재사용** | `provider.request_model` → `execute_request`(예산·시도·원문 아티팩트), `players.load_prompt`/`build_prompt`(제품 R4 프롬프트), `players.parse_model_output`, `players.model_players`, `players.resolve_selection_names` + DB 한국어 해석기(`DisplayNames`), `players.compose_players_body`, `runner.run_section_workflow`, `store`/`artifacts`(preview_dev 기록), `sections._prepare_implementation`(D0 저장자료 읽기) |
| **대체(프로토타입 전용)** | `form.validate_response`의 **grounding URL 정확 일치 + API 문자열 사실 대조** 경계 → `validate_bundle_references`. `google_search` 도구도 요청에서 제거 |
| **추가(제품 아님)** | 저장 검색 후보 재사용, 브라우저 없는 HTTP 수집, Trafilatura/텍스트 폴백 추출, 정보 원문 묶음 스키마 |

`form.validate_response`를 대체한 이유는 그 경계가 **입력 기사 자체를 거부**하기 때문이다. `_resolve_sources`는 모델이 인용한 URL이 공급자 chunk 목록에 정확히 있어야 웹 근거로 인정하는데, 이번 시험은 chunks가 없다. 그 필터를 그대로 두면 수집한 기사가 처음부터 탈락한다. **대체 검증기는 제품/승인 모듈이 아니며 이 파일 안에만 있다.**

## 수집 (브라우저 없음)

새 유료 검색 호출은 **0회**다. 저장된 두 응답에서 URL 후보만 재사용했다.

- `latest-full-response.json`: `grounding_chunks` **필드 없음**, queries 8
- `previous-success-full-response.json`: chunks 8, supports 9

후보 6개를 실제 HTTP로 가져왔다(`httpx`, 리다이렉트 5, 타임아웃 25초).

| # | 최종 URL | 방법 | HTTP | 본문 | 판정 |
|---|---|---|---|---|---|
| 1 | forebet.com/…predictions-tips-manchester-city-fulham-1925345 | fresh_http | 403 | 0자 | **실패** — Cloudflare 챌린지(`Enable JavaScript and cookies to continue`). 재시도 안 함 |
| 2 | manchestercitynews.co.uk/squad | fresh_http | 200 | 2,096자 | 확보. 텍스트 폴백 경로(명단 26인 보존) |
| 3 | fulhamfc.com/news/2026/november/06/josh-king-called-up-to-england-squad/ | fresh_http | 200 | 0자 | **실패** — JS 셸. 정적 HTML에 기사 텍스트 없음 |
| 4 | plstats.uk/players/erling-haaland/ | fresh_http (grounding redirect 경유) | 200 | 1,820자 | 확보 |
| 5 | theguardian.com/football/2026/nov/04/rb-leipzig-manchester-city-champions-league-match-report | fresh_http (redirect 경유) | 200 | 4,735자 | 확보. **지난 경기 리포트** |
| 6 | en.wikipedia.org/wiki/Oscar_Bobb | fresh_http (redirect 경유) | 200 | 14,958자 | 확보 |

**수집 HTTP 6회 + Fulham 공개 API 시도 3회 = 외부 비모델 요청 9회.** 브라우저 렌더·스크린샷·자동화는 쓰지 않았다.

### 저장 HTTP 재사용과 새 수집의 구분

이번 번들은 **전부 새 HTTP 수집(`fresh_http`)** 이다. 이전 조사가 저장한 `/tmp/preview-scraper-compare.PRpmWn/raw/*.html` 재사용 경로와 `stored_http_replay`(명시 기록 시각 포함) 표시는 구현했으나, 이번 실행에서는 후보 최종 URL과 저장 캡처의 대응이 Wikipedia 1건뿐이라 새 수집으로 통일했다. **브라우저 렌더 캡처(`fulham_rendered.html`)는 의도적으로 쓰지 않았다.** 브라우저 없이 얻은 본문이라는 주장에 렌더 결과를 섞으면 그 주장이 거짓이 된다.

### Fulham JS 기사 — 좁은 시도와 중단

정적 HTML 안에 `#__NUXT_DATA__`가 있으나 `{"prerenderedAt":…,"serverRendered":2}` 뿐이고 `serverRendered: 2`(SSR off)다. 기사 문자열(`Josh King`)은 정적 HTML에 0회 나온다. 공개 경로 후보 3개만 확인하고 멈췄다.

| 시도 | HTTP | 결과 |
|---|---|---|
| `…/josh-king-called-up-to-england-squad/_payload.json` | 200 | HTML 반환(JSON 아님) |
| `…/josh-king-called-up-to-england-squad/payload.json` | 200 | 같은 HTML |
| `fulhamfc.com/_payload.json` | 200 | 69바이트 빈 payload |

사이트 전체 크롤·인증·CAPTCHA 우회·비공개 경로는 시도하지 않았다. **본문 미확보로 기록하고 다른 출처로 넘어갔다.**

## 출처 성격 라벨

기사 원문을 프리뷰라고 부르지 않기 위해 수집 단계에서 라벨을 붙였다.

| source | 라벨 | 근거 |
|---|---|---|
| forebet | `preview` | 경로에 `predictions-tips` (본문 미확보) |
| manchestercitynews/squad | `stats` | 스쿼드/명단 페이지 |
| fulhamfc 기사 | `unavailable` | 본문 미확보 |
| plstats | `stats` | 선수 개인 기록 페이지 |
| theguardian | `past_match_report` | 리그가 아닌 UCL 경기 리포트(2026-11-04 RB Leipzig vs Man City). **이번 경기 프리뷰가 아니다** |
| wikipedia | `profile` | 백과 선수 소개 |

프롬프트에도 "지난 경기 리포트는 이번 경기 프리뷰가 아니다"를 명시하고, 그 내용을 이번 경기 전망으로 바꿔 쓰지 말라고 지시했다.

**조립 출력과의 차이.** `players.compose_players_body`가 넘기는 `sources[].kind`는 계약상 `web_article` 하나로 고정돼 있어, 위 성격 구분이 생성 파일의 출처 목록에는 그대로 드러나지 않는다. 그래서 `generated-preview.md`와 `run-summary.json`의 `source_type_labels`에 실제 성격을 함께 적었다. 실제 "이번 경기 프리뷰 성격" 기사 본문은 **0건**이다.

## DB 스냅샷 (읽기 전용)

| 항목 | 내용 |
|---|---|
| 역할 | `preview_dev_fixture_ro`(경기·순위·부상), `preview_dev_names_ro`(이름) |
| 경기 | external `1557474`, 내부 `41125`, Premier League 2026, Man City(내부 13) vs Fulham(내부 4), 킥오프 2026-11-21T12:30Z, 상태 NS |
| 팀 한국어 | 13 `맨체스터 시티`, 4 `풀럼` (`public.team + public.team_translation`) |
| 순위 | 내부 13 → 3위 10경기 7승0무3패 승점21 득21 실13 폼 LLLWW / 내부 4 → 15위 10경기 2승4무4패 승점10 득10 실12 폼 DDWWL |
| 부상 | 저장 행 0건 → `unknown`. **"부상자 없음"의 증거가 아니다** |
| 지난 경기 | FT 10건(예: 1557465 등), `public.fixture` 읽기 전용 |
| 이름 로스터 | 40행(내부 선수 ID + 한국어명) |

ID 공간은 저장 경기 기준 **internal**(DB 기본키)이며, 별도 비교 스크립트에서 확인한 값(예: player 533)은 external 공간이라 이번 묶음의 표시에는 쓰지 않았다.

## 정보 원문 묶음의 모양

설계 요구를 코드로 옮긴 결과다(사전 작성 구현 없음).

- `sources[]`: `source_id`, 요청/최종 URL, 제목, `capture_time`, `method`, `stored_capture_at`, `http_status`, `html_sha256`, `body_sha256`, **실제 본문**, `passages[]`, `failure`(실패 진단)
- `db_snapshot`: 경기·팀 식별자, 순위, 부상 상태, 지난 경기, 로스터, 역할, 실패 목록, 조회 시각, 출처 테이블 식별자
- `db_facts[]`: 모델 입력으로 넘긴 구조화 사실 문장(`api:standings-13` 등)
- `limits`: 실제 적용 상한과 사용량
- `browser_used: false` + 명시 주석

발췌 상한은 설계 §6.1 제안값을 따랐다: 출처당 최대 3개 구간, 구간 1,500자, 웹 근거 총 16,000자. 이번 사용량은 **5,311자**(12,170자 프롬프트 중). 산문을 표·인포박스·각주보다 먼저 고르게 했고, 각주/외부링크 줄은 발췌에서 제외했다.

## 모델 요청에 실제로 들어간 것

전송 전 오프라인 preflight에서 파서·검증·이름·조립과 **전송 뒤 경로 전체**를 합성 응답으로 한 번 돌려 확인했다(전송 0회).

전송 후 저장된 요청 아티팩트(`f85827cb-95dd-46b2-ba09-c9d7dca125da`, 17,382바이트, `redacted=true`)에서 문자열 존재를 확인했다.

| 확인 | 결과 |
|---|---|
| 출처 id 4개 | 전부 포함 |
| DB 사실 id(`api:fixture-identity`, `api:standings-13/4`, `api:past-*` …) | 포함 |
| 경기 id `1557474` | 포함 |
| `google_search` 도구 | **없음** (`google_search_tool_absent: true`) |
| 요청 본문 글자수 | 12,761자 |

즉 "본문이 모델에 들어간 뒤에만 근거로 쓴다"는 조건은 요청 단위에서 확인됐다.

## 실제 전송 회계 (작업 전체, 프로세스 기준)

`external_calls: 1`은 **살아남은 run 한 건의 값**이며 작업 전체 전송 수가 아니다. 작업 전체는 최소 2회다.

전사에서 확인된 실제 호출 수: **총 27회**(`collect` 13 · `preflight` 6 · `run` 1 · `reprocess` 7). `--phase` 없이 실행된 호출은 0건이라 기본값 `all`로 인한 추가 전송은 없다.

| # | 프로세스 | 시작(UTC / KST) | 실제 전송 | 응답 | 흔적 |
|---|---|---|---|---|---|
| 1 | `--phase collect` (당시 가드 없음) | 2026-11-10T23:56:52Z / 11-11 08:56:52 | **1회 전송됨** | HTTP 200 도착 후 `AttributeError` | **전부 소실** (롤백) |
| 2 | `--phase run` | 2026-11-11T00:17:33Z / 11-11 09:17:33 | **1회 전송됨** | HTTP 200, 보존 | 아티팩트 4건 + run/attempt 1건 |
| — | `--phase collect` 가드 추가 후 (10회) | 08:59Z~09:16Z 대 | **0회** | 해당 없음 | 수집만, `전송하지 않았습니다`로 종료 |
| — | `--phase collect` 문법 오류 (2회) | 08:56Z 대 | **0회** | 해당 없음 | 실행 전 파싱 실패 |
| — | `--phase preflight` (6회) | 위 구간 | **0회** | 합성 기록 응답 | 파일만 갱신 |
| — | `--phase reprocess` (7회) | 09:18Z~09:25Z 대 | **0회** | 저장된 2차 응답 재사용 | 파일만 갱신 |

**작업 전체 실제 Vertex 전송 = 최소 2회.** 이 전사에서 확인된 것은 2회이며, 전사에 남지 않은 외부 프로세스가 있었다면 더 있을 수 있다(계산 근거는 아래 "어떻게 셌나"). 1차 전송의 토큰·비용은 **알 수 없다**(원문 소실).

### 2차 전송 상세 (보존된 쪽)

| 항목 | 값 |
|---|---|
| run | `a32f3ed4-df88-4ce3-939f-702c357ef7b2` |
| 저장된 섹션 결과 행 | `4d5b51c2-0fcc-4055-a788-44b6c27d0e30` (v1, **본문 길이 0**) |
| 모델 | `gemini-3.5-flash` / `global` / provider `vertex` |
| 예산 | `attempts_per_call=1`, `model_requests=1`, `normal_model_calls=1`, deadline 900초 |
| 이 run의 실제 전송 | 1회 (`external_calls: 1`, attempt 0, HTTP 200, 재시도 없음) |
| 사용량 | input 6,026 / output 687 tokens (search queries 미제공) |
| 시각 | 2026-11-11 00:17:36Z 시작 → 00:18:01Z 종료 |
| `generation_config` | `temperature 0.2`, `response_mime_type: application/json` (검색 도구 없음) |

**전송 앞 구간 단계별 1회 관측(벤치마크 아님)**: DB 스냅샷 5,356 ms → HTTP 수집 8,614 ms(개별 323~1,994 ms, 합 5,750 ms) → preflight <1 ms → `run_section_workflow` 전체 28,574 ms → 그중 모델 전송 19,994 ms.

### 1차 전송에서 무슨 일이 났나

1. `--phase collect`가 수집 후 종료하지 않고 preflight·전송으로 이어졌다(당시 그 분기가 없었다).
2. 전송 성공. 응답 원문이 그 세션의 아티팩트로 기록됐다.
3. 후처리에서 `result.response.usage.as_dict()` 호출 → `AttributeError`(실제 메서드는 `to_dict`). **이 줄은 응답을 받은 뒤에 실행되는 코드다.** 즉 실패 시점에는 이미 유료 응답이 손에 있었다.
4. 예외가 runner 밖으로 전파되어 세션이 커밋되지 못했고, **그 실행의 run·시도·원문 행이 전부 롤백**됐다.

읽기 전용 재확인: 1차 전송 구간(2026-11-10 23:56Z~23:58Z)에 남은 `preview_runs`/`preview_attempts`/`preview_artifacts` 행은 **각 0건**이다. trial 라벨이 붙은 살아남은 run은 `a32f3ed4` 하나뿐이다.

### 어떻게 셌나 (재현 가능한 근거)

- 세션 전사(`~/.dsh/sessions/--Users-woolee-benchmark--/e5084d5c-…/session.v4.jsonl.zstd`)에서 trial 스크립트를 실행한 **모든** bash 호출을 시간순으로 뽑아, 각 호출의 실제 출력을 분류했다.
- 실제 호출 27회를 phase별로 셌다: `collect` 13, `preflight` 6, `run` 1, `reprocess` 7. 스크립트를 python 인자로 실행한 bash 호출만 세고, `ast.parse`·`grep`·heredoc에서 파일명이 언급된 경우는 제외했다.
- `--phase run` 호출은 **1회뿐**이다(t=1794356253602).
- `--phase collect` 중 전송까지 간 것은 **1회뿐**이다(t=1794355012449). 그 출력에 `=== 전송 상한 ===`와 `usage.as_dict` traceback이 함께 있다. 나머지 collect 12회는 문법 오류 2회(실행 전 실패)와 가드 이후 10회(`collect: … 전송하지 않았습니다`)다.
- `preflight` 6회·`reprocess` 7회는 합성/저장 응답만 썼고(`external_calls: 0`) 네트워크 전송이 없다.
- 다른 send-capable 스크립트(`preview_section_live_run.py` 등) 실행은 0건이다.
- **DB attempt 수는 이 계산에 쓰지 않았다.** 롤백된 1차 전송은 DB에 흔적이 없으므로, DB만 보면 1회로 잘못 보인다.

이것이 설계 §10이 경고한 "이전 R4 후처리 예외로 유료 응답이 롤백된" 실패의 재현이다. 그래서 스크립트를 이렇게 고쳤다.

- **`_persist_paid_response`**: 응답 직후 별도 아티팩트로 응답 텍스트를 저장하고 **즉시 commit**한다. 후처리는 그 뒤에 별도 try로 감싼다.
- **전송 뒤 경로 리허설**: preflight에서 `RecordedTransport`(mode=replay, 전송 0회)로 `execute_request` → 응답 읽기 → usage → 검증 → 조립까지 실제 코드 경로를 돌린다.
- **수집 단계 분리**: `--phase collect`가 preflight·전송까지 흘러가지 않게 끝낸다(실제로 첫 시도에서 이 누락으로 의도치 않게 유료 전송이 나갔다).

이번 실행(run `a32f3ed4`)에서는 응답이 저장된 뒤 후처리가 정상 통과해, 유료 응답은 아티팩트 `9dc1a4be-…`(3,259B)와 `68fcd640-…`(2,858B)에 남아 있다.

## 검증기 결함과 재처리

첫 실행의 검증기가 세 항목을 모두 `reference_not_in_bundle`로 탈락시켰다. 원인은 **내 코드**다. 프롬프트는 `src:…#p0` 형식으로 구간 단위 인용을 지시했는데, 검증기는 `src:…`만 허용 목록에 넣었다. 모델은 지시대로 인용했고 검증기가 틀렸다.

검증기를 고친 뒤 **새 전송 없이** 저장된 응답을 재처리했다(`--phase reprocess`, `new_send: false`, `external_calls: 0`).

## 생성된 한국어 R4 (재처리 결과)

```
이번 경기의 주목 선수 3명입니다.

선정 선수: 엘링 홀란드
선정 이유: 이번 시즌 리그 10경기에서 9골을 기록 중이며, 최근 챔피언스리그 라이프치히전에서도
결승골을 터뜨리며 핵심 공격수로서의 득점 감각을 유지하고 있습니다.

선정 선수: 오스카 보브
선정 이유: 과거 맨체스터 시티에서 활약했으나 현재는 풀럼 소속의 윙어로 활약 중이며,
친정팀을 상대로 어떤 경기력을 보여줄지 기대를 모읍니다.

선정 선수: 루벤 디아스
선정 이유: 이번 시즌 15경기에 출전했으나 최근 라이프치히전에서는 엔초 마레스카 감독의 선택을
받지 못하고 선발 제외되었기에, 이번 풀럼전 선발 복귀 여부가 주목됩니다.
```

필드 확인:

| 항목 | 결과 |
|---|---|
| 두 표시 필드 분리 | `selected_player` / `selection_reason` 분리 유지 |
| 이름 출처 | 3명 전부 `db_korean`, `mapping_status: resolved`, `unmapped: []` |
| 모델이 고른 표기 보존 | `model_selected_player`에 원문 유지 |
| 팀 표시 | `맨체스터 시티` / `풀럼` (DB 값) |
| 감독 표기 | `Enzo Maresca` → DB 값 `엔초 마레스카` 적용(`db_value_wins`) |
| 독자 본문 | 내부 ID·URL·진단 미노출, 출처는 관리자 영역에 별도 |
| 본문 생성 경로 `quality` | 파일 기준 `ready` (저장된 섹션 행은 `insufficient`·본문 0 — 위 "본문은 어디에 있나") |

### 출처 라벨 (관리자 영역)

본문 조립이 넘기는 `sources`는 기존 계약상 `kind: web_article`로 표기된다. 그러나 이번 묶음은 출처 성격을 구분해 수집했으므로, **표시 라벨과 실제 성격을 함께 적는다.**

| 출처 | 묶음의 `source_type` | 실제 성격 |
|---|---|---|
| manchestercitynews 스쿼드 | `stats` | 팀 명단·출전 기록. 기사 아님 |
| plstats 홀란드 | `stats` | 선수 개인 기록. 기사 아님 |
| Guardian 라이프치히전 | `past_match_report` | **지난 경기 리포트**. 이번 경기 프리뷰 아님 |
| Wikipedia 보브 | `profile` | 백과 프로필. 기사 아님 |
| 저장 경기·순위 | `api` | 읽기 전용 DB |

즉 `web_article`은 **계약상 공통 라벨**이고, 이번 4건 중 실제 "이번 경기 프리뷰 성격" 기사는 **0건**이다. 이 구분은 프로토타입의 수집 라벨(`stats`/`profile`/`past_match_report`)에 이미 있었으나, 조립 출력이 공통 라벨로 뭉쳐 있어 문서에서 따로 밝힌다.

### 사실 전제가 실제 입력에 있는가 (수동 대조)

검증기가 아니라 내가 직접 대조한 결과다.

| 문장의 사실 전제 | 입력 묶음의 근거 |
|---|---|
| 홀란드 리그 10경기 9골 | plstats `10 appearances (890 minutes), 9 goals and 0 assists` — 있음 |
| 홀란드 UCL 라이프치히 결승골 | Guardian `Haaland slid home a priceless winner` — 있음 |
| 디아스 15경기 | 스쿼드 페이지 `#3 Rúben Dias Defender 15 Apps · 0 Goals` — 있음 |
| 디아스 선발 제외 | Guardian `Maresca's dropping of Rúben Dias` — 있음 |
| 보브 풀럼 소속 윙어 | Wikipedia `plays as a right winger for Premier League club Fulham` — 있음 |

다섯 건 모두 입력에 존재한다. 다만 **홀란드의 "9골"은 plstats(2026-27 PL) 값이고 Guardian이 언급한 "13골"은 다른 맥락**이다. 이번 문장은 9골을 골랐으므로 틀리지 않았지만, 이는 검증기가 아니라 모델이 우연히 맞춘 것이다.

## 이 시험이 확인한 것 / 확인하지 않은 것

**확인한 것**

- 브라우저 없이 실제 본문을 수집해 정보 묶음을 만들고, 그 묶음을 **실제 모델 요청에 넣어** R4 한국어 프리뷰를 얻을 수 있다.
- Google `grounding_chunks`/`supports`는 이 경로의 **필수 조건이 아니다**(이번 응답에 grounding metadata가 없어도 본문이 나왔다).
- 기사와 DB를 교차 검증하지 않아도, 기사 본문에 있는 내용으로 선정 이유를 쓸 수 있다.
- 기사 수집 실패 2건(+Fulham API 3회 실패)이 나머지 근거와 결과를 지우지 않았다.
- 2차 전송 1회·재전송 0회, 그 응답 원문 보존 확인(1차 전송은 유실 — 위 회계 참조).
- 이름은 DB 한국어 우선이 실제로 동작했다(3/3 `db_korean`).

**확인하지 않은 것 (중요)**

- **문장이 출처를 실제로 뒷받침하는지** 기계적으로 검사하지 않았다. 이 프로토타입의 검증기는 (a) 참조 id가 입력 묶음에 있는지 (b) 이유 문장의 숫자가 입력 어딘가에 있는지만 봤다. 이는 프로토타입의 한계이며, 사용자 정책이 요구한 범위를 넘는 검증을 하지 않은 것이다.
- 주체·시즌·대회 일치, 다른 선수의 수치 혼입, 과거 시즌 값의 현재 기록 오용을 검사하지 않았다.
- 기사 내용과 DB의 충돌 여부를 판정하지 않았다(정책상 판정하지 않는 것이 맞다).
- 1차 전송의 응답 내용·토큰·비용은 **알 수 없다**(롤백으로 소실).
- Fulham 기사 본문은 확보하지 못했다. `preview` 성격 출처는 본문 0건이다.
- 이 시험은 **한 경기**다. 다른 경기·리그·사이트로 일반화할 수 없다.
- 토큰/비용 추정(2차분만 확인), 배포 환경(Koyeb small) 동작, 지연 분포는 이번 범위 밖이다.
- "모든 관련 기사를 다뤘다"거나 "사실이 검증됐다"고 말할 수 없다.

## 검증 범위 (정정)

이전 판본은 §7.2 수준의 구조화 사실 검증(주체·시즌·대회·수치 대조)을 **제품 필수 게이트**처럼 적고 "무엇이 남았나"의 첫 항목으로 올렸다. **그 틀은 철회한다.**

- 사용자 확정 정책(2026-11-11)은 이 시험에 **새 주체/시즌/claim 검증 엔진을 요구하지 않는다.** 기사 본문을 확보하면 그 기사를 근거로 쓰고, API·DB와 교차 검증하거나 충돌을 이유로 기사 내용을 탈락시키는 절차를 두지 않는다. AI 자체 전망은 API·DB 자료에 연결한다.
- 이 시험은 그 정책을 그대로 따랐다. 나온 본문 3명분은 **근거 없는 생성이 아니다.** 다만 연결 지점을 정확히 나누면 이렇다.
  - **사실 전제**(골 수·출전 수·선발 제외 등)는 모두 **실제 수집 기사 본문 참조**를 갖고 있다(아래 사실 전제 대조표). 세 항목 모두 `evidence`가 웹 출처 구간 id다.
  - **DB 입력**은 경기/팀 식별, 리그 순위·지난 경기 사실, 선수 후보 로스터, 그리고 **표시 이름**으로 쓰였다. 표시 이름은 3/3 DB 한국어 값이다.
  - 즉 이번 문장들에서 DB는 **사실 전제의 출처가 아니라 식별·표시·후보 범위**로 작동했다. DB 사실(순위·폼)을 인용한 문장은 나오지 않았다.
- 다만 이 시험의 검증기는 "참조가 입력 묶음 안에 있는가 + 이유 문장의 숫자가 입력 어딘가에 있는가"만 본다. 그건 **이 프로토타입의 한계이지 제품이 갖춰야 할 미완의 게이트가 아니다.**
- §7.2의 구조화 claim 검증은 설계 문서의 **미승인 제안**이며, 도입 여부는 사용자가 정할 사항이다. 이 보고서가 그 도입을 전제로 다음 작업을 제안하지 않는다.

## 남은 위험과 다음 판단거리

1. **전송 회계를 DB로만 판단하면 틀린다.** 이번에 롤백된 1차 전송이 그 증거다. 후처리 실패가 이미 지불한 응답을 지우는 구조는 이 시험 스크립트에서 고쳤지만, 같은 모양의 결함이 제품 모듈에 있으면 같은 일이 반복된다.
2. **수집 성공률.** 후보 6개 중 4개(67%)만 본문을 얻었다. 후보 선별·추출기 조합(문단 우선, 목록 폴백)이 실제 모집단에서 어떤 비율을 내는지는 표본 1건으로 알 수 없다.
3. **Fulham 같은 JS 셸 사이트.** 이번엔 포기하고 다른 출처로 대체했지만, 특정 구단 기사가 중요할 때 이 경로는 계속 비어 있다.
4. **비용 구조.** 모델 호출은 run당 1회지만 이번 작업은 실제로 2회 나갔다(1회는 유실). 수집 HTTP도 9회 늘었다. 전체 예산 배분은 미정이다.
5. **재처리 경로의 지위.** 이번 재처리는 같은 응답을 다시 쓰는 오프라인 단계다. 제품에서 "재처리"를 어떤 단위(새 결과 버전? 새 실행?)로 기록할지는 정해지지 않았다.
6. **이번 시험은 제품 경로가 아니다.** 섹션 결과 행에 본문이 없다(아래 참조). 승인된 워크플로우나 정상 프리뷰로 쓰려면 별도 작업이 필요하다.

## 본문은 어디에 있나 (저장 행과 생성 파일의 구분)

`run-summary.json`의 `section_result_id`가 `null`인 것은 **생성이 실패했다는 뜻이 아니다.** 두 가지가 섞여 있다.

| 무엇 | 값 | 의미 |
|---|---|---|
| `preview_dev`에 저장된 섹션 결과 행 | `4d5b51c2-0fcc-4055-a788-44b6c27d0e30`, v1 | **원 실행 시점**에 저장된 행이다. 당시 내 검증기 결함으로 3항목이 전부 탈락해 `quality=insufficient`, **`body` 길이 0**, `unavailable_reason="검증을 통과한 선정 항목이 없어…"` |
| 이 문서·증거의 본문 | 파일 | **오프라인 재처리 결과**다. 저장된 2차 응답을 다시 파싱·검증·조립해 만든 것이며 `preview_dev` 섹션 행을 갱신하지 않았다 |
| `section_result_id: null` | run-summary | 재처리 요약 객체에는 이 필드를 채우지 않았다. **원 실행의 섹션 행 ID는 위 `4d5b51c2-…`이며 사라진 것이 아니다** |

정리하면, **본문은 파일로만 존재하고 저장소의 승인 가능한 섹션 결과 행에는 들어 있지 않다.** 그래서 관리자 화면에서 이 섹션을 "ready 본문"으로 보여줄 수 있는 상태가 아니다. 재처리 결과를 제품 기록으로 남기려면 재처리 전용 저장 경로(새 결과 버전 등)를 정해야 하며, 이번 작업은 그것을 하지 않았다.

## 산출물

- 스크립트(실험 전용): `scripts/preview_r4_information_bundle_trial.py`
- 보고서: `docs/implementation/match-preview/r4-information-bundle-trial.md` (이 문서)
- 증거: `docs/implementation/match-preview/evidence/r4-information-bundle/`
  - `source-bundle.json` — 정보 원문 묶음(본문 전문 제외, 해시·발췌·출처)
  - `source-bundle.md` — 같은 내용 읽기용
  - `preflight.json` — 전송 전 확인 + 전송 뒤 경로 리허설
  - `generated-preview.md` / `generated-preview.json` — 실제 생성 본문·출처·필드
  - `run-summary.json` — run/섹션/시도/아티팩트 ID, 예산, 단계 시간 + **회계 정정 블록**(`accounting`, `section_row_disclosure`, `source_type_labels`)
- 본문 전문(저장소 밖): `/tmp/preview-r4-information-bundle.json`, preview_dev 아티팩트 `971ea8ba-…`(묶음)·`f85827cb-…`(요청)·`9dc1a4be-…`/`68fcd640-…`(응답)

**주의.** 스크립트의 `_write_outputs`를 다시 실행하면 `generated-preview.md`의 회계 문구와 출처 성격 라벨, `run-summary.json`의 회계 정정 블록이 **덮어써진다**(이번 정정은 파일 직접 편집분이다). 재생성이 필요하면 이 정정을 다시 적용해야 한다. 이번 작업에서는 그 자동 보존을 구현하지 않았다(범위: 회계 정정 보고).

## 범위 준수

- 제품 코드·테스트·프런트엔드·설정·`requirements.txt`·정책·`Plans.md`: **수정 없음**. 새 파일은 위 스크립트와 이 문서·증거뿐이다.
- git 스테이징/커밋: 없음. 기존 삭제·dirty 파일 보존.
- DB: `preview_dev`의 이 실행 소유 행만 씀. 기존 경기·계정 자료는 읽기만. 이번 회계 정정 작업에서는 **DB 쓰기 0회**(읽기 SELECT만).
- 유료 모델 전송: **작업 전체 최소 2회**(1차 유실·2차 보존). 재전송·모델 교체·검색 도구·브라우저 실행 없음.
- 새 유료 검색 호출: 0회. 저장 후보 URL만 사용.
- 서버 재시작·배포·사용자 승인·새 에이전트: 없음.

## 이번 정정 작업의 범위

이 문서·증거를 고친 작업은 **회계·범위 정정 보고**이며 새 구현이 아니다.

- 새 모델 호출·네트워크 요청·DB 쓰기·제품 편집: **없음**.
- 근거로 쓴 것: 세션 전사(모든 trial 스크립트 실행과 그 출력), 기존 `run-summary.json`, 기존 증거 JSON, `preview_dev` 읽기 전용 SELECT.
- 계산 방식: DB attempt 수가 아니라 **프로세스별 실제 전송 여부**(각 호출 출력의 `=== 전송 상한 ===` / `전송하지 않았습니다` / `=== 실행 요약 ===`)로 셌다.
- 한계: 세션 전사에 남지 않은 외부 프로세스가 있었다면 그만큼 더 있을 수 있다. 그래서 **"최소 2회"**로 적고 "정확히 2회"라고 단정하지 않는다.

EDITING STOPPED
