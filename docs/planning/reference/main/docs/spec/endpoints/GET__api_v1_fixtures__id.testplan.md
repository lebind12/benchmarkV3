> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `main` 워크트리의 `docs/spec/endpoints/GET__api_v1_fixtures__id.testplan.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

---
endpoint_id: GET__api_v1_fixtures__id
kind: endpoint-testplan
owner: be-test
created: 2026-05-14
---

# Test Plan: GET /api/v1/fixtures/{external_id}

## Scope

Validate the match header endpoint for fixture-detail. Tests cover the public route contract, DB-only behavior, translation nullable fallback fields, score/status rules, and 404 handling.

Target implementation files for coverage:

| Area | Expected files |
|---|---|
| Router | `app/api/fixture_detail.py` |
| Service/query layer | `app/services/fixture_detail.py` or equivalent |
| Response schemas | `app/schemas/fixture_detail.py` or equivalent |

Coverage target after implementation: at least 80% for changed endpoint implementation files.

## Unit Tests

File: `tests/unit/test_fixture_detail_match_endpoint.py`

| ID | Case | Setup | Expected | Paths covered |
|---|---|---|---|---|
| M-U-01 | Normal FT response | Override fixture-detail service with payload | `200`, schema keys, score, league slug, goal event type | router, dependency, schema serialization |
| M-U-02 | Not found | Service returns `None` | `404`, detail `fixture_not_found` | router 404 mapping |
| M-U-03 | Invalid path param | Request `/api/v1/fixtures/not-an-int` | `422` | FastAPI param validation |
| M-U-04 | Translation nullable fallback fields | Payload includes `name_ko=null` for away team | Response keeps nullable field and includes English `name` | schema null handling |

All unit tests mock DB/external services through the service dependency. No API-Football, OpenAI, Supabase, or Upstash calls are allowed.

## Integration Tests

File: `tests/integration/test_fixture_detail_match_endpoint.py`

| ID | Case | Setup | Expected | Paths covered |
|---|---|---|---|---|
| M-I-01 | DB-backed FT match | Isolated schema, migrated DB, seed fixture/league/team/player/event rows | `200`, joined refs, translated Korean fields, goal history sorted | DB query, joins, JSONB event normalization |
| M-I-02 | Missing fixture | Isolated schema with no fixture id | `404 fixture_not_found` | DB not-found branch |
| M-I-03 | NS score rule | Seed `NS` fixture with no detail events | `200`, score nulls, `goal_events=[]` | status/score branch |

Integration tests use `tests/conftest.py::isolated_db`, whose schema name follows `test_<run_id>_<endpoint>`. They do not call external APIs.

## Red Evidence

During spec drafting, run:

```bash
pytest -m unit tests/unit/test_fixture_detail_match_endpoint.py
```

Expected initial result before implementation: failure due to missing `app.api.fixture_detail` router or unregistered endpoint.
