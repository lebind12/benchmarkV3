# PS-06 수정 확인 (수정 후 1회 검증)

작성: 2026-11-11 KST. 담당: **별도 새 DeepSeek 세션**(Orca `dsh-tui`, 실제 모델
`deepseek-ai/deepseek-v4.1-flash-1017`, Max). 성격: **수정 확인 1회**이며 전체 재검토가 아니다.

- 확인 시작: `2026-11-11T15:37:06+09:00`
- 확인 종료: `2026-11-11T15:55:00+09:00` (후속 확인 §10 추가: `2026-11-11T15:59+09:00`)
- 기준 리비전: `HEAD = 4d2821de089a39742ca69df377cd02425e65da9c` (새 경로 파일은 여전히 미추적/수정 상태)
- 원 검토 보고서: [preview-sections-independent-review.md](preview-sections-independent-review.md) §8의 8항목
- 수정 보고서(대조 대상): [ps06-section-fixes.md](ps06-section-fixes.md) (E, F1·F2·F3·F4·R2)
- 확인 범위: **§8의 8항목 + 이미 확정된 DB 한글 우선/같은 응답 fallback 연결**만. 옛 `test_outlook_module.py`
  시계 문제, 전체 스위트, 새 재현 스크립트·제품·테스트 편집, DB·HTTP·모델 호출은 범위 밖이며 하지 않았다.
- 비용·연결: 유료 모델 **0회**, 외부 HTTP **0회**, DB **0회**(아래 §7의 사고 1건 포함 — 데이터 접근 없음).
  새 파일은 이 보고서 하나뿐이고 코드·테스트·설정·마이그레이션 편집 0, stage/commit 0.

## 0. 결론

| 항목 | 판정 | 한 줄 근거 |
|---|---|---|
| F1 순위·부상 사실 | **통과** | D0의 `text`·`expected_status`가 실제 builder 요청 본문에 그대로 들어가고 "순위 값 없음"·모순 문장이 사라짐(§2) |
| F2 선수 통계 → 후보 | **부분 통과** | `display_name_ko` 경로와 후보 우선순위는 고쳐졌으나, **제품 해석기로는 이름 확인이 실패**해 실제 실행에서 여전히 후보 0건이 될 수 있음(§3) |
| F3 전망 구조화 투영 | **통과** | `structured.forecast` → `available=true`, `score/lean/reasoning` 그대로(§4) |
| F4 필수 예상 스코어 | **통과** | 스코어 없는 전망은 섹션 `insufficient` + 실행 단위 게이트까지 이중으로 막힘(§5) |
| F5 reuse 재생성 | **부분 통과** | 새 실행기가 실제 묶음으로 작성하고 검색·수집 0을 코드로 만족하나, **AI 전망/배당 재생성이 게이트에서 422로 막히고** 재생성 경로가 F2 주입을 빠뜨림(§6.1) |
| F6 nested availability | **통과** | 응답이 `availability{available,reason,artifact_id,sequence}` 중첩이고 테스트도 중첩 기준(§6.2) |
| F7 홉 예산·자동 redirect | **부분 통과** | on_hop 전송 전 차감·자동 추종 금지는 구현·검증됨. 다만 **홉이 `attempts_per_call`(3)에 걸려** 4홉 이상 URL이 예산 24를 남기고도 실패(§6.3) |
| F8 bundle hash | **통과** | 전달 기록 추가 후 저장 해시 == 재계산 해시(§6.4) |
| F9 배당 팀 이름 | **통과** | 팀 이름 전달 시 지원 형식에서 `quotes=1`(1x2_regulation), 미전달 시 0(§6.5) |
| DB 한글 우선 / 같은 응답 fallback | **통과(표시 규칙)** | DB 값이 이기고 DB에 없을 때만 같은 응답 표기 사용. 다만 제품 해석기에는 `register_model_labels`가 없음(§6.6) |

차단 항목은 **F2(부분)** 하나다. 나머지 부분 통과(F5·F7)는 §8에 남은 조건을 명시했다.

## 1. 확인한 리비전·해시

