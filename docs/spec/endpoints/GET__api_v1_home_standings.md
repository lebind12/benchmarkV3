# GET__api_v1_home_standings

Endpoint id: `GET__api_v1_home_standings`
Method / path: `GET /api/v1/home/standings`
Feature source: `docs/features/main-home.spec.md`
FE request: `frontend/endpoint-requests/GET__api_v1_home_standings.request.json`

## 1. Purpose

Return the main-home right-panel team standings for one MVP league. This endpoint feeds the compact standings block only; it reads DB state produced by `daily-sync` and does not fetch live data.

## 2. Auth

Public GET endpoint. No JWT, role, session, refresh token, or Upstash access is required.

## 3. Query Parameters

| Name | Type | Required | Default | Rule |
|---|---|---:|---|---|
| `league_id` | integer | no | `39` | API-Football league external id. Allowed values: `39`, `2`, `3`, `48`, `45`. Unsupported values return `422`. |

## 4. Response

Status `200`.

```json
{
  "league": {
    "external_id": 39,
    "slug": "premier-league",
    "name_ko": "프리미어리그",
    "short_name_ko": "EPL",
    "name": "Premier League"
  },
  "season": 2025,
  "rows": [
    {
      "rank": 1,
      "team": {
        "external_id": 40,
        "slug": "liverpool-40",
        "name_ko": "리버풀",
        "short_name_ko": "리버풀",
        "name": "Liverpool",
        "logo_url": "https://example.test/liverpool.png"
      },
      "points": 72,
      "played": 32,
      "win": 22,
      "draw": 6,
      "loss": 4,
      "goals_for": 75,
      "goals_against": 30
    }
  ]
}
```

## 5. Response Fields

| Field | Rule |
|---|---|
| `league` | Selected `league` row by external id; translation fields from `league_translation` left join |
| `season` | `league.current_season` for the selected league |
| `rows[]` | `standings` rows for selected league/current season, sorted by `rank ASC`, then `team.name ASC` |
| `rows[].team` | `team` joined by `standings.team_id`; translation fields from `team_translation` left join |

## 6. Business Rules

1. Default league is EPL (`league.external_id = 39`).
2. Only five MVP league ids are accepted: `39`, `2`, `3`, `48`, `45`.
3. Read only `league.is_active = true`.
4. Use the selected league's `current_season` as the season source of truth.
5. Return only `standings.season_year = league.current_season`.
6. Cup competitions with no standings are valid empty states: return `200` with the league ref, season, and `rows: []`.
7. Do not synthesize Korean names. Return nullable `name_ko` / `short_name_ko` and English fallback fields.
8. Do not call API-Football, OpenAI, Supabase client SDK, or Upstash while handling the request.

## 7. Errors

| Status | Case |
|---|---|
| `422` | Non-integer or unsupported `league_id`. |
| `404` | Allowed league id is not present or not active in DB. |
| `500` | Selected league has no `current_season` or unexpected DB/session failure. Do not expose SQL text or secrets. |

## 8. DB Dependencies

| Table | Use |
|---|---|
| `league` | Selected league, active flag, current season |
| `league_translation` | Korean league labels, nullable |
| `standings` | Rank and table stats |
| `team` | Team refs |
| `team_translation` | Korean team labels, nullable |

## 9. Implementation Interface Expected By Tests

The route-level unit tests expect `app.api.v1.home` to expose:

- `router`: FastAPI router with `GET /standings`
- `get_home_service`: dependency override point

The DB integration tests expect `app.services.home` to expose:

- `get_home_standings(session, *, league_id: int) -> dict`

The dev implementation may add classes internally, but these public seams must remain available for testability.

## 10. SSOT Check

No conflict found with `AGENTS.md`, `docs/spec/db-schema.md`, or `docs/features/main-home.spec.md`. This endpoint follows the main-home DB-only freshness policy and the translation fallback policy.
