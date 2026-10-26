import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSeed } from '../../fixtures/management/data'
import { applyScenario, cancelRun, MockStateError, readState, resetState, saveTarget, saveTranslation, startRun, STORAGE_KEY, translationKey, updateRuns } from '../../fixtures/management/state'
import { managementApi, ManagementApiError } from '@/lib/api/management'
vi.mock('@/lib/api/session',()=>({authenticatedFetch:(...args:Parameters<typeof fetch>)=>fetch(...args)}))
import { retryIds } from '@/components/management/display'

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-24T12:00:00Z'))
  localStorage.clear()
  resetState()
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); localStorage.clear() })

describe('management test fixtures: user operations', () => {
  it('edits an existing target and explicitly clears the limit without duplicating it', () => {
    const state = createSeed()
    expect(state.targets.find((target) => target.id === 3)?.fixture_limit).toBe(10)
    saveTarget(state, { fixture_limit: null }, 3)
    const updated = saveTarget(state, { league_id: 3, season: 2026, include_players: false })
    expect(updated.id).toBe(3)
    expect(updated.fixture_limit).toBeNull()
    expect(state.targets).toHaveLength(6)
    expect(readState().targets.find((target) => target.id === 3)?.include_players).toBe(false)
  })
  it.each([0, -1, 1.5, NaN])('rejects invalid fixture limit %s while preserving settings', (fixture_limit) => {
    const state = createSeed()
    expect(() => saveTarget(state, { fixture_limit }, 3)).toThrow(MockStateError)
    expect(state.targets.find((target) => target.id === 3)?.fixture_limit).toBe(10)
  })
  it('allows the previous actual World Cup season and rejects an arbitrary intervening year', () => {
    const state = createSeed()
    expect(saveTarget(state, { league_id: 1, season: 2022 }).season).toBe(2022)
    expect(() => saveTarget(state, { league_id: 1, season: 2025 })).toThrow('최신 두 개최 시즌')
  })
  it('rejects inactive/missing targets, empty selections and overlapping execution', () => {
    const state = createSeed()
    expect(() => startRun(state, [], 'initial')).toThrow('대상과 실행 방식')
    expect(() => startRun(state, [5], 'initial')).toThrow('비활성')
    expect(() => startRun(state, [999], 'initial')).toThrow('제외된')
    startRun(state, [1], 'initial')
    expect(() => startRun(state, [2], 'refresh')).toThrow('진행 중인 작업')
  })
  it('preserves committed counts and unprocessed counts after cancellation and reload', () => {
    const state = createSeed()
    const run = startRun(state, [1, 2], 'initial')
    vi.advanceTimersByTime(9000)
    updateRuns(state)
    expect(run.items[0].saved).toBeGreaterThan(0)
    const saved = run.items[0].saved
    cancelRun(state, run.id)
    expect(run.status).toBe('cancel_requested')
    vi.advanceTimersByTime(1000)
    updateRuns(state)
    expect(run.status).toBe('cancelled')
    vi.advanceTimersByTime(60_000)
    updateRuns(state)
    const restored = readState().runs.find((entry) => entry.id === run.id)!
    expect(restored.items[0].saved).toBe(saved)
    expect(restored.items[0].pending).toBeGreaterThan(0)
    expect(restored.finished_at).not.toBeNull()
  })
  it('uses an execution-time snapshot and respects a target limit in refresh mode', () => {
    const state = createSeed()
    const run = startRun(state, [3], 'refresh')
    expect(run.items[0].total).toBe(10)
    saveTarget(state, { fixture_limit: null, include_players: false }, 3)
    expect(run.items[0].options).toMatchObject({ fixture_limit: 10, include_players: true })
  })
  it('marks a limited initial collection as partial when a run completes', () => {
    const state = createSeed()
    const run = startRun(state, [3], 'initial')
    vi.advanceTimersByTime(31_000)
    updateRuns(state)
    expect(run.status).toBe('succeeded')
    expect(state.targets.find((target) => target.id === 3)?.initial_status).toBe('일부 적재')
  })
  it.each(['include_details', 'include_players', 'include_standings'] as const)('marks an initial collection with %s omitted as partial', (field) => {
    const state = createSeed()
    saveTarget(state, { [field]: false }, 1)
    startRun(state, [1], 'initial')
    vi.advanceTimersByTime(31_000)
    updateRuns(state)
    expect(state.targets.find((target) => target.id === 1)?.initial_status).toBe('일부 적재')
  })
  it('does not count unsupported cup standings as an omitted supported area', () => {
    const state = createSeed()
    saveTarget(state, { include_players: true }, 4)
    startRun(state, [4], 'initial')
    vi.advanceTimersByTime(31_000)
    updateRuns(state)
    expect(state.targets.find((target) => target.id === 4)?.initial_status).toBe('최초 수집 완료')
  })
  it('selects only failed or unprocessed targets for a retry and links its parent', () => {
    const state = createSeed()
    const source = state.runs.find((run) => run.status === 'partial_failed')!
    expect(retryIds(source)).toEqual([2])
    const retry = startRun(state, retryIds(source), source.mode, source.id)
    expect(retry.items.map((item) => item.target_id)).toEqual([2])
    expect(retry.parent_run_id).toBe(source.id)
  })
  it('stores deliberate empty Korean fields as protected NULL with a before/after history', () => {
    const state = createSeed()
    const original = state.translations[6].original
    const result = saveTranslation(state, 'player', 7, { name_ko: ' ', short_name_ko: '', expected_version: 1 })
    expect(result).toMatchObject({ original, name_ko: null, short_name_ko: null, protected: true, version: 2 })
    expect(state.changes[translationKey(result)][0]).toMatchObject({ before: { name_ko: '부카요 사카' }, after: { name_ko: null } })
  })
  it('returns latest data on a version conflict, then records both explicit edits', () => {
    const state = createSeed()
    applyScenario(state, 'conflict')
    let conflict: MockStateError | null = null
    try { saveTranslation(state, 'player', 7, { name_ko: '내 검수 이름', short_name_ko: '사카', expected_version: 1 }) }
    catch (error) { conflict = error as MockStateError }
    expect(conflict?.status).toBe(409)
    expect(conflict?.current?.version).toBe(2)
    expect(state.translations[6].name_ko).not.toBe('내 검수 이름')
    const reviewed = saveTranslation(state, 'player', 7, { name_ko: '내 검수 이름', short_name_ko: '사카', expected_version: conflict!.current!.version })
    expect(reviewed.version).toBe(3)
    expect(state.changes[translationKey(reviewed)]).toHaveLength(2)
  })
  it('recovers malformed storage and resets only the management namespace', () => {
    localStorage.setItem('authUser', 'preserve-auth')
    localStorage.setItem('mockRole', 'USER')
    localStorage.setItem('theme', 'dark')
    localStorage.setItem(STORAGE_KEY, '{broken')
    expect(readState().targets).toHaveLength(6)
    resetState()
    expect(localStorage.getItem('authUser')).toBe('preserve-auth')
    expect(localStorage.getItem('mockRole')).toBe('USER')
    expect(localStorage.getItem('theme')).toBe('dark')
  })
  it('keeps in-memory changes when storage writes are unavailable', () => {
    const state = readState()
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('storage unavailable') })
    saveTarget(state, { fixture_limit: 5 }, 1)
    expect(readState().targets.find((target) => target.id === 1)?.fixture_limit).toBe(5)
  })
  it('prunes old terminal logs while preserving the current active job', () => {
    const state = createSeed()
    state.runs[0].finished_at = new Date(Date.now() - 8 * 86_400_000).toISOString()
    const oldId = state.runs[0].id
    const active = startRun(state, [1], 'refresh')
    active.created_at = new Date(Date.now() - 8 * 86_400_000).toISOString()
    updateRuns(state)
    expect(state.runs.some((run) => run.id === oldId)).toBe(false)
    expect(state.runs.some((run) => run.id === active.id)).toBe(true)
  })
})

describe('management authenticated API client', () => {
  it('uses the production management endpoint namespace', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ reset: true }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)
    await managementApi.targets()
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/admin/management/targets', expect.objectContaining({ method: 'GET' }))
  })
  it('preserves a conflict response for the editor to compare', async () => {
    const current = { ...createSeed().translations[6], version: 2 }
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ code: 'version_conflict', message: '다른 사용자 수정', current }), { status: 409, headers: { 'Content-Type': 'application/json' } })))
    const promise = managementApi.saveTranslation({ ...current, version: 1 }, '내 수정', '사카')
    await expect(promise).rejects.toMatchObject<Partial<ManagementApiError>>({ status: 409, code: 'version_conflict', current })
  })
})


it('can retry a target cancelled before its collection size was measured', () => {
  const run = createSeed().runs[0]
  run.status = 'cancelled'
  run.items = [{ target_id: 7, name: 'New league', season: 2026, status: 'cancelled', total: 0, saved: 0, failed: 0, pending: 0, total_known: false }]
  expect(retryIds(run)).toEqual([7])
})
