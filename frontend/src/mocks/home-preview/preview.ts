import records from './previews.json'
import type { Match } from './data'
import { homePreviewSchema, type HomePreview } from '@/lib/api/homePreviewSchema'

export type PreviewDataKey = 'summary' | 'keyPoints' | 'injuries' | 'homeForm' | 'awayForm' | 'ai' | 'external' | 'odds'
export type PreviewDataStatus = 'available' | 'partial' | 'missing'
export function previewBlocks(preview: HomePreview) {
  return { summary: preview.analysis.summary, keyPoints: preview.analysis.key_points, injuries: preview.facts.injuries, homeForm: preview.facts.home_form, awayForm: preview.facts.away_form,
    ai: preview.analysis.ai_prediction, external: preview.external.predictions, odds: preview.external.odds }
}
export function buildMockPreview(match: Match, state: string | undefined, edits: Partial<Record<PreviewDataKey, PreviewDataStatus>> = {}): HomePreview {
  const raw = (records as Record<string, unknown>)[String(match.id)]
  const result = homePreviewSchema.parse(raw)
  const blocks = previewBlocks(result)
  for (const key of Object.keys(blocks) as PreviewDataKey[]) {
    const block = blocks[key]
    const value = edits[key] ?? (state === 'partial' && ['external', 'odds'].includes(key) ? 'missing' : state === 'partial' && key === 'awayForm' ? 'partial' : 'available')
    block.status = value
    if (value === 'missing') { block.data = null; block.reason = 'not_collected'; block.as_of = null; block.source_ids = [] }
    else if (value === 'partial' && (key === 'homeForm' || key === 'awayForm')) {
      const form = key === 'homeForm' ? result.facts.home_form : result.facts.away_form
      if (form.data) form.data.matches = form.data.matches.slice(0, 3)
      block.reason = 'insufficient_sample'
    }
  }
  if (state === 'facts') {
    for (const block of Object.values(result.analysis)) Object.assign(block, { status: 'missing', reason: 'generation_pending', as_of: null, source_ids: [], data: null })
    result.generated_at = null
  }
  return homePreviewSchema.parse(result)
}
export function parsePreviewFile(json: string, fixtureId: number): HomePreview {
  const value = homePreviewSchema.parse(JSON.parse(json))
  if (value.fixture.external_id !== fixtureId) throw new Error('경기 ID가 일치하지 않습니다.')
  return value
}
