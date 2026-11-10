# MP-07 R3 배당·외부 전망 조사 완료 보고

**목표.** 축구를 아는 독자와 중계 준비 스트리머가 이 경기의 **공개 배당, 외부 매체
전망, 제공자 알고리즘 예측**을 섞이지 않은 채로 읽고, 각 값의 출처·시점을 확인할 수
있게 한다. 내부 조사 모듈 하나가 아니라 **섹션 워크플로우 전체**가 사용자 테스트
단위이며, 이번 산출물은 그 워크플로우 안의 조사 노드(R3)와 전용 진단 패널이다.

**한 줄 결론.** R3 조사·본문 조립·섹션 노드 어댑터·전용 패널·검사 25건·프런트 검사
8건을 갖췄고 모두 통과했다. 세 자료 종류는 claim 종류·문단·근거 목록에서 끝까지
분리되며, 검증에서 제외된 배당·매체 전망은 관리자 기록에만 남는다. **실제 모델·API
호출은 하지 않았다.** 검증은 녹화(합성) transport로만 했으므로 live 조사 품질·실제
본문·사용자 승인은 아직 없다.

## 실행 모델

| 항목 | 값 | 확인 방법 |
|---|---|---|
| 제공자 / 모델 | hive / `deepseek-ai/deepseek-v4.1-flash-1017` | 배정 프리앰블 + `DSH_PROFILE=dsh-tui` |
| 추론 강도 | max (설정 변경 없음) | 프리앰블 값, `~/.dsh/profiles/dsh-tui/cordis.patch.yml`의 `reasoning: max` |
| 프로필 | `dsh-tui` | `DSH_PROFILE=dsh-tui` |
| 작업 디렉터리 | `/Users/woolee/benchmark` | CWD |
| 작업 ID / Dispatch | task_29d3e0276b2b / ctx_68e49fe1e4d7 | 배정 프리앰블 |
| 하위 워커 | **없음** (지시: no subworkers) | 이 세션 단독 수행 |
| HEAD (착수) | `db06346` | `git rev-parse --short HEAD` |

모델·추론 강도를 바꾸지 않았고 다른 모델로 대체 실행하지 않았다.

## 파일과 소유권

이번 작업이 **직접 편집한 파일**은 아래가 전부다. 모두 unstaged이며 스테이징·커밋하지
않았다.

| 경로 | 상태 | 성격 |
|---|---|---|
| `app/preview/modules/outlook.py` | 신규 | R3 조사·검증·본문 조립·노드 어댑터 |
| `app/preview/prompts/outlook.md` | 신규 | R3 조사 프롬프트(검색 근거만, 스코어 창작 금지) |
| `frontend/src/features/match-preview/panels/OutlookPanel.vue` | 신규 | R3 전용 진단 패널 |
| `frontend/src/features/match-preview/panels/OutlookPanel.test.ts` | 신규 | 패널 검사 8건 |
| `tests/preview/test_outlook_module.py` | 신규 | 백엔드 검사 25건 |
| `tests/preview/fixtures/outlook.json` | 신규 | 녹화(합성) 모델·API 자료 |
| `docs/implementation/match-preview/MP-07-report.md` | 신규 | 이 보고서 |
| `docs/implementation/match-preview/evidence/mp07/commands.txt` | 신규 | 실행 명령·결과 |
| `docs/implementation/match-preview/evidence/mp07/section-workflow-mock.json` | 신규 | 섹션 워크플로우 3케이스 증거 |

**손대지 않은 공통 파일.** `app/preview/modules/__init__.py`, `registry.py`,
`runner.py`, `provider.py`, `contracts.py`, `data.py`, `app/api/v1/*`,
`frontend/src/features/match-preview/{types.ts,api.ts,router}`,
`ModuleResultPanel.vue`, `RunInspector.vue`, `Plans.md`, `AGENTS.md`, `CLAUDE.md`,
`alembic/`, 808건 기존 삭제. 모두 MP-05·GPT 조정자 소유다.

## 1. 공개 인터페이스 (MP-05 인계용 확정값)

