export const BROADCAST_FIXTURE_QUERY_PARAM = 'fixtureId'
export const BROADCAST_LEGACY_FIXTURE_QUERY_PARAM = 'fixture'
export const BROADCAST_TEAM_COLOR_MODE_QUERY_PARAM = 'teamColorMode'

export type BroadcastTeamColorMode = 'field' | 'full' | 'marker-primary'

export function readBroadcastFixtureId(searchParams: URLSearchParams): number | null {
  const raw =
    searchParams.get(BROADCAST_FIXTURE_QUERY_PARAM)
    ?? searchParams.get(BROADCAST_LEGACY_FIXTURE_QUERY_PARAM)

  if (raw == null) return null

  const value = raw.trim()
  if (!/^\d+$/.test(value)) return null

  const fixtureId = Number.parseInt(value, 10)
  return Number.isSafeInteger(fixtureId) ? fixtureId : null
}

export function readBroadcastTeamColorMode(
  searchParams: URLSearchParams,
): BroadcastTeamColorMode {
  const requestedMode = searchParams.get(BROADCAST_TEAM_COLOR_MODE_QUERY_PARAM)
  if (requestedMode === 'full' || requestedMode === 'marker-primary') {
    return requestedMode
  }
  return 'field'
}
