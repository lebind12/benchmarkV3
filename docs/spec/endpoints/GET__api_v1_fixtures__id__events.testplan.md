---
endpoint_id: GET__api_v1_fixtures__id__events
kind: endpoint-testplan
owner: be-test
created: 2026-05-14
---

# Test Plan: GET /api/v1/fixtures/{external_id}/events

## Scope

Validate the fixture-detail timeline endpoint. Tests cover route contract, canonical event types, nullable player refs, empty events, ordering, and not-found behavior.

Target implementation files for coverage:

| Area | Expected files |
|---|---|
| Router | `app/api/fixture_detail.py` |
| Service/query layer | `app/services/fixture_detail.py` or equivalent |
| Response schemas | `app/schemas/fixture_detail.py` or equivalent |

Coverage target after implementation: at least 80% for changed endpoint implementation files.

## Unit Tests

File: `tests/unit/test_fixture_detail_events_endpoint.py`

| ID | Case | Setup | Expected | Paths covered |
|---|---|---|---|---|
| E-U-01 | Normal timeline payload | Override service with all canonical event kinds | `200`, `events` list, canonical `type` values preserved | router, dependency, schema serialization |
| E-U-02 | Empty timeline | Service returns `{"events":[]}` | `200`, empty list | empty branch |
| E-U-03 | Not found | Service returns `None` | `404 fixture_not_found` | router 404 mapping |
| E-U-04 | Invalid path param | Request `/api/v1/fixtures/not-an-int/events` | `422` | FastAPI param validation |

All unit tests mock DB/external services through the service dependency.

## Integration Tests

File: `tests/integration/test_fixture_detail_events_endpoint.py`

| ID | Case | Setup | Expected | Paths covered |
|---|---|---|---|---|
| E-I-01 | JSONB raw events normalize and sort | Seed fixture and unsorted `fixture_detail.events` JSONB | `200`, sorted by minute/extra, raw goal/card/sub/VAR mapped to canonical types | DB query, JSONB normalization, player joins |
| E-I-02 | Existing fixture with no detail row | Seed fixture only | `200 {"events":[]}` | empty detail branch |
| E-I-03 | Missing fixture | No fixture row | `404 fixture_not_found` | not-found branch |

Integration tests use isolated Postgres schema and do not call external APIs.

## Red Evidence

During spec drafting, run:

```bash
pytest -m unit tests/unit/test_fixture_detail_events_endpoint.py
```

Expected initial result before implementation: failure due to missing `app.api.fixture_detail` router or unregistered endpoint.
