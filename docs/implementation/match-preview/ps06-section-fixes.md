# PS-06 검토 수정 보고 (F1·F2·F3·F4·R2)

작성: DeepSeek 구현 워커 / 실제 모델 `deepseek-ai/deepseek-v4.1-flash-1017` (dsh-tui)
범위: 검토 보고서 `preview-sections-independent-review.md`의 **F1·F2·F3·F4·R2** 구현 수정.
F5–F9·R1은 이 작업 범위가 아니다(수정하지 않았다).

## 0. 비용·연결 사실 (먼저 읽을 것)

| 항목 | 값 |
|---|---|
| 유료 모델 호출 | **0회** |
| 외부 HTTP 수집 | **0회** |
| 운영 DB 접속·조회 | **0회** (테스트 DB도 열지 않았다 — 아래 검사는 저장을 하지 않는 단위 검사다) |
| 마이그레이션·권한(grant)·서버 재시작 | **없음** |
| 새 에이전트·stage·commit | **없음** |
| 검사가 쓴 transport | `provider.RecordedTransport`(mode=live, `uses_network=False`, `is_recorded_transport=True`) |

모든 프롬프트 증거는 `provider.RecordedTransport.calls`에 실제로 전달된 `RequestSpec`의
`parameters.contents[0].parts[0].text`에서 뽑았다. 화면에 보이는 값은 저장 payload와
같은 값이다.

## 1. 재현한 실패 단언 (수정 전)

`tests/preview/test_bundle_review_fixes.py`를 먼저 작성하고 **수정 전 코드에서 실패**를
확인했다(10 failed / 1 passed). 대표 실패:

```
E AssertionError: assert None == {'lean': 'home', 'reasoning': ['리그 3위'], 'score': '2-0'}
    test_draft_structured_forecast_matches_saved_projection      # F3
E AssertionError: assert <QualityStatus.READY: 'ready'> is <QualityStatus.INSUFFICIENT: 'insufficient'>
    test_forecast_without_score_is_insufficient_and_keeps_partial_body   # F4
```

F1·F2 쪽은 `_sent_prompt()`가 돌려준 실제 요청 본문에 순위 문장·부상 상태·선수 후보가
없어서 실패했다(아래 §3의 수정 후 증거와 대조).

## 2. 무엇을 고쳤나 (파일별)

### `app/preview/modules/bundle_sections.py`

- **F1 (순위·부상 사실)**
  - `_db_material`이 행의 `text`/`sentence`/`statement`를 **먼저** 읽는다. D0이 만든 완성
    문장을 구조 키로 다시 쪼개지 않고 그대로 한 줄로 쓴다. `text`가 있으면 팀 라벨을
    덧붙이지 않는다(문장에 이미 팀 이름이 있다).
  - `_INJURY_KEYS`에 `expected_status`·`type_marker`를 넣었다. 실제 D0 행 모양
    (`{player_name: None, team_id, expected_status}`)이 이제 근거 줄이 된다.
  - 부상 행 이름이 `None`이면 **이름을 만들지 않는다.** 저장 DB에서 읽은 `player_id`와
    **주입된 해석기**가 있을 때만 `_resolver_player_name`이 DB 한국어 이름을 확인한다
    (`id_is_hint=False` — 저장 DB 값이므로 신뢰 ID다). DB 조회는 이 모듈에서 하지 않는다.
  - 부상 사실 id는 `player_id`가 없으면 `api:injury-row<N>`(순번)이다. 없는 선수 id를
    지어내지 않는다.
  - `_DbMaterial`에 `injury_ids`·`injury_lines`를 추가해 **실제 직렬화한 부상 사실**만
    센다. `_injury_state`는 그 건수로 문장을 만든다:
    - 1건 이상 → `저장된 부상 사실 N건을 전달했습니다.`
    - 행은 있으나 직렬화한 값이 없음 → `전달된 부상 사실은 0건이다.`
    - 행 0건·읽기 가능 → `empty_response`
  - `_db_injury_block`이 부상 프롬프트의 `{db_injuries}`를 채운다. 값이 없으면
    "행은 있으나 근거로 쓸 값이 직렬화되지 않았다"고 적고, `_NO_DB_NOTE`(자료가 제공되지
    않았다)로 뭉개지 않는다. **같은 요청 안에서 "전달했다"와 "자료 없음"이 모순되지 않는다.**
  - 부상 섹션의 호출 여부 판정도 `material.injuries`(행 존재)가 아니라
    `material.injury_ids`(실제 근거) 기준이다.

