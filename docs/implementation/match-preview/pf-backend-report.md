# PF-B — 부상 이름·사진 연결과 배당 실제 공급 경로

작성: 2026-11-12 KST. 담당: DeepSeek 구현 워커(PF-B). 실제 모델 `deepseek-ai/deepseek-v4.1-flash-1017`(dsh-tui, Max 유지).
소유 범위: backend(`app/preview/**`, `app/api/v1/preview_admin.py`)와 대응 `tests/preview/**`. frontend·`Plans.md`·public/저장 결과는 수정하지 않았다.

## 1. 결론 먼저

| 항목 | 원인 구분 | 상태 |
|---|---|---|
| 부상 영문 이름·사진 부재 | **코드 결함** | 수정. 저장된 run `6c2ce4c2…`의 기존 payload만으로 한글 이름·외부 ID·사진이 실제로 채워짐(실측) |
| 배당 부재 | **자료 결함 + 미연결 코드 경로** | 공개 표 미확인은 자료 사실. `/odds` 보충 경로를 신설했으나 **이 환경에 API-Football 키가 없어 실제 읽기 0회**(합성값 없음) |
| 하단 주목 선수/AI 전망 중복 | **frontend** | PF-F 소유. 이 워커는 손대지 않음 |

## 2. 부상 이름·사진 — 원인과 수정

### 원인(코드)

1. 저장된 R2 모델 응답이 세 선수 모두 `player_id: null`로 왔다(저장 아티팩트 원문 확인).
2. `bundle_sections._injury_rows`는 int가 아닌 `player_id`를 그대로 `None`으로 두고, 이름을 DB와 대조하는 경로가 없었다.
3. `section_structured._injuries`는 `id_context.player_external_id(player_id)`가 있어야 `external_player_id`/`photo_url`을 만든다 → 셋 다 `null`.
4. 그래서 본문에는 한글 표기가 있어도(다른 경로가 문장을 치환) 표 쪽은 영어 이름·사진 없음으로 남았다.

대조군: 같은 저장본의 `section_players`는 `player_id`가 있어 `external_player_id`/`photo_url`이 정상으로 채워졌다(Haaland 1100 등). 즉 결함은 **부상 행 경로에만** 있었다.

### 수정

- `bundle_sections._verified_injury_player()`: 모델이 적은 **이름**을 이미 주입된 DB 해석기(`resolve_player`)로 확인한다. 범위는 `_scope_team_ids()`가 만든 **이 경기 두 팀**뿐이다. 모델이 준 숫자는 신뢰 ID가 아니므로 쓰지 않는다.
- `_injury_rows()`: 확인되면 `player_id`와 DB 한국어 표기를 채우고, **모델이 적은 ID가 이름과 다른 선수를 가리키면 ID를 비운다**(다른 선수 사진 방지). 확인되지 않으면 ID 없이 이름만 남긴다.
- `structured` payload에 `player_id`/`team_id`를 함께 저장한다(다음 경로가 화면 값을 만들 수 있게).
- `section_structured.StructuredIdContext`: `scope_team_ids`를 받고 `player_by_name()`/`team_by_name()`을 추가했다. 저장 payload에 ID가 없고 이름만 있는 **기존 저장본**도 재읽기에서 ID·외부 ID·사진을 얻는다. 저장 원문은 그대로 둔다(투영만 개선).
- `preview_admin.get_section_results`: `StructuredIdContext`에 이 경기 두 팀 범위를 넘긴다(새 연결·새 grant 없음. 이미 열린 이름 해석기 재사용).

### 실제 자료 근거(읽기 전용, 쓰기·모델호출 0)

run `6c2ce4c2-68c5-4d9b-8863-ac068e063c58` / fixture 1557474.

| 모델이 적은 이름 | 확인된 내부 ID | 외부 ID | DB 한국어 표기 | 사진 URL |
|---|---|---|---|---|
| Marc Guéhi | 549 | 67971 | 마크 게히 | `.../players/67971.png` |
| Antoine Semenyo | 88 | 19281 | 앙투안 세메뉴 | `.../players/19281.png` |
| Tom Cairney | 132 | 19025 | 톰 케어니 | `.../players/19025.png` |

팀 표시 이름도 저장 payload의 `team`(Manchester City/Fulham)에서 DB 한국어 값(맨체스터 시티/풀럼)으로 확인된다.

