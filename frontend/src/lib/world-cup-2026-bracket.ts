export type WorldCupSlotKind = 'seed' | 'winner' | 'loser'

export interface WorldCupSlot {
  kind: WorldCupSlotKind
  label: string
  matchNo?: number
}

export interface WorldCupMatchTemplate {
  matchNo: number
  roundLabel: string
  home: WorldCupSlot
  away: WorldCupSlot
}

export interface WorldCupTreeMatch extends WorldCupMatchTemplate {
  children: WorldCupTreeMatch[]
}

export const WORLD_CUP_2026_FINAL_MATCH_NO = 104
export const WORLD_CUP_2026_THIRD_PLACE_MATCH_NO = 103

const seed = (label: string): WorldCupSlot => ({ kind: 'seed', label })
const winner = (matchNo: number): WorldCupSlot => ({ kind: 'winner', label: `W${matchNo}`, matchNo })
const loser = (matchNo: number): WorldCupSlot => ({ kind: 'loser', label: `L${matchNo}`, matchNo })

export const WORLD_CUP_2026_MATCHES: Record<number, WorldCupMatchTemplate> = {
  73: { matchNo: 73, roundLabel: '32강', home: seed('2A'), away: seed('2B') },
  74: { matchNo: 74, roundLabel: '32강', home: seed('1E'), away: seed('3A/B/C/D/F') },
  75: { matchNo: 75, roundLabel: '32강', home: seed('1F'), away: seed('2C') },
  76: { matchNo: 76, roundLabel: '32강', home: seed('1C'), away: seed('2F') },
  77: { matchNo: 77, roundLabel: '32강', home: seed('1I'), away: seed('3C/D/F/G/H') },
  78: { matchNo: 78, roundLabel: '32강', home: seed('2E'), away: seed('2I') },
  79: { matchNo: 79, roundLabel: '32강', home: seed('1A'), away: seed('3C/E/F/H/I') },
  80: { matchNo: 80, roundLabel: '32강', home: seed('1L'), away: seed('3E/H/I/J/K') },
  81: { matchNo: 81, roundLabel: '32강', home: seed('1D'), away: seed('3B/E/F/I/J') },
  82: { matchNo: 82, roundLabel: '32강', home: seed('1G'), away: seed('3A/E/H/I/J') },
  83: { matchNo: 83, roundLabel: '32강', home: seed('2K'), away: seed('2L') },
  84: { matchNo: 84, roundLabel: '32강', home: seed('1H'), away: seed('2J') },
  85: { matchNo: 85, roundLabel: '32강', home: seed('1B'), away: seed('3E/F/G/I/J') },
  86: { matchNo: 86, roundLabel: '32강', home: seed('1J'), away: seed('2H') },
  87: { matchNo: 87, roundLabel: '32강', home: seed('1K'), away: seed('3D/E/I/J/L') },
  88: { matchNo: 88, roundLabel: '32강', home: seed('2D'), away: seed('2G') },
  89: { matchNo: 89, roundLabel: '16강', home: winner(74), away: winner(77) },
  90: { matchNo: 90, roundLabel: '16강', home: winner(73), away: winner(75) },
  91: { matchNo: 91, roundLabel: '16강', home: winner(76), away: winner(78) },
  92: { matchNo: 92, roundLabel: '16강', home: winner(79), away: winner(80) },
  93: { matchNo: 93, roundLabel: '16강', home: winner(83), away: winner(84) },
  94: { matchNo: 94, roundLabel: '16강', home: winner(81), away: winner(82) },
  95: { matchNo: 95, roundLabel: '16강', home: winner(86), away: winner(88) },
  96: { matchNo: 96, roundLabel: '16강', home: winner(85), away: winner(87) },
  97: { matchNo: 97, roundLabel: '8강', home: winner(89), away: winner(90) },
  98: { matchNo: 98, roundLabel: '8강', home: winner(93), away: winner(94) },
  99: { matchNo: 99, roundLabel: '8강', home: winner(91), away: winner(92) },
  100: { matchNo: 100, roundLabel: '8강', home: winner(95), away: winner(96) },
  101: { matchNo: 101, roundLabel: '4강', home: winner(97), away: winner(98) },
  102: { matchNo: 102, roundLabel: '4강', home: winner(99), away: winner(100) },
  103: { matchNo: 103, roundLabel: '3위 결정전', home: loser(101), away: loser(102) },
  104: { matchNo: 104, roundLabel: '결승', home: winner(101), away: winner(102) },
}

export function buildWorldCup2026Tree(matchNo = WORLD_CUP_2026_FINAL_MATCH_NO): WorldCupTreeMatch {
  const match = WORLD_CUP_2026_MATCHES[matchNo]
  if (!match) {
    throw new Error(`Unknown World Cup 2026 match number: ${matchNo}`)
  }

  const children = [match.home, match.away]
    .filter((slot) => slot.kind === 'winner' && slot.matchNo != null)
    .map((slot) => buildWorldCup2026Tree(slot.matchNo as number))

  return { ...match, children }
}

export const WORLD_CUP_2026_TREE = buildWorldCup2026Tree()
export const WORLD_CUP_2026_THIRD_PLACE_MATCH = buildWorldCup2026Tree(WORLD_CUP_2026_THIRD_PLACE_MATCH_NO)
