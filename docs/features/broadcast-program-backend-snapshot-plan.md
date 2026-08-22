# Broadcast Program Backend Snapshot Plan

## Goal

Move the broadcast program page's live data preparation from the frontend to the backend.

The frontend currently calls API-Football directly, merges translations, normalizes lineups/events/statistics, and computes display-only values. The backend should precompute a frontend-ready snapshot so the broadcast page can render from one project API response.

## Branch

`backend-broadcast-program-snapshot`

## Current frontend data flow

`frontend/src/lib/api/apiFootballLive.ts` currently calls:

- `GET /fixtures`
- `GET /fixtures/events`
- `GET /fixtures/lineups`
- `GET /fixtures/statistics`
- `GET /fixtures/players`
- `GET /teams`
- `POST /api/v1/broadcast/translations`
- `GET /api/v1/fixtures/{fixtureId}/league-standings`

The frontend then builds `ApiFootballBroadcastSnapshot`.

## Existing backend overlap

The backend already has:

- `GET /api/v1/broadcast/fixtures/{external_id}/overlay`
- `app/services/broadcast.py`
- API-Football block fetching and Upstash cache
- translation lookup helpers
- lineups/events/statistics normalization for overlay use

However, the overlay response shape is not identical to the broadcast program page's `ApiFootballBroadcastSnapshot` shape.

## Proposed endpoint

Add:

```txt
GET /api/v1/broadcast/fixtures/{external_id}/program-snapshot
```

Authorization:

- Same as existing broadcast overlay endpoint.
- `ADMIN` only.

Response target:

- Compatible with the current frontend `ApiFootballBroadcastSnapshot` shape.
- May include extra backend-computed fields for future frontend simplification.

## Required snapshot fields

### Fixture core

```txt
fixtureId
leagueId
leagueName
leagueShortName
season
home
away
homeId
awayId
homeCode
awayCode
homeEnglishCode
awayEnglishCode
homeLogoUrl
awayLogoUrl
score
clock
addedTime
status
venue
```

Backend responsibilities:

- Build score string.
- Build clock and added-time labels.
- Convert API-Football status to Korean display label.
- Resolve stable team codes.
- Apply Korean translations where available.

### Lineups

Required shape:

```txt
lineups[]
  teamId
  name
  code
  primaryColor
  secondaryColor
  accentColor
  shape
  coach
    id
    name
    longName
    photoUrl
  players[]
    id
    no
    name
    longName
    pos
    grid
    rating
    photoUrl
    minutes
    shotsTotal
    shotsOnGoal
    passesTotal
    passesAccuracy
    foulsCommitted
    statGoals
    statAssists
    statYellowCards
    statRedCards
  substituteNumbers
```

Backend responsibilities:

- Normalize `startXI` into `players`.
- Resolve `primaryColor` from `team_color.primary_color` by API-Football team ID;
  return `null` when the team has no curated color.
- Resolve `secondaryColor` from `team_color.secondary_color` for formation player
  markers; return `null` when it is not curated.
- Resolve `accentColor` from `team_color.accent_color` for existing formation
  borders and badges; return `null` when it is not curated.
- Build `substituteNumbers` from API-Football substitutes.
- Merge `/fixtures/players` stats into lineup players.
- Include player photos from `/fixtures/players`.
- Apply player and coach Korean display names.
- Preserve enough player stats for substituted-in players that are not in the initial start XI.

### Events

Required shape:

```txt
events[]
  id
  kind
  teamId
  teamCode
  opponentCode
  minute
  title
  detail
  playerId
  player
  playerShortName
  playerNumber
  playerPhotoUrl
  assistId
  assist
  assistShortName
  assistNumber
  assistPhotoUrl
  score
  inPlayer
  inPlayerShortName
  inPlayerNumber
  inPlayerPhotoUrl
  outPlayer
  outPlayerShortName
  outPlayerNumber
  outPlayerPhotoUrl
  teamLogoUrl
```

Backend responsibilities:

- Convert API-Football event type/detail to frontend event kind.
- Generate stable event IDs.
- Map substitution `assist` to incoming player.
- Map substitution `player` to outgoing player.
- Attach player numbers and photos from lineup/player data.
- Apply Korean player names.

### Statistics

