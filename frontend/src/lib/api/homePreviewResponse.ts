import { z } from 'zod'
import { homePreviewSchema, publicPreviewReason } from './homePreviewSchema'

const time = z.string().datetime({ offset: true })
export const homePreviewResponseSchema = z.object({
  schema_version: z.literal('1.0'), fixture_id: z.number().int().positive(),
  publication: z.object({
    state: z.enum(['ready', 'partial', 'pending', 'failed', 'unavailable']),
    served: z.enum(['current', 'previous']).nullable(), reason: publicPreviewReason.nullable(),
    generated_at: time.nullable(), as_of: time.nullable(),
  }).strict(),
  refresh: z.object({
    state: z.enum(['idle', 'queued', 'running', 'failed']), last_attempt_at: time.nullable(), reason: publicPreviewReason.nullable(),
  }).strict(),
  preview: homePreviewSchema.nullable(),
}).strict().superRefine((value, ctx) => {
  const fail = (message: string) => ctx.addIssue({ code: 'custom', message })
  const { preview, publication: pub, refresh } = value
  if (preview === null) {
    if (['ready', 'partial'].includes(pub.state) || pub.served !== null || pub.generated_at !== null || pub.as_of !== null || pub.reason === null) fail('No snapshot requires null payload, clocks and served pointer plus public reason')
  } else {
    const complete = [...Object.values(preview.analysis), ...Object.values(preview.facts), ...Object.values(preview.external)].every(block => block.status === 'available')
    if (pub.state !== (complete ? 'ready' : 'partial') || pub.served === null) fail('Publication must describe the served payload coverage')
    if (preview.fixture.external_id !== value.fixture_id) fail('Publication fixture mismatch')
    if (pub.generated_at !== preview.generated_at || pub.as_of !== preview.as_of) fail('Publication clocks must match the saved snapshot')
    if (pub.served === 'current' && refresh.state !== 'idle') fail('A refreshing publication serves its previous snapshot')
    if (pub.reason !== null) fail('Snapshot gaps belong to section reasons')
    if (pub.served === 'previous' && refresh.state === 'idle') fail('Previous snapshot requires a pending or failed refresh')
  }
  if (preview === null && pub.state === 'failed' && refresh.state !== 'failed') fail('Failed publication requires failed attempt metadata')
  if (preview === null && pub.state === 'unavailable' && refresh.state !== 'idle') fail('Unavailable publication has no active attempt')
  if (refresh.state === 'failed' && (!refresh.reason || !refresh.last_attempt_at)) fail('Failed refresh requires public reason and attempt time')
  if (refresh.state === 'idle' && refresh.reason !== null) fail('Idle refresh has no failure reason')
  if (refresh.state === 'running' && !refresh.last_attempt_at) fail('Running refresh requires attempt time')
  if (pub.served === 'previous' && refresh.last_attempt_at && preview?.generated_at && Date.parse(refresh.last_attempt_at) < Date.parse(preview.generated_at)) fail('Refresh attempt precedes served generation')
})
export type HomePreviewResponse = z.infer<typeof homePreviewResponseSchema>
