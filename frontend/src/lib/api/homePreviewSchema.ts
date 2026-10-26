import { z } from 'zod'

const text = z.string().min(1)
const time = z.string().datetime({ offset: true })
const id = z.number().int().positive()
const refs = z.array(text).min(1)
export const publicPreviewReason = z.enum(['not_collected', 'insufficient_sample', 'confirmed_no_absences', 'no_source', 'source_unverified', 'upstream_failed', 'outside_generation_window', 'generation_pending', 'generation_failed', 'refresh_failed', 'kickoff_passed', 'no_valid_snapshot', 'budget_deferred'])
const status = z.enum(['available', 'partial', 'missing', 'unverified', 'error'])
function section<T extends z.ZodTypeAny>(data: T) {
  return z.object({ status, reason: publicPreviewReason.nullable(), as_of: time.nullable(), source_ids: z.array(text), data: data.nullable() }).strict()
}
const team = z.object({ external_id: id, name: text }).strict()
const supportedText = z.object({ text, evidence_ids: refs }).strict()
const point = z.object({ title: text, description: text, evidence_ids: refs }).strict()
const prediction = z.object({ home_goals: z.number().int().min(0).max(30), away_goals: z.number().int().min(0).max(30), confidence: z.enum(['low', 'medium', 'high']), reason: text, evidence_ids: refs }).strict()
const keyAbsence = z.object({ team_id: id, player_id: id, reason: text, evidence_ids: refs }).strict()
const playerFocus = z.enum(['season_contribution', 'scoring_streak', 'assist_streak', 'involvement_streak', 'recent_contribution'])
const playerWatchpoint = z.object({ team_id: id, player_id: id, focus: playerFocus, reason: text.max(1000).optional(), evidence_ids: refs }).strict()
export const homePreviewAnalysisSchema = z.object({ summary: section(supportedText), key_points: section(z.array(point).min(1)), ai_prediction: section(prediction), key_absences: section(z.array(keyAbsence).max(4)).optional(), player_watchpoints: section(z.array(playerWatchpoint).max(4)).optional() }).strict()
export const recentMatchSchema = z.object({ fixture_id: id, kickoff_at: time, opponent: text, competition: text, goals_for: z.number().int().nonnegative(), goals_against: z.number().int().nonnegative(), status: z.enum(['FT', 'AET', 'PEN']), penalties: z.object({ for: z.number().int().nonnegative(), against: z.number().int().nonnegative() }).strict().nullable() }).strict().superRefine((row, ctx) => {
  if (row.status !== 'PEN' && row.penalties !== null) ctx.addIssue({ code: 'custom', message: 'Only PEN can have penalty scores' })
  if (row.penalties && (row.goals_for !== row.goals_against || row.penalties.for === row.penalties.against)) ctx.addIssue({ code: 'custom', message: 'Penalty decision requires a tied match and a non-tied shootout' })
})
const form = z.object({ team_id: id, expected_count: z.literal(5), matches: z.array(recentMatchSchema).max(5) }).strict()
const importance = z.object({ recognition_name: text.optional(), selection_reason: text.optional(), eligible: z.boolean(), recent_games: z.number().int().min(0).max(10), lineup_games: z.number().int().min(0).max(10), player_games: z.number().int().min(0).max(10), recent_starts: z.number().int().nonnegative().nullable(), recent_minutes: z.number().int().nonnegative().nullable(), seasons: z.array(z.object({ season_year: id, appearances: z.number().int().nonnegative().nullable(), minutes: z.number().int().nonnegative().nullable() }).strict()).max(2), source_ids: refs }).strict()
const absenceCause = z.object({ code: z.enum(['hamstring', 'groin', 'thigh', 'knee', 'acl', 'ankle', 'calf', 'achilles', 'muscle', 'hip', 'foot', 'shin', 'shoulder', 'illness', 'red_card', 'yellow_cards']).nullable(), label: text.max(32), occurred_on: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable(), occurred_month: z.string().regex(/^\d{4}-(0[1-9]|1[0-2])$/).nullable() }).strict()
const injury = z.object({ cause: section(absenceCause).optional(), team_id: id, player_id: id.optional(), status_conflict: z.boolean().optional(), importance_evidence: importance.optional(), player_name: text, photo_url: z.string().url().nullable().optional(), availability: z.enum(['out', 'doubtful']), detail: text, impact: text, source_ids: refs }).strict()
const recentPlayerForm = z.object({ team_match_count: z.number().int().min(0).max(10), observed_appearances: z.number().int().min(0).max(10), goals: z.number().int().nonnegative().nullable(), assists: z.number().int().nonnegative().nullable(), minutes: z.number().int().nonnegative().nullable(), goal_samples: z.number().int().min(0).max(10), assist_samples: z.number().int().min(0).max(10), minute_samples: z.number().int().min(0).max(10) }).strict()
const recordNotes = z.object({ recent_contribution: text.nullable().optional(), season_contribution: text.nullable(), scoring_streak: text.nullable(), assist_streak: text.nullable(), involvement_streak: text.nullable() }).strict()
const spotlight = z.object({ team_id: id, player_id: id, player_name: text, photo_url: z.string().url().nullable().optional(), canonical_name: text, competition_name: text.optional(), season_year: id, appearances: z.number().int().nonnegative().nullable(), goals: z.number().int().nonnegative().nullable(), assists: z.number().int().nonnegative().nullable(), minutes: z.number().int().nonnegative().nullable(), recent_form: recentPlayerForm.optional(), recent_match_count: z.number().int().min(0).max(10), scoring_streak: z.number().int().min(0).max(10), assist_streak: z.number().int().min(0).max(10), involvement_streak: z.number().int().min(0).max(10), record_notes: recordNotes, source_ids: refs }).strict()
const externalPrediction = z.object({ source_id: text, outlook: text, summary: text }).strict()
const forecastCoverage = z.object({ target_count: z.literal(3), web_source_count: z.number().int().min(0).max(4), total_source_count: z.number().int().min(0).max(5).optional(), candidate_count: z.number().int().min(0).max(12), checked_at: time.nullable(), reason_codes: z.array(z.enum(['no_verified_source', 'original_unavailable', 'wrong_match', 'unverified_publication', 'unverified_quote', 'unusable_grounding', 'duplicate_publisher', 'budget_reached'])).max(8) }).strict()
const forecastSection = section(z.array(externalPrediction).min(1)).extend({ coverage: forecastCoverage.optional() }).strict()
const odds = z.object({ source_id: text, bookmaker: text, market: z.literal('1x2_90min'), format: z.literal('decimal'), home: z.number().gt(1), draw: z.number().gt(1), away: z.number().gt(1), collected_at: time }).strict()
export const homePreviewSchema = z.object({
  schema_version: z.literal('1.1'), is_mock: z.boolean(), fixture: z.object({ external_id: id, kickoff_at: time, home: team, away: team }).strict(),
  generated_at: time.nullable(), as_of: time,
  search_suggestions: z.object({ provider: z.literal('google'), rendered_content: z.string().min(1).max(32768), queries: z.array(z.string().min(1).max(500)).max(100) }).strict().nullable(),
  search_suggestions_extra: z.array(z.object({ provider: z.literal('google'), rendered_content: z.string().min(1).max(32768), queries: z.array(z.string().min(1).max(500)).max(100) }).strict()).max(1).optional(),
  sources: z.array(z.object({ id: text, fixture_id: id, kind: z.enum(['db', 'web', 'api']), title: text, url: z.string().url().nullable(), published_at: time.nullable(), published_on: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(), retrieved_at: time }).strict()),
  analysis: homePreviewAnalysisSchema,
  facts: z.object({ player_spotlights: section(z.array(spotlight).max(8)).optional(), injuries: section(z.array(injury)), home_form: section(form), away_form: section(form) }).strict(),
  external: z.object({ predictions: forecastSection, odds: section(z.array(odds).min(1)) }).strict(),
}).strict().superRefine((value, context) => {
  const fail = (message: string) => context.addIssue({ code: z.ZodIssueCode.custom, message })
  const clock = value.generated_at ?? value.as_of
  if (value.generated_at === null && Object.values(value.analysis).some(block => block.data !== null)) fail('AI analysis requires an actual generation time')
  const sources = new Map(value.sources.map(source => [source.id, source]))
  if (value.fixture.home.external_id === value.fixture.away.external_id) fail('Fixture teams must differ')
  if (sources.size !== value.sources.length) fail('Duplicate source ID')
  if (Date.parse(value.as_of) > Date.parse(clock)) fail('Data snapshot is newer than generation')
  if (Date.parse(clock) >= Date.parse(value.fixture.kickoff_at)) fail('Prematch generation must precede kickoff')
  for (const source of value.sources) {
    if (source.published_on) {
      const parsed = new Date(source.published_on + 'T00:00:00Z')
      if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0,10) !== source.published_on || source.published_on > source.retrieved_at.slice(0,10)) fail('Invalid publication day')
    }
    if (source.fixture_id !== value.fixture.external_id) fail('Source fixture mismatch')
    if (Date.parse(source.retrieved_at) > Date.parse(clock)) fail('Source retrieved after generation')
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
    if (block.as_of && Date.parse(block.as_of) > Date.parse(clock)) fail('Section snapshot is newer than generation')
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
  const spotlights = value.facts.player_spotlights
  const spotlightIds = new Set<string>()
  for (const player of spotlights?.data ?? []) {
    if (player.photo_url && !/^https?:\/\//.test(player.photo_url)) fail('Photo URL must use HTTP')
    const key = `${player.team_id}:${player.player_id}`
    if (spotlightIds.has(key) || ![value.fixture.home.external_id, value.fixture.away.external_id].includes(player.team_id)) fail('Invalid spotlight player identity')
    spotlightIds.add(key); checkRefs(player.source_ids, ['db'])
    if (player.recent_form) {
      const form = player.recent_form
      if (form.team_match_count !== player.recent_match_count || form.observed_appearances > form.team_match_count) fail('Recent player sample exceeds observed matches')
      for (const [field, sample] of [['goals', 'goal_samples'], ['assists', 'assist_samples'], ['minutes', 'minute_samples']] as const) {
        if (form[sample] > form.observed_appearances || (form[field] === null) !== (form[sample] === 0)) fail('Unknown recent player records must remain null')
      }
    }
    for (const n of [player.scoring_streak, player.assist_streak, player.involvement_streak]) if (n > player.recent_match_count) fail('Streak exceeds observed matches')
    for (const [focus, n] of [['scoring_streak', player.scoring_streak], ['assist_streak', player.assist_streak], ['involvement_streak', player.involvement_streak]] as const) if (player.record_notes[focus] && n < 2) fail('Streak note needs at least two matches')
  }
  const watches = value.analysis.player_watchpoints
  const watched = new Set<string>(); const watchedTeams = new Map<number, number>()
  for (const pick of watches?.data ?? []) {
    const key = `${pick.team_id}:${pick.player_id}`
    const player = spotlights?.data?.find(row => row.team_id === pick.team_id && row.player_id === pick.player_id)
    if (!player || !player.record_notes[pick.focus]) fail('Watchpoint requires a verified player record')
    if (watched.has(key)) fail('Duplicate player watchpoint')
    watched.add(key); watchedTeams.set(pick.team_id, (watchedTeams.get(pick.team_id) ?? 0) + 1)
    if (watchedTeams.get(pick.team_id)! > 2) fail('At most two player watchpoints per team')
    checkRefs(pick.evidence_ids, ['db'])
    if (!pick.evidence_ids.some(ref => player?.source_ids.includes(ref)) || pick.evidence_ids.some(ref => !watches!.source_ids.includes(ref))) fail('Watchpoint requires matching DB evidence')
  }
  const selected = value.analysis.key_absences
  const selectedIds = new Set<string>(); const teamCounts = new Map<number, number>()
  for (const pick of selected?.data ?? []) {
    checkRefs(pick.evidence_ids)
    if (pick.evidence_ids.some(ref => !selected!.source_ids.includes(ref))) fail('Key absence evidence must be included in section sources')
    const key = `${pick.team_id}:${pick.player_id}`
    const candidate = value.facts.injuries.data?.find(row => row.player_id === pick.player_id && row.team_id === pick.team_id)
    if (!candidate?.importance_evidence?.eligible || candidate.status_conflict) fail('Key absence must be an eligible known injury')
    if (selectedIds.has(key)) fail('Duplicate key absence')
    selectedIds.add(key); teamCounts.set(pick.team_id, (teamCounts.get(pick.team_id) ?? 0) + 1)
    if (teamCounts.get(pick.team_id)! > 2) fail('At most two key absences per team')
    if (!pick.evidence_ids.some(ref => candidate?.source_ids.includes(ref)) || !pick.evidence_ids.some(ref => candidate?.importance_evidence?.source_ids.includes(ref))) fail('Key absence needs injury and participation evidence')
  }
  for (const item of value.facts.injuries.data ?? []) {
    if (item.photo_url && !/^https?:\/\//.test(item.photo_url)) fail('Photo URL must use HTTP')
    for (const ref of item.importance_evidence?.source_ids ?? []) if (sources.get(ref)?.kind !== 'db') fail('Participation evidence must reference DB sources')
    if (![value.fixture.home.external_id, value.fixture.away.external_id].includes(item.team_id)) fail('Injury team mismatch')
    checkRefs(item.source_ids, ['db', 'web', 'api'])
    if (item.cause) {
      const cause = item.cause; checkRefs(cause.source_ids, ['web'])
      if (cause.data) {
        if (cause.status !== 'available' || !cause.as_of || !cause.source_ids.length) fail('Verified cause requires original web evidence')
        if (cause.data.occurred_on && cause.data.occurred_month) fail('Cause occurrence must have one precision')
        const occurred = cause.data.occurred_on ?? (cause.data.occurred_month ? `${cause.data.occurred_month}-01` : null)
        if (occurred && (Number.isNaN(Date.parse(occurred)) || Date.parse(occurred) > Date.parse(cause.as_of ?? ''))) fail('Cause occurrence cannot be in the future')
        if (cause.data.occurred_on && new Date(cause.data.occurred_on).toISOString().slice(0, 10) !== cause.data.occurred_on) fail('Invalid cause occurrence date')
      } else if (!['missing', 'unverified', 'error'].includes(cause.status) || !cause.reason) fail('Unverified cause must remain empty')
    }
  }
  if (value.facts.injuries.status === 'available' && value.facts.injuries.data?.length === 0 && value.facts.injuries.reason !== 'confirmed_no_absences') fail('Empty verified injury list needs explicit confirmed_no_absences')
  for (const block of [value.analysis.summary, value.analysis.key_points, value.analysis.ai_prediction]) {
    const rows = Array.isArray(block.data) ? block.data : block.data ? [block.data] : []
    for (const item of rows) {
      checkRefs(item.evidence_ids)
      if (item.evidence_ids.some(ref => !block.source_ids.includes(ref))) fail('Evidence must be included in section sources')
    }
  }
  if (value.external.predictions.coverage) {
    const coverage = value.external.predictions.coverage
    const publishers = new Set((value.external.predictions.data ?? []).map(row => sources.get(row.source_id)).filter(source => source?.kind === 'web' && source.url).map(source => new URL(source!.url!).hostname.replace(/^www\./, '').replace(/^bbc\.co\.uk$/, 'bbc.com')))
    if (coverage.web_source_count !== publishers.size) fail('Forecast coverage must count independent web publishers only')
    const apiCount = (value.external.predictions.data ?? []).some(row => { const source=sources.get(row.source_id); if(source?.kind!=='api'||!source.url)return false; const url=new URL(source.url); return url.hostname==='v3.football.api-sports.io'&&url.pathname==='/predictions' }) ? 1 : 0
    const total = publishers.size + apiCount
    if (coverage.total_source_count !== undefined && coverage.total_source_count !== total) fail('Forecast total coverage mismatch')
    if (total < 3 && value.external.predictions.status === 'available') fail('Three forecast sources required including API-Football')
  }
  for (const item of value.external.predictions.data ?? []) checkRefs([item.source_id], ['web', 'api'])
  for (const item of value.external.odds.data ?? []) {
    checkRefs([item.source_id], ['web', 'api'])
    if (Date.parse(item.collected_at) >= Date.parse(value.fixture.kickoff_at) || Date.parse(item.collected_at) > Date.parse(clock)) fail('Odds collection time is not prematch')
  }
})
export type HomePreview = z.infer<typeof homePreviewSchema>

export function recentMatchResult(row: z.infer<typeof recentMatchSchema>): '승' | '무' | '패' | '?' {
  const score = row.status === 'PEN' ? row.penalties : { for: row.goals_for, against: row.goals_against }
  return score === null ? '?' : score.for > score.against ? '승' : score.for < score.against ? '패' : '무'
}