- **F2 (선수 후보)**
  - `_ROSTER_NAME_KEYS`에 통계 조회기의 실제 키 **`display_name_ko`**를 넣었다.
  - `_roster_lines`가 이름 뒤에 **실제 기록 값**(`포지션=`, `출전=`, `분=`, `골=`, `도움=`,
    `평점=`)을 붙인다. 55행을 읽고 "후보 없음"만 내던 상태를 없앴다. 없는 값은 생략하고
    0으로 채우지 않는다.
  - 이름이 없으면 저장된 이름 → 주입된 해석기(신뢰 `player_id`) 순서로 확인하고, 그래도
    없으면 그 행은 후보 줄로 만들지 않되 **몇 행이 이름 없이 남았는지** 밝힌다(개수 혼동
    방지). 읽은 행 수를 후보 수로 말하지 않는다.
  - 팀 이름은 `_team_label`(묶음의 DB 팀 이름)로 붙인다.

- **F4 (스코어 없는 전망)**
  - 전망 문장이 있어도 `predicted_score`가 없으면 `quality=INSUFFICIENT`이고
    `unavailable_reason`에 "AI 예상 스코어가 응답에 없어 필수 본문을 채우지 못했다"를
    남긴다. **부분 본문(전망 문장)은 보존**하고 스코어 절은 넣지 않는다. 스코어를
    만들지 않는다(`structured.forecast.score`는 `None`).
  - 스코어가 있으면 기존처럼 `READY`다(과잉 차단 없음).

- **R2 (한글 표기)**
  - `_model_korean_labels(parsed)` 결과를 이제 **쓴다.** 주입된 해석기의
    `register_model_labels`로 넘겨 DB 값 우선 규칙을 그대로 적용하고(DB가 이기면
    `db_value_wins`로 거부), 모델 응답의 표기를 저장 payload
    `structured.korean_labels`에 남긴다.
  - `_apply_model_labels`가 **DB에서 확인되지 않은 행만** 같은 응답의 표기로 바꾼다
    (`name_source="model_same_response"`). DB에서 확인된 행은 덮어쓰지 않는다.
    대소문자·앞뒤 공백만 같은 표기를 같은 이름으로 본다(그 외 유사 일치 없음).
  - 해석기가 주입되지 않았으면 한글 표기를 반영하지 못했다는 사실을 진단에 남긴다
    (조용히 버리지 않는다).

- **A 인계 계약(시그니처 확장, 기존 인자 유지)**
  - `build_bundle_section(... player_candidates: Sequence[Mapping] | None = None ...)`를
    추가했다. A의 `REQUIRED_BUILDER_PARAMS`가 이미 이 이름을 요구한다.
  - `player_candidates`를 주면 묶음의 `roster`보다 **우선**한다(호출자가 DB 통계에서
    만든 값을 그대로 쓴다. 여기서 DB를 다시 조회하지 않는다).

### `app/preview/section_structured.py`

- **F3**: `_forecast`가 `forecast` 하위 dict를 **먼저** 읽고, 없으면 `ai_prediction`,
  그다음 최상위 `score`/`lean`/`reasoning`을 본다. `structured_from_payload`의 기존
  병합(`{**structured, **data}`)에서 `structured.forecast`가 최상위 dict로 올라오므로
  이 순서가 필요하다. 화면 파서(`sectionStructured.ts:232`)와 백엔드 shape이 이미
  `forecast`를 읽으므로 **서버 투영만 계약에 맞춘다.** `available` 계산은 그대로다.

### 프롬프트 (`app/preview/prompts/bundle_*.md`)