```python
# app/preview/modules/outlook.py
MODULE_ID = "R3"
IMPLEMENTATION_VERSION = "mp07-r3-1"
PROMPT_VERSION = "r3-outlook-1"
OUTLOOK_OUTPUT_CONTRACT_VERSION = "mp07-outlook-output-1"

def research_outlook(
    session, *, context: ExecutionContext, module_input: ModuleInput | None = None,
    transport=None, budget: RunBudget | None = None, actor_id: int | None = None,
    d0: Mapping | None = None, fixture: FixtureIdentity | Mapping | None = None,
    module_execution_id: uuid.UUID | None = None, now: datetime | None = None,
    sleeper=None,
) -> OutlookResearch

def compose_outlook_body(research: OutlookResearch) -> str            # 결정적, 모델 호출 없음
def compose_outlook_sources(research: OutlookResearch) -> tuple[dict, ...]
def compose_outlook_section(payload: Mapping) -> ComposedSection      # compose_body 노드용
def outlook_node(*, transport=None, d0=None, now=None) -> Callable    # form_node와 같은 모양
def outlook_node_implementation(*, mode=RunMode.LIVE, transport=None,
                                implementation_version=..., prompt_version=...)
    -> runner.NodeImplementation
def build_generation_config() -> dict   # {"tools":[{"google_search":{}}], ...}
```

`OutlookResearch.to_dict()`가 저장 payload이며, `reader_body`·`reader_sources`·
`grounding`·`coverage`·`diagnostics`를 함께 담는다.

### runner 등록에 필요한 것 (MP-05가 하는 일)

```python
runner.WorkflowImplementations(
    prepare_data=...,                      # 기존 D0 노드
    research=(outlook.outlook_node_implementation(
        mode=RunMode.LIVE, transport=<공통 Vertex transport>),),
    compose_body=runner.NodeImplementation(  # Adapter: compose_outlook_section 호출
        module_id=runner.COMPOSE_MODULE_ID, ...),
)
runner.run_section_workflow(session, workflow_id="section_outlook", ...)
```

### 인계 시 반드시 같이 넘길 계약 4가지

1. **본문 재사용.** `compose_body` 노드는 `compose_outlook_section(state["research"]["R3"])`
   를 부르면 된다. 이미 계산된 `reader_body`를 그대로 쓰므로 두 번째 모델 호출이 없다.
2. **근거 중복 금지.** `research` 단계가 이미 `state["sources"]`에 근거를 넣는다.
   `compose_body`의 `NodeOutcome.sources`를 비워야 저장 근거가 두 번 들어가지 않는다.
   (초기 증거 생성에서 실제로 10건으로 중복됐고, 그래서 고쳤다.)
3. **D0 자료.** `state["data"]`에 `odds_raw`·`prediction_raw`(저장 아티팩트 본문)를
   넘기면 그 값을 쓴다. 없으면 이 모듈이 같은 실행의 D0 결과가 가리키는 아티팩트를
   저장소에서 직접 읽는다. **어느 경로도 새 API 호출을 만들지 않는다.**
4. **모드 정직성.** `NodeImplementation.mode`는 MP-05가 정한다. 내 모듈의
   `external_calls`는 **실제로 전송된 시도 수**다(공통
   `provider.sent_attempt_count(result, transport.mode)`). 성공 여부로 세지 않는다.
   429 뒤 재시도하면 2회다. mock·replay transport와 설정 부족으로 보내지 못한 시도는
   0회다.

## 2. 세 자료를 어떻게 끝까지 분리했나

| 자료 | 출처 | claim 종류 | 독자 문단 | 근거 항목 `kind` |
|---|---|---|---|---|
| 경기 전 승무패 배당 | D0의 API-Football `/odds` 저장 아티팩트 | `EXTERNAL_FORECAST` | `### 경기 전 승무패 배당` | `bookmaker` |
| 외부 매체 전망 | 모델 Google Search grounding | `EXTERNAL_FORECAST` + `source_url` | `### 외부 매체 전망` | `media` |
| 제공자 알고리즘 예측 | D0의 API-Football `/predictions` | `API_PREDICTION` | `### 제공자 알고리즘 예측` | `api_prediction` |

배당은 업체·시장·기준 시각을, 매체 전망은 매체·URL·게시 시각을, 제공자 예측은
"매체 의견 아님"을 값으로 갖는다. 검사는 세 값이 서로의 자리에 새지 않는지를 본다
(`test_api_prediction_not_media_opinion`은 55%가 매체 문단에 없음을 확인한다).

## 3. 수용 기준별 결과

### 3.1 `test_pre_match_market_not_qualification` 통과

녹화 배당 원문에는 승무패(`Match Winner`)와 함께 라이브 변형(`Match Winner (Live)`),
`To Qualify`, `Double Chance`가 섞여 있다. 결과는 이렇다.

