import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { contracts, documentSchema } from '../../../scripts/export-home-preview-contracts'
import { homePreviewResponseSchema } from '@/lib/api/homePreviewResponse'
import { homePreviewSchema, recentMatchSchema, recentMatchResult } from '@/lib/api/homePreviewSchema'
import { homeRecommendationsSchema } from '@/lib/api/homeRecommendationsSchema'
import { buildMockResponse } from '@/mocks/home-preview/response'
import { buildMockPreview } from '@/mocks/home-preview/preview'
import { sampleMatches, sampleDay, rank } from '@/mocks/home-preview/data'
import { buildMockRecommendations } from '@/mocks/home-preview/recommendations'
import responses from '@/mocks/home-preview/responses.json'
import recommendations from '@/mocks/home-preview/recommendations.json'
const match = sampleMatches[0]!
const response = () => buildMockResponse(match, 'ready', buildMockPreview(match, 'ready'))

describe('stored publication boundary', () => {
  it('validates checked-in examples and generated structural schemas without drift', () => {
    for (const value of Object.values(responses)) expect(homePreviewResponseSchema.safeParse(value).success).toBe(true)
    expect(homeRecommendationsSchema.safeParse(recommendations).success).toBe(true)
    for (const [name, schema] of Object.entries(contracts)) {
      const file = resolve(process.cwd(), `../docs/spec/schemas/home-preview-${name}.schema.json`)
      expect(JSON.parse(readFileSync(file, 'utf8'))).toEqual(documentSchema(name, schema))
    }
  })
  it('does not manufacture a body or generation clock for absent snapshots', () => {
    for (const state of ['pending', 'failed', 'unavailable']) {
      const value = buildMockResponse(match, state, null)
      expect(value.preview).toBeNull()
      expect(value.publication.generated_at).toBeNull()
      expect(value.publication.as_of).toBeNull()
      const invalid = structuredClone(value); invalid.publication.generated_at = '2026-10-25T09:00:00Z'
      expect(homePreviewResponseSchema.safeParse(invalid).success).toBe(false)
    }
  })
  it('keeps a valid snapshot and original clocks when a refresh fails', () => {
    const saved = buildMockPreview(match, 'ready')
    const value = buildMockResponse(match, 'previous', saved)
    expect(value.preview).toEqual(saved)
    expect(value.publication.served).toBe('previous')
    expect(value.refresh.state).toBe('failed')
    expect(value.publication.generated_at).toBe(saved.generated_at)
    const invalid = structuredClone(value); invalid.refresh.last_attempt_at = null
    expect(homePreviewResponseSchema.safeParse(invalid).success).toBe(false)
  })
  it('rejects crossed fixtures, coverage lies, overwritten clocks and internal error messages', () => {
    const crossed = response(); crossed.fixture_id = 1
    const clock = response(); clock.publication.generated_at = '2026-10-25T09:00:00Z'
    const coverage = response(); coverage.publication.state = 'partial'
    const reason = response(); (reason.refresh as { reason: unknown }).reason = 'Provider api_key secret debug stack'
    for (const invalid of [crossed, clock, coverage, reason]) expect(homePreviewResponseSchema.safeParse(invalid).success).toBe(false)
    const invalidSection = buildMockPreview(match, 'ready'); (invalidSection.facts.injuries as { reason: unknown }).reason = 'raw upstream trace'
    expect(homePreviewSchema.safeParse(invalidSection).success).toBe(false)
  })
  it('supports facts-only data with no fake AI generation time', () => {
    const facts = buildMockPreview(match, 'facts')
    expect(facts.generated_at).toBeNull()
    expect(facts.facts.home_form.data?.matches).toHaveLength(5)
    expect(buildMockResponse(match, 'facts', facts).publication.state).toBe('partial')
    const invalid = buildMockPreview(match, 'ready'); invalid.generated_at = null
    expect(homePreviewSchema.safeParse(invalid).success).toBe(false)
  })
})

describe('recommendation response', () => {
  it('keeps every eligible fixture and separates stored results', () => {
    const value = buildMockRecommendations(sampleMatches, sampleDay).response
    expect(value.items).toHaveLength(9)
    expect(value.items[0]?.state).toBe('ongoing')
    expect(value.today_results.map(row => row.fixture_id)).toEqual([90010])
    expect(value.items.find(row => row.fixture_id === 90003)?.preview.generated_at).toBeNull()
  })
  it('handles fallback and empty lists with explicit KST dates', () => {
    const future = sampleMatches.filter(row => row.day > sampleDay)
    const fallback = buildMockRecommendations(future, sampleDay).response
    expect(fallback.display_date).toBe('2026-10-27')
    expect(fallback.fallback_reason).toBe('no_eligible_today')
    expect(fallback.items[0]?.preview.state).toBe('unavailable')
    expect(buildMockRecommendations([], sampleDay).response.items).toEqual([])
  })
  it('rejects duplicates, wrong KST dates, order and future state snapshots', () => {
    const base = buildMockRecommendations(sampleMatches, sampleDay).response
    const duplicate = structuredClone(base); duplicate.items.push(duplicate.items[0]!)
    const wrongDate = structuredClone(base); wrongDate.items[0]!.kickoff_at = '2026-10-25T16:00:00Z'
    const order = structuredClone(base); order.items.reverse()
    const clock = structuredClone(base); clock.items[0]!.status_as_of = '2026-10-26T00:00:00Z'
    const date = structuredClone(base); date.requested_date = '2026-02-30'
    for (const invalid of [duplicate, wrongDate, order, clock, date]) expect(homeRecommendationsSchema.safeParse(invalid).success).toBe(false)
  })
  it('accepts configured domestic cups without a fixed display-name allowlist', () => {
    const cup = { ...match, league: '추가된 국내 컵', competitionType: 'domestic_cup' as const }
    expect(rank(cup)).toBe(7)
  })
})

describe('cup form result policy', () => {
  const row = () => ({ fixture_id: 1, kickoff_at: '2026-10-01T00:00:00Z', opponent: '상대', competition: '컵', goals_for: 1, goals_against: 1, status: 'PEN' as const, penalties: null as { for: number; against: number } | null })
  it('keeps an unknown shootout unknown and uses confirmed penalty scores', () => {
    const value = row()
    expect(recentMatchResult(recentMatchSchema.parse(value))).toBe('?')
    value.penalties = { for: 5, against: 4 }
    expect(recentMatchResult(recentMatchSchema.parse(value))).toBe('승')
    value.penalties = { for: 3, against: 4 }
    expect(recentMatchResult(recentMatchSchema.parse(value))).toBe('패')
  })
  it('uses the final extra-time score and rejects contradictory shootouts', () => {
    expect(recentMatchResult(recentMatchSchema.parse({ ...row(), status: 'AET', goals_for: 2 }))).toBe('승')
    expect(recentMatchSchema.safeParse({ ...row(), status: 'FT', penalties: { for: 5, against: 4 } }).success).toBe(false)
    expect(recentMatchSchema.safeParse({ ...row(), goals_for: 2, penalties: { for: 5, against: 4 } }).success).toBe(false)
  })
})