## 3. 배당 — 원인 분리와 신설 경로

### 원인(자료)

- 저장 묶음: `odds.available=false`, `quotes=[]`, 진단 `"접근 가능한 공개 배당 표에서 이 경기의 1X2 값을 확인하지 못했습니다."`
- `retrieval._collect_odds`는 **이미 수집한 본문**만 CSV 표로 파싱하며 새 HTTP를 보내지 않는다. 이 실행의 수집 본문에 1X2 표가 없었다.

### 원인(코드)

- API-Football `/odds`(`sources/api_football.py:parse_odds`, `data.py` D0 경로)는 **bundle 경로에서 호출되지 않았다.** 계획의 "API-Football 보완"이 실제로 연결되어 있지 않았다.

### 수정

- 신규 `app/preview/sources/provider_odds.py`: 경기 한 건의 `/odds`를 **한 번** 읽어(`max_retries=1`) 정규시간 1X2 세 값이 모두 있고 신선도(6시간)를 통과한 줄만, 서로 다른 북메이커 **최대 3행**으로 만든다. `/predictions`·라이브 시장·합성값은 쓰지 않는다. 키는 기존 설정(`Settings.api_football_key`)만 재사용하고 값은 출력하지 않는다.
- `bundle_sections._odds_section(provider_odds=...)`: 공개 표 값을 **1행으로 먼저** 두고 남는 자리만 제공자 줄로 채운다. 제공자 결과가 없으면 이전과 동일하게 빈 섹션 + 사유다.
- 호출 지점은 **명시적 생성/재생성** 두 곳뿐이다.
  - `bundle_pipeline._section_node`(SEC_ID=section_odds): 공개 표 채택값이 **없을 때만** 호출.
  - `bundle_pipeline.run_section_regeneration`: 배당 섹션을 명시적으로 다시 만들 때만.
  - `_provider_odds_for`가 API 예산을 먼저 확인하고 `RequestClass.API`로 차감한다(예산 없으면 전송 0 + 사유).
- **GET reader 경로에는 넣지 않았다.** `section_preview`/`preview_admin` 조회는 `provider_odds`를 넘기지 않으므로 저장 결과를 다시 여는 것만으로 외부 호출이 생기지 않는다.
- `_call_bundle_builder`에 `OPTIONAL_BUILDER_PARAMS=("provider_odds",)`를 두어, 이 인자를 받지 않는 기존 검사 대역에는 넘기지 않는다(필수 인자 계약은 그대로 강제).

### 실제 읽기 결과(정직 보고)

- 이 환경에는 API-Football 키가 **없다**: `Settings().api_football_key` 미설정, `~/.config/match-preview/*.env` 및 셸 환경에 해당 키 이름 없음, 실행 중 서버(127.0.0.1:8000) 환경에도 없음.
- 그래서 실제 `/odds` 읽기는 **0회**였고, 결과는 `sent=0`, 사유 `"API-Football 키가 설정되지 않아 배당 보충 읽기를 시작하지 않았습니다…"`다.
- **실제 배당을 표시했다고 보고하지 않는다.** 키가 연결되면 같은 코드가 그대로 1회 읽기 → 최대 3행을 만든다. 저장본 반영은 새 배당 섹션 실행(1회)이 필요하다.

## 4. 변경 파일

- `app/preview/modules/bundle_sections.py` — 부상 이름→검증 ID/한글명 연결, `player_id`/`team_id` 저장, 배당 섹션 제공자 보충 인자
- `app/preview/section_structured.py` — 이름 기반 확인(`player_by_name`/`team_by_name`), 범위 인자, 부상 투영에 적용
- `app/preview/bundle_pipeline.py` — `_provider_odds_for`, 배당 노드/재생성 연결, `OPTIONAL_BUILDER_PARAMS`
- `app/preview/sources/provider_odds.py`(신규) — `/odds` 1회 읽기 + 공개 표 우선 병합
- `app/api/v1/preview_admin.py` — 섹션 결과 구조 값에 경기 팀 범위 전달
- `tests/preview/test_bundle_review_fixes.py` — 대표 검사 5건 추가

frontend, `Plans.md`, public 스키마, 저장 결과, 마이그레이션은 수정하지 않았다. 모델 호출·전체 생성·수집·서버 제어 없음.

