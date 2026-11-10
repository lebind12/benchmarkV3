/**
 * D0 자료 패널 검사 (MP-03).
 *
 * 이 파일이 확인하는 것:
 * - 빈 부상 응답을 "부상자 없음"으로 표시하지 않고 서버가 준 상태·사유를 그대로 쓴다.
 * - 실행 성공과 근거 확보를 따로 보여준다.
 * - 실행 방식(mock/replay/live)과 자료 출처(api/search)를 다른 축으로 표시한다.
 * - 스냅샷마다 수집 시각과 원문 참조를 함께 보여준다.
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import DataPanel from '@/features/match-preview/panels/DataPanel.vue'
import type { D0ResultView } from '@/features/match-preview/fixtures'

function d0(overrides: Partial<D0ResultView> = {}): D0ResultView {
  return {
    result: {
      result_id: '66666666-6666-4666-8666-666666666666',
      module_id: 'D0',
      module_execution_id: '77777777-7777-4777-8777-777777777777',
      run_id: '88888888-8888-4888-8888-888888888888',
      version: 1,
      status: 'succeeded',
      quality: 'pending',
      coverage: [],
      diagnostics: [],
      failure_code: null,
      implementation_version: 'mp03-d0-1',
    },
    snapshots: [
      {
        snapshot_id: '99999999-9999-4999-8999-999999999999',
        source_kind: 'api',
        provider: 'api-football',
        collected_at: '2026-11-10T16:00:00+00:00',
        provider_updated_at: null,
        artifact_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        validation_status: 'verified',
        note: 'D0-injuries',
      },
    ],
    coverage: [
      { topic: '부상·출전 불확실', state: 'unknown', detail: '부상 응답이 비어 있습니다. 이는 부상자 없음의 증거가 아닙니다.' },
      { topic: '최근 성적', state: 'available', detail: '팀 50 폼 WWDLW' },
      { topic: '경기 전 승무패 배당', state: 'call_error', detail: 'provider said 500' },
    ],
    claims: [
      {
        claim_id: 'd0-injury-7101',
        kind: 'fact',
        text: '선수 Recorded Doubtful 상태: Questionable, 사유 Knock',
        decision: 'adopted',
        decision_reason: '출전 불확실 표기를 그대로 보존했습니다. 결장 확정이 아닙니다.',
        snapshot_ids: ['99999999-9999-4999-8999-999999999999'],
      },
      {
        claim_id: 'd0-injury-7103',
        kind: 'fact',
        text: '선수 Recorded Unlabelled 상태: 표기 없음',
        decision: 'excluded',
        decision_reason: '표기가 없어 확정 사실로 채택하지 않았습니다.',
        snapshot_ids: [],
      },
    ],
    diagnostics: ['부상 응답이 비어 있습니다. 이는 부상자 없음의 증거가 아닙니다.'],
    fixture: {
      fixture_id: 1200001,
      league_id: 39,
      season: 2026,
      home_team_id: 50,
      away_team_id: 49,
      kickoff_at: '2026-11-12T20:00:00+00:00',
    },
    mode: 'live',
    provider_calls: 9,
    external_calls: 9,
    ...overrides,
  }
}

describe('DataPanel', () => {
  it('shows execution status and quality separately from evidence', () => {
    const wrapper = mount(DataPanel, { props: { result: d0() } })

    expect(wrapper.get('[data-test="d0-status"]').text()).toContain('실행 성공')
    expect(wrapper.get('[data-test="d0-status"]').text()).toContain('품질 pending')
    expect(wrapper.get('[data-test="d0-claims"]').text()).toContain('Recorded Doubtful')
  })

  it('never prints an empty injury response as "no injuries"', () => {
    const wrapper = mount(DataPanel, { props: { result: d0() } })
    const coverage = wrapper.get('[data-test="d0-coverage"]').text()

    expect(coverage).toContain('알 수 없음')
    expect(coverage).toContain('부상자 없음의 증거가 아닙니다')
    // 상태 문구 자체에 "부상자 0명" 같은 단정이 없어야 한다.
    expect(coverage).not.toContain('부상자 0')
  })

  it('distinguishes a call error from missing data', () => {
    const wrapper = mount(DataPanel, { props: { result: d0() } })
    const states = wrapper.findAll('[data-test="coverage-state"]').map((cell) => cell.text())

    expect(states).toContain('호출 오류')
    expect(states).toContain('확보')
    expect(states).not.toContain('제공자 미제공')
  })

  it('shows the run mode and source kind as separate axes', () => {
    const wrapper = mount(DataPanel, { props: { result: d0({ mode: 'mock', external_calls: 0 }) } })

    expect(wrapper.get('[data-test="d0-mode"]').text()).toContain('모의 실행')
    // mock은 실행기를 불러도 외부 호출로 세지 않는다.
    expect(wrapper.get('[data-test="d0-external-calls"]').text()).toContain('0회')
    // 자료 출처는 api 그대로다. 재생·모의를 자료 출처에 덮어쓰지 않는다.
    expect(wrapper.get('[data-test="d0-snapshots"]').text()).toContain('api')
  })

  it('keeps unadopted claims out of the adopted list but still inspectable', () => {
    const wrapper = mount(DataPanel, { props: { result: d0() } })

    const adopted = wrapper.get('[data-test="d0-claims"]').text()
    expect(adopted).not.toContain('Recorded Unlabelled')
    expect(wrapper.text()).toContain('채택하지 않은 근거 (1건)')
  })

  it('shows the snapshot reference and the empty-state note', () => {
    const wrapper = mount(DataPanel, { props: { result: d0() } })
    const snapshots = wrapper.get('[data-test="d0-snapshots"]').text()

    expect(snapshots).toContain('api-football')
    expect(snapshots).toContain('2026-11-10T16:00:00+00:00')
    expect(snapshots).toContain('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')

    const empty = mount(DataPanel, { props: { result: null } })
    expect(empty.get('[data-test="d0-empty"]').text()).toContain('아직 D0를 실행하지 않았습니다')
  })

  it('renders a stored failure without inventing values', () => {
    const failed = d0({
      claims: [],
      result: {
        ...d0().result,
        status: 'failed',
        quality: 'insufficient',
        failure_code: 'provider_error',
      },
      coverage: [{ topic: '경기 식별', state: 'validation_rejected', detail: '다른 경기' }],
    })
    const wrapper = mount(DataPanel, { props: { result: failed } })

    expect(wrapper.get('[data-test="d0-status"]').text()).toContain('실행 실패')
    expect(wrapper.text()).toContain('채택한 근거가 없습니다')
    expect(wrapper.get('[data-test="d0-coverage"]').text()).toContain('검증 탈락')
  })
})
