# MP-03 구현 보고: D0 경기 선택과 API 자료

**목표.** 관리자가 저장된 경기 자료에서 경기 한 건을 고르면, 조사 모듈들이 함께 쓸
공통 자료 묶음(D0)이 만들어진다. 그 자료는 출처·시각·확보 상태가 붙어 있어야 하고,
"자료가 없다"와 "가져오지 못했다"와 "부상자가 없다"가 서로 다른 상태로 남아야 한다.
이 보고서는 그 입력 구간만 다룬다. 조사·종합·본문 생성은 MP-05 이후 소유다.

**가장 작은 변경.** 전송 계층 없이 요청 명세와 응답 해석만 있는 API-Football
어댑터, 저장된 경기만 읽는 읽기 전용 조회기, 그리고 `import_fixtures`·`list_fixtures`·
`prepare_match_data` 세 함수. 저장은 MP-02가 만든 `preview_dev` 표를 그대로 쓴다.

## 실행 모델

| 항목 | 값 |
|---|---|
| 제공자 / 모델 | hive / `deepseek-ai/deepseek-v4.1-flash-1017` |
| 추론 강도 | max (유지, 변경 없음) |
| 프로필 | dsh-tui |
| 작업 디렉터리 | `/Users/woolee/benchmark` |
| 작업 ID / Dispatch | task_a78ea0727cd7 / ctx_e97a28de39b0 |
| 커밋 기준 HEAD (착수) | `b6174b2` |

세션 기록의 `model/selection`(provider `hive`, model `deepseek-ai/deepseek-v4.1-flash-1017`,
`reasoningEffort: max`)과 `request/header`의 같은 값을 직접 확인했다. 프롬프트 문구로
대체하지 않았고, 모델·추론 강도를 바꾸지 않았으며, 다른 모델로 실행하지 않았다.

## 범위와 경계

| 항목 | 이번 작업 | 근거 |
|---|---|---|
| 쓰기 대상 | `preview_dev`의 기존 표만 (새 표·마이그레이션 없음) | `app/preview/data.py`가 `store.*` 함수만 호출 |
| 기존 `public` 영역 | 읽기만 시도. 권한 없음 확인 | 아래 "읽기 권한 경계" |
| 외부 API 호출 | 앱에서 0회 | 어댑터에 전송 계층 없음, 실행기 주입 |
| 유료 API 호출 | 0회 | live 미검증 |
| 공통 파일(`contracts.py`, `api.ts`, `types.ts`, 라우터, registry) | 수정하지 않음 | MP-04 소유 |
| 기존 809건 삭제 | 건드리지 않음 | 선별 스테이징만 |
| Plans.md·AGENTS.md·CLAUDE.md | 수정하지 않음 | 조정자 소유 |

## 소유 파일

| 파일 | 역할 |
|---|---|
| `app/preview/data.py` | `import_fixtures`, `list_fixtures`(+`store_candidates`), `prepare_match_data` |
| `app/preview/sources/api_football.py` | 요청 명세·응답 봉투 해석·부상 불확실성·배당 신선도. 전송 계층 없음 |
| `app/preview/sources/fixtures.py` | 저장된 경기·부상·순위 읽기 전용 조회기와 권한 점검 |
| `app/preview/sources/__init__.py` | 패키지 경계 설명 |
| `frontend/src/features/match-preview/FixtureSelector.vue` | 저장된 목록 조회 + 명시적 목록 수집 |
| `frontend/src/features/match-preview/panels/DataPanel.vue` | D0 자료·근거·스냅샷 표시 |
| `frontend/src/features/match-preview/fixtures.ts` | D0 전용 자료형과 호출(공통 `api.ts`·`types.ts` 미수정) |
| `tests/preview/test_data.py`, `test_api_football.py`, `fixtures/api_football.json` | 수용 기준 검사와 기록 자료 |
| `frontend/src/features/match-preview/FixtureSelector.test.ts`, `panels/DataPanel.test.ts` | 화면 검사 |

## 내보내는 인터페이스 (MP-04 연결용)

