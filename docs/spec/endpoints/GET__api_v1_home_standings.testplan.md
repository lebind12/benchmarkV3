# GET__api_v1_home_standings Test Plan

Target spec: `docs/spec/endpoints/GET__api_v1_home_standings.md`

## 1. Test Files

| Layer | Path | Marker | External services |
|---|---|---|---|
| Unit | `tests/unit/test_home_standings.py` | `unit` | None. Service is mocked. |
| Integration | `tests/integration/test_home_standings.py` | `integration` | Real Postgres through `isolated_db`; no API-Football, OpenAI, or Upstash. |

## 2. Unit Cases

| ID | Case | Expected |
|---|---|---|
| HS-U-01 | Route is registered on `app.main.app` | `/api/v1/home/standings` exists. |
| HS-U-02 | Public default request | No `Authorization` header required; route calls service with `league_id=39`; returns `200`. |
| HS-U-03 | Explicit allowed league | `league_id=2` is accepted and passed to service. |
| HS-U-04 | Unsupported league id | `league_id=999` returns `422`. |
| HS-U-05 | Empty standings payload | Service returns `rows: []`; route returns `200` with league and season. |
| HS-U-06 | Response shape passthrough | Route returns league ref, team refs, rank, points, W-D-L, and goals. |

## 3. Integration Cases

| ID | Case | Seed | Expected |
|---|---|---|---|
| HS-I-01 | Current-season standings | EPL `current_season=2025`, standings rows for 2025 and 2024 | Only 2025 rows are returned. |
| HS-I-02 | Rank ordering | Rows inserted out of order | Response rows sorted by `rank ASC`. |
| HS-I-03 | Translation fallback payload | One team translation has `name_ko=NULL` | Response keeps `name_ko: null` and includes English `name`. |
| HS-I-04 | Empty cup standings | Allowed cup league with current season but no standings rows | Response has selected league, season, and `rows: []`. |

## 4. Coverage Mapping

| Code path | Cases |
|---|---|
| Router registration and public auth | HS-U-01, HS-U-02 |
| Query validation/defaults | HS-U-02 through HS-U-04 |
| Response serialization | HS-U-05, HS-U-06, HS-I-03 |
| Current-season filtering | HS-I-01 |
| Rank ordering | HS-I-02 |
| Empty cup standings | HS-I-04 |

Target implementation coverage: at least 80% for the endpoint router/service files changed by be-dev.

## 5. Red Expectation

At spec handoff time the endpoint router/service is not implemented. Unit tests are expected to fail with missing route/module or `404`; this is the TDD Red signal for be-dev. Integration tests may skip if `TEST_DATABASE_URL` is absent; when present, they fail until `app.services.home.get_home_standings` is implemented.