- `bundle_forecast.md`: 스코어가 필수 항목임을 명시. **`null`은 근거가 정말 없을 때만**
  쓰고, 그때 이 초안은 준비되지 않은 초안(`insufficient`)이며 스코어를 추정해 채우지
  않는다고 적었다. 전망 문장은 보존된다.
- `bundle_players.md`: 후보 줄에 `player_ref`와 **실제 기록값**이 함께 온다는 사실,
  이유에 쓰는 수치는 그 값만 쓴다는 규칙을 추가.
- `bundle_availability.md`: `{injury_state_detail}`이 말하는 **전달된 사실 건수**가 실제
  근거 수이며, 0건이면 부상자를 단정하지 않는다는 문장과, 이름이 없으면 순번 id로만
  나타난다는 문장을 추가. id 표기 문장을 `api:injury-<선수 id>` 고정에서 "인용 목록에
  있는 값"으로 고쳤다(순번 id 때문에).

### 버전 (결과 의미가 바뀐 섹션만 올림)

| 섹션 | 구현 버전 | 프롬프트 버전 |
|---|---|---|
| `section_players` | `mp11-bundle-sections-2` | `mp11-bundle-players-prompt-2` |
| `section_availability` | `mp11-bundle-sections-2` | `mp11-bundle-availability-prompt-2` |
| `section_ai_forecast` | `mp11-bundle-sections-2` | `mp11-bundle-forecast-prompt-2` |
| `section_outlook` | `mp11-bundle-sections-2` | `mp11-bundle-outlook-prompt-1` (변경 없음) |
| `section_odds` | `mp11-bundle-sections-2` | `mp11-bundle-odds-no-model-1` (변경 없음) |

`IMPLEMENTATION_VERSION`은 이 파일 전체 축이라 하나만 올렸다. `section_outlook`은
프롬프트가 바뀌지 않았지만 구현 축이 함께 올라간다(같은 모듈). **기존 승인 버전을
덮어쓰지 않는다** — 새 버전으로 다시 확인해야 한다.

## 3. 수정 후 직접 증거 (기록 transport가 실제로 보낸 요청 본문)

F1 — 최종 전망 요청에 D0의 순위 문장이 **그대로** 들어간다(순위 값 없음 문장 없음):

```
- api:standings-13: 맨체스터 시티는 10경기 7승 0무 3패, 승점 21, 리그 3위입니다. 최근 5경기 폼은 LLLWW입니다.
- api:standings-4: 풀럼는 10경기 3승 2무 5패, 승점 11, 리그 15위입니다.
```

F1 — 부상 행(`player_name=None`, `expected_status=doubtful`)이 인용 가능한 사실이 된다:

```
- api:injury-row1: 맨체스터 시티 — 부상: expected_status=doubtful
- `api:injury-row1`      (인용 가능한 근거 id 목록)
```

F2 — 55행을 읽고 실제 후보·기록이 프롬프트에 들어간다(이름 없는 54행은 후보가 아님을 밝힘):

```
- 엘링 홀란 (맨체스터 시티) [player_ref=7000] 포지션=FW, 출전=10, 분=800, 골=0, 도움=0, 평점=7.1
- (이름이 확인되지 않은 통계 54행은 후보로 쓰지 않았습니다.)
```

F3 — 저장 payload `{"structured": {"forecast": {...}}}` → `structured_from_payload`가
`score="2-1"`, `lean="home"`, `reasoning=[...]`, `available=True`를 낸다.

F4 — 스코어 없는 전망: `quality=INSUFFICIENT`, `unavailable_reason` 존재,
본문에 `## AI 경기 전망`만 있고 `### AI 예상 스코어` 없음, `structured.forecast.score is None`.

R2 — DB 한국어가 있으면 DB 값(`엘링 홀란`)이 이기고, DB 값이 없는 선수만 같은 응답의
표기(`필 포든`)를 쓴다.

## 4. 실행한 검사와 결과

