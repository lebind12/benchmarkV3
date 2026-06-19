# GCP AI / Broadcast Momentum Handoff - 2026-06-14

## Context

The project is `/Users/woolee/benchmark`.

Current focus:
- Prepare GCP AI model usage, likely Vertex AI / Gemini, for future AI commentary.
- Continue local-first development. Do not deploy backend without explicit user confirmation, especially during an active match.

## Current GCP State

The user said GCP login was completed.

However, in the Codex terminal, `gcloud` is not available:

```text
zsh:1: command not found: gcloud
```

This means Google Cloud CLI is either not installed in the current environment or its PATH is not loaded for this shell.

## Next GCP Steps

1. Check whether `gcloud` is available:

```bash
gcloud --version
```

2. If not available, install Google Cloud CLI or load PATH.

Homebrew install:

```bash
brew install --cask google-cloud-sdk
```

Possible PATH setup after Homebrew install:

```bash
source "$(brew --prefix)/Caskroom/google-cloud-sdk/latest/google-cloud-sdk/path.zsh.inc"
source "$(brew --prefix)/Caskroom/google-cloud-sdk/latest/google-cloud-sdk/completion.zsh.inc"
```

3. Confirm login:

```bash
gcloud auth list
```

4. Confirm selected project:

```bash
gcloud config get-value project
```

5. If no project is selected, ask the user for the project id and run:

```bash
gcloud config set project PROJECT_ID
```

6. Confirm local Application Default Credentials:

```bash
gcloud auth application-default print-access-token
```

7. If ADC is missing:

```bash
gcloud auth application-default login
```

8. Enable Vertex AI API:

```bash
gcloud services enable aiplatform.googleapis.com
```

9. Likely local env variables:

```bash
GOOGLE_CLOUD_PROJECT=PROJECT_ID
GOOGLE_CLOUD_LOCATION=global
VERTEX_AI_MODEL=gemini-3.5-flash
```

## AI Commentary Direction

Planned future feature:
- Generate AI comments from match momentum and stat deltas.
- Intended model provider: GCP AI model, likely Vertex AI / Gemini.
- The AI comment should use already-collected broadcast data and momentum changes, not direct API-Football calls from the AI layer.

Important policy:
- The previous idea of using `codex exec` for AI comments was discussed but is not appropriate as an application runtime dependency.
- Use an explicit provider integration for production, such as Vertex AI.

## Recent Momentum Implementation State

Key files:

```text
app/services/broadcast_momentum.py
app/services/broadcast.py
frontend/src/BroadcastProgramApp.vue
frontend/src/components/broadcast/ProgramMomentumLineChart.vue
frontend/src/lib/api/apiFootballLive.ts
```

Implemented behavior:
- Momentum is calculated during broadcast `program-snapshot` calls.
- Redis keys are fixture scoped.
- Local/prod data separation uses Redis key prefix policy:
  - local: `local:`
  - production: `prod:`
- Same fixture multi-user broadcasting is guarded by Redis freshness and lock:
  - `latest.updatedAt` fresh for 8 seconds means reuse latest.
  - lock key uses `SET ... NX EX 5`.
  - only one request recalculates momentum per fixture in the short window.

Redis key patterns:

```text
broadcast:fixture:{fixtureId}:momentum:last
broadcast:fixture:{fixtureId}:momentum:samples
broadcast:fixture:{fixtureId}:momentum:latest
broadcast:fixture:{fixtureId}:momentum:lock
```

With prefix examples:

```text
local:broadcast:fixture:1489373:momentum:latest
prod:broadcast:fixture:1489373:momentum:latest
```

## Momentum Calculation Notes

Current scoring inputs:
- goals
- xG
- shots
- shots on goal
- shots inside box
- corner kicks
- danger events
- possession delta
- accurate pass delta
- opponent cards / red cards
- own cards / red cards penalties

The UI info popover includes a disclaimer:

```text
위치데이터가 없어 실제 경기 장악도를 정확히 대변하지는 않습니다.
```

## Momentum Chart State

Frontend chart:
- Uses Chart.js bar chart.
- 0 baseline is centered.
- Home-positive bars are gold: `#d8a21f`.
- Away-negative bars are blue: `#58a6ff`.
- Y-axis range is dynamic based on current data, with min range 10 and max range 100.
- Y-axis labels show top value, `0`, and bottom value.
- Frontend defensively renders one bar per minute.

History behavior:
- Backend stores samples up to `MAX_SAMPLES = 900`, enough for roughly 150 minutes at 10 second polling.
- Current momentum score uses recent weighted samples.
- Graph history returns 1 point per minute.
- Added-time display is supported:
  - `elapsed`
  - `extra`
  - `minuteKey`
  - `displayMinute`
- Example display labels:

```text
90'
90+1'
90+2'
90+4'
```

## UI Changes Recently Made

In `BroadcastProgramApp.vue`:
- Momentum panel info button added next to the title.
- Info popover z-index was raised above the chart.
- Footer was removed.
- Team momentum values and reason text moved to the top header area.
- Chart now uses the remaining lower panel area.
- Home/away momentum values have high-contrast colored boxes.

In `ProgramMomentumLineChart.vue`:
- Line chart was replaced with a bar chart.
- Uses the same home/away colors as the score boxes.
- Defensively groups chart points to one bar per minute.

## Cautions

- Do not run deployment commands unless the user explicitly asks.
- Do not assume production backend has the latest local changes.
- The user has been actively testing the broadcast page visually and expects precise UI fixes.
- Keep Korean responses concise and direct.
