---
endpoint_id: GET__api_v1_fixtures__id__lineups
method: GET
path: /api/v1/fixtures/{external_id}/lineups
feature: fixture-detail
auth: public
owner: be-test
created: 2026-05-14
---

# GET /api/v1/fixtures/{external_id}/lineups

## Purpose

Fixture-detail lineups endpoint for the right 25% panel and the center formation tab. It returns home and away lineups, including formation, coach, starting XI, bench, player refs, positions, grid coordinates, ratings, and minutes when present.

This endpoint is DB-only. It must not call API-Football at request time.

## Request

| Field | Value |
|---|---|
| Method | `GET` |
| Path | `/api/v1/fixtures/{external_id}/lineups` |
| Auth | Public, no JWT required |
| Path params | `external_id: int`, API-Football fixture id |
| Query params | None |

## Response: 200

```json
{
  "home": {
    "team": {
      "external_id": 40,
      "slug": "liverpool-40",
      "name": "Liverpool",
      "name_ko": "리버풀",
      "short_name_ko": "리버풀",
      "logo_url": "https://..."
    },
    "formation": "4-3-3",
    "coach": {"name": "Arne Slot", "name_ko": null},
    "start_xi": [
      {
        "player": {
          "external_id": 2001,
          "slug": "alisson-2001",
          "name": "Alisson",
          "name_ko": "알리송",
          "photo_url": "https://..."
        },
        "number": 1,
        "position": "GK",
        "grid": "1:1",
        "rating": 7.4,
        "minutes": 90
      }
    ],
    "bench": []
  },
  "away": {
    "team": {
      "external_id": 42,
      "slug": "arsenal-42",
      "name": "Arsenal",
      "name_ko": "아스널",
      "short_name_ko": "아스널",
      "logo_url": "https://..."
    },
    "formation": "4-2-3-1",
    "coach": {"name": "Mikel Arteta", "name_ko": null},
    "start_xi": [],
    "bench": []
  }
}
```

## Schema

Team lineup:

| Field | Type | Rule |
|---|---|---|
| `team` | team ref | Fixture home or away team |
| `formation` | string or null | API-Football formation, for example `4-3-3` |
| `coach` | object or null | `{name, name_ko}`; `name_ko` nullable |
| `start_xi` | lineup player[] | Starting players, normally 11 after lineups are announced |
| `bench` | lineup player[] | Substitutes |

Lineup player:

| Field | Type | Rule |
|---|---|---|
| `player` | player ref | `external_id`, `slug`, `name`, `name_ko`, `photo_url` |
| `number` | int or null | Shirt number |
| `position` | string or null | Normalized display position such as `GK`, `DF`, `MF`, `FW`, `CB`, `CM`, `ST` |
| `grid` | string or null | API-Football grid coordinate such as `1:1`; frontend falls back to formation lookup if null |
| `rating` | number or null | Player match rating when DB has it |
| `minutes` | int or null | Minutes played when DB has it |

The FE request file uses older field names (`starting`, `shirt_number`, `grid_row`, `grid_col`). The canonical contract follows the refined feature TypeScript shape: `start_xi`, `number`, and `grid`.

## Empty And Error Behavior

| Scenario | Response |
|---|---|
| Fixture exists, lineups not announced, for example `NS` | `200`, both teams present, `formation=null`, `coach=null`, `start_xi=[]`, `bench=[]` |
| Fixture exists, `fixture_detail` row missing | Same empty lineup shape |
| Fixture id not found | `404 {"detail":"fixture_not_found"}` |
| Non-integer path param | `422` |

## Data Dependencies

| Data | Source |
|---|---|
| Fixture existence and home/away teams | `fixture` |
| Team refs | `team` + `team_translation` |
| Raw lineups | `fixture_detail.lineups` JSONB |
| Player match stats | `fixture_detail.players` JSONB for rating/minutes when available |
| Player refs | `player` + `player_translation` |

Translation fields stay nullable. English/source fallback is available through `name`.

## Implementation Contract For Tests

Unit tests expect:

| Symbol | Contract |
|---|---|
| `app.api.fixture_detail.router` | FastAPI router exposing `/api/v1/fixtures/{external_id}/lineups` |
| `app.api.fixture_detail.get_fixture_detail_service` | FastAPI dependency override hook |
| service method | `get_fixture_lineups(external_id: int) -> dict | None` |

`None` from the service maps to `404 fixture_not_found`. A found fixture with no lineups returns the empty shape above.

## Non-Goals

- No formation coordinate calculation beyond returning raw `grid` when available.
- No live refresh.
- No API-Football request at request time.
- No auth or role branching.
