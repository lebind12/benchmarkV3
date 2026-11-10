# MP-06 — R2 부상·결장 영향 조사 (완료 보고)

**한 줄 요약.** R2 조사 모듈과 `section_availability` 섹션 워크플로우의 `research`·
`compose_body` 노드를 구현했고, 저장된 부상 자료(읽기 전용)와 Google Search grounding을
결합해 **API 원문 표기를 승격하지 않는** 한국어 독자용 본문을 결정적으로 만든다. 계획
수용 기준 5건과 섹션 전체 흐름을 자기 전용 테스트 DB(`preview_mp06_test`)에서 통과했다(23건).
**실제 모델·검색·API 호출은 이 작업에서 하지 않았고**, 녹화 transport로 만든 섹션 결과만
증거로 남겼다.

## 작업 범위와 소유 파일

| 파일 | 성격 |
|---|---|
| `app/preview/modules/availability.py` | **신규.** R2 조사·검증·본문 구성·노드 팩토리 |
| `app/preview/prompts/availability.md` | **신규.** R2 프롬프트(버전 `mp06-r2-prompt-1`) |
| `tests/preview/test_availability_module.py` | **신규.** 수용 기준 5건 + 섹션 흐름 검사 |
| `tests/preview/fixtures/availability.json` | **신규.** 녹화 응답·D0 자료·grounding 모양 |
| `frontend/src/features/match-preview/panels/AvailabilityPanel.vue` | **신규.** 관리자 진단 패널 |
| `frontend/src/features/match-preview/panels/AvailabilityPanel.test.ts` | **신규.** 패널 검사 8건 |
| `docs/implementation/match-preview/evidence/mp06/recorded-section-availability.json` | **신규.** 녹화 섹션 결과 증거 |
| `docs/implementation/match-preview/MP-06-report.md` | 이 보고서 |

**건드리지 않은 것:** `app/preview/modules/__init__.py`, `registry.py`, `runner.py`,
`provider.py`, `data.py`, `sections.py`, `contracts.py`, `app/api/**`, `frontend/src/router`,
`types.ts`, `api.ts`, `RunInspector.vue`, `ModuleResultPanel.vue`, 마이그레이션, `Plans.md`,
정책 문서, `scripts/`, 운영 프로세스(5173/8000). 스테이징·커밋도 하지 않았다.

## 실행 모델

| 항목 | 값 | 확인 |
|---|---|---|
| 제공자 / 모델 | hive / `deepseek-ai/deepseek-v4.1-flash-1017` | 세션 환경 `DSH_PROFILE=dsh-tui`, 프로필 `llm-pi-ai` 설정의 모델 id·기본 `reasoning: max` |
| 추론 강도 | max (사용자 설정 유지, 변경 없음) | 프로필 설정값, 이 작업에서 변경 없음 |
| 프로필 | `dsh-tui` | `DSH_PROFILE`, `DSH_PROFILE_DIR` |
| 작업 디렉터리 | `/Users/woolee/benchmark` | CWD |
| 작업 / Dispatch | `task_6cafe8dba318` / `ctx_ab9eb06a87a0` | 배정 프리앰블 |
| 하위 워커 | **없음** (지시: no subworkers) | 단독 수행 |

이 세션 정보는 **에이전트 실행 모델**이다. **제품 모델**(`gemini-3.5-flash`, `global`)과는
다른 축이며, 제품 모델 설정은 바꾸지 않았다.

## 공개 인터페이스 (MP-05 통합용)

```python
# 조사 1회. 모델 네트워크는 provider.request_model 하나만 통과한다.
research_availability(
    session, *, module_input: ModuleInput, context: ExecutionContext,
    transport, budget: RunBudget, material: Mapping | None = None,
    stored_loader: Callable[[int], Sequence[Any]] | None = None,
    team_names: Mapping[int, str] | None = None,
    prompt_template: str | None = None, model_name: str | None = None,
    now: datetime | None = None,
) -> AvailabilityOutcome   # mode, quality, payload, sources, diagnostics,
                           # unavailable_reason, external_calls, research, text, attempts

availability_research_node(*, transport, material=None, stored_loader=None,
                           reader=None, team_names=None, model_name=None,
                           now=None, mode=None) -> runner.NodeImplementation   # module_id="R2"

availability_compose_node(*, now=None, mode=None) -> runner.NodeImplementation
                                                    # module_id="compose_body"

build_availability_implementations(*, prepare_data: NodeImplementation, transport,
                                   material=None, stored_loader=None, reader=None,
                                   team_names=None, model_name=None,
                                   now=None) -> runner.WorkflowImplementations

compose_availability_body(payload: Mapping) -> ComposedAvailability(title, body, sources, quality, diagnostics)
extract_grounding(raw_response) -> GroundingInfo(sources, queries, supports, search_entry_point)
```

