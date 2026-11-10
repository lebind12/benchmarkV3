# MP-05P R4 주목 선수 독립 모듈 — 구현 보고

작성: 2026-11-11 KST. 작성자: DeepSeek 구현 워커
(`hive` / `deepseek-ai/deepseek-v4.1-flash-1017`, 추론 강도 `max`, 프로필 `dsh-tui`).
하위 워커 없음. 실제 모델/API 호출 **0회**. 스테이징·커밋 없음(Git index 소유자는 MP-10).

상태: **R4 새 파일 구현 완료. 편집 종료(§8).** 공유 연결은 MP-10 소유이며 이 보고는
그 연결에 필요한 인터페이스만 넘긴다.

## 1. 한 줄 결과

`section_form`(R1, 경기력 전용)과 분리된 **새 독립 모듈 R4 `section_players`**를 새 파일로
구현했다. 각 선정 항목은 `selected_player`(선정 선수, DB 한국어 이름)와
`selection_reason`(선정 이유)을 **분리된 필드**로 내고, 화면도 '선정 선수'/'선정 이유'
라벨로 따로 표시한다. 실제 DB 읽기전용 이름 조회로 `엘링 홀란드`·`알렉산더 츄카 이워비`·
`로드리고 무니즈`가 확인됐고, 저장된 R1 선정을 R4 계약으로 옮긴 **오프라인 예시**만 만들었다
(새 R4 생성 아님).

## 2. 지킨 경계

- **R1/공유 파일 편집 0.** `registry.py`, `modules/__init__.py`, `version_manifest.py`,
  `sections.py`, `runner.py`, `retry.py`, `pipeline.py`, API·`RunInspector`·`types.ts` 등
  기존 공유 파일을 고치지 않았다(`git status`로 확인). 연결은 MP-10
  `task_68ff6b6c2b1d`/`ctx_621041961f56`가 한다.
- **판단 엔진 복제 없음.** 사실/판단 경계는 기존 공유 API `form.validate_response`를
  **호출**한다. 프롬프트 파싱도 `form.parse_model_json`, grounding도 `form.parse_grounding`을
  그대로 쓴다. R4 파일은 "선정 → 두 필드 분리 → DB 이름 확인"만 담당한다.
- **이름 해석기 복제 없음.** `app/preview/localized_names.py`(이름 담당
  `task0c827d5b31a1`/`ctx_bee3cb12a042` 소유)를 import하지 않고 **주입받아** 쓴다
  (`resolver.resolve_player`/`resolve_team`/`rewrite_body` 덕 타이핑). 역할·권한을 새로
  만들지 않았다.
- **호출 1회.** `provider.request_model` 한 번뿐이며 두 번째 종합·검증 호출이 없다.
  예산은 넘겨받은 `RunBudget`만 쓰고 모듈별 상한을 새로 만들지 않는다(코드에
  `plan_limits(`/`BudgetLimits(`/`RunBudget.for_run(` 0건).
- **승인 없음.** 승인 행·워크플로우 승인 상태를 만들지 않았다. 승인은 사용자 몫이다.
- **문체 재평가·유료 호출·새 테스트 스위트 없음.** 사용자가 현 서술 방식을 수용했으므로
  문장 품질 검사나 동의어 행렬, 새 테스트 파일을 만들지 않았다.

## 3. 새 파일과 소유

| 파일 | 역할 |
|---|---|
| `app/preview/modules/players.py` | R4 모듈. 선정 요청 1회·두 표시 필드·이름 확인·본문 조립·노드/빌더 |
| `app/preview/modules/players_contract.py` | R4 JSON 출력 계약(모델 출력 스키마, payload 스키마, 라벨/필드 상수) |
| `app/preview/prompts/players.md` | R4 프롬프트 전문 |
| `frontend/src/features/match-preview/panels/PlayersPanel.vue` | R4 관리자 진단 패널(이름/이유 분리 표시) |
| `frontend/src/features/match-preview/panels/players.ts` | R4 화면 타입·표시 규칙(라벨, 상태 문구, 분리 헬퍼) |
| `scripts/preview_r4_offline_example.py` | 저장 R1 선정을 R4 계약으로 옮기는 **오프라인 예시**(호출 0) |
| `docs/implementation/match-preview/MP-R4-players-report.md` | 이 보고 |
| `docs/implementation/match-preview/evidence/mp-r4-players/` | 증거(예시 JSON·검사 로그) |