| 파일 | SHA-256(16) | mtime | E 보고와 일치 |
|---|---|---|---|
| `app/preview/modules/bundle_sections.py` | `23e7355e7f788340` | 15:19:04 | 일치(전체 해시 동일) |
| `app/preview/section_structured.py` | `091dd06b9ebe664c` | 15:13:40 | 일치 |
| `app/preview/prompts/bundle_players.md` | `724591bff162f8bb` | — | 일치 |
| `app/preview/prompts/bundle_availability.md` | `db5a6a3e5379fac4` | — | 일치 |
| `app/preview/prompts/bundle_forecast.md` | `3d8b93667e783e1a` | — | 일치 |
| `tests/preview/test_bundle_review_fixes.py` | `af93178505a5834c` | 15:26:30 | 일치 |
| `app/preview/bundle_pipeline.py` (A) | `e821bc8f6b6be6f3` | 15:13:18 | — |
| `app/preview/retrieval.py` (A) | `599c76bef6d3d689` | 15:11:30 | — |
| `app/preview/retry.py` (A) | `7e3c3f3247d5a946` | 14:57:39 | — |
| `app/preview/information_bundle.py` (A) | `b4817bd13c47485d` | 14:55:14 | — |
| `app/api/v1/preview_admin.py` (A) | `e0ceb6b214250604` (15:58:18, §10.6) | 15:58:18 | — |
| `app/preview/sections.py` | `0c7049c4da68308c` | 05:25:22 | 이번 범위 변경 없음 |
| `app/preview/sources/player_stats.py` | `60bfb0013ead82e9` | 12:35:52 | 이번 범위 변경 없음 |

E 보고 §6의 해시 표는 **현재 파일과 일치**한다(대조 완료). A 코드는 E 보고 이후에도 바뀌었으므로
A 쪽 인용은 위 해시 기준이다. 확인 중 이 파일들이 다시 바뀌지는 않았다(시작·종료 동일).

## 2. F1 — 순위·부상 사실이 실제 요청 본문에 들어간다: 통과

- 코드: `bundle_sections.py:576-592`(순위는 `text` 우선), `:606-634`(부상은 `expected_status` 포함 ·
  `player_name`이 `None`이면 이름을 만들지 않고 순번 id `api:injury-row<N>`), `:749-776`(`_db_injury_block`·
  `_injury_state`가 **직렬화한 사실 건수**로 문장 생성), `bundle_pipeline.py:258-263`(D0 부상 행 모양 그대로).
- 직접 확인(제품과 같은 D0 행 모양 → 실제 `build_bundle_section` → 기록 transport의 `RequestSpec`):
  - `"맨체스터 시티는 10경기 7승 0무 3패"` 원문 **포함**, `"순위 값 없음"` **없음**
  - `expected_status=doubtful` · `api:injury-row1` **포함**
  - `"DB 경기 자료가 제공되지 않았습니다"` **없음** → 이전의 자기모순 문장이 사라졌다.
- E의 대표 검사도 같은 성질을 본다: `test_actual_standings_text_reaches_forecast_request_verbatim`,
  `test_actual_expected_status_reaches_availability_request`, `test_injury_rows_without_serialized_values_do_not_claim_delivery`.
  대역이 아니라 `_sent_prompt()`가 `transport.calls[0].parameters["contents"]`를 꺼내므로 **고정 본문 대체가 아니다.**

## 3. F2 — 선수 통계가 후보로 들어간다: 부분 통과 (차단)

### 고쳐진 것

- `_ROSTER_NAME_KEYS`가 실제 키 `display_name_ko`를 **먼저** 읽는다(`bundle_sections.py:678`).
- 후보 줄에 실제 기록 값(포지션·출전·분·골·도움·평점)이 붙고, 이름 없는 행 수를 따로 밝힌다(`:698-746`).
- `player_candidates`가 묶음 `roster`보다 우선한다(`:2319-2326`). A가 D0 통계에서 그 목록을 만들어 넘긴다
  (`bundle_pipeline.py:617-641`, `:936`, `:952`).
- 이름이 **저장된 값으로** 있으면 정상 동작한다(아래 확인).

### 남은 문제 — 제품 해석기로는 이름 확인이 실패한다

- A가 파이프라인에서 넘기는 해석기는 `sections._name_resolver()`가 돌려주는 **`_ResolverHandle`**이다
  (`bundle_pipeline.py:593-600`, `:1434`).
