import { homeRecommendationsSchema } from '@/lib/api/homeRecommendationsSchema'
import { selectRecommendations, rank, recommendationReason, type Match } from './data'
import { buildMockPreview } from './preview'
import { buildMockResponse } from './response'

const asOf = '2026-10-25T10:20:00Z'
function fixture(match: Match) {
  const identity = match.league === 'EPL' ? [39, 'epl'] : match.league === 'UCL' ? [2, 'ucl'] : match.league === 'UEL' ? [3, 'uel'] : match.league === '카라바오컵' ? [48, 'domestic_cup'] : [45, 'domestic_cup']
  return { fixture_id: match.id, kickoff_at: `${match.day}T${match.time}:00+09:00`, status_as_of: asOf,
    competition: { external_id: identity[0], category: identity[1], name: match.league, round: match.round },
    home: { external_id: match.home.id, name: match.home.name }, away: { external_id: match.away.id, name: match.away.name } }
}
export function buildMockRecommendations(matches: Match[], date: string) {
  const selected = selectRecommendations(matches, date)
  const response = homeRecommendationsSchema.parse({
    schema_version: '1.0', requested_date: date, display_date: selected.day, timezone: 'Asia/Seoul', as_of: asOf,
    policy_version: 'home-priority-2026-10-25', fallback_reason: selected.day !== date ? 'no_eligible_today' : null,
    items: selected.matches.map(match => {
      const saved = ['ready', 'partial', 'previous'].includes(match.preview) ? buildMockPreview(match, match.preview) : null
      const publication = buildMockResponse(match, match.preview, saved).publication
      return { ...fixture(match), state: match.state, priority: rank(match), reason: recommendationReason(match),
        preview: { state: publication.state, served: publication.served, generated_at: publication.generated_at, as_of: publication.as_of } }
    }),
    today_results: selected.results.map(match => {
      const [home, away] = match.score!.split(' : ').map(Number)
      return { ...fixture(match), state: 'finished', goals_home: home, goals_away: away }
    }),
  })
  return { response, day: response.display_date, matches: response.items.map(row => selected.matches.find(match => match.id === row.fixture_id)!), results: selected.results }
}