Current labels needed by the frontend:

```txt
점유율
xG
전체슈팅
유효슈팅
박스안슈팅
박스밖슈팅
블록슈팅
세이브
코너킥
전체패스
패스성공
패스성공률
옐로카드
레드카드
파울
오프사이드
```

Required base shape:

```txt
stats[]
  label
  home
  away
  homePct
  awayPct
```

Backend responsibilities:

- Normalize API-Football statistic labels.
- Preserve `%` only for percent stats.
- Avoid adding units to non-percent numeric values.
- Calculate `homePct` and `awayPct`.

### Program stats

Recommended backend-computed extension:

```txt
programStats
  attack[]
  chance[]
  control[]
  discipline[]
```

Current desired tab composition:

```txt
attack:
  xG
  유효슈팅
  슈팅정확도

chance:
  전체슈팅
  박스안슈팅
  코너킥

control:
  점유율
  패스성공률
  오프사이드

discipline:
  파울
  옐로카드
  레드카드
```

Derived metric:

```txt
슈팅정확도 = 유효슈팅 / 전체슈팅 * 100
```

Backend responsibilities:

- Provide the tab-ready metrics so frontend does not need `compactStats()` and `shootingAccuracyMetric()`.
- If a source stat is missing, omit that metric rather than fabricating a value.

### Player event summary

Current frontend computes:

```txt
goals
yellowCards
redCards
cardLabel
```

Recommended backend-computed extension on each lineup player:

```txt
eventSummary
  goals
  yellowCards
  redCards
  cardLabel
```

Rules:

- `statGoals` from `/fixtures/players` may be used as the preferred goal count when available.
- Otherwise count goal events by scorer only.
- `cardLabel` is `RED` if red card count is greater than zero.
- `cardLabel` is `YEL` only when red card count is zero and yellow card count is greater than zero.
- If a player receives yellow then red, display `RED` only.

### Standings

Initial scope:

- Include existing DB-based `standings` payload.
- Keep the current stale/empty payload guard on the frontend until backend live group standings is implemented.

Future scope:

- Add live projected group standings for final group-stage matches.

## Phased implementation plan

### Phase 1: backend program snapshot

Goal:

```txt
Move the broadcast program page's data preparation to the backend while keeping the current frontend snapshot shape.
```

Deliverables:

- Add `GET /api/v1/broadcast/fixtures/{external_id}/program-snapshot`.
- Return a frontend-compatible `ApiFootballBroadcastSnapshot`.
- Precompute fixture core, lineups, events, base stats, program stats, and player event summaries.
- Include existing DB-based standings as passthrough.
- Keep live projected group standings out of scope.

Backend responsibilities:

- Fetch/cache API-Football blocks.
- Normalize API-Football payloads.
- Apply Korean translations.
- Merge player stats/photos/ratings into lineups.
- Generate stable event IDs.
- Build substitution in/out fields.
- Build tab-ready `programStats`.
- Build `eventSummary` per lineup player.

Frontend responsibilities:

- Add a backend fetch path.
- Keep the current direct API-Football path as fallback during migration.
- Continue rendering and substitution animation client-side.

### Phase 2: frontend migration to backend snapshot

Goal:

```txt
Make the broadcast program page consume the backend program snapshot as its primary data source.
```

Deliverables:

- Replace primary `fetchApiFootballBroadcastSnapshot()` path with backend `program-snapshot`.
- Map backend response to the current frontend model with minimal adapter code.
- Prefer backend `programStats` when present.
- Prefer backend player `eventSummary` when present.
- Keep direct API-Football calls behind an environment-controlled fallback.

Frontend code to simplify but not fully remove yet:

- `compactStats()`
- `shootingAccuracyMetric()`
- `lineupPlayerEventSummary`
- local translation merge path
- local API-Football direct fetch path

Acceptance criteria:

- Broadcast program renders lineups, events, stat tabs, player ratings, goals/cards, and standings from backend snapshot.
- Existing direct API-Football mode can still be enabled if the backend endpoint fails or is disabled.

### Phase 3: live projected group standings

Goal:

```txt
Support group-stage final-match scenarios where the standings table must update according to live scores.
```

Deliverables:

