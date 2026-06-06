---
endpoint_id: GET__api_v1_broadcast_fixtures__id__overlay
kind: endpoint-testplan
feature: broadcast-match-overlay
owner: be-test
created: 2026-05-14
---

# Test Plan: GET /api/v1/broadcast/fixtures/{external_id}/overlay

Target spec: `docs/spec/endpoints/GET__api_v1_broadcast_fixtures__id__overlay.md`

## 0. Classification

| Layer | File | Dependency | Marker |
|---|---|---|---|
| Unit | `tests/unit/test_broadcast_overlay_endpoint.py` | FastAPI TestClient + mocked service/API/cache/auth | `unit` |
| Integration | `tests/integration/test_broadcast_overlay_endpoint.py` | Isolated DB schema + fake API-Football client + fake Upstash | `integration` |

Integration tests use the shared `isolated_db` fixture and fixed API-Football JSON fixture
`tests/fixtures/api_football/broadcast_overlay_live_1000001.json`. No test should call real
API-Football, real Upstash, OpenAI, or prod schema by default. Real upstream smoke can be added
later behind an explicit manual marker.

## 1. Unit Cases

| ID | Case | Setup | Assertion |
|---|---|---|---|
| BO-U-01 | ADMIN access returns canonical payload | Override auth as ADMIN and service with full payload | `200`, `fixture`, `lineups`, `statistics`, `events`, `polling` keys present |
| BO-U-02 | STREAMER access forbidden | Override auth as STREAMER | `403`, service not called |
| BO-U-03 | USER access forbidden | Override auth as USER | `403` |
| BO-U-04 | Missing auth | No current user | `401` |
| BO-U-05 | Unknown fixture | Service raises/returns not found | `404 {"detail":"fixture_not_found"}` |
| BO-U-06 | Invalid fixture id | `/api/v1/broadcast/fixtures/not-int/overlay` | `422` |
| BO-U-07 | Partial live data serializes | Service returns empty lineups, null stats, empty events | `200`, arrays/nullable fields preserved |
| BO-U-08 | Main app registration | Inspect `app.main.app.routes` | `/api/v1/broadcast/fixtures/{external_id}/overlay` is registered |
| BO-U-09 | Upstream unavailable mapping | Service raises `BroadcastOverlayError` | `502 {"detail":"broadcast_upstream_unavailable"}` |

## 2. Integration Cases

| ID | Case | Setup | Assertion |
|---|---|---|---|
| BO-I-01 | Live full upstream aggregation | Seed fixture/team/player translations; fake API returns fixture/events/lineups/statistics/players | Payload has score clock, two lineups, marker ratings/goals/cards/substitution, selected stats, events |
| BO-I-02 | Cache hit avoids upstream calls | Preload fake cache assembled overlay | Response uses cached payload and API client call count is zero |
| BO-I-03 | Cache miss writes split cache keys | Empty cache + fake API full payload | Response `cache_hit=false`; cache writes core/events/statistics/players/lineups/overlay keys |
| BO-I-04 | Lineups unavailable | Fake API lineups empty | `lineups` includes both teams with `formation=null` and `players=[]` |
| BO-I-05 | Player stats unavailable | Fake API players empty but events present | Markers derive goals/cards/sub state from events, `rating=null` |
| BO-I-06 | Statistics null handling | Fake API stats include nulls and percent strings | Display labels are strings; meter pct values are bounded 0-100, null pair returns 50/50 |
| BO-I-07 | Non-live DB fallback | Fixture status `FT`; DB fixture_detail has JSONB blocks; fake API client should not be called | Response uses DB data and polling interval can be >= 30 |
| BO-I-08 | Upstream failure with no fallback | Live fixture + API failure + no cache/DB detail | `502`, no secret or upstream body leaked |

Initial integration skeleton covers BO-I-01, BO-I-02, BO-I-07, and BO-I-08. Remaining cases
are listed for be-dev expansion after the service/router boundary exists.

## 3. Normalization Assertions

Events:

| Raw | Expected |
|---|---|
| `type=Goal`, `detail=Normal Goal` | `kind=goal`, `player` set, `score_label` set |
| `type=Card`, `detail=Yellow Card` | `kind=yellow-card` |
| `type=Card`, `detail=Red Card` | `kind=red-card` |
| `type=subst` | `kind=substitution`, `in_player` and `out_player` set |
| `type=Var` | `kind=var` |

Statistics:

| Raw API-Football label | Expected `type` |
|---|---|
| `Ball Possession` | `possession` |
| `Total Shots` | `shots_total` |
| `Shots on Goal` / `Shots on Target` | `shots_on_goal` |
| `Corner Kicks` | `corner_kicks` |
| `Passes %` / `Passes accurate %` | `passes_pct` |

Player markers:

| Source | Assertion |
|---|---|
| `/fixtures/players` rating `"7.2"` | `rating=7.2` number |
| two goal events for same player | `goals=2` |
| yellow + red card events | card counts preserved separately |
| substitution event | incoming player `substitution=in`, outgoing player `substitution=out` |

## 4. Red Expectation

At handoff time this endpoint route and override hooks are not implemented. The initial Red
command is:

```bash
.venv/bin/python -m pytest tests/unit/test_broadcast_overlay_endpoint.py -q
```

Expected Red symptoms:

- `BO-U-08` fails because the main app lacks `/api/v1/broadcast/fixtures/{external_id}/overlay`.
- Route-level tests fail until `app.api.v1.broadcast` exposes
  `get_broadcast_current_user()` and `get_broadcast_overlay_service()`.

The Red log is recorded in
`.codex/state/endpoint-flow/GET__api_v1_broadcast_fixtures__id__overlay/unit.log`.

## 5. Coverage Target

Expected implementation files: broadcast route, schema, overlay service, API-Football client
adapter, cache adapter, normalization helpers. The cases above cover auth, routing,
serialization, cache hit/miss, upstream fallback, event/stat/player normalization, and error
mapping. Target at least 80% coverage for changed endpoint implementation files.

## 6. Coverage Map

| Code path | Cases |
|---|---|
| Route registration/path params/query validation | BO-U-06, BO-U-08 |
| Auth and role gate | BO-U-01, BO-U-02, BO-U-03, BO-U-04 |
| Service result/error mapping | BO-U-01, BO-U-05, BO-U-07 |
| Upstream unavailable mapping | BO-U-09, BO-I-08 |
| Cache hit/miss behavior | BO-I-02, BO-I-03 |
| Live API-Football aggregation | BO-I-01, BO-I-04, BO-I-05, BO-I-06, BO-I-08 |
| Non-live DB fallback | BO-I-07 |
| Event/stat/player normalization | BO-I-01, BO-I-04, BO-I-05, BO-I-06 |
