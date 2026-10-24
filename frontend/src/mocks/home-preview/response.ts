import type { Match } from './data'
import type { HomePreview } from '@/lib/api/homePreviewSchema'
import { homePreviewResponseSchema, type HomePreviewResponse } from '@/lib/api/homePreviewResponse'

// Evaluation-only state fixtures. Public GET will only read persisted state.
export function buildMockResponse(match: Match, state: string | undefined, preview: HomePreview | null): HomePreviewResponse {
  const saved = ['ready', 'partial', 'previous', 'facts'].includes(state ?? '') ? preview : null
  const complete = saved && [...Object.values(saved.analysis), ...Object.values(saved.facts), ...Object.values(saved.external)].every(block => block.status === 'available')
  const failed = state === 'failed' || state === 'previous'
  return homePreviewResponseSchema.parse({
    schema_version: '1.0', fixture_id: match.id,
    publication: {
      state: saved ? complete ? 'ready' : 'partial' : state === 'failed' ? 'failed' : state === 'unavailable' ? 'unavailable' : 'pending',
      served: saved ? state === 'previous' ? 'previous' : 'current' : null,
      reason: saved ? null : state === 'failed' ? 'generation_failed' : state === 'unavailable' ? 'outside_generation_window' : 'generation_pending',
      generated_at: saved?.generated_at ?? null, as_of: saved?.as_of ?? null,
    },
    refresh: { state: failed ? 'failed' : state === 'pending' ? 'queued' : 'idle', last_attempt_at: failed ? '2026-10-25T09:00:00Z' : null, reason: failed ? 'generation_failed' : null },
    preview: saved,
  })
}
