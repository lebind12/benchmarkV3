import { z } from 'zod'

const text = z.string().min(1)
const time = z.string().datetime({ offset: true })
const id = z.number().int().positive()
const refs = z.array(text).min(1)
const status = z.enum(['available', 'partial', 'missing', 'unverified', 'error'])
function section<T extends z.ZodTypeAny>(data: T) {
  return z.object({ status, reason: text.nullable(), as_of: time.nullable(), source_ids: z.array(text), data: data.nullable() }).strict()
}
const team = z.object({ external_id: id, name: text }).strict()
const supportedText = z.object({ text, evidence_ids: refs }).strict()
const point = z.object({ title: text, description: text, evidence_ids: refs }).strict()
const prediction = z.object({ home_goals: z.number().int().min(0).max(30), away_goals: z.number().int().min(0).max(30), confidence: z.enum(['low', 'medium', 'high']), reason: text, evidence_ids: refs }).strict()
export const homePreviewAnalysisSchema = z.object({ summary: section(supportedText), key_points: section(z.array(point).min(1)), ai_prediction: section(prediction) }).strict()
const recentMatch = z.object({ fixture_id: id, kickoff_at: time, opponent: text, competition: text, goals_for: z.number().int().nonnegative(), goals_against: z.number().int().nonnegative() }).strict()
const form = z.object({ team_id: id, expected_count: z.literal(5), matches: z.array(recentMatch).max(5) }).strict()
const injury = z.object({ team_id: id, player_name: text, availability: z.enum(['out', 'doubtful']), detail: text, impact: text, source_ids: refs }).strict()
const externalPrediction = z.object({ source_id: text, outlook: text, summary: text }).strict()
const odds = z.object({ source_id: text, bookmaker: text, market: z.literal('1x2_90min'), format: z.literal('decimal'), home: z.number().gt(1), draw: z.number().gt(1), away: z.number().gt(1), collected_at: time }).strict()
export const homePreviewSchema = z.object({
  schema_version: z.literal('1.0'), is_mock: z.boolean(), fixture: z.object({ external_id: id, kickoff_at: time, home: team, away: team }).strict(),
  generated_at: time, as_of: time,
  sources: z.array(z.object({ id: text, fixture_id: id, kind: z.enum(['db', 'web', 'api']), title: text, url: z.string().url().nullable(), published_at: time.nullable(), retrieved_at: time }).strict()),
  analysis: homePreviewAnalysisSchema,
  facts: z.object({ injuries: section(z.array(injury)), home_form: section(form), away_form: section(form) }).strict(),
  external: z.object({ predictions: section(z.array(externalPrediction).min(1)), odds: section(z.array(odds).min(1)) }).strict(),
}).strict().superRefine((value, context) => {
  const fail = (message: string) => context.addIssue({ code: z.ZodIssueCode.custom, message })
  const sources = new Map(value.sources.map(source => [source.id, source]))
  if (value.fixture.home.external_id === value.fixture.away.external_id) fail('Fixture teams must differ')
  if (sources.size !== value.sources.length) fail('Duplicate source ID')
  if (Date.parse(value.as_of) > Date.parse(value.generated_at)) fail('Data snapshot is newer than generation')
  if (Date.parse(value.generated_at) >= Date.parse(value.fixture.kickoff_at)) fail('Prematch generation must precede kickoff')
  for (const source of value.sources) {
    if (source.fixture_id !== value.fixture.external_id) fail('Source fixture mismatch')
    if (Date.parse(source.retrieved_at) > Date.parse(value.generated_at)) fail('Source retrieved after generation')
    if (Date.parse(source.retrieved_at) > Date.parse(value.as_of)) fail('Source retrieved after data snapshot')
    if (source.published_at && Date.parse(source.published_at) >= Date.parse(value.fixture.kickoff_at)) fail('Post-kickoff evidence is not prematch evidence')
    if (source.published_at && Date.parse(source.published_at) > Date.parse(source.retrieved_at)) fail('Source published after retrieval')
    if (source.url && !/^https?:\/\//i.test(source.url)) fail('Source URL must use HTTP')
    if (!value.is_mock && source.kind !== 'db' && (!source.url || !/^https?:\/\//.test(source.url))) fail('External source requires an HTTP URL')
  }
  const checkRefs = (ids: string[], kinds?: string[]) => ids.forEach(sourceId => {
    const source = sources.get(sourceId)
    if (!source) fail(`Unknown source ${sourceId}`)
    else if (kinds && !kinds.includes(source.kind)) fail('Source kind does not match section responsibility')
  })
  const sections = [
    ...Object.values(value.analysis), ...Object.values(value.facts), ...Object.values(value.external),
  ]
  for (const block of sections) {
    checkRefs(block.source_ids)
    if (['missing', 'unverified', 'error'].includes(block.status)) {
      if (block.data !== null || !block.reason) fail('Unavailable section requires null data and a reason')
    } else if (block.data === null || !block.as_of || !block.source_ids.length) fail('Available section requires data, time and sources')
    if (block.status === 'partial' && !block.reason) fail('Partial section requires a reason')
    if (block.as_of && Date.parse(block.as_of) > Date.parse(value.generated_at)) fail('Section snapshot is newer than generation')
  }
  const homeAway = [[value.facts.home_form, value.fixture.home.external_id], [value.facts.away_form, value.fixture.away.external_id]] as const
  for (const [block, teamId] of homeAway) {
    checkRefs(block.source_ids, ['db'])
    if (!block.data) continue
    if (block.data.team_id !== teamId) fail('Recent form team mismatch')
    if (block.status === 'available' && block.data.matches.length !== 5) fail('Full recent form requires five games')
    if (block.status === 'partial' && (block.data.matches.length < 1 || block.data.matches.length >= 5)) fail('Partial recent form requires one to four games')
    const ids = new Set<number>()
    for (const match of block.data.matches) {
      if (ids.has(match.fixture_id) || match.fixture_id === value.fixture.external_id) fail('Duplicate or current fixture in recent form')
      ids.add(match.fixture_id)
      if (Date.parse(match.kickoff_at) >= Date.parse(value.fixture.kickoff_at)) fail('Future match in recent form')
      if (Date.parse(match.kickoff_at) > Date.parse(value.as_of)) fail('Recent match is newer than input snapshot')
    }
  }
  for (const item of value.facts.injuries.data ?? []) {
    if (![value.fixture.home.external_id, value.fixture.away.external_id].includes(item.team_id)) fail('Injury team mismatch')
    checkRefs(item.source_ids, ['db', 'web', 'api'])
  }
  if (value.facts.injuries.status === 'available' && value.facts.injuries.data?.length === 0 && value.facts.injuries.reason !== 'confirmed_no_absences') fail('Empty verified injury list needs explicit confirmed_no_absences')
  for (const block of [value.analysis.summary, value.analysis.key_points, value.analysis.ai_prediction]) {
    const rows = Array.isArray(block.data) ? block.data : block.data ? [block.data] : []
    for (const item of rows) {
      checkRefs(item.evidence_ids)
      if (item.evidence_ids.some(ref => !block.source_ids.includes(ref))) fail('Evidence must be included in section sources')
    }
  }
  for (const item of value.external.predictions.data ?? []) checkRefs([item.source_id], ['web'])
  for (const item of value.external.odds.data ?? []) {
    checkRefs([item.source_id], ['web', 'api'])
    if (Date.parse(item.collected_at) >= Date.parse(value.fixture.kickoff_at) || Date.parse(item.collected_at) > Date.parse(value.generated_at)) fail('Odds collection time is not prematch')
  }
})
export type HomePreview = z.infer<typeof homePreviewSchema>