- Add live projected standings calculation to backend.
- Include projected standings in `program-snapshot`, or expose a dedicated backend helper consumed by `program-snapshot`.
- Use current fixture score and same-group same-round fixture scores.
- Recalculate played, win, draw, loss, goals for, goals against, goal difference, and points.
- Sort and rank rows.

Minimum algorithm:

```txt
current fixture
-> league / season / round / teams
-> standings for league-season
-> find group containing current teams
-> fetch fixtures in same round
-> filter fixtures involving teams in same group
-> apply current live scores
-> recalculate points, GD, GF
-> sort and rank
```

Minimum sort policy:

```txt
points desc
goal_diff desc
goals_for desc
team_name asc
```

Key implementation questions:

- Whether API-Football standings during live matches are pre-match, partially live, or already updated.
- How to prevent double-counting when standings already include the current fixture.
- How to handle same-group simultaneous fixtures that are not live yet, postponed, suspended, or finished.

MVP policy:

- During live statuses, compute projection from baseline standings plus live fixture scores.
- Use simple ranking: points, goal difference, goals for, team name.
- Do not implement exact competition tie-breakers in this phase unless required.

### Phase 4: remove frontend direct API-Football dependency

Goal:

```txt
Make backend `program-snapshot` the sole live data source for the broadcast program page.
```

Deliverables:

- Remove or quarantine frontend API-Football direct fetch logic.
- Remove frontend API-Football key dependency from the broadcast program path.
- Remove frontend translation POST from the broadcast program path.
- Remove frontend stat normalization and player event summary calculation once backend fields are stable.
- Keep only render-state and animation-state logic on the frontend.

Final frontend data flow:

```txt
BroadcastProgramApp.vue
-> frontend API client
-> GET /api/v1/broadcast/fixtures/{external_id}/program-snapshot
-> render
```

Final backend data flow:

```txt
program-snapshot endpoint
-> API-Football cached blocks
-> DB translations
-> optional projected group standings
-> optional momentum
-> optional AI commentary
-> frontend-ready payload
```

Acceptance criteria:

- No `VITE_API_FOOTBALL_KEY` requirement for broadcast program frontend runtime.
- Browser no longer calls API-Football directly for broadcast program data.
- One backend endpoint provides all data needed by the broadcast program page.

### Phase 5: Redis-backed match momentum

Goal:

```txt
Compute a broadcast-friendly "경기 흐름" metric from live stat deltas collected by the backend.
```

Data source:

- API-Football cumulative statistics from `/fixtures/statistics`.
- API-Football events from `/fixtures/events`.
- Backend `program-snapshot` polling cadence.

Storage:

- Use Redis/Upstash, not Postgres.
- Momentum samples are short-lived derived broadcast state.
- Do not add a DB table unless post-match replay or long-term analysis becomes a product requirement.

Redis keys:

```txt
broadcast:fixture:{fixtureId}:momentum:samples
broadcast:fixture:{fixtureId}:momentum:bucket:{bucket}
```

Redis type:

```txt
samples: List
bucket: string lock/dedupe key
```

Suggested commands:

```txt
SET bucketKey 1 NX EX 15
RPUSH samplesKey sampleJson
LTRIM samplesKey -60 -1
EXPIRE samplesKey 21600
LRANGE samplesKey 0 -1
```

TTL:

```txt
6h
```

Sampling policy:

- One sample per fixture per 10-second bucket.
- Use `SET NX` bucket dedupe so multiple broadcast clients do not append duplicate samples.
- Keep last 60 samples, roughly 10 minutes at 10-second polling.
- Calculate momentum from the most recent 5-minute window.

Sample shape:

```json
{
  "capturedAt": 1780000000000,
  "status": "2H",
  "clock": "63:00",
  "home": {
    "ts": 12,
    "sog": 4,
    "sib": 7,
    "ck": 5,
    "xg": 1.24,
    "goals": 1,
    "redCards": 0
  },
  "away": {
    "ts": 8,
    "sog": 2,
    "sib": 3,
    "ck": 2,
    "xg": 0.61,
    "goals": 0,
    "redCards": 0
  }
}
```

V1 scoring formula:

```txt
threat =
  ΔxG * 60
+ ΔSOG * 10
+ ΔSIB * 5
+ ΔTS * 2
+ ΔCK * 4
+ goalEvent * 25
+ opponentRedCardEvent * 10
- ownRedCardEvent * 15
```

