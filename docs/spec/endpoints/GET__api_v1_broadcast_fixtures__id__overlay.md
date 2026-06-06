---
endpoint_id: GET__api_v1_broadcast_fixtures__id__overlay
method: GET
path: /api/v1/broadcast/fixtures/{external_id}/overlay
feature: broadcast-match-overlay
auth: STREAMER
owner: be-test
created: 2026-05-14
---

# GET /api/v1/broadcast/fixtures/{external_id}/overlay

## Current Status

2026-05-24 기준 이 문서는 `broadcast-match-overlay` 백엔드 endpoint lifecycle 의 정본이다. 이전 목업 단계에서 FE 가 API-Football 을 직접 호출하던 흐름은 이 endpoint 전환 후 더 이상 방송용 overlay 의 정본 데이터 경로가 아니다.

FE handoff source 는 `frontend/endpoint-requests/GET__api_v1_broadcast_fixtures__id__overlay.request.json` 이며, FastAPI 구현은 아래 요청/응답/권한/캐시 규칙을 따라야 한다.

## Purpose

Broadcast match overlay endpoint for the 1920x1080 streaming mockup. It returns one
polling payload for:

- top scoreboard
- left formation cards
- right-bottom statistics board
- center-bottom event toast loop

This endpoint is intentionally different from normal user fixture pages. Normal pages are
DB-only and may be stale up to the 6h worker SLA. This broadcast endpoint is for
STREAMER/ADMIN users and may call API-Football at request time through an Upstash cache.

FE handoff source: `frontend/endpoint-requests/GET__api_v1_broadcast_fixtures__id__overlay.request.json`.

## API-Football References

Official references checked on 2026-05-14:

- API-Football v3 documentation: `https://www.api-football.com/documentation-v3`
- API-SPORTS fixtures guide: `https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide`
- API-SPORTS World Cup 2026 data guide: `https://www.api-football.com/news/post/fifa-world-cup-2026-guide-to-using-data-with-api-sports`

Relevant source endpoints:

| Source | Purpose | Runtime use |
|---|---|---|
| `GET /fixtures?id={fixture_id}` or `GET /fixtures?ids={fixture_id}` | fixture status, teams, scores; docs/guides may include embedded match detail blocks | First call / fallback aggregation |
| `GET /fixtures/events?fixture={fixture_id}` | goals, cards, substitutions, VAR timeline | Event toast and marker goal/card/sub state |
| `GET /fixtures/lineups?fixture={fixture_id}` | formations, starting XI, bench, coach, player grid | Formation cards |
| `GET /fixtures/statistics?fixture={fixture_id}` | team match stats | Stats board |
| `GET /fixtures/players?fixture={fixture_id}` | player ratings, goals, assists, cards, minutes, substitute state | Player marker badges |

Implementation may use embedded detail blocks from `/fixtures?id=...` when present to reduce
calls. If embedded blocks are absent or incomplete, call the explicit sub-endpoints above.

## Request

| Field | Value |
|---|---|
| Method | `GET` |
| Path | `/api/v1/broadcast/fixtures/{external_id}/overlay` |
| Auth | `STREAMER` or `ADMIN` JWT required |
| Path params | `external_id: int`, API-Football fixture id |

Query params:

| Name | Type | Required | Rule |
|---|---|---:|---|
| `league_slug` | string | no | Optional FE theme hint. If supplied, must be one of `premier-league`, `champions-league`, `europa-league`, `carabao-cup`, `fa-cup`, `world-cup-2026`; invalid values return `422`. Backend still derives canonical league/theme from fixture DB/API data. |

## Response: 200

