# GET__api_v1_fixtures__id__statistics Test Plan

Target spec: `docs/spec/endpoints/GET__api_v1_fixtures__id__statistics.md`

## 0. Classification

| Layer | File | Dependency | Marker |
|---|---|---|---|
| Unit | `tests/unit/test_fixture_detail_statistics_endpoint.py` | FastAPI TestClient + mocked analytics service | `unit` |
| Integration | `tests/integration/test_fixture_detail_statistics_endpoint.py` | Isolated Postgres schema + real route/service DB query | `integration` |

## 1. Mock / Isolation Policy

- Unit tests override `get_fixture_detail_analytics_service()` and must not open a DB connection.
- Integration tests use `tests/conftest.py::isolated_db` and override `get_session()` to that schema.
- API-Football is not called in tests or endpoint runtime. `fixture_detail.statistics` is the only statistics source.

## 2. Unit Cases

| ID | Case | Assertion | Code Path |
|---|---|---|---|
| ST-U-01 | Normal payload | Current FE field names returned: `possession`, `shots_on_target`, `passes_accuracy`, `yellow`, `red` | route wiring, serialization |
| ST-U-02 | Empty/NS payload | Metric fields can be `null` while `team_external_id` remains present | nullable serialization |
| ST-U-03 | Unknown fixture | Service `FixtureNotFoundError` maps to `404` | error mapping |

## 3. Integration Cases

| ID | Case | Assertion | Code Path |
|---|---|---|---|
| ST-I-01 | Raw API-Football JSONB normalization | `Ball Possession`, `Shots on Goal`, `Passes %` normalize to FE keys and numeric values | JSONB parser/normalizer |
| ST-I-02 | Missing statistics row | Valid fixture with no `fixture_detail.statistics` returns metric values `null` | empty state |
| ST-I-03 | Unknown fixture | Missing `fixture.external_id` returns `404` | not found |
| ST-I-04 | Zero preservation | Raw `0` values remain `0`, not `null` | value coercion |

## 4. Red Expectation

At spec time the route module is not implemented. Unit tests are expected to fail with
`ModuleNotFoundError` or `404`, which is the intended TDD Red signal.

## 5. Coverage Target

Expected implementation files: route module, schema module, fixture detail analytics
service/repository. The cases cover route serialization, 404 mapping, JSONB
normalization, null handling, zero preservation, and FE field-name compatibility; this
should support at least 80% coverage on changed endpoint implementation files.
