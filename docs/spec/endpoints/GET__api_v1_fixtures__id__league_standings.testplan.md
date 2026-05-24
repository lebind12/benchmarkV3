# GET__api_v1_fixtures__id__league_standings Test Plan

Target spec: `docs/spec/endpoints/GET__api_v1_fixtures__id__league_standings.md`

## 0. Classification

| Layer | File | Dependency | Marker |
|---|---|---|---|
| Unit | `tests/unit/test_fixture_detail_league_standings_endpoint.py` | FastAPI TestClient + mocked analytics service | `unit` |
| Integration | `tests/integration/test_fixture_detail_league_standings_endpoint.py` | Isolated Postgres schema + real route/service DB query | `integration` |

## 1. Mock / Isolation Policy

- Unit tests override `get_fixture_detail_analytics_service()` and must not open a DB connection.
- Integration tests use `tests/conftest.py::isolated_db` and override `get_session()` to that schema.
- API-Football, OpenAI, and Upstash are not called.

## 2. Unit Cases

| ID | Case | Assertion | Code Path |
|---|---|---|---|
| LS-U-01 | Normal table payload | Flat `rows`, `group_name`, and `highlighted_team_ids` payload returned | route wiring, serialization |
| LS-U-02 | Tournament/no standings | `rows=[]`, `group_name=null`, `highlighted_team_ids` still present | empty/tournament serialization |
| LS-U-03 | Unknown fixture | Service `FixtureNotFoundError` maps to `404` | error mapping |

## 3. Integration Cases

| ID | Case | Assertion | Code Path |
|---|---|---|---|
| LS-I-01 | EPL single table | All same-season rows returned sorted by rank; highlighted home/away external ids present | standings query |
| LS-I-02 | UCL group filter | Only the fixture teams' group is returned; other groups excluded | group selection |
| LS-I-03 | Tournament/no standings | Valid fixture with no rows returns `rows=[]` | empty state |
| LS-I-04 | Unknown fixture | Missing `fixture.external_id` returns `404` | not found |

## 4. Red Expectation

At spec time the route module is not implemented. Unit tests are expected to fail with
`ModuleNotFoundError` or `404`, which is the intended TDD Red signal.

## 5. Coverage Target

Expected implementation files: route module, schema module, fixture detail analytics
service/repository. The cases cover route serialization, 404 mapping, table standings,
group-filtered standings, tournament empty state, translation fallback shape, and
highlighted ids; this should support at least 80% coverage on changed endpoint
implementation files.