- 그 클래스의 `resolve_player`는 **`scope_team_ids`가 없으면 `KeyError`**를 던진다(`sections.py:1204-1208`,
  `_names_for(scope)`가 `None`이면 예외).
- builder의 이름 확인은 scope를 넘기지 않는다(`bundle_sections.py:531-556` — `resolve_player("", player_id=…, id_space=…, id_is_hint=False)`).
- 그래서 `except Exception`이 그 `KeyError`를 삼키고(`:554-556`) 이름은 `None`이 된다.
- 직접 확인(제품과 같은 계약의 해석기 + 실제 D0 통계 행 `display_name_ko=None` + A의 `player_candidates`):
  후보 블록은 여전히 `- 선수 통계 1행을 읽었으나 이름이 확인된 후보가 없습니다. 이름을 만들지 않는다.`
  이고, 해석기가 받은 인자는 `scope_team_ids=[None]`(후보 조회) / `[13, 4]`(모델 응답 선수 조회)로 갈렸다.
- **실제 제품 영향**: 선수 통계 읽기 역할이 켜져 있고 `display_name_ko`가 비어 있는 경기(= D0이 `name_lookup` 없이
  호출하는 현재 경로, `bundle_pipeline.py:237-242`)에서는 55행을 읽어도 **후보 0건**이다. 그 상태에서 웹 수집도 0건이면
  주목 선수는 근거 없이 비고 실행은 `failed`가 된다 — 원 검토 F2가 지적한 결과와 같다.
- 왜 E 검사가 놓쳤나: E는 `DisplayNames(LocalizedNameIndex(...))`를 주입한다. 그 클래스는 scope 없이도 동작하고
  `register_model_labels`도 갖는다(아래 §6.6). 제품이 실제로 넘기는 `_ResolverHandle`과 계약이 다르다.
- 가장 작은 수정(문장): builder가 후보/부상 이름 확인 시 **`scope_team_ids`(= 홈·원정 팀 id)를 함께 넘기거나**,
  `_ResolverHandle.resolve_player`가 `player_id`만으로도 동작하도록 범위를 스스로 좁히게 한다. 둘 중 하나면 되고
  새 조회 경로를 만들 필요는 없다.

## 4. F3 — 전망 구조화 투영: 통과

- 코드: `section_structured.py:164-195`가 `payload["forecast"]`를 **먼저** 읽고 `ai_prediction` → 최상위 순으로 폴백.
- 직접 확인: `{"structured":{"forecast":{"lean":"home","score":"2-1","reasoning":["리그 3위"]}}}` →
  `{'lean':'home','score':'2-1','reasoning':['리그 3위'],'note':None}` 이고 `available=true`.
  스코어 없는 초안은 `{'lean':None,'score':None,'reasoning':[]}`로 **값을 만들지 않는다.**
- E 검사 `test_saved_forecast_structured_projects_score_and_lean`, `test_draft_structured_forecast_matches_saved_projection`도
  같은 성질을 본다. 저장 payload는 `bundle_sections.py:2195-2210`의 실제 초안 모양이다.

## 5. F4 — 필수 예상 스코어: 통과

- 섹션 단위: `bundle_sections.py:2211-2229` — 전망 문장만 있고 스코어가 없으면 `quality=INSUFFICIENT`,
  `unavailable_reason`에 사유를 남기고 **부분 본문(전망 문장)은 보존**, 스코어 절은 넣지 않는다.
- 실행 단위: `bundle_pipeline.py:1195-1226` — 필수 판정이 `section_quality == ready`를 요구하고, 전망에
  `structured.forecast.score`가 없으면 `required_missing`에 추가한다. 즉 **이중으로** 막힌다.
- 직접 확인(스코어 없는 응답): 이전 검토에서 `ready`였던 초안이 지금은 `insufficient` + 사유가 된다.
- E 검사: `test_forecast_without_score_is_insufficient_and_keeps_partial_body`, `test_forecast_with_score_stays_ready`.

## 6. F5–F9 및 이름 규칙

### 6.1 F5 — reuse 재생성: 부분 통과

- 새 실행기 `run_section_regeneration`(`bundle_pipeline.py:1546-1779`)이 **실제 묶음**으로 작성한다.
  `reuse`는 `store.load_information_bundle`로 저장 묶음을 읽고 `collect_with_bodies`를 부르지 않는다(수집 0).
  옛 노드를 돌려 놓고 "재사용"이라고 적던 이전 경로는 `preview_admin.py:878-885`에서 **거부**로 바뀌었다.
