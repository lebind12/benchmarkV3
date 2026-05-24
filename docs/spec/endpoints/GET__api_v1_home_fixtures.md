# GET__api_v1_home_fixtures

Endpoint id: `GET__api_v1_home_fixtures`
Method / path: `GET /api/v1/home/fixtures`
Feature source: `docs/features/main-home.spec.md`
FE request: `frontend/endpoint-requests/GET__api_v1_home_fixtures.request.json`

## 1. Purpose

Return the main-home center panel fixture summaries for the five MVP leagues. This is a normal user page endpoint: it reads DB state only, does not call API-Football, does not use Upstash response cache, and does not enable polling or live freshness guarantees.

## 2. Auth

Public GET endpoint. No JWT, role, session, refresh token, or Upstash access is required.

## 3. Query Parameters

| Name | Type | Required | Default | Rule |
|---|---|---:|---|---|
| `league_id` | integer | no | omitted | API-Football league external id. Allowed values: `39`, `2`, `3`, `48`, `45`. Omitted means all five leagues. Unsupported values return `422`. |
| `period` | string enum | no | `day` | One of `day`, `week`, `month`. Period windows are calculated in `Asia/Seoul`. |
| `date` | `YYYY-MM-DD` | no | today in KST | Optional exact KST date override. If present, the fixture window is that KST date from `00:00` inclusive to the next day `00:00` exclusive. `period` is still validated and echoed for FE state consistency. |

Period windows when `date` is omitted:

| Period | KST window |
|---|---|
| `day` | Today `00:00` inclusive to tomorrow `00:00` exclusive |
| `week` | Current KST week Monday `00:00` inclusive to next Monday `00:00` exclusive |
| `month` | Current KST month day 1 `00:00` inclusive to next month day 1 `00:00` exclusive |

## 4. Response

Status `200`.

```json
{
  "items": [
    {
      "external_id": 1200001,
      "league": {
        "external_id": 39,
        "slug": "premier-league",
        "name_ko": "프리미어리그",
        "short_name_ko": "EPL",
        "name": "Premier League"
      },
      "home": {
        "external_id": 33,
        "slug": "manchester-united-33",
        "name_ko": "맨체스터 유나이티드",
        "short_name_ko": "맨유",
        "name": "Manchester United",
        "logo_url": "https://example.test/manutd.png"
      },
      "away": {
        "external_id": 40,
        "slug": "liverpool-40",
        "name_ko": null,
        "short_name_ko": null,
        "name": "Liverpool",
        "logo_url": "https://example.test/liverpool.png"
      },
      "kickoff_at": "2026-05-14T10:00:00Z",
      "status_short": "NS",
      "goals_home": null,
      "goals_away": null
    }
  ],
  "filters_applied": {
    "period": "day",
    "league_id": 39
  }
}
```

`filters_applied.league_id` is omitted or `null` when no league filter is applied. The FE request shape does not require `date` in `filters_applied`; the endpoint must not make `date` a required response field.

## 5. Response Fields

| Field | Rule |
|---|---|
| `items[].external_id` | `fixture.external_id` |
| `items[].league` | `league` joined by `fixture.league_id`; translation fields from `league_translation` left join |
| `items[].home` / `away` | `team` joined by `fixture.home_team_id` / `away_team_id`; translation fields from `team_translation` left join |
| `kickoff_at` | UTC ISO8601 datetime from DB `timestamptz` |
| `status_short` | DB value as stored from API-Football. Do not call API-Football or normalize live statuses in this endpoint. |
| `goals_home` / `goals_away` | Nullable DB goals. Planned fixtures return `null`. |

## 6. Business Rules

1. Read only `league.is_active = true` rows whose `league.external_id` is in the five MVP ids: `39`, `2`, `3`, `48`, `45`.
2. Restrict results to each league's current season: `fixture.season_year = league.current_season`.
3. Apply KST window filtering to `fixture.kickoff_at` using UTC-safe bounds.
4. If `league_id` is provided, filter by `league.external_id`.
5. Sort by `fixture.kickoff_at ASC`, then `fixture.external_id ASC`.
6. Exclude cup placeholder rows whose `home_team_id` or `away_team_id` is `NULL`; the home card response shape requires concrete team refs. The DB still stores those rows for full schedule pages.
7. Do not synthesize Korean names. Return `name_ko` / `short_name_ko` from translation tables as nullable values; FE handles English fallback.
8. Empty result is not an error: return `200` with `items: []` and echoed filters.

## 7. Errors

| Status | Case |
|---|---|
| `422` | Invalid `period`, invalid `date` format, non-integer `league_id`, or unsupported `league_id`. |
| `500` | Unexpected DB/session failure. Do not expose SQL text or secrets. |

## 8. DB Dependencies

| Table | Use |
|---|---|
| `fixture` | Main source: external id, season, teams, kickoff, status, score |
| `league` | MVP league filter, active flag, current season, league ref |
| `league_translation` | Korean league labels, nullable |
| `team` | Home/away refs |
| `team_translation` | Korean team labels, nullable |

No external API, OpenAI, Supabase client SDK, or Upstash call is allowed in request handling.

## 9. Implementation Interface Expected By Tests

The route-level unit tests expect `app.api.v1.home` to expose:

- `router`: FastAPI router with `GET /fixtures`
- `get_home_service`: dependency override point

The DB integration tests expect `app.services.home` to expose:

- `list_home_fixtures(session, *, league_id: int | None, period: str, date: date | None) -> dict`

The dev implementation may add classes internally, but these public seams must remain available for testability.

## 10. SSOT Check

No conflict found with `AGENTS.md`, `docs/spec/db-schema.md`, or `docs/features/main-home.spec.md`. This endpoint follows the main-home DB-only freshness policy and the Korean-name fallback policy.