```
.venv/bin/python -m pytest tests/preview/test_bundle_review_fixes.py -q
  → 12 passed
.venv/bin/python -m pytest tests/preview/test_bundle_sections.py tests/preview/test_bundle_review_fixes.py -q
  → 22 passed  (기존 10 + 신규 12)
.venv/bin/python -m pytest tests/preview/test_bundle_integration.py -q
  → 17 passed
.venv/bin/python -m pytest tests/preview/test_bundle_retrieval.py test_bundle_discovery.py test_bundle_runtime.py test_section_approvals.py test_workflow_version.py -q
  → 60 passed
.venv/bin/python -m pytest tests/preview/test_localized_names.py tests/preview/test_player_stats_reader.py -q
  → 31 passed
.venv/bin/python -m pytest tests/preview/test_bundle_pipeline.py::test_forecast_without_score_is_not_counted_as_a_complete_run -q
  → 1 passed   (A의 필수 게이트가 내 draft를 그대로 읽는 것을 확인)
```

### 아직 실패하는 검사 (내 파일 밖, A 소유)

`tests/preview/test_bundle_pipeline.py`에서 3건이 실패한다. 원인은 **A의 테스트 대역**
(`_contract_builder_stub`)이 `delivery=None`을 돌려주고 본문을 `f"{section_id} 본문"`으로
고정해 두었기 때문이다. 실패 단언은 `assert deliveries`(묶음에 전달 기록이 없다)와
`assert '선정 선수: 엘링 홀란' in 'section_players 본문'`이다. 내 모듈이 아니라 A가
소유한 대역이 실제 계약(전달 기록·본문)을 흉내 내지 않는 상태다.

같은 조건을 A의 대역 대신 **실제 작성기**로 바꾼 임시 확인(`build_bundle_section`을 그대로
쓰고 6회 계약만 흉내)에서는:

```
status RunStatus.SUCCEEDED
logical ['discovery_people','discovery_outlook','section_ai_forecast','section_availability','section_outlook','section_players']
sections  ['section_ai_forecast','section_availability','section_odds','section_outlook','section_players']
```

즉 6회 논리 호출·5개 섹션 저장·필수 섹션 ready가 성립한다. A는 대역을 실제 계약에
맞추면(전달 기록·본문 생성) 이 3건이 통과한다.

`tests/preview/test_outlook_module.py`(15건)와 `test_form_module`/`test_inspection_api`
일부 오류도 관측되었으나 **내 변경과 무관**하다: outlook 실패는 이 환경의 고정 시각
(`MOMENT = 2026-11-10T16:00Z`)과 실제 현재 시각 차이로 `DeadlineExceeded`가 나
(`외부 매체 전망 조사 호출이 실패했습니다: 전체 실행 기한(1800초)이 지나 더 보내지 않습니다.`)
전송이 0회가 되는 것이고, `test_form_module::test_mock_section_result_cannot_be_approved`는
단독 실행에서 통과한다(순서 의존). 내 파일들은 outlook/form을 import하지 않는다
(`grep`으로 확인).

## 5. A가 알아야 할 출력 계약 (F4)

- **`section_ai_forecast` 초안의 `quality`**: `predicted_score`(홈·원정 정수)가 **둘 다**
  있을 때만 `ready`다. 전망 문장만 있으면 `insufficient` + `unavailable_reason`이며
  본문은 부분 보존된다.
- **`structured.forecast`**: 항상 `{lean, score, reasoning}` 3키다. 스코어가 없으면
  `lean=None`, `score=None`이고 `reasoning`은 모델이 준 값만 남는다.
- **A의 필수 게이트**: `quality == "ready"` + `structured.forecast.score` 존재를 함께
  보면 된다. A가 이미 넣은 `forecast_score_present` 검사와 내 `quality` 변경은 같은 결론을
  가리키며 서로 모순되지 않는다(내 섹션 단위에서 먼저 insufficient가 되고, A의 실행
  단위 게이트가 그 위를 다시 확인한다).
- **부상 섹션 프롬프트 변수**: `{db_injuries}`는 이제 "직렬화한 부상 사실 줄"만 담는다.
  행이 있는데 값이 없으면 "전달된 사실 0건" 문장이 들어간다.

## 6. 인계: 기대 주입과 파일 해시

### A가 넘겨야 하는 주입(이름·형태 고정)