| 시장 | 판정 | 값 |
|---|---|---|
| `Match Winner` (업체 A) | 채택 | 홈 1.85 / 무 3.60 / 원정 4.20 |
| `Match Winner` (업체 B) | 채택 | 홈 1.90 / 무 3.45 / 원정 4.00 |
| `Match Winner (Live)` | 제외 | 라이브 시장, 1X2로 쓰지 않음 (1.10이 승무패로 새지 않음) |
| `To Qualify` | 제외 | 컵대회 진출 시장, 1X2 아님 (1.22 미사용) |
| `Double Chance` | 제외 | 승무패 아님 |

판정 순서는 **라이브 → 다른 시장 → 승무패 화이트리스트**다. 순서를 라이브 우선으로
둔 이유는 `Match Winner (Live)`가 승무패 부분 문자열을 포함하기 때문이다. 그래서
`Live`를 먼저 걸러야 화이트리스트가 라이브를 삼키지 않는다. 시장 이름을 모르면
채택하지 않는다.

### 3.2 `test_other_fixture_odds_rejected` 통과

응답의 `fixture.id`가 요청 경기와 다르면 채택하지 않고 `rejected_odds`에 사유
(`요청한 경기 1200001이 아니라 999999의 배당…`)를 남긴다. 경기 ID가 없을 때도
채택하지 않는다. 결과적으로 배당 근거가 없으므로 본문에 배당 문단 자체가 없고,
coverage는 `validation_rejected`다. 갱신 시각이 오래된 배당도 별도 검사
(`test_stale_odds_rejected`)로 같은 방식 제외된다.

### 3.3 `test_api_prediction_not_media_opinion` 통과

`kind=API_PREDICTION` claim 1건이 `source_url=None`으로 남고
`decision_reason`에 "매체 의견이나 이 서비스의 결론이 아닙니다"가 붙는다. 본문에서는
매체 문단이 먼저, 제공자 예측 문단이 뒤에 오고 `55%`는 제공자 문단에만 있다.

### 3.4 `test_missing_media_uses_api_without_fabrication` 통과

매체 전망이 0건이어도 배당·제공자 예측으로 본문을 만든다. 이때 매체 문단은 만들지
않고(빈 제목 금지), 본문에 URL도 "예상 스코어"도 없다. 소개 문장도 매체 전망을
언급하지 않는다(이 문장은 실제로 한 번 고쳤다. 아래 §6 참조). 검색이 없으면
coverage는 `search_not_found`다.

전송 계층 자체가 없을 때(`test_transport_absent_still_composes_from_api_only`)는
호출하지 않고(`external_calls=0`) 같은 방식으로 본문을 만들며, coverage는
`not_run` + 사유다. 근거가 하나도 없으면(`test_no_sources_at_all_makes_no_body`)
본문은 빈 문자열이고 `quality=insufficient`다. 빈 카드나 안내 문장을 만들지 않는다.

### 3.5 `test_grounding_metadata_missing_is_visible_in_admin` 통과

grounding 메타데이터가 없는 응답에서는 매체 전망을 **채택하지 않는다**(출처를 확인할
수 없으므로). 그 사실은 세 곳에만 남는다.

| 위치 | 값 |
|---|---|
| `result.grounding.present` / `absence_reason` | `False` / "모델 응답에 Google Search grounding 메타데이터가 없어…" |
| `coverage`의 `검색 근거(Google Search grounding)` | `unknown` + 같은 사유 |
| `payload["grounding"]` (관리자 화면) | 위 값 그대로 |
| 독자 본문 | **없음** (검사가 `grounding`·`누락`·`실패`·`미확보` 부재를 확인) |

### 3.6 그 밖에 확인한 것