재사용만 하고 고치지 않은 공유 모듈: `form.py`(판단 경계·파서), `provider.py`,
`runner.py`(`NodeOutcome`/`NodeImplementation`), `contracts.py`, `retry.py`.

## 4. 안정 인터페이스 (MP-10 연결용)

### 4.1 `app/preview/modules/players.py`

상수:

```
PLAYERS_MODULE_ID = "R4"
IMPLEMENTATION_VERSION = "mp05p-r4-1"
PROMPT_VERSION = "mp05p-r4-prompt-1"
COMPOSE_IMPLEMENTATION_VERSION = "mp05p-r4-compose-1"
LOGICAL_CALL_ID = "section_players/research-r4"
```

함수:

```python
research_players(
    session, *, module_input: ModuleInput, context: ExecutionContext,
    transport, budget: RunBudget, material: PlayersMaterial | None = None,
    resolver=None, name_map: Mapping[str, str] | None = None,
    roster: Sequence[Mapping[str, Any]] = (), id_space: str = "internal",
    prompt_template: str | None = None, model_name: str | None = None,
    now: datetime | None = None, recorded_raw_response=None, origin: str = "live",
) -> PlayersResearch

players_research_node(*, transport, resolver=None, name_map=None, material=None,
                      roster=(), id_space="internal", model_name=None, now=None,
                      mode=None, origin=None) -> NodeImplementation   # module_id="R4"

players_compose_node(*, mode=None) -> NodeImplementation            # module_id="compose_body"

build_players_implementations(*, prepare_data: NodeImplementation, transport,
                              resolver=None, name_map=None, material=None, roster=(),
                              id_space="internal", model_name=None, now=None
                              ) -> WorkflowImplementations

compose_players_body(payload: Mapping[str, Any]) -> ComposedPlayers

resolve_selection_names(items, *, resolver=None, name_map=None,
                        scope_team_ids=None, id_space="internal",
                        id_is_hint=True
                        ) -> tuple[list[dict], list[Mapping]]

load_prompt(path=None) -> str
build_prompt(*, template, facts, roster=(), today) -> str
parse_model_output(text) -> Mapping | None
model_players(payload) -> list[dict]
```

`build_players_implementations`는 `availability`와 **같은 방식**으로 D0 준비 노드를
인자로 받는다. 그래서 이 파일만으로도 공유 `sections.build_implementations`에 붙일 수 있다.

### 4.2 `app/preview/modules/players_contract.py`

```
OUTPUT_CONTRACT_VERSION = "mp05p-r4-players-output-1"
MAX_SELECTED_PLAYERS = 3
DISPLAY_FIELDS = ("selected_player", "selection_reason")
DISPLAY_LABELS = {"selected_player": "선정 선수", "selection_reason": "선정 이유"}
INTERNAL_FIELDS = ("team", "team_id", "player_id", "external_id", "id_space",
                   "name_source", "mapping_status", "mapping_reason", "mapping_detail",
                   "model_selected_player", "evidence", "superlative_basis",
                   "source_url", "claim_id")
MODEL_OUTPUT_SCHEMA, MODULE_PAYLOAD_SCHEMA, contract_summary(), display_fields(item)
```

이 스키마는 **문서·검증용**이다. 제공자에 `response_schema`로 강제하지 않는다(R4는 기존과
같이 정상 호출 + Google grounding 경로를 쓴다). `jsonschema` 패키지는 설치돼 있지 않으므로
스키마 확인은 키·enum·필수 필드 대조로 했다(새 의존성 추가 없음).

### 4.3 저장 payload 모양 (`ModuleResult.payload`)

