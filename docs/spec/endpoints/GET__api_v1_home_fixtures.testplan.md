# GET__api_v1_home_fixtures Test Plan

Target spec: `docs/spec/endpoints/GET__api_v1_home_fixtures.md`

## 1. Test Files

| Layer | Path | Marker | External services |
|---|---|---|---|
| Unit | `tests/unit/test_home_fixtures.py` | `unit` | None. Service is mocked. |
| Integration | `tests/integration/test_home_fixtures.py` | `integration` | Real Postgres through `isolated_db`; no API-Football, OpenAI, or Upstash. |

## 2. Unit Cases

| ID | Case | Expected |
|---|---|---|
| HF-U-01 | Route is registered on `app.main.app` | `/api/v1/home/fixtures` exists. |
| HF-U-02 | Public default request | No `Authorization` header required; route calls service with `league_id=None`, `period=day`, `date=None`; returns `200`. |
| HF-U-03 | League + period query | `league_id=39&period=week` is accepted and passed to service. |
| HF-U-04 | Date override query | `date=2026-05-14` is accepted and passed as a `date` object/string equivalent. |
| HF-U-05 | Invalid period | `period=year` returns `422`. |
| HF-U-06 | Unsupported league id | `league_id=999` returns `422`. |
| HF-U-07 | Response shape passthrough | Route returns fixture refs, nullable translation fields, status, goals, and `filters_applied`. |

## 3. Integration Cases

| ID | Case | Seed | Expected |
|---|---|---|---|
| HF-I-01 | KST day filtering | Fixture at `2026-05-13T15:30:00Z` (2026-05-14 00:30 KST) and fixture at `2026-05-14T15:00:00Z` (2026-05-15 00:00 KST) | Only first fixture is returned for `date=2026-05-14`. |
| HF-I-02 | League filter | EPL and UCL rows in same KST window | `league_id=39` returns only EPL. |
| HF-I-03 | Translation fallback payload | One team translation has `name_ko=NULL` | Response keeps `name_ko: null` and includes English `name`. |
| HF-I-04 | Cup placeholder exclusion | Fixture with `home_team_id=NULL` | Row is excluded from home summary response. |
| HF-I-05 | Empty result | Valid league/date with no rows | `200` style dict with `items: []` and echoed filters. |

## 4. Coverage Mapping

| Code path | Cases |
|---|---|
| Router registration and public auth | HF-U-01, HF-U-02 |
| Query validation | HF-U-03 through HF-U-06 |
| Response serialization | HF-U-07, HF-I-03 |
| KST bounds | HF-I-01 |
| League/current-season filtering | HF-I-02 |
| Placeholder exclusion | HF-I-04 |
| Empty state | HF-I-05 |

Target implementation coverage: at least 80% for the endpoint router/service files changed by be-dev.

## 5. Red Expectation

At spec handoff time the endpoint router/service is not implemented. Unit tests are expected to fail with missing route/module or `404`; this is the TDD Red signal for be-dev. Integration tests may skip if `TEST_DATABASE_URL` is absent; when present, they fail until `app.services.home.list_home_fixtures` is implemented.
