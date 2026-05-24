---
endpoint_id: GET__api_v1_fixtures__id
method: GET
path: /api/v1/fixtures/{external_id}
feature: fixture-detail
auth: public
owner: be-test
created: 2026-05-14
---

# GET /api/v1/fixtures/{external_id}

## Purpose

Fixture-detail core match endpoint for the `/fixtures/{external_id}` header. It returns the DB snapshot needed for the 25vh match header: league, teams, venue/referee/kickoff metadata, score, status, and inline goal history.

This is a normal user page endpoint. It must use DB data only and must not call API-Football, OpenAI, Supabase client APIs, or Upstash at request time. Live matches may be stale up to the normal 6h sync SLA.

## Request

| Field | Value |
|---|---|
| Method | `GET` |
| Path | `/api/v1/fixtures/{external_id}` |
| Auth | Public, no JWT required |
| Path params | `external_id: int`, API-Football fixture id |
| Query params | None |

Invalid non-integer path params are handled by FastAPI validation as `422`.

## Response: 200

```json
{
  "external_id": 1000001,
  "league": {
    "external_id": 39,
    "slug": "premier-league",
    "name": "Premier League",
    "name_ko": "프리미어리그",
    "short_name_ko": "EPL",
    "logo_url": "https://..."
  },
  "round": "32라운드",
  "status_short": "FT",
  "status_long": "Match Finished",
  "kickoff_at": "2026-05-13T10:00:00Z",
  "venue": {"name": "Anfield", "city": "Liverpool"},
  "referee": "J. Pratt",
  "home": {
    "external_id": 40,
    "slug": "liverpool-40",
    "name": "Liverpool",
    "name_ko": "리버풀",
    "short_name_ko": "리버풀",
    "logo_url": "https://..."
  },
  "away": {
    "external_id": 42,
    "slug": "arsenal-42",
    "name": "Arsenal",
    "name_ko": "아스널",
    "short_name_ko": "아스널",
    "logo_url": "https://..."
  },
  "goals_home": 3,
  "goals_away": 1,
  "penalty_home": null,
  "penalty_away": null,
  "goal_events": [
    {
      "minute": 23,
      "extra": null,
      "scorer": {
        "external_id": 1001,
        "slug": "mohamed-salah-1001",
        "name": "Mohamed Salah",
        "name_ko": "모하메드 살라",
        "photo_url": "https://..."
      },
      "team_external_id": 40,
      "type": "normal"
    }
  ]
}
```

### Schema

`status_short` enum:

`NS | 1H | HT | 2H | ET | BT | P | PEN | FT | AET | PST | CANC | SUSP`

`league`, `home`, and `away` use public refs:

| Field | Type | Rule |
|---|---|---|
| `external_id` | int | API-Football external id |
| `slug` | string | DB slug |
| `name` | string | English/source name, always present |
| `name_ko` | string or null | Translation row value; null is allowed |
| `short_name_ko` | string or null | Translation row value; null is allowed |
| `logo_url` | string or null | DB logo URL |

`goal_events[]`:

| Field | Type | Rule |
|---|---|---|
| `minute` | int | Elapsed minute |
| `extra` | int or null | Added time, for example `2` in `45+2` |
| `scorer` | player ref | `external_id`, `slug`, `name`, `name_ko`, `photo_url` |
| `team_external_id` | int | Scoring team external id after own-goal attribution |
| `type` | enum | `normal | penalty | own_goal` |

Goal events must be sorted by `(minute, extra null as 0, source order)`.

## Status And Score Rules

| Match status | Score fields | Goal history |
|---|---|---|
| `NS` | `goals_home=null`, `goals_away=null`, penalties null | `[]` |
| `1H/HT/2H/ET/BT/P` | Return DB snapshot values if present. Do not fetch live data | DB snapshot goal events |
| `FT/AET` | Final score from DB | All known normal, penalty, own-goal events |
| `PEN` | Final score plus `penalty_home/away` from DB | All known events including penalty shootout if stored |
| `PST/CANC/SUSP` | `goals_home=null`, `goals_away=null`, penalties null | `[]` unless DB has historical events |

The frontend converts kickoff time to KST. The API returns ISO8601 UTC.

## Error Responses

| Status | Body | Rule |
|---|---|---|
| 404 | `{"detail":"fixture_not_found"}` | No `fixture.external_id` row, or fixture is outside retained seasons and absent from DB |
| 422 | FastAPI validation body | Path param is not an integer |
| 500 | Standard error body | Unexpected server error |

## Data Dependencies

Primary tables:

| Data | Source |
|---|---|
| Fixture/status/score | `fixture` |
| Detail events for goal history | `fixture_detail.events` JSONB |
| League ref | `league` + `league_translation` |
| Home/away team refs | `team` + `team_translation` |
| Venue | `venue` |
| Scorer refs | `player` + `player_translation` |

Translation fields stay nullable. English/source fallback is available through the sibling `name` field; the API must not overwrite translation rows.

## Implementation Contract For Tests

Unit tests expect:

| Symbol | Contract |
|---|---|
| `app.api.fixture_detail.router` | FastAPI router exposing `/api/v1/fixtures/{external_id}` |
| `app.api.fixture_detail.get_fixture_detail_service` | FastAPI dependency override hook |
| service method | `get_match_detail(external_id: int) -> dict | None` |

`None` from the service maps to `404 fixture_not_found`.

## Non-Goals

- No polling or live refresh.
- No API-Football request.
- No auth or role branching.
- No cache writes.
