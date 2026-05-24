# GET__api_v1_fixtures__id__h2h Test Plan

Target spec: `docs/spec/endpoints/GET__api_v1_fixtures__id__h2h.md`

## 0. Classification

| Layer | File | Dependency | Marker |
|---|---|---|---|
| Unit | `tests/unit/test_fixture_detail_h2h_endpoint.py` | FastAPI TestClient + mocked analytics service | `unit` |
| Integration | `tests/integration/test_fixture_detail_h2h_endpoint.py` | Isolated Postgres schema + real route/service DB query | `integration` |

## 1. Mock / Isolation Policy

- Unit tests override `get_fixture_detail_analytics_service()` and must not open a DB connection.
- Integration tests use `tests/conftest.py::isolated_db` (`test_<run_id>_<endpoint>` schema) and override `get_session()` to that schema.
- API-Football, OpenAI, Supabase public schema, and Upstash are never called.

## 2. Unit Cases

| ID | Case | Assertion | Code Path |
|---|---|---|---|
| H2H-U-01 | Default request | `GET /h2h` calls service with `limit=5` and returns current FE payload shape | route wiring, serialization |
| H2H-U-02 | `limit=10` accepted | Service receives `limit=10` | query parsing |
| H2H-U-03 | `limit=11` rejected | `422`, service not called | FastAPI validation |
| H2H-U-04 | Missing fixture | Service `FixtureNotFoundError` maps to `404` | error mapping |

## 3. Integration Cases

| ID | Case | Assertion | Code Path |
|---|---|---|---|
| H2H-I-01 | Pair query normal path | Current fixture pair returns finished H2H rows, reversed home/away slots included | `fixture` -> `h2h_fixture` pair lookup |
| H2H-I-02 | Sorting/exclusion | Current fixture external id and `NS` rows excluded; result sorted `kickoff_at DESC` | filters/order/limit |
| H2H-I-03 | Empty pair | Valid fixture with no prior pair returns `{"h2h":[]}` | empty state |
| H2H-I-04 | Unknown fixture | Missing `fixture.external_id` returns `404` | not found |

## 4. Red Expectation

At spec time the route module is not implemented. Unit tests are expected to fail with
`ModuleNotFoundError` or `404`, which is the intended TDD Red signal.

## 5. Coverage Target

Expected implementation files: route module, schema module, fixture detail analytics
service/repository. The cases cover route validation, 404 mapping, H2H pair lookup,
sorting, status filtering, limit handling, and response serialization; this should support
at least 80% coverage on changed endpoint implementation files.
