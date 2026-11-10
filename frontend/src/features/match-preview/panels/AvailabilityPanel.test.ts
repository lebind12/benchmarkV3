/**
 * R2 부상·결장 패널 검사 (MP-06).
 *
 * 이 파일이 확인하는 것:
 * - API 원문 표기와 정규화 상태를 따로 보여주고, 출전 불확실을 결장 확정으로 쓰지 않는다.
 * - 빈 부상 응답을 "부상자 없음"으로 표시하지 않고 서버가 준 상태 문장을 그대로 쓴다.
 * - 상충 자료를 숨기지 않고 양쪽을 함께 보여준다.
 * - 근거 없는 영향 해석은 채택 목록에 넣지 않는다.
 * - 검색 출처가 없으면 그 사실을 진단 영역에만 적는다.
 * - 이름이 없으면 식별자만 쓰고 선수 이름을 만들지 않는다.
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import AvailabilityPanel from '@/features/match-preview/panels/AvailabilityPanel.vue'
import type { AvailabilityR2ResultView } from '@/features/match-preview/panels/AvailabilityPanel.vue'

function r2(overrides: Partial<AvailabilityR2ResultView> = {}): AvailabilityR2ResultView {
  return {
    module_id: 'R2',
    implementation_version: 'mp06-r2-1',
    prompt_version: 'mp06-r2-prompt-1',
    mode: 'mock',
    attempt_count: 1,
    status: 'succeeded',
    quality: 'ready',
    claims: [
      {
        claim_id: 'r2-api-7101',
        kind: 'fact',
        text: 'API 부상 자료: 선수 7101 표기 Questionable, 사유 Knock',
        decision: 'adopted',
        decision_reason: '출전 불확실 표기를 그대로 보존했습니다. 결장 확정이 아닙니다.',
        source_url: null,
      },
      {
        claim_id: 'r2-impact-0',
        kind: 'ai_interpretation',
        text: '교체 자원 운용이 경기 당일 결정될 수 있습니다.',
        decision: 'adopted',
        decision_reason: '근거가 연결된 해석입니다: api:injury-7101',
        source_url: null,
      },
    ],
    coverage: [
      { topic: '부상·출전 불확실 API', state: 'available', detail: '3건' },
      { topic: '부상 맥락 검색', state: 'search_not_found', detail: '이번 호출에서 검색 출처가 비어 있습니다.' },
    ],
    research: {
      material_state: 'available',
      material_detail: '3건(불확실 포함)',
      facts: [
        {
          evidence_id: 'api:injury-7101',
          player_id: 7101,
          player_name: null,
          team_id: 50,
          type_marker: 'Questionable',
          reason: 'Knock - 75% chance of playing',
          uncertainty: 'uncertain',
          expected_status: 'doubtful',
          collected_at: '2026-11-10T16:00:00+00:00',
          snapshot_id: '11111111-1111-4111-8111-111111111111',
          adopted: true,
        },
        {
          evidence_id: 'api:injury-7103',
          player_id: 7103,
          player_name: null,
          team_id: 50,
          type_marker: null,
          reason: null,
          uncertainty: 'unknown',
          expected_status: 'unknown',
          collected_at: '2026-11-10T16:00:00+00:00',
          snapshot_id: '22222222-2222-4222-8222-222222222222',
          adopted: false,
        },
      ],
      player_updates: [
        {
          player_id: 7101,
          player_name: 'Recorded Doubtful',
          team_id: 50,
          status: 'doubtful',
          summary: '최근 훈련에 부분 참여했고 출전 여부는 경기 전 결정됩니다.',
          evidence: ['api:injury-7101'],
          conflict: false,
          api_status: 'doubtful',
        },
      ],
      reported_absences: [],
      impacts: [
        {
          team_id: 50,
          summary: '출전이 불확실한 선수의 자리는 경기 전까지 확정되지 않습니다.',
          basis: ['api:injury-7101'],
        },
      ],
      uncertainties: ['출전 불확실 선수의 최종 명단은 킥오프 전에 확정됩니다.'],
      search_note: null,
      rejected: [],
      grounding: {
        available: false,
        sources: [],
        queries: [],
        supports: [],
        search_entry_point: null,
      },
      search_snapshot_id: null,
      team_names: { '50': 'Recorded Home', '49': 'Recorded Away' },
      fixture_label: 'Recorded Home vs Recorded Away',
    },
    raw_grounding: {
      available: false,
      sources: [],
      queries: [],
      supports: [],
      search_entry_point: null,
    },
    model_text: null,
    ...overrides,
  }
}

describe('AvailabilityPanel', () => {
  it('keeps the API marker and normalized status apart and never calls doubtful an absence', () => {
    const wrapper = mount(AvailabilityPanel, { props: { result: r2() } })

    const facts = wrapper.get('[data-test="r2-facts"]').text()
    expect(facts).toContain('Questionable')
    expect(facts).toContain('출전 불확실')
    expect(facts).toContain('Knock - 75% chance of playing')

    const updates = wrapper.get('[data-test="r2-updates"]').text()
    expect(updates).toContain('출전 불확실')
    expect(updates).not.toContain('결장(확정 표기)')
    // 표기가 없는 행은 확정 사실로 채택하지 않았다고 남긴다.
    expect(facts).toContain('확정 사실로 채택하지 않음')
  })

  it('never prints an empty injury response as "no injuries"', () => {
    const empty = r2({
      research: {
        ...r2().research,
        material_state: 'empty_response',
        material_detail:
          "부상 응답이 비어 있습니다. 이는 '부상자 없음'의 증거가 아니며, 자료 없음(미확보)으로 기록합니다.",
        facts: [],
        player_updates: [],
        impacts: [],
      },
      coverage: [{ topic: '부상·출전 불확실 API', state: 'unknown', detail: '증거가 아닙니다.' }],
    })
    const wrapper = mount(AvailabilityPanel, { props: { result: empty } })

    const state = wrapper.get('[data-test="r2-material-state"]').text()
    expect(state).toContain('부상 항목 비어 있음')
    expect(state).toContain('부상자 0명의 증거 아님')
    expect(wrapper.get('[data-test="r2-no-facts"]').text()).toContain(
      "이는 '부상자 없음'의 증거가 아닙니다",
    )
    expect(wrapper.get('[data-test="r2-no-updates"]').text()).toContain('본문을 만들지 않습니다')
    expect(wrapper.text()).not.toContain('부상자 0명입니다')
  })

  it('shows both sides of a conflicting report instead of hiding one', () => {
    const conflicted = r2()
    conflicted.research.player_updates = [
      {
        player_id: 7101,
        player_name: 'Recorded Doubtful',
        team_id: 50,
        status: 'confirmed_absence',
        summary: '현지 보도는 이번 경기 결장으로 전했습니다.',
        evidence: ['api:injury-7101', 'https://recorded.example.test/home-team-news'],
        conflict: true,
        api_status: 'doubtful',
      },
    ]
    const wrapper = mount(AvailabilityPanel, { props: { result: conflicted } })

    const conflict = wrapper.get('[data-test="r2-conflict"]').text()
    expect(conflict).toContain('출전 불확실')
    expect(conflict).toContain('양쪽을 함께 보존했습니다')
    expect(wrapper.get('[data-test="r2-conflict-details"]').text()).toContain('Recorded Doubtful')
    // API 사실 자체도 화면에 남아 있다.
    expect(wrapper.get('[data-test="r2-facts"]').text()).toContain('Questionable')
  })

  it('does not list impact interpretations that have no basis', () => {
    const noImpact = r2()
    noImpact.research.impacts = []
    noImpact.research.rejected = ['impact[0]: 근거가 연결되지 않은 영향 해석을 채택하지 않았습니다.']
    const wrapper = mount(AvailabilityPanel, { props: { result: noImpact } })

    expect(wrapper.get('[data-test="r2-no-impacts"]').text()).toContain('근거 없는 해석은 채택하지 않았습니다')
    expect(wrapper.get('[data-test="r2-rejected"]').text()).toContain('근거가 연결되지 않은 영향 해석')
  })

  it('marks missing search sources as diagnostics, not as body text', () => {
    const wrapper = mount(AvailabilityPanel, { props: { result: r2() } })

    expect(wrapper.get('[data-test="r2-no-sources"]').text()).toContain('grounding 출처가 비어 있습니다')
    expect(wrapper.get('[data-test="r2-no-sources"]').text()).toContain(
      '독자용 본문에는 이 안내를 넣지 않습니다',
    )
    // 검색 스냅샷이 없으면 링크 목록을 만들지 않는다.
    expect(wrapper.find('[data-test="r2-sources"]').exists()).toBe(false)
  })

  it('renders grounding sources and search suggestions without executing them', () => {
    const withSearch = r2()
    withSearch.research.grounding = {
      available: true,
      sources: [
        { uri: 'https://recorded.example.test/home-team-news', title: 'Recorded Home team news', domain: 'recorded.example.test' },
      ],
      queries: ['Recorded Home Recorded Away team news'],
      supports: [{ groundingChunkIndices: [0] }],
      search_entry_point: {
        rendered_content: '<div class="recorded-suggestions">검색 제안</div>',
        sdk_blob: 'UkVDT1JERUQ=',
      },
    }
    const wrapper = mount(AvailabilityPanel, { props: { result: withSearch } })

    const sources = wrapper.get('[data-test="r2-sources"]').text()
    expect(sources).toContain('https://recorded.example.test/home-team-news')
    expect(wrapper.get('[data-test="r2-queries"]').text()).toContain('Recorded Home Recorded Away')

    const frame = wrapper.get('[data-test="r2-suggestions"] iframe')
    // 제공된 HTML을 그대로 넣되, 스크립트 실행이 없는 sandbox다.
    expect(frame.attributes('srcdoc')).toContain('recorded-suggestions')
    expect(frame.attributes('sandbox')).toBe('')
    expect(frame.attributes('referrerpolicy')).toBe('no-referrer')
  })

  it('labels a stored row without a name by identifier only', () => {
    const wrapper = mount(AvailabilityPanel, { props: { result: r2() } })

    const facts = wrapper.get('[data-test="r2-facts"]').text()
    expect(facts).toContain('선수 ID 7101')
    expect(facts).toContain('선수 ID 7103')
    // 이름을 만들어 넣지 않는다.
    expect(facts).not.toContain('Unknown Player')
  })

  it('shows the run mode and empty states honestly', () => {
    const wrapper = mount(AvailabilityPanel, { props: { result: r2({ mode: 'live', attempt_count: 1 }) } })
    expect(wrapper.get('[data-test="r2-mode"]').text()).toContain('실호출')
    expect(wrapper.get('[data-test="r2-attempts"]').text()).toContain('1회')

    const mock = mount(AvailabilityPanel, { props: { result: r2() } })
    expect(mock.get('[data-test="r2-mode"]').text()).toContain('모의 실행')

    const empty = mount(AvailabilityPanel, { props: { result: null } })
    expect(empty.get('[data-test="r2-empty"]').text()).toContain('아직 R2 조사 결과가 없습니다')

    const failed = mount(AvailabilityPanel, { props: { result: null, errorMessage: '읽기 실패' } })
    expect(failed.get('[data-test="r2-error"]').text()).toBe('읽기 실패')
  })
})