```json
{
  "fixture": {
    "external_id": 1000001,
    "league": {
      "external_id": 39,
      "slug": "premier-league",
      "name": "Premier League",
      "name_ko": "프리미어리그",
      "short_name_ko": "EPL",
      "logo_url": "https://...",
      "theme_slug": "premier-league"
    },
    "status_short": "2H",
    "status_long": "Second Half",
    "elapsed": 63,
    "extra": null,
    "clock_label": "63:10",
    "added_time_label": "+0",
    "home": {
      "external_id": 40,
      "slug": "liverpool-40",
      "name": "Liverpool",
      "name_ko": "리버풀",
      "short_name_ko": "리버풀",
      "logo_url": "https://...",
      "badge_url": "https://...",
      "code": "LIV"
    },
    "away": {
      "external_id": 42,
      "slug": "arsenal-42",
      "name": "Arsenal",
      "name_ko": "아스널",
      "short_name_ko": "아스널",
      "logo_url": "https://...",
      "badge_url": "https://...",
      "code": "ARS"
    },
    "goals_home": 2,
    "goals_away": 1
  },
  "lineups": [
    {
      "team_external_id": 40,
      "team_side": "home",
      "team_name": "Liverpool",
      "team_name_ko": "리버풀",
      "team_code": "LIV",
      "team_logo_url": "https://...",
      "formation": "4-3-3",
      "players": [
        {
          "player_external_id": 2001,
          "number": 1,
          "name": "Alisson",
          "name_ko": "알리송",
          "short_name_ko": "알리송",
          "position": "GK",
          "grid": "1:1",
          "rating": 7.1,
          "goals": 0,
          "yellow_cards": 0,
          "red_cards": 0,
          "substitution": "none"
        }
      ]
    }
  ],
  "statistics": [
    {
      "type": "possession",
      "label_ko": "점유율",
      "home": 61,
      "away": 39,
      "home_display": "61%",
      "away_display": "39%",
      "home_pct": 61,
      "away_pct": 39
    }
  ],
  "events": [
    {
      "event_id": "1000001:12",
      "kind": "substitution",
      "team_external_id": 40,
      "team_side": "home",
      "team_code": "LIV",
      "team_logo_url": "https://...",
      "minute": 63,
      "extra": null,
      "clock_label": "63:10",
      "title_ko": "선수 교체",
      "detail_ko": "측면 압박 강화를 위한 교체",
      "score_label": "2 : 1",
      "player": null,
      "assist": null,
      "in_player": {
        "external_id": 2050,
        "name": "Player In",
        "name_ko": "교체투입",
        "short_name_ko": "투입"
      },
      "out_player": {
        "external_id": 2040,
        "name": "Player Out",
        "name_ko": "교체아웃",
        "short_name_ko": "아웃"
      },
      "stat": null
    }
  ],
  "polling": {
    "interval_seconds": 10,
    "cache_hit": true,
    "cache_ttl_seconds": 8,
    "generated_at": "2026-05-14T02:00:00Z"
  }
}
```

## Schema Rules

### Fixture

| Field | Type | Rule |
|---|---|---|
| `league.theme_slug` | enum | One of `premier-league`, `champions-league`, `europa-league`, `carabao-cup`, `fa-cup`, `world-cup-2026`. Derived from league external id. |
| `clock_label` | string | Display clock. Live: elapsed/extra based label. Non-live: `FT`, `HT`, `NS`, etc. |
| `added_time_label` | string or null | `+N` when available. Return `null` if not known. |
| `home/away.badge_url` | string or null | For clubs this can equal `logo_url`; for national teams it may be a flag/badge asset URL. |
| `home/away.code` | string | 2-4 char display code. Prefer short translation or team code; fallback to uppercase slug prefix. |

### Lineups And Player Markers

`lineups` must contain home and away objects when fixture teams are known. If lineups are not
announced, return both sides with `formation=null` and `players=[]`.

Player marker fields required by the mock:

| Field | Source | Rule |
|---|---|---|
| `number` | lineups `player.number` | Nullable but strongly preferred. |
| `short_name_ko` | `player_translation.short_name_ko` fallback | FE shows this under the marker. Fallback to `name_ko`, then source short name/name. |
| `grid` | lineups `player.grid` | Raw API-Football grid such as `2:3`; nullable. FE may use formation fallback when null. |
| `rating` | `/fixtures/players` statistics rating | Number 0-10 or null. |
| `goals` | events or `/fixtures/players` goals total | Integer, supports multi-goal display. |
| `yellow_cards` | events or `/fixtures/players` cards yellow | Integer. |
| `red_cards` | events or `/fixtures/players` cards red | Integer. |
| `substitution` | events or `/fixtures/players` substitute info | `in`, `out`, or `none`. |

If `/fixtures/players` is unavailable, use `/fixtures/events` to derive goals/cards/substitution
and set `rating=null`.

### Statistics

Return the display rows the current board needs, in this order when available:

1. `possession`
2. `shots_total`
3. `shots_on_goal`
4. `corner_kicks`
5. `passes_pct`
6. Optional: `offsides`, `yellow_cards`, `red_cards`

Raw API-Football stat names should normalize as follows:

| API-Football stat | Type |
|---|---|
| `Ball Possession` | `possession` |
| `Total Shots` | `shots_total` |
| `Shots on Goal`, `Shots on Target` | `shots_on_goal` |
| `Corner Kicks` | `corner_kicks` |
| `Passes %`, `Passes accurate %`, `Passes Accurate` | `passes_pct` |
| `Offsides` | `offsides` |
| `Yellow Cards` | `yellow_cards` |
| `Red Cards` | `red_cards` |

`home_pct` and `away_pct` are UI meter widths. For percentage stats, use parsed percentage
values. For count stats, compute proportional values from both sides; if both sides are zero or
null, return `50/50`.

### Events

Return recent displayable events sorted oldest to newest. FE loops through the returned array.
Recommended count: last 5 to 8 events.

Canonical event kinds:

| Raw API-Football event | Canonical `kind` | Required fields |
|---|---|---|
| Goal / Normal Goal | `goal` | `player`, optional `assist`, `score_label` |
| Goal / Penalty | `goal` | `player`, `detail_ko` mentions penalty |
| Card / Yellow Card | `yellow-card` | `player` |
| Card / Red Card, Yellow-Red Card | `red-card` | `player` |
| subst | `substitution` | `in_player`, `out_player` |
| Var | `var` | `detail_ko` |
| Derived metric alert | `stat` | `stat.label_ko`, `stat.value_label` |