- 응답도 사실에 맞게 갈린다(`preview_admin.py:810-840`): `reuse`면 "묶음만 재사용", `refresh`면 "새로 수집".
- 남은 조건 2건:
  1. **AI 전망·배당 재생성이 게이트에서 막힌다.** `create_section_run`이 재생성 분기보다 **먼저**
     `_section_implementations(...)`를 부른다(`preview_admin.py:733`). 그 함수는
     `sections._IMPLEMENTED_SECTIONS`(`sections.py:79-85`, `section_odds`·`section_ai_forecast` 없음)로 422를 낸다.
     직접 확인: 두 섹션 모두 `"실제 조사·생성 구현이 아직 등록되지 않았습니다"`로 거부된다. 즉 `REGENERABLE_SECTIONS`에
     들어 있지만(`bundle_pipeline.py:1487-1493`) API로는 도달할 수 없다. 조정자 지시의 "F5 실제 reuse 묶음"은
     선수·부상·매체 3섹션에서만 성립한다.
  2. **재생성 경로가 F2 주입을 빠뜨린다.** `_call_bundle_builder` 호출에 `player_candidates`가 없고
     `resolver=None`이다(`bundle_pipeline.py:1718-1729`). 그래서 재생성한 '주목 선수'는 묶음 `roster`만 쓰고,
     이름 해석기 없이 원문 표기를 유지한다(같은 응답 표기는 표시에 반영되나 진단에 실패가 남는다).
  - 참고: `_call_bundle_builder`의 필수 인자 검사(`:577-590`)는 `name in kwargs`일 때만 누락으로 세므로,
    **아예 넘기지 않은** `player_candidates`를 잡아내지 못한다(직접 확인: `missing=[]`). 그래서 위 누락이 조용히 지나간다.

### 6.2 F6 — nested availability: 통과

- `preview_admin.py:1126-1146`이 `availability{available,reason,artifact_id,sequence}` + `bundle` + `summary`를 낸다.
- A의 테스트도 중첩 기준으로 바뀌었다(`test_bundle_integration.py:276-279`, `:308-311`).
  프론트 파서(`informationBundle.ts:471-480`)와 manifest §4가 기대하는 모양과 이제 같다.

### 6.3 F7 — 홉 예산·자동 redirect: 부분 통과

- **해결됨**
  - `StandardHttpClient`/`ScraplingHttpClient`가 `supports_hop_gate=True`이고, 루프마다 **전송 직전** `on_hop`을 부른다
    (`retrieval.py:241,256-265`, `:359,373-380`). 게이트가 거부하면 그 홉은 나가지 않는다.
  - `urlopen`의 자동 추종을 끈다(`_no_redirect_opener`, `:443-455`) — 3xx를 직접 받아 홉을 센다.
  - 게이트 없는 클라이언트는 `1+MAX_REDIRECT_HOPS`를 **전송 전에 예약**하고 실제 홉 수를 안 뒤 반환하며,
    예약을 넘긴 출처는 `redirect_over_budget`으로 **채택하지 않는다**(`:1263-1359`).
  - 검증: `test_budget_caps_actual_transmissions_not_just_accounting`(예산 3에서 실제 전송 3),
    `test_standard_http_client_does_not_follow_redirects_implicitly`(핸들러가 `None` 반환).