버전 축: `IMPLEMENTATION_VERSION="mp06-r2-1"`, `COMPOSE_IMPLEMENTATION_VERSION="mp06-r2-compose-1"`,
`PROMPT_VERSION="mp06-r2-prompt-1"`.

### `section_availability` 연결에 필요한 것 (MP-05 소유)

1. `sections.build_implementations`(또는 같은 통합 지점)에서 D0 `prepare_data` 노드를 만든 뒤
   `build_availability_implementations(prepare_data=<D0 노드>, transport=<모델 transport>,
   reader=<FixtureReader>)`를 호출한다. `reader`를 주면 `injuries_for_fixture`를 저장
   부상 행 로더로 쓴다. `reader`가 없으면 API/claim 사실만으로 진행하고 진단에 남긴다.
2. `registry.py`의 `section_availability`를 `implemented=True`, `unrunnable_reason=None`으로
   바꾸고 `modules/__init__.py`의 `_IMPLEMENTED`에 R2 버전을 추가한다.
3. 모델 transport는 기존 검증된 `provider.GoogleGenAIHttpTransport`(설정값 `gemini-3.5-flash`,
   `global`)를 그대로 넘긴다. **대체 모델·fallback 없음.** `generation_config`는 모듈이 고정한다:
   `{"temperature": 0.2, "tools": [{"google_search": {}}]}`.
4. 정상 경로 모델 호출은 **R2 1회**다. `compose_body`는 LLM을 부르지 않는다(결정적 조립).

## 실제 D0 입력 계약 (관측된 모양)

MP-05의 `sections.read_stored_context`가 만드는 `prepare_data` payload를 그대로 받는다.

| 키 | 쓰는 방법 |
|---|---|
| `coverage[].topic` | `부상` 또는 `injur` 포함 여부로 부상 항목 판별(라벨 의존 없음). 같은 주제가 여러 번 오면 `not_run`보다 실제 수집 결과를 우선 |
| `coverage[].state` | `available`→수신, `unknown`→**빈 응답(부상자 0명 아님)**, `api_not_provided`, `call_error`, `not_run`, `source_conflict` |
| `facts[]`/`claims[]` | `d0-injury-<player_id>` 항목만 선수 사실로 읽는다(문장에서 표기·사유를 되읽음). `api:injury-count` 같은 집계 항목은 **선수 사실로 쪼개지 않는다** |
| `facts[].snapshot_id`/`collected_at` | API 사실의 근거 스냅샷·수집 시각 |
| `topics` (선택) | D0가 남긴 호출별 `collected_at`·`snapshot_id`. 없으면 `시각 미상`으로 남기고 **값을 만들지 않는다** |
| `fixture.home_team`/`away_team`(+`_id`) | 팀 id→이름. 없으면 `팀 <id>` |

저장된 DB 부상 행은 `StoredInjury(player_id, team_id, type_marker, reason, reported_at)`이며
`player_name`은 **항상 None**이다(승인된 읽기 경계에 `public.player`가 없음). 그래서 이름은
검색에서 실제로 확인된 경우에만 쓰고, 그 밖에는 `선수 ID <id>`로 표기한다.

## 수용 기준 결과

| 계획 검사 | 결과 | 근거 |
|---|---|---|
| `test_questionable_not_confirmed_absence` | 통과 | `Questionable`→`doubtful`, `api_status` 보존, 본문에 `결장 확정` 미사용 |
| `test_empty_list_not_no_injuries` | 통과 | `empty_response`→coverage `unknown`, 본문 빈 값(초안), 진단에만 사유 |
| `test_conflicting_reports_preserved` | 통과 | API `doubtful` + 보도 `confirmed_absence`를 `conflict` claim·`source_conflict` coverage로 병존 |
| `test_injury_impact_has_basis` | 통과 | 근거 없는 `impact`는 폐기, 근거 있는 해석만 `ai_interpretation` claim |
| `test_api_only_availability_result` | 통과 | grounding 비어도 API 사실로 본문·근거 생성, 누락 문구는 본문에 없음 |

추가로 확인한 것: 표기 없는 행 미승격, 이름 미생성, grounding 출처·검색어·Search
Suggestions·supports 보존, 발명 URL 거부, 401 미재시도 + API 사실 보존, D0 라벨 비의존,
공통 payload(집계 사실) + 저장 행 로더 결합, 저장 행의 D0 스냅샷 참조(모호하면 미부착),
섹션 전체 흐름 저장.

## 실행 명령과 결과

```sh
# 백엔드 (전용 DB: preview_mp06_test, 자기 엔진·스키마 fixture 사용)
.venv/bin/python -m pytest tests/preview/test_availability_module.py -q
# → 23 passed, 1 warning (경고는 starlette TestClient deprecation, 이 작업과 무관)

# 프론트 패널
npm --prefix frontend run test:unit -- src/features/match-preview/panels/AvailabilityPanel.test.ts
# → 8 passed

# 프론트 타입 검사 (전체)
npm --prefix frontend run type-check
# → 통과(출력 없음). 내 파일(AvailabilityPanel.vue/.test.ts) 포함 오류 0건.
```