```python
# app/preview/data.py
import_fixtures(session, query: FixtureCatalogQuery, *, context: ExecutionContext,
                executor: ApiExecutor, season: int | None = None,
                actor_id: int | None = None, now: datetime | None = None) -> ImportedFixtures
list_fixtures(session, *, query: FixtureCatalogQuery | None = None,
              reader: StoredFixtureReader | None = None, limit: int = 50,
              now: datetime | None = None) -> FixtureListResult
prepare_match_data(session, fixture: FixtureIdentity, context: ExecutionContext, *,
                   executor: ApiExecutor, actor_id: int | None = None,
                   now: datetime | None = None) -> D0Result

# app/preview/sources/api_football.py
ApiExecutor = Callable[[RequestSpec], ApiExchange]   # MP-04 execute_request가 붙는 자리
ApiExchange(response: ProviderResponse, body: Mapping | None)
d0_calls(fixture_id, *, league_id, season, home_team_id, away_team_id) -> tuple[ApiFootballCall, ...]
catalog_call(*, league_id, date, timezone_name, season) -> ApiFootballCall
request_spec(call, *, module_id="D0", contract_version=None) -> RequestSpec

# app/preview/sources/fixtures.py
StoredFixtureReader.from_url(url) / .access() / .list_fixtures(...) / .get_fixture(...)
FixtureReadAccess.probe(engine) -> FixtureReadAccess
```

`ApiExecutor`는 `RequestSpec` 하나를 받아 `ApiExchange` 하나를 돌려준다. D0는 논리 호출
9개에 대해 정확히 9번 부르고, 재시도는 하지 않는다. 재시도·예산·시도 순번은 공통
실행기의 몫이며, D0는 실패한 호출을 `CALL_ERROR`로 남기고 다음 호출로 넘어간다.

**중복 기록 금지 규칙.** 공통 실행기가 시도를 이미 남겼다면(`ProviderResponse.attempt_id`
가 있음) D0는 시도도 원문 아티팩트도 만들지 않고, 스냅샷이 그 ID를 가리키게 한다. 같은
요청을 두 번 기록하면 시도 수·재시도 빈도·429 빈도가 두 배로 부푼다. 주입한 실행기가
아무것도 남기지 않는 경우(기록 자료로 도는 모의 실행기)에만 D0가 기록을 만든다.

### MP-04에 필요한 연결 (라우터·전송 계층)

1. `POST /api/v1/admin/preview/fixtures/import` → `data.import_fixtures`
   - 요청: `league_id`, `date`, `timezone`, 선택 `season`, 선택 `mode`
   - `operation_kind=fixture_catalog` 문맥을 만들어 넘겨야 한다(다른 값이면 `ContractError`)
2. `GET /api/v1/admin/preview/fixtures` → `data.list_fixtures`
   - 쿼리: 선택 `league_id`, `date`, `timezone`, `limit`
   - 저장된 조회기가 주입되지 않으면 `stored_access.readable=false`로 응답하고 조용한 빈
     목록이 되지 않는다
3. `execute_request(RequestSpec) -> ApiExchange` 구현. `ApiExchange.body`는 파싱용 수신
   본문이며 원문 저장은 실행기가 소유한다.
4. D0 단독 실행 진입점은 `prepare_match_data`를 호출하고 `D0Result.to_dict()`를 그대로
   돌려주면 화면(`panels/DataPanel.vue`)이 붙는다.

`ProviderResponse`·`RequestSpec` 필드는 바꾸지 않았다. 새 계약 파일도 만들지 않았다.

## 검증 결과

### 백엔드

```
PREVIEW_TEST_DATABASE_URL=.../preview_mp03_test \
  .venv/bin/python -m pytest tests/preview/test_data.py tests/preview/test_api_football.py -q
28 passed, 1 warning in 5.87s
```

수용 기준 매핑:

| 계획 §6 MP-03 항목 | 검사 |
|---|---|
| `test_external_fixture_identity` | 외부 `fixture_id`를 요청·저장에 쓰고 내부 DB ID를 식별자로 쓰지 않음 |
| `test_empty_injuries_not_zero` | 빈 부상 응답 → `CoverageState.UNKNOWN`, 부상 claim 미생성 |
| `test_questionable_preserved` | `Questionable` → `uncertain`, 결장 확정 아님, 표기 없음은 `excluded` |
| `test_wrong_fixture_rejected` | 응답 경기 ID 불일치 → `VALIDATION_REJECTED`, 나머지 호출 중단 |
| `test_api_error_not_missing` | 제공자 오류 → `CALL_ERROR`(≠ `API_NOT_PROVIDED`), 시도 1건 |
| `test_view_uses_stored_fixtures` | 목록 조회 중 수집 함수 호출 금지, `external_calls=0` |
| (추가) `test_executor_recorded_attempt_is_not_double_counted` | 공통 실행기가 남긴 시도·원문을 D0가 다시 만들지 않음 |

### 프론트엔드

```
npm --prefix frontend run test:unit -- src/features/match-preview/FixtureSelector.test.ts \
  src/features/match-preview/panels/DataPanel.test.ts
Test Files  2 passed (2) · Tests  15 passed (15)

npm --prefix frontend run type-check
(no output = 통과)
```

## 실제 vs 모의

| 구분 | 상태 | 근거 |
|---|---|---|
| 어댑터 해석 로직 | 검증됨(기록 자료) | `tests/preview/fixtures/api_football.json`, 응답 모양은 API-Football v3 문서 |
| D0 저장 경로 | 검증됨(모의 실행기) | `evidence/mp03/d0_mock_run.json`: 결과 1, 스냅샷 9, 시도 9 |
| 기존 DB 경기 목록 | **검증됨(실제 저장 자료)** | `preview_dev_fixture_ro`로 실 운영 DB 읽기, 외부 호출 0 |
| 실제 API-Football 호출 | **미검증** | 전송 계층 없음, live 미실행 |
| 화면 | 단위 검사만 통과 | 브라우저 실행 증거 없음(라우터 미등록) |

D0 증거 파일은 `mode: mock`, `provider_calls: 9`, `external_calls: 0`, 그리고
"실제 API 호출이 아니고 live 미검증"이라는 문장을 함께 담는다. 이 파일을 live 근거로
인용하면 안 된다.

## 읽기 권한 경계 (해결됨)

착수 시점에는 읽을 수 없었다. 조정자 승인을 받아 **새** 전용 읽기 역할을 준비했다.

| 역할 | `public.app_user` SELECT | 경기 관련 표 SELECT |
|---|---|---|
| `preview_dev_identity_ro` (기존) | 있음 | 없음 **(변경 없음)** |
| `preview_dev_app` (기존) | 없음 | 없음 **(변경 없음)** |
| `preview_dev_fixture_ro` (신규) | 없음 | `fixture`, `team`, `league`, `injury`, `standings` |

| 항목 | 값 |
|---|---|
| 준비 스크립트 | `scripts/preview_dev_fixture_ro_provision.py` (`--dry-run` 지원) |
| 자격 증명 위치 | `~/.config/match-preview/preview-dev.env` (0600), 키 `PREVIEW_FIXTURES_DATABASE_URL` |
| 관리자 DSN | `PREVIEW_PROVISION_ADMIN_URL` 환경변수로만 사용, 0600 임시 파일은 사용 후 삭제 |
| 앱 접속 롤 | `preview_dev_fixture_ro` (앱이 관리자 롤로 접속하지 않음) |

새 역할에 준 것은 `CONNECT`·`public` `USAGE`·위 5개 표의 `SELECT`뿐이다.
`SUPERUSER`·`CREATEDB`·`CREATEROLE`·`BYPASSRLS`는 없다. `public` `CREATE`와
`preview_dev` 접근은 없다. 기존 두 역할의 권한·비밀번호는 바꾸지 않았고 다른 자격
증명도 재설정하지 않았다.

검증은 **권한 introspection과 읽기 전용 트랜잭션**으로만 했다. 운영 데이터에 실제
쓰기 탐침을 실행하지 않았다.