```json
{
  "module_id": "R4",
  "output_contract_version": "mp05p-r4-players-output-1",
  "implementation_version": "mp05p-r4-1",
  "prompt_version": "mp05p-r4-prompt-1",
  "mode": "live|replay|mock",
  "origin": "live|reused_r1_selection|...",
  "display_labels": {"selected_player": "선정 선수", "selection_reason": "선정 이유"},
  "fixture": {"fixture_id": 0, "league_id": 0, "season": 0, "home_team_id": 0,
              "away_team_id": 0, "kickoff_at": "...", "home_team": "...",
              "away_team": "...", "league": null},
  "players": [
    {
      "selected_player": "엘링 홀란드",
      "selection_reason": "…해결사입니다.",
      "team": "맨체스터 시티",
      "model_selected_player": "Erling Haaland",
      "model_team": "Manchester City",
      "player_id": 533,
      "external_id": null,
      "id_space": "internal",
      "name_source": "db_korean|db_short_korean|original",
      "mapping_status": "resolved|unresolved|resolver_not_injected",
      "mapping_reason": null,
      "mapping_detail": null,
      "team_display_name": "맨체스터 시티",
      "team_mapping": null,
      "evidence": [],
      "superlative_basis": null,
      "source_url": null,
      "claim_id": "r4-player-0"
    }
  ],
  "unmapped": [{"kind": "player|team", "original": "...", "display_name": "...",
                "reason": "...", "detail": "..."}],
  "mapping": {"resolved": 3, "unresolved": 0, "resolver_injected": true},
  "claims": [], "coverage": [], "diagnostics": [], "uncertainties": [],
  "dropped_facts": [], "unasserted_premises": [],
  "search_note": null, "raw_grounding": {}, "raw_model_text": "...",
  "reader_sources": [], "selection_rule_note": "...",
  "attempt_count": 1, "external_calls": 1
}
```

**표시 필드는 `selected_player`·`selection_reason` 둘뿐이다.** 나머지는 내부 메타데이터이며
화면 본문에 합쳐 쓰지 않는다.

### 4.4 `ModuleResult`/`NodeOutcome` 통합

- `players_research_node`는 정상 `NodeOutcome(payload=…, quality, diagnostics,
  unavailable_reason, external_calls)`를 돌려준다. 공통 runner가 이 값을
  `ModuleResult`(module_id `R4`)로 저장한다. **새 계약 모델이 필요 없다.**
- payload의 `claims`(D0 API 사실 + R4 선정 claim)·`coverage`는 기존 계약
  (`EvidenceClaim`/`CoverageEntry`) 모양이다. 다만 `ModuleResult.claims`는
  `EvidenceClaim` 튜플을 기대하므로, runner 경로(권장)에서는 `outcome.payload["claims"]`가
  그대로 dict로 저장되고 `_run_node`가 `tuple(payload.get("claims") or ())`로 넘긴다.
  기존 R2/R3도 같은 방식을 쓰므로 동작은 동일하다. **단독 `run_module`으로 돌릴 때도
  같은 경로다.**
- `players_compose_node`는 `state["research"]["R4"]`를 입력으로 본문을 만든다. 두 표시
  필드를 `선정 선수:`/`선정 이유:` 두 줄로 낸다(한 문장으로 합치지 않음).
- 선정 claim id는 `r4-player-N`으로 정규화했다. 공유 판단 API가 만든 `r1-player-N`을
  그대로 두면 기록에서 R1 결과처럼 읽히기 때문이다(문장·근거는 공유 API 결과 그대로).

## 5. 실제 DB 한글명 의존 (이름 담당 인계 사항)

- 확인한 실제 값(읽기 전용, 범위 한정 `team_ids=[13,4]`):
  `Manchester City → 맨체스터 시티`, `Fulham → 풀럼`,
  `Erling Haaland → 엘링 홀란드`, `A. Iwobi → 알렉산더 츄카 이워비`,
  `Rodrigo Muniz → 로드리고 무니즈`. 로스터 66행만 읽었다.
- 사용한 연결: 저장소 밖 0600 파일의 `PREVIEW_NAMES_DATABASE_URL`
  (이름 담당이 만든 `preview_dev_names_ro` 역할). 값은 출력·기록하지 않았다.