Fallback formula when xG is unavailable:

```txt
threat =
  ΔSOG * 18
+ ΔSIB * 10
+ ΔTS * 5
+ ΔCK * 5
+ goalEvent * 25
+ opponentRedCardEvent * 10
- ownRedCardEvent * 15
```

Delta rules:

- Compare adjacent cumulative samples.
- Treat negative deltas as `0`, because they usually indicate source refresh/reset behavior.
- Ignore missing stat deltas.
- Count goals and red cards from events and dedupe by stable event ID when possible.

Decay:

```txt
weight = exp(-ageSeconds / 90)
```

Normalization:

```txt
prior = 8
homeMomentum = (homeRaw + prior) / (homeRaw + awayRaw + prior * 2) * 100
awayMomentum = 100 - homeMomentum
```

Display smoothing:

```txt
displayHome = previousDisplayHome * 0.65 + currentHomeMomentum * 0.35
```

Backend response extension:

```json
{
  "momentum": {
    "label": "경기 흐름",
    "home": 62,
    "away": 38,
    "windowSeconds": 300,
    "sampleCount": 29,
    "generatedAt": "2026-06-14T00:00:00Z"
  }
}
```

Required Upstash adapter additions:

```txt
set_nx(key, value, ttl_seconds)
rpush_json(key, value)
lrange_json(key, start, stop)
ltrim(key, start, stop)
expire(key, ttl_seconds)
```

Out of scope for Phase 5:

- DB persistence.
- Post-match momentum replay.
- Exact SofaScore/FotMob formula replication.

### Phase 6: AI broadcast commentary from momentum and stat deltas

Goal:

```txt
Generate short Korean broadcast commentary based on momentum shifts, important events, and stat deltas.
```

Inputs:

- Current `program-snapshot`.
- Momentum output from Phase 5.
- Recent stat deltas from Redis samples.
- Recent events: goals, cards, substitutions, VAR, major xG or shot swings.
- Match context: score, clock, team names, group standings context when available.

Output:

```json
{
  "aiCommentary": {
    "headline": "한국이 최근 5분 동안 흐름을 잡았습니다.",
    "bullets": [
      "박스 안 슈팅과 유효슈팅이 동시에 늘었습니다.",
      "상대는 아직 최근 구간에서 유효슈팅을 만들지 못했습니다."
    ],
    "tone": "broadcast",
    "generatedAt": "2026-06-14T00:00:00Z"
  }
}
```

Generation policy:

- Generate only when there is a meaningful change.
- Minimum interval: 30s to 60s per fixture.
- Reuse cached commentary when inputs have not materially changed.
- Keep output short enough for lower-third or caster prompt usage.
- Do not hallucinate facts not present in snapshot/deltas.

Suggested trigger conditions:

- Momentum swing greater than 15 points within 3 minutes.
- Goal, red card, penalty, VAR decision.
- xG delta greater than 0.25 in recent window.
- Two or more shots in a recent short window.
- Group standings rank or qualification position changes.

Redis keys:

```txt
broadcast:fixture:{fixtureId}:ai-commentary:latest
broadcast:fixture:{fixtureId}:ai-commentary:bucket:{bucket}
```

TTL:

```txt
30m to 2h
```

Operational note on Codex CLI:

- Do not depend on a locally logged-in Codex CLI session from a deployed backend.
- The local Codex CLI login/session is tied to the developer machine and is not a production credential model.
- A deployed backend cannot reliably or safely reuse the current local login session.
- Running `codex` as a subprocess in production also introduces process lifecycle, latency, auth, audit, scaling, and sandboxing problems.

Recommended production approach:

- Use the OpenAI API from the backend with a server-side API key stored in deployment secrets.
- Treat AI commentary as a backend service function with explicit prompts, model selection, timeout, retries, and cache.
- Store only the short generated commentary in Redis with TTL.

Development-only option:

- A local-only adapter may call `codex exec` for experimentation.
- It must be disabled in deployed environments.
- It must not be the production implementation path.

Acceptance criteria:

- Backend can produce AI commentary from structured match facts.
- Commentary is cached and rate-limited per fixture.
- No browser-side OpenAI/Codex credentials.
- No production dependency on local Codex CLI login state.