| 검사 | 확인 내용 |
|---|---|
| `test_media_url_must_exist_in_grounding` | grounding 출처에 없는 주소(창작 URL)는 채택하지 않고 본문에도 없다 |
| `test_predicted_score_without_statement_is_dropped` | 인용문에 없는 예상 스코어는 비운다(3-0 창작 차단) |
| `test_recorded_score_is_kept_when_the_source_states_it` | 출처가 적은 `2-1`은 보존한다 |
| `test_single_model_call_per_research` | 정상 경로 모델 호출 **1회**, 예산 `model_used=1`, 요청에 `tools=[{"google_search":{}}]` |
| `test_mock_mode_is_not_counted_as_live_call` | 모의 실행 `external_calls=0`, `mode=mock` |
| `test_replay_opens_no_socket` | 재생은 소켓을 열지 않고, 저장 응답 변환은 다시 한다 |
| `test_model_failure_keeps_api_body_and_records_reason` | 429 실패에도 API 근거로 본문을 만들고, 실패 문구는 본문에 없고 coverage `call_error`. 실패한 시도도 전송된 호출이라 1회로 센다 |
| `test_retried_live_call_counts_every_sent_attempt` | 429 뒤 성공은 **2회**다. 마지막 시도 기준으로 1회로 뭉개지 않는다 |
| `test_configuration_error_is_not_counted_as_a_sent_call` | 설정 부족은 시도 행은 남지만 `external_calls=0`이다 |
| `test_search_snapshot_is_recorded_for_search_sources` | 검색 스냅샷(`vertex-google-search`, 수집 시각, 원문 참조)이 실행에 남는다 |
| `test_compose_outlook_section_returns_body_and_sources` | compose_body 진입점이 본문·근거·품질을 그대로 넘기고, 근거 없으면 빈 본문+사유 |
| `test_section_workflow_produces_reader_body_and_sources` | **prepare→research→compose→finalize 전체**가 실제 본문·3종 근거·섹션 결과 ID를 만든다 |
| `test_node_implementation_*` | 노드 어댑터가 claims/coverage/reader_body를 주고, 근거 없으면 `unavailable_reason` |

## 4. 독자용 본문 실물 (녹화 자료 기준)

정상 케이스 본문 길이는 824자. 구조는 `## 배당과 외부 전망` 아래 세 문단이며, 각
문단은 근거가 없으면 통째로 생략된다. 실제 생성물은
[evidence/mp07/section-workflow-mock.json](evidence/mp07/section-workflow-mock.json)의
`cases[].reader_body`에 있다. 매체 전망이 없을 때의 본문은 524자이고, 소개 문장에
"외부 매체 전망"이 등장하지 않는다(검사로 고정).

본문에 넣지 않은 것: 누락·미확보·실패·재시도·grounding 안내, 원본 기사 전문, 베팅
권유, 근거 없는 예상 스코어.

## 5. 실행한 명령과 결과

원문: [evidence/mp07/commands.txt](evidence/mp07/commands.txt)

| 명령 | 결과 |
|---|---|
| `CREATE DATABASE preview_mp07_test` (루프백, 전용) | 생성. `*_test` 이름이라 `_dbguard` 통과 |
| `PREVIEW_TEST_DATABASE_URL=…preview_mp07_test .venv/bin/python -m pytest tests/preview/test_outlook_module.py -q` | **25 passed** |
| `npx --prefix frontend vitest run --root frontend src/features/match-preview/panels/OutlookPanel.test.ts` | **8 passed** |
| `npm --prefix frontend run type-check` | 통과(출력 없음) |
| 증거 생성 스크립트(임시, 실행 후 삭제) | 3케이스 JSON 생성 |

**반복하지 않은 것.** 전체 백엔드 회귀(233건)와 전체 프런트 단위 검사는 신규 모듈
1개 + 전용 패널 1개 변경에 필요하지 않아 다시 돌리지 않았다(AGENTS.md 테스트 범위
규칙). 기존 통과 근거를 재사용한다.

## 6. 이번에 발견해 고친 현재 결함

1. **근거 중복 저장.** `research` 노드가 `state["sources"]`에 근거를 넣는데
   `compose` 노드가 `NodeOutcome.sources`로 또 넣어 저장 근거가 10건(5건×2)이 됐다.
   compose는 비우고, 증거 JSON과 검사로 고정했다.
2. **없는 자료를 소개하는 문장.** 매체 전망이 0건인데 소개 문장이 "매체 전망은 게시
   시각과 출처를 함께 적었습니다"라고 썼다. 확보한 자료만 소개하도록 고치고
   `test_reader_body_does_not_mention_absent_parts`로 고정했다.
3. **스코어 중복 표기.** 인용문에 이미 있는 `2-1`을 뒤에 한 번 더 붙였다. 인용문에
   있으면 덧붙이지 않는다.
4. **시장 판정 순서.** 라이브 검사를 다른 시장 검사보다 먼저 해야
   `Match Winner (Live)`가 승무패로 통과하지 않는다.
5. **외부 호출 집계가 성공 여부에 묶여 있었음.** MP-05가 `execute_request`의
   `response.outcome`은 **마지막** 시도만 반영한다고 지적했다. 성공으로 세면 429 뒤
   실패한 live 실행이 0회로 보여 지표가 틀어진다. 공통
   `provider.sent_attempt_count(result, transport.mode)`로 바꿨고, 재시도 2회와 설정
   오류 0회를 검사로 고정했다. 같은 시점에 MP-05가 내 파일의 호출부를 먼저 공통
   도우미로 바꿔 두었고, 그 결합으로 `attempt_summary`가 `external_calls`보다 먼저
   평가되는 순서 결함이 생겨 있어 내가 바로잡았다.
