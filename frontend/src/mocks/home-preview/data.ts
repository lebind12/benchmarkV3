export type Team = { id: number; name: string; english: string; color: string }
export type Match = {
  id: number; home: Team; away: Team; league: string; competitionType?: 'domestic_cup';
  round: string; day: string; time: string; state: 'ongoing' | 'scheduled' | 'finished';
  score?: string; preview: 'ready' | 'partial' | 'pending' | 'failed' | 'previous' | 'unavailable';
}
export const sampleDay = '2026-10-25'
export const teams: Record<string, Team> = {
  arsenal: { id: 42, name: '아스널', english: 'Arsenal', color: '#d71920' },
  liverpool: { id: 40, name: '리버풀', english: 'Liverpool', color: '#c8102e' },
  city: { id: 50, name: '맨체스터 시티', english: 'Manchester City', color: '#6cabdd' },
  chelsea: { id: 49, name: '첼시', english: 'Chelsea', color: '#034694' },
  united: { id: 33, name: '맨체스터 유나이티드', english: 'Manchester United', color: '#da291c' },
  spurs: { id: 47, name: '토트넘', english: 'Tottenham Hotspur', color: '#132257' },
  brighton: { id: 51, name: '브라이턴', english: 'Brighton', color: '#0057b8' },
  villa: { id: 66, name: '애스턴 빌라', english: 'Aston Villa', color: '#670e36' },
  bayern: { id: 157, name: '바이에른 뮌헨', english: 'Bayern Munich', color: '#dc052d' },
  inter: { id: 505, name: '인터 밀란', english: 'Inter Milan', color: '#0068a8' },
}
const t = teams as Record<string, Team>
export const sampleMatches: Match[] = [
  { id: 90001, home: t.arsenal!, away: t.liverpool!, league: 'EPL', round: '샘플 라운드', day: sampleDay, time: '22:00', state: 'scheduled', preview: 'ready' },
  { id: 90002, home: t.city!, away: t.chelsea!, league: 'EPL', round: '샘플 라운드', day: sampleDay, time: '19:00', state: 'ongoing', preview: 'partial' },
  { id: 90003, home: t.brighton!, away: t.villa!, league: 'EPL', round: '샘플 라운드', day: sampleDay, time: '23:00', state: 'scheduled', preview: 'pending' },
  { id: 90004, home: t.liverpool!, away: t.bayern!, league: 'UCL', round: '8강', day: sampleDay, time: '21:00', state: 'scheduled', preview: 'previous' },
  { id: 90005, home: t.bayern!, away: t.inter!, league: 'UCL', round: '결승', day: sampleDay, time: '20:00', state: 'scheduled', preview: 'ready' },
  { id: 90006, home: t.inter!, away: t.bayern!, league: 'UCL', round: '4강', day: sampleDay, time: '18:00', state: 'scheduled', preview: 'partial' },
  { id: 90007, home: t.brighton!, away: t.inter!, league: 'UEL', round: '결승', day: sampleDay, time: '18:00', state: 'scheduled', preview: 'failed' },
  { id: 90008, home: t.united!, away: t.villa!, league: 'FA컵', round: '4강', day: sampleDay, time: '18:00', state: 'scheduled', preview: 'ready' },
  { id: 90009, home: t.inter!, away: t.bayern!, league: 'UCL', round: '8강', day: sampleDay, time: '18:00', state: 'scheduled', preview: 'ready' },
  { id: 90010, home: t.spurs!, away: t.united!, league: 'EPL', round: '샘플 라운드', day: sampleDay, time: '16:00', state: 'finished', score: '2 : 1', preview: 'ready' },
  { id: 90011, home: t.arsenal!, away: t.chelsea!, league: 'EPL', round: '샘플 라운드', day: '2026-10-27', time: '04:00', state: 'scheduled', preview: 'unavailable' },
]
const bigSix = new Set([40, 50, 33, 47, 49, 42])
export function rank(match: Match): number {
  const big = bigSix.has(match.home.id) || bigSix.has(match.away.id)
  if (['FA컵', '카라바오컵'].includes(match.league) && !['4강', '준결승', '결승', 'semi-finals', 'semi-final', 'semifinals', 'final'].includes(match.round.toLowerCase().trim().split(' - ')[0]!)) return Infinity
  if (match.league === 'EPL') return big ? 1 : 2
  if (match.league === 'UCL' && ['8강', '4강', '결승'].includes(match.round) && big) return 3
  if (match.league === 'UCL' && match.round === '결승') return 4
  if (match.league === 'UCL' && match.round === '4강') return 5
  if (match.league === 'UEL' && match.round === '결승' && !big) return 6
  if ((match.league === 'UEL' || match.league === 'FA컵' || match.league === '카라바오컵' || match.competitionType === 'domestic_cup') && big) return 7
  if (match.league === 'UCL' && match.round === '8강') return 8
  return Infinity
}
export function recommendationReason(match: Match): string {
  return ['', '빅6 EPL 경기', '프리미어리그', '빅6 챔피언스리그', '챔피언스리그 결승', '챔피언스리그 4강', '유로파리그 결승', '빅6 컵대회', '챔피언스리그 8강'][rank(match)] ?? ''
}
export function selectRecommendations(matches: Match[], day: string) {
  const unique = [...new Map(matches.map(m => [m.id, m])).values()]
  const eligible = unique.filter(m => m.state !== 'finished' && Number.isFinite(rank(m)))
  const today = eligible.filter(m => m.day === day)
  const nextDay = today.length ? day : eligible.filter(m => m.day > day && m.state === 'scheduled').map(m => m.day).sort()[0]
  const selected = today.length ? today : eligible.filter(m => m.day === nextDay && m.state === 'scheduled')
  return {
    day: nextDay ?? day,
    matches: selected.sort((a, b) => Number(b.state === 'ongoing') - Number(a.state === 'ongoing') || rank(a) - rank(b) || a.time.localeCompare(b.time) || a.id - b.id),
    results: unique.filter(m => m.day === day && m.state === 'finished').sort((a, b) => a.time.localeCompare(b.time)),
  }
}