- **남은 문제 — 홉이 논리호출 시도 상한에 걸린다.** 홉 차감이 `budget.charge(...)`를 쓰고
  `charge`는 `attempts_by_call`을 올린다(`retry.py:425-438`). 그래서 한 `fetch:` 호출의 **홉 합계**가
  `attempts_per_call`(기본 3, `retry.py:75`)에 닿으면 게이트가 거부한다. 직접 확인:

  | 실제 홉 | 전송 | api_used(상한 24) | 결과 |
  |---|---|---|---|
  | 1 | 1 | 1 | 채택 |
  | 2 | 2 | 2 | 채택 |
  | 3 | 3 | 3 | 채택 |
  | 4 | 3 | 3 | **미채택(budget_exhausted)** |

  같은 조건에서 `attempts_per_call=6`으로 두면 5홉이 정상 채택된다(전송 5). 즉 원인은 예산이 아니라 시도 상한이다.
  `MAX_REDIRECT_HOPS`가 5이므로 **4~5홉 URL은 예산이 24 남아 있어도 항상 실패**한다. 원 검토 F7의 "상한 초과 전송"은
  사라졌지만, 그 대신 리다이렉트가 긴 정상 기사에서 본문을 잃는 동작이 생겼다. 실패 사유 문구도 `budget_exhausted`라
  원인(시도 상한)을 오해하게 한다.
  - 가장 작은 수정(문장): 홉은 `reserve_transports`/`release_reserved`처럼 **사용량만** 잡고 시도 수는 올리지 않는다
    (`retry.py`에 이미 그런 경로가 있다). 또는 홉 전용 상한을 따로 둔다.
- 참고: 이전 구현의 `_charge()` 헬퍼는 지금 호출되지 않는 죽은 코드다(`retrieval.py:1093`, 호출 0회).

### 6.4 F8 — bundle hash: 통과

- `information_bundle.py:859-862`가 해시를 **항상 현재 내용으로 다시 계산**하고 저장값을 쓰지 않는다.
- 직접 확인: 전달 기록 1건을 붙인 뒤 저장 해시와 재계산 해시가 **같다**(이전에는 달랐다).

### 6.5 F9 — 배당 팀 이름: 통과

- 파이프라인이 D0 팀 이름을 `collect_with_bodies(home_team_names=…, away_team_names=…)`로 넘긴다
  (`bundle_pipeline.py:847-856`). 재생성 refresh도 넘긴다(`:1693-1694`).
- 직접 확인(지원 형식 `HomeTeam,AwayTeam,B365H/D/A` 표 + 팀 이름 전달): `quotes=1`, `Bet365 2.1/3.4/3.2`,
  `market=1x2_regulation`. 팀 이름 미전달이면 `quotes=0`(값을 만들지 않음).
- 한계(차단 아님): 파서는 **CSV 열 이름 규약**(`HomeTeam`/`AwayTeam`, `B365H` 같은 업체 접두+H/D/A)만 읽는다.
  표가 본문 중간에 산문과 섞여 있으면 `unknown_table_structure`가 된다. 이는 설계 §58의 "구조를 알 수 없는
  배당 자료는 채우지 않는다"와 일치하므로 결함으로 세지 않는다.

### 6.6 DB 한글 우선 / 같은 응답 fallback: 표시 규칙 통과

- `_apply_model_labels`(`bundle_sections.py:1102-1143`)가 `mapping_status=resolved`(DB 확인) 행은 **덮어쓰지 않고**,
  DB에 없는 행만 같은 응답 표기를 쓴다. 직접 확인: DB 값 `엘링 홀란`이 유지되고, 미해석 행은
  `name_source="model_same_response"`로만 대체된다.
- 같은 응답 표기는 `structured.korean_labels`에 남고(`:1308-1311`), 해석기가 없으면 반영하지 못했다는 **진단**이 남는다
  (조용히 버리지 않음).
- 제약(차단 아님): 제품이 주입하는 `_ResolverHandle`에는 `register_model_labels`가 **없다**(`sections.py:1166-1235`에 미구현).
  `register_model_labels`는 `DisplayNames`·`DisplayNameBridge`에만 있다. 그래서 제품 경로에서는 등록 호출이 생략되고
  진단 문구("주입되지 않아 …")가 사실과 다르게 나간다(실제로는 주입됐지만 메서드가 없음). 표시 결과는 `_apply_model_labels`
  덕분에 의도대로 동작한다.

## 7. 실행한 검사 (대표 기존 검사만, DB·HTTP·모델 0)

| 명령 | 결과 | 비고 |
|---|---|---|
| `pytest tests/preview/test_bundle_review_fixes.py -q` | **12 passed** | E의 신규 대표 검사. 기록 transport만 사용, DB 픽스처 없음 |
| `pytest tests/preview/test_bundle_retrieval.py tests/preview/test_bundle_sections.py -q` | **35 passed** | F7·F9·상한·중복수집 및 섹션 정직성 규칙 |

