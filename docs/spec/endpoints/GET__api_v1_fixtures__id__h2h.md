# GET__api_v1_fixtures__id__h2h

## 1. Summary

Fixture detail analytical tab endpoint for recent head-to-head matches.

| Field | Value |
|---|---|
| Method | `GET` |
| Path | `/api/v1/fixtures/{external_id}/h2h` |
| Auth | Public, no JWT required |
| FE request | `frontend/endpoint-requests/GET__api_v1_fixtures__id__h2h.request.json` |
| Consumer | `frontend/src/lib/api/fixtureDetail.ts#getH2H` |
| Feature refs | `docs/features/fixture-detail.spec.md` §6.3, `docs/features/fixture-detail.devplan.md` §6-7 |

The endpoint is for a normal user page, so it must read DB state only. It must not call
API-Football, OpenAI, Upstash, or do polling/cache refresh work.

## 2. Request

### Path Parameters

| Name | Type | Rule |
|---|---|---|
| `external_id` | integer | API-Football fixture id. Must identify a row in `fixture.external_id`. |

### Query Parameters

| Name | Type | Default | Rule |
|---|---|---|---|
| `limit` | integer | `5` | `1 <= limit <= 10`; values above 10 return `422`. FE currently calls `limit=5`. |

## 3. Response

`200 OK`

```json
{
  "h2h": [
    {
      "external_id": 999001,
      "league": {
        "external_id": 39,
        "slug": "premier-league",
        "short_name_ko": "EPL",
        "name": "Premier League"
      },
      "kickoff_at": "2025-12-21T15:00:00Z",
      "home": {
        "external_id": 42,
        "slug": "arsenal",
        "name": "Arsenal",
        "name_ko": "아스널",
        "short_name_ko": "아스널",
        "logo_url": null
      },
      "away": {
        "external_id": 40,
        "slug": "liverpool",
        "name": "Liverpool",
        "name_ko": "리버풀",
        "short_name_ko": "리버풀",
        "logo_url": null
      },
      "goals_home": 1,
      "goals_away": 2,
      "status_short": "FT"
    }
  ]
}
```

### Schema

| Field | Type | Rule |
|---|---|---|
| `h2h` | array | Sorted by `kickoff_at DESC`, length `<= limit`. Empty array is valid. |
| `h2h[].external_id` | integer | H2H fixture external id. |
| `h2h[].league.external_id` | integer \| null | `h2h_fixture.league_external_id`; may be outside active league list. |
| `h2h[].league.slug` | string \| null | From `league.slug` when known by external id, otherwise generated slug or `null`. |
| `h2h[].league.short_name_ko` | string \| null | From `league_translation.short_name_ko` when known. |
| `h2h[].league.name` | string \| null | Prefer `league.name`; fallback `h2h_fixture.league_name`. |
| `h2h[].home`, `h2h[].away` | `TeamRef` | Includes `external_id`, `slug`, `name`, `name_ko`, `short_name_ko`, `logo_url`. Korean fields may be `null`; FE falls back to English. |
| `h2h[].goals_home`, `h2h[].goals_away` | integer | Finished score. |
| `h2h[].status_short` | string | Must be `FT`, `AET`, or `PEN`; MVP tests require `FT` filtering. |

## 4. Business Rules

1. Load the current fixture by `fixture.external_id`. If it does not exist, return `404`.
2. The current fixture must have both `home_team_id` and `away_team_id`; if either is null, return `200 {"h2h":[]}`.
3. Query `h2h_fixture` for the same unordered pair:
   `LEAST(home_team_id, away_team_id)` and `GREATEST(home_team_id, away_team_id)` must match the current fixture pair.
4. Exclude the current fixture itself (`h2h_fixture.external_id != fixture.external_id`).
5. Include finished matches only. MVP filter: `status_short IN ('FT', 'AET', 'PEN')`; tests assert `FT` rows and exclude `NS`.
6. Sort by `kickoff_at DESC` and apply `limit`.
7. Team names must join `team_translation` with English fallback by allowing `name_ko` and `short_name_ko` to be null.
8. League translation joins are best-effort. H2H rows from leagues not present in `league` are still valid if `h2h_fixture.league_name` exists.

## 5. Errors

| Status | Case |
|---|---|
| `404` | `fixture.external_id` not found. |
| `422` | Non-integer path/query value or `limit` outside `1..10`. |
| `500` | Unexpected DB or serialization error. Do not expose secrets. |

## 6. DB Dependencies

| Table | Usage |
|---|---|
| `fixture` | Resolve current fixture and current home/away internal team ids. |
| `h2h_fixture` | Source rows; use `h2h_pair_idx` functional index. |
| `team` | Home/away refs. |
| `team_translation` | Korean labels. |
| `league`, `league_translation` | Best-effort league ref enrichment by `league.external_id`. |

## 7. Implementation Contract For Tests

The endpoint router should be included in `app.main.app` and should be testable through
`app.api.v1.fixture_detail_analytics`.

Expected test hooks:

- `get_fixture_detail_analytics_service()` dependency for unit tests.
- `get_session()` dependency for integration tests.
- Service method: `get_h2h(external_id: int, limit: int = 5) -> dict`.

## 8. Reconciliation Notes

The request JSON captures endpoint id/path/auth. Its response example omits `status_short`
and some live FE team fields. The implementation must follow the current fixture-detail
TypeScript type and mock payload because `H2HTab.vue` consumes those fields.

## 9. Change Log

| Date | Change |
|---|---|
| 2026-05-14 | Initial be-test spec for fixture-detail H2H analytical tab. |
