# GET__api_v1_fixtures__id__statistics

## 1. Summary

Fixture detail analytical tab endpoint for home/away match statistics.

| Field | Value |
|---|---|
| Method | `GET` |
| Path | `/api/v1/fixtures/{external_id}/statistics` |
| Auth | Public, no JWT required |
| FE request | `frontend/endpoint-requests/GET__api_v1_fixtures__id__statistics.request.json` |
| Consumer | `frontend/src/lib/api/fixtureDetail.ts#getStatistics` |
| Feature refs | `docs/features/fixture-detail.spec.md` §6.4, `docs/features/fixture-detail.devplan.md` §6-7 |

The endpoint is DB-only. It must normalize the last worker-synced statistics stored in
`fixture_detail.statistics`; it must not call API-Football directly.

## 2. Request

### Path Parameters

| Name | Type | Rule |
|---|---|---|
| `external_id` | integer | API-Football fixture id. Must identify a row in `fixture.external_id`. |

No query parameters.

## 3. Response

`200 OK`

```json
{
  "home": {
    "team_external_id": 40,
    "possession": 58,
    "shots_total": 16,
    "shots_on_target": 7,
    "passes_total": 540,
    "passes_accuracy": 88,
    "corners": 8,
    "fouls": 9,
    "yellow": 1,
    "red": 1,
    "offsides": 2
  },
  "away": {
    "team_external_id": 42,
    "possession": 42,
    "shots_total": 11,
    "shots_on_target": 4,
    "passes_total": 392,
    "passes_accuracy": 82,
    "corners": 5,
    "fouls": 12,
    "yellow": 2,
    "red": 0,
    "offsides": 3
  }
}
```

### TeamStat Schema

| Field | Type | Rule |
|---|---|---|
| `team_external_id` | integer | Home or away team external id from current fixture. |
| `possession` | number \| null | Percent, normalized from `"58%"` to `58`. |
| `shots_total` | integer \| null | Total shots. |
| `shots_on_target` | integer \| null | Shots on goal/on target. |
| `passes_total` | integer \| null | Total passes. |
| `passes_accuracy` | number \| null | Percent, normalized from `"88%"` to `88`. |
| `corners` | integer \| null | Corner kicks. |
| `fouls` | integer \| null | Fouls. |
| `yellow` | integer \| null | Yellow cards. |
| `red` | integer \| null | Red cards. |
| `offsides` | integer \| null | Offsides. |

All metric values may be `null`, especially before kickoff or when API-Football has not
reported a live metric yet. `team_external_id` must still be present when the fixture has
team ids.

## 4. Business Rules

1. Load the current fixture by `fixture.external_id`. If it does not exist, return `404`.
2. Home/away identity is determined by `fixture.home_team_id` and `fixture.away_team_id`, not by the order inside JSONB.
3. If a fixture exists but has no statistics row, return both `TeamStat` objects with metric values `null`.
4. Normalize API-Football statistics keys from `fixture_detail.statistics`:
   - `Ball Possession` -> `possession`
   - `Total Shots` -> `shots_total`
   - `Shots on Goal`, `Shots on Target` -> `shots_on_target`
   - `Total passes`, `Total Passes` -> `passes_total`
   - `Passes %`, `Passes accurate %`, `Passes Accurate` -> `passes_accuracy`
   - `Corner Kicks` -> `corners`
   - `Fouls` -> `fouls`
   - `Yellow Cards` -> `yellow`
   - `Red Cards` -> `red`
   - `Offsides` -> `offsides`
5. Numeric strings and percent strings must parse to numbers. Missing, `null`, or unparsable values become `null`.
6. Preserve zero as `0`; do not convert `0` to `null`.
7. For live matches, return the DB value as-is after normalization. No polling and no freshness warning from this endpoint.

## 5. Errors

| Status | Case |
|---|---|
| `404` | `fixture.external_id` not found. |
| `422` | Non-integer path value. |
| `500` | Unexpected DB or serialization error. Do not expose secrets. |

## 6. DB Dependencies

| Table | Usage |
|---|---|
| `fixture` | Resolve current fixture, home/away teams, and status. |
| `fixture_detail` | Source `statistics` JSONB. |
| `team` | Home/away `external_id`. |

## 7. Implementation Contract For Tests

The endpoint router should be included in `app.main.app` and should be testable through
`app.api.v1.fixture_detail_analytics`.

Expected test hooks:

- `get_fixture_detail_analytics_service()` dependency for unit tests.
- `get_session()` dependency for integration tests.
- Service method: `get_statistics(external_id: int) -> dict`.

## 8. Reconciliation Notes

The request JSON uses older aliases such as `possession_pct`, `shots_on`, and
`passes_accurate_pct`. The live fixture-detail FE type and mock payload use
`possession`, `shots_on_target`, and `passes_accuracy`; those names are authoritative for
this endpoint.

## 9. Change Log

| Date | Change |
|---|---|
| 2026-05-14 | Initial be-test spec for fixture-detail statistics analytical tab. |