| 인자 | 형태 | 출처 | 내가 하는 일 |
|---|---|---|---|
| `fixture_names` | `{"home_team","away_team","league"}` | A가 만든 팀 표시 이름 | 팀 라벨·경기 제목에 사용 |
| `resolver` | `DisplayNames`(또는 `resolve_player`·`resolve_team`·`register_model_labels`를 가진 파사드) | `sections._name_resolver` | 선수/팀 이름 확인, 한글 표기 등록. **DB 조회는 여기서 하지 않는다** |
| `player_candidates` | `Sequence[{player_id, team_id, display_name_ko, position, appearances, minutes, goals, assists, rating}]` | A의 `_player_candidates` | 묶음 `roster`보다 우선. 없는 값은 만들지 않음 |

`resolver`가 `None`이면: DB 이름 확인 없이 원래 표기를 유지하고, 같은 응답의 한글 표기는
반영하지 못했다고 진단에 남긴다. `player_candidates`가 비면 묶음의 `roster`를 쓴다.

### 파일 해시 (sha256, 이 보고서 작성 시점)

| 파일 | sha256 | bytes |
|---|---|---|
| `app/preview/modules/bundle_sections.py` | `23e7355e7f788340d58264095066e48e208d193e25a4591e784cfedd90610508` | 92854 |
| `app/preview/section_structured.py` | `091dd06b9ebe664c50e7e40eb5cbc74e00410aa390d6185a86a681f1160ab306` | 10529 |
| `tests/preview/test_bundle_sections.py` | `7a60d6a81564f56dc973f9b84388f204a61b804921a625c1f14617e0ee1f64ea` | 17438 |
| `tests/preview/test_bundle_review_fixes.py` | `af93178505a5834cee0714de6c7c3c1793466876f7510048b3dbc1aae6550f23` | 23334 |
| `app/preview/prompts/bundle_players.md` | `724591bff162f8bb19af85b4de9993bbba431196480917ac66d704acedd7bb46` | 3726 |
| `app/preview/prompts/bundle_availability.md` | `db5a6a3e5379fac47aa433ef85f54d7ca086e15b3645c593c50040eff21de289` | 3126 |
| `app/preview/prompts/bundle_forecast.md` | `3d8b93667e783e1a304af84f796dd3c1d3583671a136f52b7cd9648b2d9bbb81` | 3567 |

`tests/preview/test_bundle_sections.py`는 **내용을 바꾸지 않았다**(기존 10건 그대로 통과).
목록에 넣은 것은 인계 대상 파일이기 때문이다.

### 수정한 파일 (내 소유 범위 안)

- `app/preview/modules/bundle_sections.py` — F1·F2·F4·R2 + `player_candidates` 인자
- `app/preview/section_structured.py` — F3
- `app/preview/prompts/bundle_players.md`, `bundle_availability.md`, `bundle_forecast.md`
- `tests/preview/test_bundle_review_fixes.py` (**신규** 12건)
- 이 보고서

손대지 않은 것: `tests/preview/test_bundle_sections.py`(내용 무변경), `bundle_pipeline.py`,
API 라우터, 옛 모듈(`players.py`·`availability.py`·`outlook.py`·`synthesis.py`),
`conftest.py`, 타입 파일, F5–F9·R1.

## 7. 남은 것

1. A가 `test_bundle_pipeline.py`의 대역을 실제 계약(전달 기록·본문)에 맞추면 그 3건이
   풀린다. 내가 A의 파일을 고치지 않는다(소유권).
2. 새 버전(`mp11-bundle-sections-2` + prompt-2)으로 **섹션 워크플로우 승인**을 다시
   받아야 한다. 프롬프트·자료 채택·필수 판정이 바뀌었으므로 기존 승인은 그대로 유효하지
   않다.
3. 실제 유료 실행 1건에서 순위 문장·부상 사실·선수 후보가 본문에 반영되는지는 A의
   후속 실행 증거로만 확인된다(이 작업은 유료 호출 0회).

**EDITING STOPPED** — 이 보고서 작성 이후 이 세션은 어떤 파일도 추가로 만들거나 고치지
않는다.