Derived `stat` events are optional for MVP. If implemented, generate them only from cached
stat deltas to avoid noisy alerts.

## Caching And Polling

FE polls every 10 seconds while the broadcast page is open. Backend must cache API-Football
calls with separate keys so one slow-changing block does not force every source call.

Suggested Upstash keys:

| Key | TTL | Source |
|---|---:|---|
| `broadcast:fixture:{id}:core` | 10-15s | `/fixtures` |
| `broadcast:fixture:{id}:events` | 10-15s | `/fixtures/events` |
| `broadcast:fixture:{id}:statistics` | 55-60s | `/fixtures/statistics` |
| `broadcast:fixture:{id}:players` | 55-60s | `/fixtures/players` |
| `broadcast:fixture:{id}:lineups` | 5-10m before confirmed, 1-6h after confirmed | `/fixtures/lineups` |
| `broadcast:fixture:{id}:overlay` | 5-10s | assembled response |

Follow project API-Football policy: Ultra plan limit is 450 req/min; use cache-first behavior
and semaphore limit 6 for external calls.

## Status Behavior

| Scenario | Response |
|---|---|
| Live fixture (`1H`, `HT`, `2H`, `ET`, `BT`, `P`, `LIVE`) | Use API-Football through cache; return live score/events/statistics when available. |
| Not started (`NS`) | Return DB snapshot plus cached/pre-match API data if available; lineups may be empty. |
| Finished (`FT`, `AET`, `PEN`) | Prefer DB fallback unless a short post-match refresh window is configured. |
| Postponed/cancelled/suspended (`PST`, `CANC`, `SUSP`) | Return fixture payload with empty `events`/`statistics` as appropriate. |
| API-Football partial coverage | Return null/empty arrays for missing blocks, not 500. |

## Errors

| Status | Case |
|---|---|
| `401` | Missing/expired JWT. |
| `403` | Authenticated user lacks `STREAMER` or `ADMIN` role. |
| `404` | Fixture external id not found in DB and not found in API-Football lookup. |
| `422` | Non-integer path param or invalid query param. |
| `502` | API-Football failed and no usable cached/DB fallback exists for a live fixture. |
| `500` | Unexpected server error. Do not expose keys or upstream response bodies. |

## DB Dependencies

| Table | Usage |
|---|---|
| `fixture` | Fixture identity, league/team FK, DB fallback score/status. |
| `league`, `league_translation` | League names and theme slug mapping. |
| `team`, `team_translation` | Team refs, Korean names, short names, logos. |
| `player`, `player_translation` | Player refs and Korean marker labels. |
| `fixture_detail` | DB fallback JSONB for events, lineups, statistics, player stats if stored. |

No schema change is required for the FE mock handoff itself. BE implementation may need a
small helper/mapping layer for `league.external_id -> theme_slug`; if no column exists, keep it
in code or a seedable lookup rather than changing the FE response shape.

## Implementation Contract For Tests

Expected backend shape:

| Symbol | Contract |
|---|---|
| route module | `app.api.v1.broadcast.router` included in `app.main.app` |
| route path | `/api/v1/broadcast/fixtures/{external_id}/overlay` |
| auth dependency | `get_broadcast_current_user()` override hook returning an object with `role`; route must allow `STREAMER` and `ADMIN`, reject `USER` with `403`, and propagate missing/expired JWT as `401` |
| service dependency | `get_broadcast_overlay_service()` override hook for unit tests |
| service method | `get_overlay(external_id: int, user: CurrentUser, league_slug: str | None = None) -> dict | None`; `None` maps to `404 fixture_not_found`; `BroadcastOverlayError` maps to `502 broadcast_upstream_unavailable` |
| API client dependency | `get_broadcast_api_football_client()` override hook for integration tests; default implementation must respect project semaphore/rate-limit policy |
| cache dependency | `get_broadcast_cache()` override hook for integration tests; tests use fake cache and must not require real Redis |

## Non-Goals

- BE does not return CSS colors, component variant names, or layout percentages.
- BE does not calculate player marker pixel/% positions. Return `formation` and raw `grid`;
  FE owns formation layout.
- BE does not create OBS/chroma behavior.
- BE does not implement general-user live score polling.

## MVP Defaults For Reviewer/Dev

| Topic | Default |
|---|---|
| Finished match refresh | Immediately prefer DB fallback after `FT`/`AET`/`PEN`; post-match live refresh window is post-MVP unless reviewer requests otherwise. |
| Derived `stat` event alerts | Post-MVP. Return API-Football match events only for MVP, plus empty `stat` events unless a later spec extends this. |
| National-team `badge_url` | Use API-Football team logo as `logo_url`/`badge_url` fallback. Internal flag asset mapping is post-MVP. |

## Change Log

| Date | Change |
|---|---|
| 2026-05-24 | Refreshed stale FE-direct status; added explicit auth/dependency/cache contracts and MVP defaults for backend lifecycle. |
| 2026-05-14 | Initial FE handoff endpoint spec for broadcast overlay mock completion. |
