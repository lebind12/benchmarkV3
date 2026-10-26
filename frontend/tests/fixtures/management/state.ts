import { catalog, createSeed, type ManagementState } from './data'
import type { CollectionRun, TranslationEntry, TargetInput, TranslationChange } from '@/lib/api/managementTypes'
export const STORAGE_KEY = 'benchmark:management-mock:v1'
let fallback: ManagementState | null = null
export let persistenceAvailable = true
export class MockStateError extends Error { constructor(public status: number, public code: string, message: string, public current?: TranslationEntry) { super(message) } }
export function readState(): ManagementState {
  if (!persistenceAvailable && fallback) return fallback
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      let value: ManagementState
      try { value = JSON.parse(raw) as ManagementState }
      catch { const seed = createSeed(); writeState(seed); return seed }
      if (value.version === 1 && Array.isArray(value.targets) && Array.isArray(value.runs) && Array.isArray(value.translations) && value.changes && Number.isInteger(value.next_id)) {
        for (const sample of createSeed().translations.filter(row => row.affiliations)) {
          const row = value.translations.find(entry => entry.type === sample.type && entry.id === sample.id)
          if (row && !row.affiliations) row.affiliations = sample.affiliations
        }
        for (const target of value.targets) if (target.logo_url === undefined) target.logo_url = catalog.find(row => row.id === target.league_id)?.logo_url
        // Upgrade only untouched sample log fixtures from the previous preview.
        for (const sample of createSeed().runs) {
          const run = value.runs.find(entry => entry.id === sample.id)
          if (run && !run.logs.some(log => log.code)) run.logs.push(...sample.logs.filter(log => log.code))
        }
        return value
      }
    }
    const seed = createSeed(); writeState(seed); return seed
  } catch { persistenceAvailable = false; return fallback ?? (fallback = createSeed()) }
}
export function writeState(state: ManagementState) { fallback = state; try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); persistenceAvailable = true } catch { persistenceAvailable = false } }
export function resetState() { fallback = null; persistenceAvailable = true; const state = createSeed(); writeState(state); return state }
export const isActiveRun = (run: CollectionRun) => ['queued', 'running', 'cancel_requested'].includes(run.status)
export function updateRuns(state: ManagementState, now = Date.now()) {
  for (const run of state.runs) {
    if (!isActiveRun(run)) continue
    if (run.status === 'cancel_requested') {
      if (now - new Date(run.cancel_requested_at!).getTime() < 700) continue
      run.status = 'cancelled'; run.finished_at = new Date(now).toISOString(); run.stage = '취소 완료'
      for (const item of run.items) item.status = item.pending ? 'cancelled' : 'succeeded'
      run.logs.push({ at: run.finished_at, message: '취소를 완료했습니다. 이미 저장한 데이터는 유지하며 남은 작업은 처리하지 않았습니다.' }); continue
    }
    const progress = Math.min(100, Math.floor((now - new Date(run.started_at).getTime()) / 300))
    run.progress = Math.max(0, progress); run.status = progress < 4 ? 'queued' : 'running'
    const stage = progress < 10 ? '수집 범위 확인' : progress < 35 ? '경기 목록 수집' : progress < 70 ? '경기 상세·선수 통계 수집' : '결과 저장·확인'
    if (stage !== run.stage && progress < 100) run.logs.push({ at: new Date(now).toISOString(), message: stage })
    run.stage = stage
    for (const item of run.items) { item.saved = Math.floor(item.total * progress / 100); item.pending = item.total - item.saved; item.status = progress === 100 ? 'succeeded' : 'running' }
    if (progress === 100) {
      run.status = 'succeeded'; run.finished_at = new Date(now).toISOString(); run.stage = '수집 완료'
      run.logs.push({ at: run.finished_at, message: '선택한 모든 대상의 샘플 수집을 완료했습니다.' })
      for (const item of run.items) {
        const target = state.targets.find((entry) => entry.id === item.target_id)
        if (!target) continue
        target.last_sync = run.finished_at
        if (run.mode === 'initial') {
          const options = item.options
          const supportsStandings = catalog.find((league) => league.id === target.league_id)?.standings
          const partial = options && (options.fixture_limit !== null || !options.include_details || !options.include_players || (supportsStandings && !options.include_standings))
          target.initial_status = !options ? '선택 범위 완료' : partial ? '일부 적재' : '최초 수집 완료'
        }
      }
    }
  }
  state.runs = state.runs.filter((run) => isActiveRun(run) || !run.finished_at || now - new Date(run.finished_at).getTime() <= 7 * 86_400_000)
  writeState(state)
}
export function saveTarget(state: ManagementState, input: Partial<TargetInput>, id?: number) {
  const existing = id ? state.targets.find((target) => target.id === id) : undefined
  if (id && !existing) throw new MockStateError(404, 'target_missing', '이 수집 대상이 더 이상 존재하지 않습니다.')
  const leagueId = input.league_id ?? existing?.league_id
  const season = input.season ?? existing?.season
  const league = catalog.find((entry) => entry.id === leagueId)
  if (!league || !league.seasons.includes(season!)) throw new MockStateError(422, 'invalid_season', '리그의 최신 두 개최 시즌 중 하나를 선택하세요.')
  if (input.fixture_limit != null && (!Number.isInteger(input.fixture_limit) || input.fixture_limit <= 0)) throw new MockStateError(422, 'invalid_limit', '경기 수 제한은 1 이상의 정수로 입력하거나 비워두세요.')
  const duplicate = existing ?? state.targets.find((target) => target.league_id === league.id && target.season === season)
  const row = { ...(duplicate ?? { id: state.next_id++, initial_status: '미수집', last_sync: null, is_active: true, include_details: true, include_players: true, include_standings: league.standings, fixture_limit: null }), ...input, league_id: league.id, season: season!, logo_url: league.logo_url, name: league.name, name_en: league.name_en, country: league.country }
  if (!league.standings) row.include_standings = false
  if (duplicate) state.targets = state.targets.map((target) => target.id === duplicate.id ? row : target)
  else state.targets.push(row)
  writeState(state); return row
}
export function startRun(state: ManagementState, ids: number[], mode: 'initial' | 'refresh', parent: string | null = null) {
  updateRuns(state)
  if (state.runs.some(isActiveRun)) throw new MockStateError(409, 'already_running', '이미 진행 중인 작업이 있습니다. 현재 작업을 확인하세요.')
  if (!ids?.length || !['initial', 'refresh'].includes(mode)) throw new MockStateError(422, 'invalid_run', '수집할 대상과 실행 방식을 선택하세요.')
  const targets = [...new Set(ids)].map((id) => state.targets.find((target) => target.id === id))
  if (targets.some((target) => !target?.is_active)) throw new MockStateError(422, 'inactive_target', '비활성 또는 제외된 대상을 실행할 수 없습니다.')
  const now = new Date().toISOString()
  const items = targets.map((target) => {
    const total = Math.min(target!.fixture_limit ?? Infinity, mode === 'initial' ? 120 : 40)
    return { target_id: target!.id, name: target!.name, season: target!.season, status: 'queued', total, saved: 0, failed: 0, pending: total, options: { include_details: target!.include_details, include_players: target!.include_players, include_standings: target!.include_standings, fixture_limit: target!.fixture_limit } }
  })
  const run: CollectionRun = { id: `mock-${state.next_id++}`, mode, status: 'queued', created_at: now, started_at: now, finished_at: null, cancel_requested_at: null, actor: '스트리머 지민', parent_run_id: parent, progress: 0, stage: '실행 준비', items, logs: [{ at: now, message: `${targets.length}개 대상을 ${mode === 'initial' ? '시즌 전체 최초 수집' : '최근 경기 갱신'}으로 시작했습니다.` }] }
  state.runs.unshift(run); writeState(state); return run
}
export function cancelRun(state: ManagementState, id: string) {
  updateRuns(state); const run = state.runs.find((entry) => entry.id === id)
  if (!run) throw new MockStateError(404, 'run_missing', '작업을 찾을 수 없습니다.')
  if (isActiveRun(run) && run.status !== 'cancel_requested') { run.status = 'cancel_requested'; run.cancel_requested_at = new Date().toISOString(); run.stage = '현재 저장 단위가 끝나면 취소합니다'; run.logs.push({ at: run.cancel_requested_at, message: '취소를 요청했습니다. 이미 저장된 데이터는 유지합니다.' }) }
  writeState(state); return run
}
export function translationKey(row: TranslationEntry) { return `${row.type}:${row.id}` }
export function saveTranslation(state: ManagementState, type: string, id: number, input: { name_ko: string | null; short_name_ko: string | null; expected_version: number }) {
  const row = state.translations.find((entry) => entry.type === type && entry.id === id)
  if (!row) throw new MockStateError(404, 'translation_missing', '번역 항목을 찾을 수 없습니다.')
  if (state.scenario === 'conflict') {
    const before = { name_ko: row.name_ko, short_name_ko: row.short_name_ko }
    row.name_ko = `${row.name_ko ?? row.original} (검수 수정)`; row.version++; row.editor = '관리자 민수'; row.updated_at = new Date().toISOString(); row.protected = true
    const key = translationKey(row)
    state.changes[key] = [{ version: row.version, editor: row.editor, at: row.updated_at, before, after: { name_ko: row.name_ko, short_name_ko: row.short_name_ko } }, ...(state.changes[key] ?? [])]
    state.scenario = 'normal'; writeState(state)
  }
  if (input.expected_version !== row.version) throw new MockStateError(409, 'version_conflict', '다른 사용자가 먼저 수정했습니다. 최신값과 내 입력을 비교해 주세요.', { ...row })
  const clean = (value: string | null) => value?.trim() || null
  if ((input.name_ko?.length ?? 0) > 80 || (input.short_name_ko?.length ?? 0) > 40) throw new MockStateError(422, 'name_too_long', '이름은 80자, 짧은 이름은 40자 이내로 입력하세요.')
  const before = { name_ko: row.name_ko, short_name_ko: row.short_name_ko }
  row.name_ko = clean(input.name_ko); row.short_name_ko = clean(input.short_name_ko); row.protected = true; row.version++; row.editor = '스트리머 지민'; row.updated_at = new Date().toISOString()
  const change: TranslationChange = { version: row.version, editor: row.editor, at: row.updated_at, before, after: { name_ko: row.name_ko, short_name_ko: row.short_name_ko } }
  const key = translationKey(row); state.changes[key] = [change, ...(state.changes[key] ?? [])]; writeState(state); return row
}
export function applyScenario(state: ManagementState, scenario: string) {
  state.scenario = scenario
  if (scenario === 'partial_failed' || scenario === 'interrupted') {
    updateRuns(state)
    let run = state.runs.find(isActiveRun)
    if (!run) { const ids = state.targets.filter((target) => target.is_active).slice(0, 2).map((target) => target.id); if (ids.length) run = startRun(state, ids, 'initial') }
    if (run) { run.status = scenario; run.progress = scenario === 'partial_failed' ? 100 : 42; run.stage = scenario === 'partial_failed' ? '일부 대상 수집 실패' : '작업 중단'; run.finished_at = new Date().toISOString(); run.items.forEach((item, i) => { item.saved = i === 0 ? item.total : Math.floor(item.total * .4); item.failed = i === 0 || scenario === 'interrupted' ? 0 : 3; item.pending = item.total - item.saved - item.failed; item.status = i === 0 ? 'succeeded' : scenario }); if (scenario === 'partial_failed') run.logs.push({ at: run.finished_at, code: 'API_TIMEOUT', level: 'error', target_id: run.items.at(-1)?.target_id, stage: '경기 상세', attempt: 3, max_attempts: 3, message: 'ReadTimeout: retries exhausted for /fixtures/events' }); run.logs.push({ at: run.finished_at, message: scenario === 'partial_failed' ? '일부 대상의 응답을 받지 못했습니다. 저장된 데이터는 보존했습니다.' : '작업 중단 샘플입니다. 저장한 데이터를 유지하며 안전하게 다시 실행할 수 있습니다.' }) }
    state.scenario = 'normal'
  }
  writeState(state)
}