- **`id_space`를 반드시 지정해야 한다.** 저장 DB 경기(`origin=stored_db`)는 `internal`
  (DB 기본키), API-Football에서 수집한 경기는 `external`(API ID)이다. 섞으면 다른
  선수를 고르지 않고 `unresolved`로 떨어진다. MP-10은 경기 자료 출처에 맞춰 넘겨야 한다.
  같은 이유로, MP-10이 **검증된** 선수 ID를 직접 넘기는 경로를 만들면 `id_is_hint=False`를
  써야 한다(R4 기본값은 모델 참조용 힌트 `True`).
- **이름 인덱스는 로스터를 포함해야 한다.** 이름 담당 안내대로 `load_name_index(...,
  include_rosters=True)`(기본값)로 만들어야 이름 매칭이 동작한다. 로스터 없이 만든
  인덱스로는 `Erling Haaland`가 `not_found`가 된다(실측). 그때도 R4는 원래 표기를 유지하고
  `unmapped`에 사유를 남길 뿐, 이름을 만들거나 예외로 멈추지 않는다.
- - 해석 실패는 **원래 표기 유지 + 사유 기록**이다. `ambiguous`/`db_korean_missing`/
  `not_found`/`empty`/`resolver_not_injected`를 `unmapped`와 `mapping`에 남기고,
  화면에는 "요구사항 충족으로 표시하지 않습니다"를 함께 낸다. 한국어 이름을 만들지 않는다.
- 이 모듈은 해석기 인터페이스를 **복제하지 않는다.** 이름 담당이 `resolve_player`/
  `resolve_team`/`rewrite_body` 시그니처를 바꾸면 `players.py`의 덕 타이핑 호출도 함께
  확인해야 한다(현재 `DisplayNames`와 일치).

### 5.1 모델이 적은 ID는 힌트다 (`id_is_hint`)

이름 담당의 최종 시그니처(`resolve_player(..., id_space='internal', id_is_hint=False)`,
`NameReason.CONFLICT`)에 맞춰 호출 지점을 최소 수정했다.

- R4는 모델이 응답에 적은 `player_ref`를 **검증되지 않은 힌트**로 넘긴다
  (`id_is_hint=True`). 모델이 숫자를 잘못 적었다고 해서 범위 안에서 유일하게 확인되는
  한국어 이름을 포기하지 않기 위해서다.
- 반대로 저장 DB/API에서 확인한 **신뢰 ID**를 넘길 때는 호출자가 `id_is_hint=False`를
  지정한다. 그때 ID와 이름이 서로 다른 선수를 가리키면 해석기는 `conflict`로 멈추고
  원래 표기를 유지한다(다른 사람 이름을 붙이지 않음).
- 확인(실제 읽기 전용 DB):

| 입력 | 결과 |
|---|---|
| `player_ref=999999`(모델 힌트) + `Erling Haaland` | `엘링 홀란드` resolved, player_id 533 |
| `player_ref=124`(신뢰 ID) + `Erling Haaland`, `id_is_hint=False` | resolved 안 함, `conflict`, 원래 표기 유지 |

## 6. 오프라인 예시 (새 R4 생성 아님)

`scripts/preview_r4_offline_example.py`는 **이미 저장된 R1 원문**의 `hot_players`를
읽어 R4 계약으로 옮긴다. 결과에는 `origin="reused_r1_selection"`,
`not_live_r4_generation: true`, `model_calls: 0`이 붙는다.

- 읽기 경로 ①: `preview_dev.preview_results`(`--r1-run-id`, 읽기 전용·statement timeout).
- 읽기 경로 ②: 저장 근거 JSON(`--r1-source`). 저장 payload보다 정보가 적다
  (`superlative_basis`·`team`이 빠져 일부 항목이 검증에서 빠질 수 있다).

실행 결과(기준 실행 `6e59041a-3767-4756-a412-991008873f50`, R1 `mp05-form-3`):

