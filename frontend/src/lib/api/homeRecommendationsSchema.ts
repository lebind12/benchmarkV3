import { z } from 'zod'
const time = z.string().datetime({ offset: true })
const date = z.string().regex(/^\d{4}-\d{2}-\d{2}$/).refine(value => {
  const parsed = new Date(`${value}T00:00:00Z`)
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value
}, 'Invalid calendar date')
const team = z.object({ external_id: z.number().int().positive(), name: z.string().min(1) }).strict()
export const recommendationFixtureSchema = z.object({
  fixture_id: z.number().int().positive(), kickoff_at: time, status_as_of: time,
  competition: z.object({ external_id: z.number().int().positive(), name: z.string().min(1), category: z.enum(['epl', 'ucl', 'uel', 'domestic_cup', 'other']), round: z.string().min(1) }).strict(),
  home: team, away: team,
}).strict()
const candidate = recommendationFixtureSchema.extend({
  state: z.enum(['ongoing', 'scheduled']), priority: z.number().int().min(1).max(8), reason: z.string().min(1),
  preview: z.object({ state: z.enum(['ready', 'partial', 'pending', 'failed', 'unavailable']), served: z.enum(['current', 'previous']).nullable(), generated_at: time.nullable(), as_of: time.nullable() }).strict(),
}).strict()
const result = recommendationFixtureSchema.extend({ state: z.literal('finished'), goals_home: z.number().int().nonnegative(), goals_away: z.number().int().nonnegative() }).strict()
export const homeRecommendationsSchema = z.object({
  schema_version: z.literal('1.0'), requested_date: date, display_date: date, timezone: z.literal('Asia/Seoul'),
  as_of: time.nullable(), policy_version: z.literal('home-priority-2026-10-25'), fallback_reason: z.literal('no_eligible_today').nullable(),
  items: z.array(candidate), today_results: z.array(result),
}).strict().superRefine((value, ctx) => {
  const fail = (message: string) => ctx.addIssue({ code: 'custom', message })
  const kstDate = (clock: string) => new Date(Date.parse(clock) + 9 * 3600000).toISOString().slice(0, 10)
  if (value.display_date < value.requested_date || (value.display_date !== value.requested_date) !== (value.fallback_reason !== null)) fail('Fallback must be a later eligible date')
  if (value.items.length === 0 && (value.display_date !== value.requested_date || value.fallback_reason !== null)) fail('Empty selection stays on requested date')
  const ids = new Set<number>()
  for (const row of [...value.items, ...value.today_results]) {
    if (ids.has(row.fixture_id)) fail('Duplicate fixture in recommendations or results')
    ids.add(row.fixture_id)
    if (row.home.external_id === row.away.external_id) fail('Fixture teams must differ')
    if (!value.as_of || Date.parse(row.status_as_of) > Date.parse(value.as_of)) fail('Fixture state is newer than snapshot')
    if (kstDate(row.kickoff_at) !== ('priority' in row ? value.display_date : value.requested_date)) fail('Fixture belongs to wrong KST date')
  }
  const compare = (a: z.infer<typeof candidate>, b: z.infer<typeof candidate>) => Number(b.state === 'ongoing') - Number(a.state === 'ongoing') || a.priority - b.priority || Date.parse(a.kickoff_at) - Date.parse(b.kickoff_at) || a.fixture_id - b.fixture_id
  value.items.forEach((row, index) => {
    if (index > 0 && compare(value.items[index - 1]!, row) > 0) fail('Unstable recommendation order')
    if (value.fallback_reason && row.state !== 'scheduled') fail('Fallback can only contain scheduled fixtures')
    if (row.preview.served === null && (row.preview.generated_at !== null || row.preview.as_of !== null || ['ready', 'partial'].includes(row.preview.state))) fail('No snapshot must not claim publication clocks')
    if (row.preview.served !== null && (!['ready', 'partial'].includes(row.preview.state) || row.preview.as_of === null)) fail('Saved snapshot requires publication state and data clock')
    if (row.preview.generated_at && Date.parse(row.preview.generated_at) >= Date.parse(row.kickoff_at)) fail('Generation must precede kickoff')
  })
})
export type HomeRecommendations = z.infer<typeof homeRecommendationsSchema>
