import {
  WORLD_CUP_2026_MATCHES,
  WORLD_CUP_2026_THIRD_PLACE_MATCH,
  WORLD_CUP_2026_TREE,
} from '@/lib/world-cup-2026-bracket'

function collectLeaves(match: typeof WORLD_CUP_2026_TREE): number[] {
  if (match.children.length === 0) return [match.matchNo]
  return match.children.flatMap((child) => collectLeaves(child))
}

describe('world cup 2026 bracket template', () => {
  it('builds the championship tree from the final down to round-of-32 leaves', () => {
    expect(WORLD_CUP_2026_TREE.matchNo).toBe(104)
    expect(WORLD_CUP_2026_TREE.children.map((child) => child.matchNo)).toEqual([101, 102])
    expect(collectLeaves(WORLD_CUP_2026_TREE)).toEqual([
      74, 77, 73, 75, 83, 84, 81, 82, 76, 78, 79, 80, 86, 88, 85, 87,
    ])
  })

  it('keeps FIFA seed slots on round-of-32 fixtures', () => {
    expect(WORLD_CUP_2026_MATCHES[74].home.label).toBe('1E')
    expect(WORLD_CUP_2026_MATCHES[74].away.label).toBe('3A/B/C/D/F')
    expect(WORLD_CUP_2026_MATCHES[87].home.label).toBe('1K')
    expect(WORLD_CUP_2026_MATCHES[87].away.label).toBe('3D/E/I/J/L')
  })

  it('keeps the third-place match as a separate loser path', () => {
    expect(WORLD_CUP_2026_THIRD_PLACE_MATCH.matchNo).toBe(103)
    expect(WORLD_CUP_2026_THIRD_PLACE_MATCH.home.label).toBe('L101')
    expect(WORLD_CUP_2026_THIRD_PLACE_MATCH.away.label).toBe('L102')
    expect(WORLD_CUP_2026_THIRD_PLACE_MATCH.children).toEqual([])
  })
})
