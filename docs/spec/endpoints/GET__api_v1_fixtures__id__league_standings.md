# GET__api_v1_fixtures__id__league_standings

## 1. Summary

Fixture detail analytical tab endpoint for standings relevant to the fixture's league and
season.

| Field | Value |
|---|---|
| Method | `GET` |
| Path | `/api/v1/fixtures/{external_id}/league-standings` |
| Auth | Public, no JWT required |
| FE request | `frontend/endpoint-requests/GET__api_v1_fixtures__id__league_standings.request.json` |
| Consumer | `frontend/src/lib/api/fixtureDetail.ts#getLeagueStandings` |
| Feature refs | `docs/features/fixture-detail.spec.md` §6.5, `docs/features/fixture-detail.devplan.md` §6-7 |

The endpoint is DB-only. It must not call API-Football directly and must not depend on
Upstash.

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
  "league": {
    "external_id": 39,
    "slug": "premier-league",
    "name": "Premier League",
    "name_ko": "프리미어 리그",
    "short_name_ko": "EPL",
    "logo_url": null
  },
  "season": 2025,
  "group_name": null,
  "highlighted_team_ids": [40, 42],
  "rows": [
    {
      "rank": 1,
      "team": {
        "external_id": 50,
        "slug": "man-city",
        "name": "Manchester City",
        "name_ko": "맨체스터 시티",
        "short_name_ko": "맨시티",
        "logo_url": null
      },
      "played": 32,
      "win": 22,
      "draw": 6,
      "loss": 4,
      "goals_for": 72,
      "goals_against": 28,
      "goal_diff": 44,
      "points": 72,
      "group_name": null
    }
  ]
}
```

### Schema

| Field | Type | Rule |
|---|---|---|
| `league` | `LeagueRef` | Current fixture league with Korean translation fields nullable. |
| `season` | integer | `fixture.season_year`. |
| `group_name` | string \| null | Relevant group for this fixture, or `null` for single table / tournament no-table. |
| `highlighted_team_ids` | `[integer, integer]` | `[home.external_id, away.external_id]`; FE highlights these rows. |
| `rows` | array | Sorted by `rank ASC`. Empty for tournament/no standings. |
| `rows[].team` | `TeamRef` | Includes `external_id`, `slug`, `name`, `name_ko`, `short_name_ko`, `logo_url`. |
| `rows[].goal_diff` | integer | Prefer `standings.goals_diff`; if null, compute `goals_for - goals_against`. |

## 4. Business Rules

1. Load the current fixture by `fixture.external_id`. If it does not exist, return `404`.
2. Use the fixture's `league_id` and `season_year`; do not use `league.current_season` if it differs from the fixture season.
3. `highlighted_team_ids` must use team external ids in home/away order.
4. Single-table leagues (`group_name IS NULL` standings rows) return all rows for `(league_id, season_year)` sorted by rank.
5. Group-stage leagues/cups:
   - If both match teams have standings rows in the same `group_name`, return only that group.
   - If one team has a group row and the other is missing, return that team's group and preserve empty/missing highlighting.
   - Do not return rows from other groups.
6. Tournament stages or cups with no standings return:
   `200 {"rows": [], "group_name": null, ...}`.
   FE displays "토너먼트 스테이지: 그룹 순위가 없습니다".
7. Korean translations are nullable. FE falls back to English.
8. This endpoint must not return all UCL/UEL groups for the fixture detail tab; it returns only the group relevant to the match.

## 5. Errors

| Status | Case |
|---|---|
| `404` | `fixture.external_id` not found. |
| `422` | Non-integer path value. |
| `500` | Unexpected DB or serialization error. Do not expose secrets. |

## 6. DB Dependencies

| Table | Usage |
|---|---|
| `fixture` | Resolve league, season, home/away team ids. |
| `league`, `league_translation` | League ref. |
| `standings` | Source rank rows. |
| `team`, `team_translation` | Team refs. |

## 7. Implementation Contract For Tests

The endpoint router should be included in `app.main.app` and should be testable through
`app.api.v1.fixture_detail_analytics`.

Expected test hooks:

- `get_fixture_detail_analytics_service()` dependency for unit tests.
- `get_session()` dependency for integration tests.
- Service method: `get_league_standings(external_id: int) -> dict`.

## 8. Reconciliation Notes

The endpoint request JSON has a grouped prototype (`format`, `groups`). The live
fixture-detail tab consumes a flat `LeagueStandingsPayload` with `rows`,
`group_name`, and `highlighted_team_ids`. This spec follows the live consumer and mock
payload. A future standings page can expose all groups in a separate endpoint.

## 9. Change Log

| Date | Change |
|---|---|
| 2026-05-14 | Initial be-test spec for fixture-detail league standings analytical tab. |