- `test_bundle_pipeline.py`·`test_bundle_integration.py`는 `client`/`session_factory`(테스트 DB)를 요구하므로
  **DB 0회 지시에 따라 실행하지 않았다.** 그래서 F5의 API 도달성은 코드 경로와 게이트 함수 직접 호출로 판정했고,
  F2의 제품 경로 영향도 builder 단위 확인으로 판정했다(§3).
- A 소유 `test_bundle_pipeline.py` 3건이 E의 대역 문제로 실패한다는 E 보고 §4의 주장은 **재실행하지 않아 확인하지 못했다**(DB 필요).
  다만 현재 파일에는 `delivery=None`을 돌려주는 스파이(`:948-951`)와 `assert deliveries`(`:299`)가 남아 있어 정합하다.

### 확인 중 사고 1건 (데이터 접근 없음)

- 제품 해석기의 동작을 확인하려고 `_ResolverHandle`을 **dummy DSN**으로 만들고 `resolve_player`를 호출했더니,
  scope 없이도 `_names_for(())`가 아니라 빈 scope 키로 조회를 시도해 **DNS 해석 실패**(`nodename nor servname`)로 끝났다.
  연결 대상이 존재하지 않는 호스트라 DB 접근·질의·쓰기는 **없었다**. 이후 같은 확인은 DB를 전혀 쓰지 않는 가짜 해석기로 다시 했고,
  `_ResolverHandle`의 계약(scope 없으면 `KeyError`)은 **DB 접속 없이** `_names_for(())`가 `None`을 돌려주는 경로로 확인했다.
  이 시도는 실수였고, 그 이후로는 외부로 나갈 수 있는 객체를 만들지 않았다.

## 8. 남은 조건 (차단/비차단)

**차단(현재 범위 실패)**

1. **F2 제품 경로 이름 확인**: scope 미전달로 `_ResolverHandle`이 `KeyError` → 선수 후보 0건. builder가 `scope_team_ids`를
   넘기거나 handle이 `player_id`만으로 해석하게 고쳐야 한다(§3).

**비차단(부분 통과의 남은 조건 — 후속 후보)**

2. F5-a: `section_odds`·`section_ai_forecast`가 `_section_implementations` 게이트에서 422로 막혀 재생성 API로 도달 불가.
   `REGENERABLE_SECTIONS`와 게이트 목록이 어긋난 상태다.
3. F5-b: 재생성 경로가 `player_candidates`·`resolver`를 넘기지 않아 재생성한 '주목 선수'가 묶음 roster에만 의존한다.
4. F7-b: 홉 차감이 `attempts_by_call`을 올려 4~5홉 URL이 예산과 무관하게 실패하고, 사유가 `budget_exhausted`로 오표기된다.
5. 참고: `_charge()`(retrieval)와 `_ResolverHandle.register_model_labels` 부재 — 죽은 코드/오해 소지 정리 항목.
6. 사용자 확인 대기: 새 버전(`mp11-bundle-sections-2`, prompt-2)으로 **섹션 워크플로우 승인**을 다시 받아야 한다.
   기존 승인은 새 프롬프트·자료 채택·필수 판정을 덮지 않는다(E 보고 §7-2와 일치).

## 9. 범위 밖으로 남긴 것

- `test_outlook_module.py` 15건(기존 시계 문제) — 확인·수정·재실행하지 않았다.
- 전체 스위트, 실제 브라우저, 유료 실행, 운영 DB 대조, 새 재현 스크립트·제품·테스트 편집 — 하지 않았다.
- 실제 유료 실행 1회에서 순위 문장·부상 사실·선수 후보가 **본문에 반영되는지**는 여전히 A의 후속 실행 증거로만 확인된다.
  이 보고서는 요청 설정까지의 연결만 확인했다.

## 10. 후속 확인 (A의 대역 제거·신규 검사, 2026-11-11T15:57 KST)

> **갱신 통지 (16:00 KST).** 이 절을 쓰는 도중 A가 `bundle_pipeline.py`(`37d173f11bde58e5`, 15:58:42),
> `retrieval.py`(`d2a8b2e829fcf012`, 15:59:23), `retry.py`(`286902453f96b8cb`, 15:59:05)를 **다시 고쳤다.**
> A는 동결을 지시받은 상태였으므로 이는 지시 위반이지만, 내용은 내가 §8에 올린 F5-a·F7-b 수정이다.
> 그래서 §10.3과 §10.4의 일부는 **이미 낡았다.** 아래 §10.6에 새 코드 기준 재판정을 덧붙인다.
> §2~§6의 본문 판정은 A가 건드리지 않은 파일(`bundle_sections.py`·`section_structured.py` 등)에 대한 것이라 그대로 유효하다.

