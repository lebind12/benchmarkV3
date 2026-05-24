---
endpoint_id: GET__api_v1_fixtures__id__lineups
kind: endpoint-testplan
owner: be-test
created: 2026-05-14
---

# Test Plan: GET /api/v1/fixtures/{external_id}/lineups

## Scope

Validate the fixture-detail lineups endpoint. Tests cover the canonical `home/away` shape, `start_xi` and `bench` arrays, empty pre-match behavior, nullable rating/minutes, and not-found handling.

Target implementation files for coverage:

| Area | Expected files |
|---|---|
| Router | `app/api/fixture_detail.py` |
| Service/query layer | `app/services/fixture_detail.py` or equivalent |
| Response schemas | `app/schemas/fixture_detail.py` or equivalent |

Coverage target after implementation: at least 80% for changed endpoint implementation files.

## Unit Tests

File: `tests/unit/test_fixture_detail_lineups_endpoint.py`

| ID | Case | Setup | Expected | Paths covered |
|---|---|---|---|---|
| L-U-01 | Full home/away lineups | Override service with home and away payloads | `200`, formations, 11 starters, bench, rating/minutes fields | router, dependency, schema serialization |
| L-U-02 | Pre-match empty lineups | Service returns empty lineup shape | `200`, teams present and empty `start_xi`/`bench` | empty branch |
| L-U-03 | Not found | Service returns `None` | `404 fixture_not_found` | router 404 mapping |
| L-U-04 | Invalid path param | Request `/api/v1/fixtures/not-an-int/lineups` | `422` | FastAPI param validation |

All unit tests mock DB/external services through the service dependency.

## Integration Tests

File: `tests/integration/test_fixture_detail_lineups_endpoint.py`

| ID | Case | Setup | Expected | Paths covered |
|---|---|---|---|---|
| L-I-01 | JSONB lineups normalize | Seed fixture, teams, 22 players, and `fixture_detail.lineups` JSONB | `200`, 11 home starters, formation, coach, normalized player refs | DB query, JSONB normalization, player joins |
| L-I-02 | Existing fixture with no detail row | Seed fixture only | `200`, empty lineup shape for both teams | empty detail branch |
| L-I-03 | Missing fixture | No fixture row | `404 fixture_not_found` | not-found branch |

Integration tests use isolated Postgres schema and do not call external APIs.

## Red Evidence

During spec drafting, run:

```bash
pytest -m unit tests/unit/test_fixture_detail_lineups_endpoint.py
```

Expected initial result before implementation: failure due to missing `app.api.fixture_detail` router or unregistered endpoint.