## Live group standings design details

This belongs to Phase 3 because it requires additional API-Football calls and tie-breaker policy decisions.

Target behavior:

```txt
current fixture
-> league / season / round / teams
-> standings for league-season
-> find group containing current teams
-> fetch fixtures in same round
-> filter fixtures involving teams in same group
-> apply current live scores
-> recalculate points, GD, GF
-> sort and rank
```

Minimum sort policy:

```txt
points desc
goal_diff desc
goals_for desc
team_name asc
```

Known limitation:

- FIFA/UEFA tie-breakers can be more complex than this. Use the simple policy for MVP unless exact competition tie-breaker support is explicitly required.

## API-Football calls and cache policy

Initial snapshot:

```txt
/fixtures?id={external_id}
/fixtures/events?fixture={external_id}
/fixtures/lineups?fixture={external_id}
/fixtures/statistics?fixture={external_id}
/fixtures/players?fixture={external_id}
optional /teams?id={team_id} when fixture team code is missing
```

Suggested TTLs:

```txt
core: 10s
events: 10s
statistics: 10s or 30s
players: 30s or 60s
lineups: 120s to 300s
program-snapshot: 10s
```

Rationale:

- Score/events must update quickly.
- Player ratings and statistics can be slightly less frequent, but broadcast UX currently expects 10-second polling.
- Lineups are stable after kickoff except substitution display, which comes from events and player stats.

## Frontend migration plan

Phase 1 frontend change:

- Add a backend fetch path in `apiFootballLive.ts`.
- Replace direct API-Football live calls with:

```txt
GET /api/v1/broadcast/fixtures/{fixtureId}/program-snapshot
```

Keep temporarily:

- Existing direct API-Football code as fallback behind an environment flag.

Eventually remove:

- Frontend API-Football key requirement.
- Frontend API-Football direct calls.
- `POST /api/v1/broadcast/translations` from broadcast program data path.
- Frontend statistic normalization.
- Frontend player event summary calculation.

## Phase 1 backend implementation steps

1. Add response serializer functions that produce `ApiFootballBroadcastSnapshot`-compatible shape.
2. Extend existing broadcast stat normalization to include all labels required by broadcast program.
3. Add program stat metric builder.
4. Add player stat map builder with rating, photo, goals, assists, cards, shots, passes, fouls.
5. Add event player metadata map for number/photo enrichment.
6. Add player event summary builder.
7. Add `BroadcastProgramSnapshotService` or method on `BroadcastOverlayService`.
8. Add `GET /api/v1/broadcast/fixtures/{external_id}/program-snapshot`.
9. Add tests for response shape, stat labels, player event summaries, substitution player stats, and cache behavior.

## Test plan

Backend unit tests:

- Statistic label normalization includes `expected_goals`, `Shots insidebox`, `Goalkeeper Saves`, `Total passes`, `Passes accurate`.
- Non-percent stats are displayed without units.
- `슈팅정확도` is calculated from `Shots on Goal / Total Shots`.
- Missing stat omits derived metric.
- Yellow plus red card produces `cardLabel = RED`.
- Goal event counts scorer only, not assist.
- Substitution event produces correct `inPlayer` and `outPlayer`.

Integration tests:

- `GET /api/v1/broadcast/fixtures/{id}/program-snapshot` requires `ADMIN`.
- Snapshot contains fixture core, lineups, events, stats, programStats, standings.
- API-Football block cache is used with expected keys/TTLs.

Frontend migration tests:

- Broadcast program can render from backend snapshot.
- Existing direct API-Football fallback still works while enabled.

## Out of scope

- Live projected group standings.
- Exact FIFA/UEFA tie-breaker rules.
- Persisting broadcast session state.
- Reworking visual layout beyond data-source migration.

## Recommended first implementation scope

Implement only:

```txt
1. /api/v1/broadcast/fixtures/{id}/program-snapshot
2. frontend-compatible snapshot shape
3. backend stat/event/lineup/player translation preparation
4. programStats
5. player event summaries
6. existing DB standings passthrough
```

Defer:

```txt
liveGroupStandings
tie-breaker exactness
momentum
aiCommentary
```
