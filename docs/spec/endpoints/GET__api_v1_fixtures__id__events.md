---
endpoint_id: GET__api_v1_fixtures__id__events
method: GET
path: /api/v1/fixtures/{external_id}/events
feature: fixture-detail
auth: public
owner: be-test
created: 2026-05-14
---

# GET /api/v1/fixtures/{external_id}/events

## Purpose

Fixture-detail events timeline endpoint for the left 25% panel. It returns one normalized, time-sorted event list. The frontend splits events into home and away columns using `team_external_id`.

This endpoint is DB-only. It must not call API-Football at request time, even for live fixtures.

## Request

| Field | Value |
|---|---|
| Method | `GET` |
| Path | `/api/v1/fixtures/{external_id}/events` |
| Auth | Public, no JWT required |
| Path params | `external_id: int`, API-Football fixture id |
| Query params | None |

## Response: 200

```json
{
  "events": [
    {
      "id": "1000001:0",
      "minute": 23,
      "extra": null,
      "team_external_id": 40,
      "type": "goal",
      "player": {
        "external_id": 1001,
        "slug": "mohamed-salah-1001",
        "name": "Mohamed Salah",
        "name_ko": "모하메드 살라",
        "photo_url": "https://..."
      },
      "assist": {
        "external_id": 1002,
        "slug": "trent-alexander-arnold-1002",
        "name": "Trent Alexander-Arnold",
        "name_ko": "트렌트 알렉산더아놀드",
        "photo_url": null
      },
      "player_out": null,
      "detail": "Normal Goal"
    }
  ]
}
```

## Schema

`events[]` fields:

| Field | Type | Rule |
|---|---|---|
| `id` | string | Stable per fixture event. If raw source has no id, use deterministic `fixture_external_id:source_index` |
| `minute` | int | Elapsed minute |
| `extra` | int or null | Added time |
| `team_external_id` | int | Team responsible for the display column |
| `type` | enum | `goal | goal_penalty | goal_own | yellow_card | red_card | yellow_red | substitution | var` |
| `player` | player ref | Event subject. For substitution this is the player coming in |
| `assist` | player ref or null | Assist player for goals when available |
| `player_out` | player ref or null | Player leaving for substitutions |
| `detail` | string or null | Reason/result such as card reason or VAR result |

Player ref:

`external_id`, `slug`, `name`, `name_ko`, `photo_url`.

The FE request file uses shorthand event types (`goal|yellow|red|sub|var`). The canonical contract uses the refined feature spec types above. Backend normalization maps shorthand/raw API-Football values to these canonical values.

## Normalization

| API-Football raw shape | Canonical type |
|---|---|
| `type=Goal`, normal detail | `goal` |
| `type=Goal`, penalty detail | `goal_penalty` |
| `type=Goal`, own goal detail | `goal_own` |
| `type=Card`, yellow card detail | `yellow_card` |
| `type=Card`, red card detail | `red_card` |
| `type=Card`, second yellow detail | `yellow_red` |
| `type=subst` or substitution | `substitution` |
| `type=Var` | `var` |

Events must be sorted by `(minute, extra null as 0, source order)`.

## Empty And Error Behavior

| Scenario | Response |
|---|---|
| Fixture exists, no events yet, for example `NS` | `200 {"events":[]}` |
| Fixture exists, `fixture_detail` row missing | `200 {"events":[]}` |
| Fixture id not found | `404 {"detail":"fixture_not_found"}` |
| Non-integer path param | `422` |

## Data Dependencies

| Data | Source |
|---|---|
| Fixture existence and home/away teams | `fixture` |
| Raw event list | `fixture_detail.events` JSONB |
| Player refs | `player` + `player_translation` |

Translation fields stay nullable. English/source fallback is available through `player.name`.

## Implementation Contract For Tests

Unit tests expect:

| Symbol | Contract |
|---|---|
| `app.api.fixture_detail.router` | FastAPI router exposing `/api/v1/fixtures/{external_id}/events` |
| `app.api.fixture_detail.get_fixture_detail_service` | FastAPI dependency override hook |
| service method | `get_fixture_events(external_id: int) -> dict | None` |

`None` from the service maps to `404 fixture_not_found`. A found fixture with no events returns `{"events":[]}`.

## Non-Goals

- No live refresh.
- No frontend home/away column splitting.
- No API-Football call at request time.
- No auth or role branching.