6. **mock 실행이 1회로 세어짐.** 공통 도우미 도입 직후 모의 transport가 live로 집계돼
   `test_mock_mode_is_not_counted_as_live_call`이 실패했다. 집계 기준을 transport의
   `mode`로 두어 해결했다(모의·재생 transport는 0회).

## 7. 하지 않은 것 / 남은 것

| 항목 | 상태 |
|---|---|
| 실제 모델 호출 | **0회.** 지시대로 조정자 조율 없이 live를 부르지 않았다 |
| 실제 API-Football 호출 | **0회.** D0 저장 자료만 읽는다 |
| 실제 조사 본문·사용자 승인 | **없음.** 승인 행을 만들지 않았다 |
| 섹션 워크플로우 실연동 | **미완.** `registry.py`의 `section_outlook` 등록·구현 연결은 MP-05 소유다 |
| 프런트 공통 등록 | **미완.** `OutlookPanel.vue`를 `ModuleResultPanel`/라우터에 붙이는 일은 MP-05 소유다 |
| 사용자 화면 확인 | **없음.** 5173 재시작·실제 브라우저 확인은 조정자 조율 후 |
| D0 배당 자료 모양 의존 | `d0`로 넘길 때 `odds_raw`/`prediction_raw`(저장 아티팩트 본문)를 기대한다. 다르면 이 모듈이 저장소에서 D0 결과를 찾는다 |
| grounding supports 세부 해석 | 문단별 인용 대응은 저장만 하고 본문 배치에 쓰지 않는다(범위 밖) |

## 8. 편집 종료와 인계 (unstaged)

**이 시점부터 이 파일들은 편집하지 않는다.** 스테이징·커밋하지 않았고, MP-05가 이번
wave의 단독 스테이징·커밋 담당이다. 인계 경로는 정확히 아래 9개(디렉터리 `evidence/mp07/` 포함)다.

```
app/preview/modules/outlook.py
app/preview/prompts/outlook.md
frontend/src/features/match-preview/panels/OutlookPanel.vue
frontend/src/features/match-preview/panels/OutlookPanel.test.ts
tests/preview/test_outlook_module.py
tests/preview/fixtures/outlook.json
docs/implementation/match-preview/MP-07-report.md
docs/implementation/match-preview/evidence/mp07/commands.txt
docs/implementation/match-preview/evidence/mp07/section-workflow-mock.json
```

### MP-05가 해야 할 일 (요청 사항)

1. `app/preview/modules/__init__.py`의 `_IMPLEMENTED`에 `"R3": ("mp07-r3-1", "r3-outlook-1")`
   추가. `backed_modules()`/`module_versions()`가 이 값을 쓴다.
2. `registry.py`의 `R3` 등록을 `implemented=True`, `prompt_version="r3-outlook-1"`로 갱신.
   `section_outlook`의 `implemented`와 `output_contract_version`(후보
   `mp07-outlook-output-1`)도 함께 올린다.
3. `section_outlook` 워크플로우에 `research=(outlook.outlook_node_implementation(...),)`
   와 `compose_body` 어댑터를 넣고 `run_section_workflow`로 실행한다.
4. 프런트 공통 등록: `ModuleResultPanel` 또는 섹션 상세에서 `module_id === "R3"`일 때
   `OutlookPanel.vue`에 `result`(R3 payload의 `outlook` 사전)를 넘긴다.
5. 실제 섹션 실행을 조율할 때 D0 배당·예측 자료가 채워지는지 확인한다. 배당·예측이
   비면 본문은 매체 전망만 또는 빈 본문이 된다(정직한 결과).

### 남은 위험

| 위험 | 내용 |
|---|---|
| live 미검증 | 실제 grounding 응답 모양·한국어 품질·모델이 JSON을 지키는 비율은 실제 호출로만 확인된다 |
| D0 odds 의존 | 배당 자료가 없으면 이 섹션의 핵심 근거 절반이 빠진다. D0 API 연동 상태에 종속된다 |
| 검색 결과 변동 | 매체 전망은 검색 시점에 따라 달라진다. 같은 실행을 재생해도 새 호출은 새 결과다 |
| 봉투 모양 | API-Football 응답 모양이 바뀌면 제외로 떨어질 수 있다(창작보다 안전한 실패) |
