/**
 * 경기 선택 화면 검사 (MP-03).
 *
 * 이 파일이 확인하는 것:
 * - 목록은 저장된 자료만 읽고, 화면을 여는 것만으로 수집(POST)을 부르지 않는다.
 * - 외부 경기 ID와 저장 행 ID를 구분해 표시한다.
 * - 저장된 자료 읽기 권한이 없으면 빈 목록이 아니라 필요한 SELECT 경계를 보여준다.
 * - 목록 수집 결과의 실행 방식(mock/replay/live)을 함께 표시한다.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import FixtureSelector from '@/features/match-preview/FixtureSelector.vue'

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function candidate(overrides: Record<string, unknown> = {}) {
  return {
    fixture_id: 1200001,
    league_id: 39,
    league_name: 'Recorded Premier League',
    season: 2026,
    home_team_id: 50,
    home_team_name: 'Recorded Home',
    away_team_id: 49,
    away_team_name: 'Recorded Away',
    label: 'Recorded Home vs Recorded Away',
    kickoff_at: '2026-11-12T20:00:00+00:00',
    status_short: 'NS',
    origin: 'stored_db',
    origin_note: '기존 DB에 저장된 경기 자료를 읽기 전용으로 표시합니다. 새 수집이 아닙니다.',
    run_id: null,
    mode: null,
    selectable: true,
    ...overrides,
  }
}

function listPayload(overrides: Record<string, unknown> = {}) {
  return {
    fixtures: [candidate()],
    sources: [
      { origin: 'stored_db', label: '기존 DB 저장 경기 (읽기 전용)', count: 1, external_calls: 0 },
    ],
    stored_access: {
      readable: true,
      role: 'preview_reader',
      tables: { 'public.fixture': true },
      missing: [],
      required: [],
      detail: null,
    },
    note: '이 목록은 저장된 자료만 읽습니다. 화면을 열어도 새 외부 수집이 일어나지 않습니다.',
    external_calls: 0,
    ...overrides,
  }
}

describe('FixtureSelector', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('reads stored fixtures with GET only and never fetches on open', async () => {
    fetchMock.mockResolvedValueOnce(json(listPayload()))

    const wrapper = mount(FixtureSelector)
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [, init] = fetchMock.mock.calls[0]
    expect((init as RequestInit | undefined)?.method ?? 'GET').toBe('GET')
    expect(wrapper.findAll('[data-test="fixture-row"]')).toHaveLength(1)
    expect(wrapper.get('[data-test="fixture-row"]').text()).toContain('Recorded Home vs Recorded Away')
  })

  it('shows both the external fixture id and the stored origin', async () => {
    fetchMock.mockResolvedValueOnce(json(listPayload()))
    const wrapper = mount(FixtureSelector)
    await flushPromises()

    const row = wrapper.get('[data-test="fixture-row"]').text()
    expect(row).toContain('fixture_id 1200001')
    expect(row).toContain('기존 DB 저장 경기')
  })

  it('shows the required SELECT boundary when stored reads are not permitted', async () => {
    fetchMock.mockResolvedValueOnce(
      json(
        listPayload({
          fixtures: [],
          sources: [],
          stored_access: {
            readable: false,
            role: 'preview_dev_identity_ro',
            tables: { 'public.fixture': false },
            missing: ['public.fixture', 'public.injury'],
            required: ['SELECT ON public.fixture', 'SELECT ON public.injury'],
            detail: '권한 없는 표',
          },
        }),
      ),
    )

    const wrapper = mount(FixtureSelector)
    await flushPromises()

    const blocked = wrapper.get('[data-test="access-blocked"]').text()
    expect(blocked).toContain('SELECT ON public.fixture')
    expect(blocked).toContain('SELECT ON public.injury')
    // 권한이 없을 때 빈 목록을 "경기 없음"으로 단정하지 않는다.
    expect(wrapper.find('[data-test="no-fixtures"]').exists()).toBe(true)
  })

  it('does not call import unless the admin presses the explicit button', async () => {
    fetchMock.mockResolvedValueOnce(json(listPayload()))
    const wrapper = mount(FixtureSelector)
    await flushPromises()

    // 여는 것만으로는 GET 한 번뿐이다. 수집(POST)은 관리자의 명시적 동작이다.
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-test="import-fixtures"]').exists()).toBe(true)

    fetchMock
      .mockResolvedValueOnce(
        json({
          run_id: '33333333-3333-4333-8333-333333333333',
          module_execution_id: '44444444-4444-4444-8444-444444444444',
          result_id: '55555555-5555-4555-8555-555555555555',
          fixtures: [candidate({ origin: 'catalog_import', mode: 'live' })],
          mode: 'live',
          status: 'succeeded',
          provider_calls: 1,
          external_calls: 1,
          coverage: [{ topic: '경기 목록', state: 'available', detail: '1건' }],
          diagnostics: [],
        }),
      )
      .mockResolvedValueOnce(json(listPayload()))

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    const posts = fetchMock.mock.calls.filter(
      ([, init]) => (init as RequestInit | undefined)?.method === 'POST',
    )
    expect(posts).toHaveLength(1)
    expect(String(posts[0][0])).toContain('/fixtures/import')

    const resultText = wrapper.get('[data-test="import-result"]').text()
    expect(resultText).toContain('실호출 (live)')
    expect(resultText).toContain('외부 호출 1회')
    expect(resultText).toContain('실행기 호출 1회')
  })

  it('labels a mock catalog import as mock, not live', async () => {
    fetchMock.mockResolvedValueOnce(json(listPayload({ fixtures: [] })))
    const wrapper = mount(FixtureSelector)
    await flushPromises()

    fetchMock
      .mockResolvedValueOnce(
        json({
          run_id: '33333333-3333-4333-8333-333333333333',
          module_execution_id: '44444444-4444-4444-8444-444444444444',
          result_id: '55555555-5555-4555-8555-555555555555',
          fixtures: [candidate({ origin: 'catalog_import', mode: 'mock' })],
          mode: 'mock',
          status: 'succeeded',
          provider_calls: 1,
          external_calls: 0,
          coverage: [],
          diagnostics: [],
        }),
      )
      .mockResolvedValueOnce(json(listPayload()))

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    const resultText = wrapper.get('[data-test="import-result"]').text()
    expect(resultText).toContain('모의 실행 (mock, 외부 호출 없음)')
    expect(resultText).not.toContain('실호출 (live)')
  })

  it('reports an unregistered route instead of pretending the list is empty', async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: 'Not Found' }, 404))

    const wrapper = mount(FixtureSelector)
    await flushPromises()

    expect(wrapper.text()).toContain('아직 서버에 연결되지 않았습니다')
  })

  it('reports the selected fixture to its parent with the external id', async () => {
    fetchMock.mockResolvedValueOnce(json(listPayload()))
    const onSelect = vi.fn()
    const wrapper = mount(FixtureSelector, { props: { onSelect } })
    await flushPromises()

    await wrapper.get('[data-test="select-fixture"]').trigger('click')

    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(onSelect.mock.calls[0][0].fixture_id).toBe(1200001)
  })

  it('disables selection for a fixture whose teams are not confirmed', async () => {
    fetchMock.mockResolvedValueOnce(
      json(
        listPayload({
          fixtures: [
            candidate({ fixture_id: 1200003, home_team_id: null, away_team_id: null, selectable: false }),
          ],
        }),
      ),
    )
    const wrapper = mount(FixtureSelector)
    await flushPromises()

    const button = wrapper.get('[data-test="select-fixture"]')
    expect(button.attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="fixture-row"]').text()).toContain('팀 미확정')
  })
})