```
preview_dev_identity_ro    SELECT -> ['public.app_user']                    # 변화 없음
preview_dev_app            SELECT -> none                                   # 변화 없음
preview_dev_fixture_ro     SELECT -> ['public.fixture','public.team',
                                      'public.league','public.injury',
                                      'public.standings']
public CREATE=False · preview_dev USAGE=False
UPDATE public.fixture 거부: InsufficientPrivilege (권한 단계에서 거부)
```

### 실제 저장 자료 읽기 (live 확인)

새 역할로 실제 운영 DB의 저장 경기를 읽었다. 외부 API 호출은 0회다.

```
list_fixtures(reader=StoredFixtureReader.from_url(PREVIEW_FIXTURES_DATABASE_URL))
  external_calls: 0
  stored_access.readable: True
  stored_access.role: preview_dev_fixture_ro
  candidates: 1557474 Manchester City vs Fulham 2026-11-21 (origin=stored_db)
              1557467 Aston Villa vs Sunderland 2026-11-21
              1557468 Bournemouth vs Nottingham Forest 2026-11-21
              1557470 Chelsea vs Leeds 2026-11-21
```

단건 조회·부상 조회·순위 조회도 같은 역할로 성공했다.

### 이 과정에서 고친 결함

경계를 실제로 열어 보니 조회기가 승인 범위 **밖** 표를 조인하고 있었다. 권한이
없으니 드러나지 않던 문제다.

| 조회 | 제거한 조인 | 처리 |
|---|---|---|
| `list_fixtures` | `public.venue` | 장소 이름을 필드에서 제거 |
| `injuries_for_fixture` | `public.player` | 선수 이름은 `None`, ID만 남김 |
| `standings_for_league` | `public.team` | `team_id`만 남김 |

권한을 넓혀 맞추지 않고 조회를 경계 안으로 좁혔다. 이름이 필요하면 별도 읽기 경계를
먼저 승인받아야 한다. 이 사실은 `sources/fixtures.py` 모듈 docstring에 남겼다.

### MP-04에 필요한 연결

1. 설정 키 `PREVIEW_FIXTURES_DATABASE_URL`을 `app/core/config.py`에 추가한다(설정
   소유는 MP-04). 값은 위 0600 파일에 이미 있다. **경로와 키 이름만 넘긴다.**
2. `list_fixtures(reader=StoredFixtureReader.from_url(settings.fixtures_database_url))`
   로 넘기면 저장 경기 목록이 실제 자료로 채워진다. 설정이 없으면 `reader=None`으로
   두고 `stored_access.readable=false`가 화면에 드러나게 한다.

## 이번에 고친 결함

1. **mock 실행을 외부 호출로 세던 문제.** 처음에는 실행기를 부른 횟수를 그대로
   `external_calls`로 돌려줬다. 그러면 모의 실행이 "외부 호출 9회"로 보여 live처럼 읽힌다.
   `provider_calls`(실행기 호출)와 `external_calls`(live에서만 계산)를 분리하고,
   `test_mock_run_does_not_count_external_calls`로 고정했다.
2. **재실행이 재시도 통계를 오염시키던 문제.** D0 재실행을 같은 모듈 실행의 두 번째
   시도로 적으면 `attempt_ordinal` 유일 제약과 부딪히고, 재시도 수가 실제 재시도처럼
   부풀었다. 재실행은 새 모듈 실행(다음 `ordinal`)으로 남기고 논리 호출 ID에 실행 순번을
   붙이도록 바꿨다. 시도 순번은 항상 0이다.
3. **저장된 목록을 읽지 못하던 문제.** 저장 결과 행은 `ModuleResult.to_dict()`를 그대로
   담아 payload가 한 단계 아래에 있다. 화면 조회가 조용히 빈 목록을 돌려주지 않도록
   두 모양을 모두 읽게 고쳤다.
4. **공통 실행기와 같은 요청을 두 번 기록하던 문제.** MP-04의 `execute_request`는
   시도 행과 원문 아티팩트를 스스로 남기고 그 ID를 `ProviderResponse.attempt_id`·
   `raw_artifact_id`로 돌려준다. D0가 같은 요청을 다시 기록하면 시도 수와 429 빈도가
   두 배로 부푼다. 응답에 `attempt_id`가 있으면 D0는 기록을 만들지 않고 그 ID를
   스냅샷에 연결한다. `test_executor_recorded_attempt_is_not_double_counted`로 고정했다.