| 선정 선수 | 선정 이유(앞부분) | 이름 |
|---|---|---|
| 엘링 홀란드 | 풀럼의 수비진을 상대로 압도적인 피지컬과 결정력을 발휘해… | `db_korean`, resolved, id 533 |
| 알렉산더 츄카 이워비 | 풀럼의 공격 전개와 기회 창출을 도맡아 하는 핵심 플레이메이커로서… | `db_korean`, resolved, id 124 |
| 로드리고 무니즈 | 기회가 왔을 때 과감하게 슈팅을 시도하는 성향을 바탕으로… | `db_korean`, resolved, id 138 |

- 모델·API 호출 **0회**, 승인 행 **0건**, DB 쓰기 **0건**(읽기만).
- 이름을 만들지 않았고, 누락을 채우지 않았다. 3명 모두 DB 값이 있어 미해결 0이다.
- 이 값은 **새 R4 live 응답이 아니다.** 사용자 승인 근거로 쓰지 않는다.

## 7. 검증 (최소 범위)

| 확인 | 결과 | 근거 |
|---|---|---|
| 새 모듈 import·프롬프트 로드 | 통과 | `01-offline-checks.txt` §1 |
| 계약 스키마 키·enum·라벨·분리 표시 | 통과 | 같은 파일 §2 |
| 모델 힌트 ID / 신뢰 ID 충돌 경계 | 통과 | 같은 파일 §4 |
| 저장 payload → 본문 조립(두 줄 분리) | 통과 | 같은 파일 §1 |
| 빈 payload에서 본문을 만들지 않음 | 통과 | 같은 파일 §2 |
| `players_research_node`/`players_compose_node`/빌더 | 통과(오프라인 replay) | `01-offline-checks.txt` §3 |
| `request_model` 호출 **1회**, `response_schema` 미강제, 예산 미생성 | 통과 | 본 보고 §2 |
| 프론트 타입 검사 `vue-tsc --noEmit` | 통과(exit 0) | `01-offline-checks.txt` §5 |
| 실제 DB 한글명 읽기(범위 한정) | 통과 | §5, 이름 담당 증거 `evidence/korean-names/02-real-db-check.json` |
| 실제 D0 노드 payload 모양에서 material 생성 | 통과 | `01-offline-checks.txt` §6 |
| 확인 안 된 수치가 든 이유는 제외(지어내지 않음) | 통과 | `01-offline-checks.txt` §7 |

새 테스트 파일은 만들지 않았다. 통합·유형 검사는 공유 소유자가 배선 후 한 번 수행한다.

## 8. 편집 종료 — 정확한 미스테이징 파일

```
app/preview/modules/players.py                                  (new, untracked)
app/preview/modules/players_contract.py                         (new, untracked)
app/preview/prompts/players.md                                  (new, untracked)
frontend/src/features/match-preview/panels/PlayersPanel.vue      (new, untracked)
frontend/src/features/match-preview/panels/players.ts            (new, untracked)
scripts/preview_r4_offline_example.py                           (new, untracked)
docs/implementation/match-preview/MP-R4-players-report.md        (new, untracked)
docs/implementation/match-preview/evidence/mp-r4-players/offline-example.json  (new)
docs/implementation/match-preview/evidence/mp-r4-players/01-offline-checks.txt (new)
```

- 스테이징·커밋·reset/amend/restore·broad add·env/dist 변경 **0**. Git index 소유자는 MP-10.
- 808건의 기존 삭제와 다른 dirty 문서를 건드리지 않았다.
- backend 8000 / frontend 5173을 재시작·종료하지 않았다.
- 다른 워커 파일(`localized_names.py`, `scripts/preview_dev_names_ro_provision.py`,
  `tests/preview/test_localized_names.py`, 이름 담당 보고서)을 고치지 않았다.

**여기서 편집을 멈춘다.** 남은 통합(등록부·modules `__init__` 버전표·version manifest·
예산 normal 5 / total 8 / 동시 2·`section_players` 섹션 등록·S1 소비·API·UI 공통 연결)은
MP-10 소유이며, coordinator가 소유권을 명시적으로 넘기기 전까지 내가 하지 않는다.