A가 `test_bundle_pipeline.py`의 임시 대역(`_contract_builder_stub`/`_install_contract_builder`)을 **삭제**하고
실제 `build_bundle_section` + 기록 transport로 되돌린 것을 현재 파일에서 확인했다(해당 문자열 0회,
`test_bundle_pipeline.py` 해시 `79bd1526585c9926`, 15:40:38). `app/preview/*`는 내 §1 해시에서 **변경 없음**.

### 10.1 A의 신규 검사가 F2 차단을 해소하지는 않는다 (판정 유지)

`test_db_stats_and_names_reach_the_real_writer_prompt`(`:991`)는 대체 스냅샷에서
`"display_name_ko": "엘링 홀란"`을 **손으로 채운** 행을 넣고 `"엘링 홀란" in payload`를 단언한다.
그러나 실 D0 경로는 `season_stats_with_state(..., name_lookup 미전달)`(`bundle_pipeline.py:237-242`)이라
`display_name_ko`가 **항상 `None`**이다(`player_stats.py:374`). 같은 행을 실 D0 동작(`None`)으로 두면
같은 단언이 **실패**한다(직접 확인). 즉 이 검사는 "이름이 이미 채워져 있으면 프롬프트에 도달한다"만 증명하고,
"DB에서 이름을 채워 넣는 배선"은 여전히 비어 있다. §3의 차단 판정은 그대로 유지된다.

### 10.2 "게이트 미지원 클라이언트는 제품 경로에 진입할 수 없다" — 사실로 확인

A 주장을 코드로 확인했고 **맞다**: 제품 경로는 `http=`를 주입하지 않고(`preview_admin.py`·
`scripts/preview_bundle_live_once.py`에 주입 없음), `collect_with_bodies`의 기본값이 `None`이면
`default_http_client()`가 선택되며 현재 환경에서 `StandardHttpClient`(`supports_hop_gate=True`)가 나온다
(`retrieval.py:1172`, 직접 확인). 따라서 **예약 방식(게이트 미지원) 경로는 테스트 대역에서만** 도달한다.
§6.3의 F7-b 지적은 그 전제를 좁혀 다시 적는다.

### 10.3 F7-b를 좁혀 다시 씀 (제품 경로 기준)

게이트 지원 클라이언트만 제품에서 쓰이므로, 실제 영향은 "상한 초과 전송"이 아니라
**4~5홉 URL이 `attempts_per_call=3`에 걸려 예산 24를 남기고도 실패**하는 동작이다(측정: 1·2·3홉 채택, 4홉 전송 3 후 실패,
`attempts_per_call=6`이면 5홉 정상). 이는 게이트 클라이언트에서도 그대로 발생한다(내 측정이 게이트 클라이언트로 했음).
차단은 아니지만, 실제 기사 URL이 리다이렉트를 4회 이상 쓰면 본문을 잃고 사유가 `budget_exhausted`로 오표기된다.

### 10.4 이번 후속 확인에서 바뀌지 않은 것

- F5-a(재생성 게이트에서 `section_odds`·`section_ai_forecast` 422), F5-b(재생성 경로 `player_candidates`/`resolver` 누락),
  F2 차단, `_charge` 죽은 코드, `_ResolverHandle.register_model_labels` 부재 — 모두 §8 그대로다.
- A가 갱신한 manifest(`2e4bc121c62302b6`, 15:43:55)는 재생성 경로를 "구현 완료"로 적지만,
  위 F5-a 게이트가 그 경로의 두 섹션을 막고 있어 **문서와 실제 도달 가능 범위가 어긋난다**(§8-2와 같은 항목).

### 10.5 방법 메모

이 후속 확인은 메일이 도착하지 않아 내가 `inbox`로 직접 찾아 읽은 지시와 A의 최신 파일을 대조한 것이다.
새 파일은 만들지 않고 이 보고서 §10만 덧붙였다. 유료·HTTP·DB 호출은 이번에도 0회다.