`preview_mp06_test` DB는 루프백 `127.0.0.1:55432`에 새로 만들었고, 테스트가 매번
`preview_dev` 스키마만 지운다(`public` 스키마는 건드리지 않음). 공통 `conftest.py`는
수정하지 않았다.

## 녹화 섹션 결과 (모의 — 승인 근거 아님)

증거: [evidence/mp06/recorded-section-availability.json](evidence/mp06/recorded-section-availability.json)

`provider.RecordedTransport`로 `section_availability` 전체 워크플로우를 실행했다.
모드 `mock`, 외부 호출 0회, 녹화 모델 호출 1회, 단계 `prepare_data → research →
compose_body → finalize`.

독자용 본문(저장된 `preview_section_results.body`):

```
이번 경기의 결장·출전 불확실 상황은 결장 표기 1명, 출전 불확실 1명으로 확인됩니다.

결장·출전 불확실
Recorded Home
- Recorded Doubtful: 출전 불확실 — 출전 여부가 확정되지 않았습니다. 최근 훈련에 부분 참여했고 출전 여부는 경기 전 결정됩니다.
  근거: API-Football 부상 자료(수집 2026-11-10), 검색 출처
Recorded Away
- Recorded Out: 결장(확정 표기). 햄스트링 부상으로 이번 경기 명단에서 빠집니다.
  근거: API-Football 부상 자료(수집 2026-11-10)

전력 영향 (근거에 기반한 해석)
- Recorded Home: 출전이 불확실한 선수의 자리는 경기 전까지 확정되지 않아, 교체 자원 운용이 경기 당일 결정될 수 있습니다.
  근거: API-Football 부상 자료(수집 2026-11-10)
- Recorded Away: 원정팀은 해당 포지션 자원을 다른 선수로 채워야 하는 상황입니다.
  근거: API-Football 부상 자료(수집 2026-11-10)

남은 불확실성
- 출전 불확실 선수의 최종 명단은 킥오프 전에 확정됩니다.
```

근거 5건(API 3 + 검색 2), 진단은 `mock 실행입니다…` 1건으로 본문과 분리돼 있다.
이름은 모두 `Recorded ...` 합성 값이고, 실제 선수·구단과 무관하다.

## 남은 격차 (정직하게 남긴다)

1. **live 미검증.** 실제 `gemini-3.5-flash` 호출로 이 섹션을 만든 적이 없다. transport 연결은
   기존 통합 세션에서 1회 확인된 사실만 인용하며, 그 확인은 **조사 품질의 증거가 아니다**.
   live 섹션 1건은 MP-05 통합 뒤 조정된 단일 실행에서 만들어야 한다(중복·무예산 호출 금지).
2. **실제 저장 경기 자료 미연결.** 저장 부상 행 로더는 주입 경로와 합성 행으로만 검증했다.
   실제 `preview_dev_fixture_ro` 역할로 읽은 행을 쓴 섹션 결과는 아직 없다.
3. **Search Suggestions 표시.** 패널은 제공된 `rendered_content`를 sandbox iframe에 넣는다.
   실제 Google 응답의 렌더 결과를 브라우저에서 확인한 적은 없다(합성 HTML로만 검사).
4. **프론트 라우터 미연결.** 이 패널은 어떤 화면에도 아직 붙지 않았다. 라우터·공통 타입·
   `RunInspector`·`ModuleResultPanel` 연결은 MP-05 소유다.
5. **다른 팀 파일.** `type-check` 전체는 지금 통과한다. 그 통과는 MP-05가 자기 파일을
   고친 결과이며, 내가 다른 팀 파일을 수정한 적은 없다.

## 편집 종료·인계

- **MP-06 편집을 끝냈다.** 이 보고서를 마지막으로 소유 파일 수정을 멈춘다.
- 아래 6개 경로는 **스테이징하지 않은 채** 그대로 둔다. 스테이징·커밋은 MP-05 단독 소유다.
  1. `app/preview/modules/availability.py`
  2. `app/preview/prompts/availability.md`
  3. `tests/preview/test_availability_module.py`
  4. `tests/preview/fixtures/availability.json`
  5. `frontend/src/features/match-preview/panels/AvailabilityPanel.vue`
  6. `frontend/src/features/match-preview/panels/AvailabilityPanel.test.ts`
- 문서 산출물: `docs/implementation/match-preview/MP-06-report.md`,
  `docs/implementation/match-preview/evidence/mp06/recorded-section-availability.json`.
- 이 작업은 사용자 승인을 만들지 않았고, D0·노드 단위 승인을 요구하지 않는다. 승인 단위는
  `section_availability` 섹션 워크플로우 버전이며 승인은 사용자 몫이다.