## 5. 검사 명령과 결과

아래는 실행한 명령과 그때 관측한 출력이다(새 실행 없음).

```
# 1) 수정한 검사 파일 단독
./.venv/bin/python -m pytest tests/preview/test_bundle_review_fixes.py -q
  19 passed

# 2) 번들·해석기·표시 대표 7개 파일
./.venv/bin/python -m pytest tests/preview/test_bundle_integration.py tests/preview/test_bundle_runtime.py \
  tests/preview/test_bundle_pipeline.py tests/preview/test_bundle_sections.py \
  tests/preview/test_localized_names.py tests/preview/test_availability_module.py \
  tests/preview/test_presentation.py -q
  152 passed, 2 skipped

# 3) 구조 값·관리자 조회 경로
./.venv/bin/python -m pytest tests/preview/test_inspection_api.py tests/preview/test_admin_access.py \
  tests/preview/test_run_store.py -q
  45 passed

# 4) 변경 경로 6개 파일 묶음(최종 확인)
./.venv/bin/python -m pytest tests/preview/test_bundle_review_fixes.py tests/preview/test_bundle_integration.py \
  tests/preview/test_bundle_runtime.py tests/preview/test_bundle_pipeline.py \
  tests/preview/test_bundle_sections.py tests/preview/test_inspection_api.py -q
  109 passed, 2 skipped
```

네 명령은 서로 다른 파일 묶음이다. `109`는 4번(6파일 묶음)의 결과이고 `19/152/45`는 1~3번의 결과다.
같은 실행의 다른 표기가 아니며, 어느 것도 실패를 숨기지 않는다(모두 `0 failed`).

대표 확인(읽기 전용, 저장 원문 무변경): 수정된 투영으로 run `6c2ce4c2…`의 `section_availability`를 다시 계산하면 `마크 게히/앙투안 세메뉴/톰 케어니`, `player_id 549/88/132`, `external_player_id 67971/19281/19025`, `photo_url` 3건이 모두 채워진다.

## 6. 새 검사와 실패 시 사용자 영향

- `test_injury_name_only_row_links_to_verified_db_player_id` — 실패하면 화면에 부상 선수 한글 이름·사진이 다시 사라진다(사용자가 지적한 증상의 회귀).
- `test_injury_name_not_in_db_keeps_name_without_id` / `test_injury_conflicting_model_player_id_is_dropped_not_guessed` — 실패하면 DB에 없는 이름이나 다른 선수 ID에 사진을 붙여 **엉뚱한 선수 사진**이 나간다.
- `test_provider_odds_reads_one_request_and_keeps_three_distinct_bookmakers` — 실패하면 배당 보충이 반복 호출되거나 4행 이상/중복 업체가 표시된다.
- `test_provider_odds_without_key_sends_nothing_and_says_why` — 실패하면 키 없이 호출을 시도하거나 값이 없는 배당을 성공으로 표시한다.
- `test_odds_section_puts_public_quote_first_then_provider_rows` / `test_odds_section_without_any_real_value_stays_empty` — 실패하면 공개 사이트 우선 원칙이 깨지거나 합성 배당이 섞인다.

## 7. 남은 문제

1. **API-Football 키 미설정**: 실제 `/odds` 읽기·실제 배당 표시는 키 연결 후 1회 실행이 필요하다. 현재 저장본은 배당 없음이 정직한 상태다.
2. **기존 저장본의 부상 표시**: 저장 payload에 `player_id`가 없고 팀 문자열이 영어다. 화면 값(한글 이름·사진)은 새 투영으로 해결되지만, **새로 생성하지 않으므로** 저장 payload 자체에는 ID가 남지 않는다.
3. **PF-F 계약 필요사항**: 추가 필드는 없다. frontend `sectionStructured.ts`는 이미 `photoUrl`/`teamExternalId`를 읽는다. 부상 팀 좌우 판정은 `section_availability` 구조 값에 `team_external_id`가 실리므로(이번 수정) **PF-F가 이 필드를 쓰면** 좌우가 ID로 확정된다.
4. 저장본에 배당을 반영하려면 관리자에서 `section_odds` 섹션 실행 1회가 필요하다(새 전체 생성 불필요).

EDITING STOPPED
