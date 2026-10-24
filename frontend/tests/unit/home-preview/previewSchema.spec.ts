import { describe, expect, it } from 'vitest'
import records from '@/mocks/home-preview/previews.json'
import { homePreviewSchema } from '@/lib/api/homePreviewSchema'
import { buildMockPreview, parsePreviewFile } from '@/mocks/home-preview/preview'
import { sampleMatches } from '@/mocks/home-preview/data'

const fresh = () => structuredClone(records['90001'])
describe('structured home preview contract', () => {
  it('validates every JSON sample and applies independent missing/partial states', () => {
    for (const value of Object.values(records)) expect(homePreviewSchema.safeParse(value).success).toBe(true)
    const value = buildMockPreview(sampleMatches[0]!, 'ready', { ai: 'missing', homeForm: 'partial' })
    expect(value.analysis.ai_prediction.data).toBeNull()
    expect(value.facts.home_form.data?.matches).toHaveLength(3)
    expect(value.external.odds.data?.[0]?.market).toBe('1x2_90min')
  })
  it('rejects Markdown, unknown fields and cross-fixture imports', () => {
    expect(() => parsePreviewFile('## 한줄 전망', 90001)).toThrow()
    expect(() => parsePreviewFile(JSON.stringify({ ...fresh(), unexpected: true }), 90001)).toThrow()
    expect(() => parsePreviewFile(JSON.stringify(fresh()), 90002)).toThrow('경기 ID')
  })
  it('rejects invented source IDs and wrong source ownership', () => {
    const value = fresh(); value.analysis.summary.data.evidence_ids = ['invented']
    expect(homePreviewSchema.safeParse(value).success).toBe(false)
    const other = fresh(); other.sources[0]!.fixture_id = 1
    expect(homePreviewSchema.safeParse(other).success).toBe(false)
  })
  it('does not accept facts hidden behind unavailable status or undocumented empty injury lists', () => {
    const value = fresh(); value.external.odds.status = 'missing'
    expect(homePreviewSchema.safeParse(value).success).toBe(false)
    const other = fresh(); other.facts.injuries.data = []
    expect(homePreviewSchema.safeParse(other).success).toBe(false)
    other.facts.injuries.reason = 'confirmed_no_absences' as never
    expect(homePreviewSchema.safeParse(other).success).toBe(true)
  })
  it('rejects future/current recent fixtures and contradictory full sample status', () => {
    const value = fresh(); value.facts.home_form.data.matches[0]!.fixture_id = value.fixture.external_id
    expect(homePreviewSchema.safeParse(value).success).toBe(false)
    const other = fresh(); other.facts.away_form.data.matches.pop()
    expect(homePreviewSchema.safeParse(other).success).toBe(false)
    const future = fresh(); future.facts.away_form.data.matches[0]!.kickoff_at = future.fixture.kickoff_at
    expect(homePreviewSchema.safeParse(future).success).toBe(false)
  })
  it('keeps deterministic facts out of AI analysis and rejects wrong odds markets and late generation', () => {
    const value = fresh(); (value.analysis as Record<string, unknown>).odds = { home: 1.2 }
    expect(homePreviewSchema.safeParse(value).success).toBe(false)
    const other = fresh(); other.external.odds.data[0]!.market = 'qualification'
    expect(homePreviewSchema.safeParse(other).success).toBe(false)
    const late = fresh(); late.generated_at = late.fixture.kickoff_at
    expect(homePreviewSchema.safeParse(late).success).toBe(false)
  })
  it('requires independently verifiable external URLs for production payloads', () => {
    const value = fresh(); value.is_mock = false
    expect(homePreviewSchema.safeParse(value).success).toBe(false)
    for (const source of value.sources) if (source.kind !== 'db') source.url = 'https://example.test/evidence' as never
    expect(homePreviewSchema.safeParse(value).success).toBe(true)
  })
})
