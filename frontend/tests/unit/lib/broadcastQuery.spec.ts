import { describe, expect, it } from 'vitest'
import {
  readBroadcastFixtureId,
  readBroadcastTeamColorMode,
} from '@/lib/broadcastQuery'

describe('broadcastQuery', () => {
  it('reads fixtureId as the canonical broadcast fixture query param', () => {
    expect(readBroadcastFixtureId(new URLSearchParams('fixtureId=1000001'))).toBe(1000001)
  })

  it('keeps the legacy fixture query param as a fallback', () => {
    expect(readBroadcastFixtureId(new URLSearchParams('fixture=260506'))).toBe(260506)
  })

  it('prefers fixtureId over the legacy fixture query param', () => {
    expect(readBroadcastFixtureId(new URLSearchParams('fixture=1&fixtureId=2'))).toBe(2)
  })

  it('ignores invalid fixture ids', () => {
    expect(readBroadcastFixtureId(new URLSearchParams('fixtureId=abc123'))).toBeNull()
    expect(readBroadcastFixtureId(new URLSearchParams('fixtureId='))).toBeNull()
  })

  it('uses field team colors by default', () => {
    expect(readBroadcastTeamColorMode(new URLSearchParams())).toBe('field')
    expect(readBroadcastTeamColorMode(new URLSearchParams('teamColorMode=invalid'))).toBe('field')
  })

  it('reads the field-only team color mode', () => {
    expect(readBroadcastTeamColorMode(new URLSearchParams('teamColorMode=field'))).toBe('field')
  })

  it('reads the full-board team color mode', () => {
    expect(readBroadcastTeamColorMode(new URLSearchParams('teamColorMode=full'))).toBe('full')
  })

  it('reads the primary-marker-only team color mode', () => {
    expect(
      readBroadcastTeamColorMode(new URLSearchParams('teamColorMode=marker-primary')),
    ).toBe('marker-primary')
  })
})