## 남은 일과 인계

| 항목 | 상태 |
|---|---|
| 라우터 등록 | MP-04. `data` 두 함수를 호출만 하면 된다 |
| 실제 API 전송·재시도·예산 | MP-04. `ApiExecutor` 구현 |
| 저장 경기 읽기 권한 | **완료**. `preview_dev_fixture_ro` 준비, 키만 MP-04 설정에 연결하면 됨 |
| live 검증 | 권한·전송 계층 이후 MP-11 |
| 섹션 워크플로우 | D0는 섹션 승인 단위가 아니다. 승인은 MP-05~MP-09가 만드는 섹션 결과 기준 |

## 실행한 명령

```
.venv/bin/python -m pytest tests/preview/test_data.py tests/preview/test_api_football.py -q   # 28 passed
npm --prefix frontend run test:unit -- src/features/match-preview/FixtureSelector.test.ts \
  src/features/match-preview/panels/DataPanel.test.ts                                        # 15 passed
npm --prefix frontend run type-check                                                         # 통과
```

테스트 전용 DB는 다른 작업과 섞이지 않도록 `preview_mp03_test`(로컬 컨테이너, 루프백)를
따로 만들어 사용했다. 공유 테스트 DB에서 다른 워커의 스키마 재생성과 충돌했기 때문이다.

## 커밋 귀속 (실제 이력)

조정자 지시에 따라 히스토리를 재작성하지 않았다(`reset`/`amend`/`rebase`/`checkout` 없음).
실제 이력은 다음과 같다.

| 시점 | 커밋 | 실제 내용 |
|---|---|---|
| 1차 | `7ef8821` "feat(preview): MP-08 stored-event operational metrics" | **MP-08 소유 파일 + MP-03 소유 12개 파일**이 함께 들어갔다 |
| 2차 | `5a8bbb2` "fix(preview): dedup D0 attempt records against the shared executor" | MP-03 소유 4개 파일만 |

원인은 세 워커가 같은 작업 트리와 **같은 git 인덱스**를 공유한 것이다. 내가 파일을
스테이징한 뒤 MP-08 워커가 커밋하면서 스테이징된 항목 전체가 그 커밋에 들어갔다.
`git commit -- <pathspec>`으로 좁혀 커밋한 2차는 의도대로 분리됐다.

`7ef8821`에 함께 들어간 MP-03 소유 경로(12개):

```
app/preview/data.py
app/preview/sources/__init__.py
app/preview/sources/api_football.py
app/preview/sources/fixtures.py
frontend/src/features/match-preview/fixtures.ts
frontend/src/features/match-preview/FixtureSelector.vue
frontend/src/features/match-preview/FixtureSelector.test.ts
frontend/src/features/match-preview/panels/DataPanel.vue
frontend/src/features/match-preview/panels/DataPanel.test.ts
tests/preview/test_data.py
tests/preview/test_api_football.py
tests/preview/fixtures/api_football.json
docs/implementation/match-preview/MP-03-report.md
docs/implementation/match-preview/evidence/mp03/d0_mock_run.json
```

위 14개 경로 중 12개가 코드·테스트, 2개가 문서·증거다.

이후 지시("이 워커의 모든 스테이징·커밋 중단")에 따라 **이 시점 이후로는 스테이징도
커밋도 하지 않았다.** 아래 "미커밋 변경"에 남은 것은 MP-04가 커밋해야 한다.

## 미커밋 변경 (MP-04가 커밋)

| 파일 | 상태 | 내용 |
|---|---|---|
| `app/preview/sources/fixtures.py` | 수정 | 승인 범위 밖 `venue`/`player`/`team` 조인 제거 |
| `tests/preview/test_data.py` | 수정 | `venue_name` 인자 제거 반영 |
| `scripts/preview_dev_fixture_ro_provision.py` | 신규 | 좁은 읽기 역할 준비 스크립트 |
| `docs/implementation/match-preview/MP-03-report.md` | 수정 | 이 보고서 갱신 |