## 10.6 A의 16:00 직전 추가 수정에 대한 재판정

A가 동결 지시 이후 세 파일을 더 고쳤다. 내 지적과 대응 관계는 다음과 같다.

### F7-b (홉/시도 분리): **해결됨**

- `RunBudget.charge_transport()`가 새로 생겼고(`retry.py:458-484`) 홉은 **사용량만** 차감하며
  `attempts_by_call`을 올리지 않는다. 게이트가 `budget.charge_transport(...)`를 쓴다(`retrieval.py:1244-1262`).
- 직접 확인(게이트 지원 클라이언트, `attempts_per_call=3`, API 상한 24):

  | 실제 홉 | 전송 | api_used | 결과 |
  |---|---|---|---|
  | 3 | 3 | 3 | 채택 |
  | 4 | 4 | 4 | **채택**(이전엔 실패) |
  | 5 | 5 | 5 | **채택**(이전엔 실패) |
  | 10 (상한 3) | 3 | 3 | 미채택 — 예산 상한은 그대로 지켜짐 |

  즉 예산 상한은 유지되면서 시도 상한과 분리됐다. §8-4(F7-b)는 **닫는다**.

### F5-a (재생성 게이트 순서): **해결됨**

- `create_section_run`이 `_section_implementations(...)` 호출보다 **먼저** 새 경로 재생성 분기로 들어간다
  (`preview_admin.py:744-784`). 그래서 `section_odds`·`section_ai_forecast`도 옛 게이트 422를 거치지 않는다.
- 이 분기는 `_model_transport`가 없으면 422로 거부하므로 모의 대체는 여전히 없다.
- §8-2(F5-a)는 **닫는다**. 다만 A의 manifest가 재생성을 "구현 완료"로 적은 것은 이제 사실과 맞다.

### F5-b (재생성 주입 누락): **남음**

- 재생성 빌더 호출이 여전히 `resolver=None`이고 `player_candidates`를 넘기지 않는다(`bundle_pipeline.py:1736-1747`).
- 그래서 재생성한 '주목 선수'는 묶음 `roster`만 쓰고, 그 roster의 `display_name_ko`는 D0 경로에서 `None`이므로(§3)
  이름 있는 후보가 나오지 않는다. §8-3은 그대로 남는다.

### F2 (제품 경로 이름 확인): **부분 개선, 차단 유지**

- `_open_name_resolver(team_ids)`가 그 경기의 두 팀 범위로 해석기를 **미리 데운다**(`bundle_pipeline.py:593-617`,
  호출 `:1452`). 이는 모델 응답 선수 이름 해석(`_player_rows`, scope 전달됨)에는 도움이 된다.
- 그러나 `_resolver_player_name`은 여전히 `scope_team_ids`를 넘기지 않고(`bundle_sections.py:531-556`),
  `_ResolverHandle.resolve_player`는 `scope_team_ids or ()`로 조회하므로 **캐시가 데워져 있어도 `KeyError`**다.
  직접 확인(캐시에 `(4,13)` 인덱스를 넣은 상태): scope 없이 호출 → `KeyError`, scope `[13,4]` 호출 → 이름 반환,
  builder의 `_resolver_player_name(533, resolver)` → **`None`**.
- 그래서 **선수 후보 목록**(`_roster_lines` → `_resolver_name`)은 여전히 이름을 못 얻는다. 차단 판정 유지.
- 가장 작은 수정: builder가 `_resolver_name`/`_resolver_player_name` 호출 시 `scope_team_ids`(홈·원정 팀 id)를 넘긴다.
  `_player_rows`는 이미 그 값을 받고 있으므로(`bundle_sections.py:923`, `:934`) 전달 경로만 추가하면 된다.

> 주의: A가 15:58~15:59에 파일을 더 고쳤으므로, 이 재판정도 **그 시점 스냅샷**이다. 이후 추가 변경이 있으면
> §8의 남은 항목(F2·F5-b)만 다시 보면 된다. 유료·HTTP·DB 호출은 재판정에서도 0회다.

**EDITING STOPPED** — 이 보고서 작성 이후 이 세션은 어떤 파일도 추가로 만들거나 고치지 않는다.
