/**
 * R3 배당·외부 전망 패널 검사 (MP-07).
 *
 * 이 파일이 확인하는 것:
 * - 독자용 본문을 먼저 보여주고, 누락·오류 안내는 관리자 영역에만 둔다.
 * - 경기 전 승무패 배당·외부 매체 전망·제공자 알고리즘 예측을 섞지 않는다.
 * - grounding 메타데이터와 그 부재 사유가 관리자 영역에 남는다.
 * - 검증 탈락 자료가 채택 목록에 섞이지 않고 사유와 함께 보인다.
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import OutlookPanel from '@/features/match-preview/panels/OutlookPanel.vue'

type PanelResult = InstanceType<typeof OutlookPanel>['$props']['result']

function outlook(overrides: Partial<NonNullable<PanelResult>> = {}): NonNullable<PanelResult> {
  return {
    module_id: 'R3',
    implementation_version: 'mp07-r3-1',
    prompt_version: 'r3-outlook-1',
    mode: 'live',
    fixture: { fixture_id: 1200001, league_id: 39, season: 2026 },
    odds: [
      {
        claim_id: 'r3-odds-8-5',
        bookmaker: 'Recorded Book A',
        market: 'Match Winner',
        observed_at: '2026-11-10T15:00:00+00:00',
        home: '1.85',
        draw: '3.60',
        away: '4.20',
        fixture_id: 1200001,
        adopted: true,
        rejection_reason: null,
      },
    ],
    rejected_odds: [
      {
        claim_id: 'r3-odds-8-24',
        bookmaker: 'Recorded Book A',
        market: 'To Qualify',
        observed_at: '2026-11-10T15:00:00+00:00',
        home: '1.22',
        draw: null,
        away: '4.50',
        fixture_id: 1200001,
        adopted: false,
        rejection_reason: "'To Qualify' 시장은 경기 전 승무패가 아니어서 이 경기의 1X2 배당으로 쓰지 않습니다.",
      },
    ],
    media: [
      {
        claim_id: 'r3-media-1',
        publisher: 'Recorded Football Desk',
        url: 'https://recorded-football.test/preview/1200001',
        published_at: '2026-11-10T09:30:00+00:00',
        statement: 'Recorded Home이 홈에서 우세하다고 봤다.',
        predicted_score: null,
        source_confirmed: true,
        adopted: true,
        rejection_reason: null,
      },
    ],
    rejected_media: [],
    api_prediction: {
      claim_id: 'r3-api-prediction',
      provider: 'api-football',
      winner_name: 'Recorded Home',
      advice: 'Recorded Home or draw',
      under_over: '-3.5',
      percent_home: '55%',
      percent_draw: '25%',
      percent_away: '20%',
    },
    grounding: {
      present: true,
      web_search_queries: ['Recorded Home Recorded Away preview prediction'],
      chunk_uris: ['https://recorded-football.test/preview/1200001'],
      chunk_titles: ['Recorded Football Desk preview'],
      search_suggestions_html: '<div>Recorded Football Desk</div>',
      absence_reason: null,
      missing_queries_note: null,
    },
    coverage: [
      { topic: '경기 전 승무패 배당', state: 'available', detail: '채택 1건' },
      { topic: '외부 매체 전망', state: 'available', detail: '채택 1건' },
      { topic: '제공자 알고리즘 예측', state: 'available', detail: '1건' },
    ],
    diagnostics: ['검증되지 않은 매체 전망 0건을 본문에서 제외했습니다.'],
    quality: 'ready',
    model_name: 'gemini-3.5-flash',
    external_calls: 1,
    reader_body:
      '## 배당과 외부 전망\n\n이 경기의 경기 전 승무패 배당, 외부 매체의 전망와 제공자 알고리즘의 예측을 정리했습니다.',
    reader_sources: [
      {
        label: 'Recorded Book A 경기 전 승무패 배당',
        kind: 'bookmaker',
        url: null,
        publisher: 'Recorded Book A',
        published_at: '2026-11-10T15:00:00+00:00',
        note: 'API-Football 배당 자료입니다.',
      },
      {
        label: 'Recorded Football Desk',
        kind: 'media',
        url: 'https://recorded-football.test/preview/1200001',
        publisher: 'Recorded Football Desk',
        published_at: '2026-11-10T09:30:00+00:00',
        note: '검색 결과 출처 목록에서 주소를 확인했습니다.',
      },
      {
        label: 'API-Football 알고리즘 예측',
        kind: 'api_prediction',
        url: null,
        publisher: 'api-football',
        published_at: null,
        note: '제공자 알고리즘 예측이며 매체 의견이 아닙니다.',
      },
    ],
    ...overrides,
  }
}

describe('OutlookPanel', () => {
  it('shows the reader body before the admin diagnostics', () => {
    const wrapper = mount(OutlookPanel, { props: { result: outlook() } })

    const body = wrapper.get('[data-test="outlook-reader-body"]').text()
    expect(body).toContain('배당과 외부 전망')
    // 관리자 진단은 접이식 영역 안에 있다(본문보다 뒤).
    expect(wrapper.get('[data-test="outlook-admin"]').text()).toContain('관리자 진단')
    const html = wrapper.html()
    expect(html.indexOf('outlook-reader-body')).toBeLessThan(html.indexOf('outlook-admin'))
  })

  it('keeps bookmaker odds, media forecasts and api prediction apart', () => {
    const wrapper = mount(OutlookPanel, { props: { result: outlook() } })

    const odds = wrapper.get('[data-test="outlook-odds"]').text()
    expect(odds).toContain('Recorded Book A')
    expect(odds).toContain('Match Winner')
    expect(odds).toContain('2026-11-10T15:00:00+00:00')

    const media = wrapper.get('[data-test="outlook-media"]').text()
    expect(media).toContain('Recorded Football Desk')
    expect(media).toContain('https://recorded-football.test/preview/1200001')

    const api = wrapper.get('[data-test="outlook-api-prediction"]').text()
    expect(api).toContain('매체 의견 아님')
    expect(api).toContain('55%')
    // 제공자 예측 숫자가 매체 전망 목록에 섞이지 않는다.
    expect(media).not.toContain('55%')
  })

  it('does not put rejected odds into the adopted table', () => {
    const wrapper = mount(OutlookPanel, { props: { result: outlook() } })

    expect(wrapper.get('[data-test="outlook-odds"]').text()).not.toContain('To Qualify')
    const rejected = wrapper.get('[data-test="outlook-rejected"]').text()
    expect(rejected).toContain('To Qualify')
    expect(rejected).toContain('경기 전 승무패가 아니어서')
  })

  it('shows grounding absence in the admin area and never in the reader body', () => {
    const missing = outlook({
      media: [],
      rejected_media: [
        {
          claim_id: 'r3-media-1',
          publisher: 'Recorded Football Desk',
          url: 'https://recorded-football.test/preview/1200001',
          published_at: '2026-11-10T09:30:00+00:00',
          statement: 'Recorded Home이 우세하다고 봤다.',
          predicted_score: null,
          source_confirmed: false,
          adopted: false,
          rejection_reason: '모델 응답에 Google Search grounding 메타데이터가 없어 검색 출처를 확인할 수 없습니다.',
        },
      ],
      grounding: {
        present: false,
        web_search_queries: [],
        chunk_uris: [],
        chunk_titles: [],
        search_suggestions_html: null,
        absence_reason:
          '모델 응답에 Google Search grounding 메타데이터가 없어 검색 출처를 확인할 수 없습니다. 확인되지 않은 매체 전망은 채택하지 않았습니다.',
        missing_queries_note: null,
      },
      reader_body: '## 배당과 외부 전망\n\n### 경기 전 승무패 배당\n\n- Recorded Book A: 홈 1.85',
    })
    const wrapper = mount(OutlookPanel, { props: { result: missing } })

    expect(wrapper.get('[data-test="outlook-grounding"]').text()).toContain('메타데이터 없음')
    expect(wrapper.get('[data-test="outlook-grounding-absence"]').text()).toContain(
      '검색 출처를 확인할 수 없습니다',
    )
    const body = wrapper.get('[data-test="outlook-reader-body"]').text()
    expect(body).not.toContain('grounding')
    expect(body).not.toContain('누락')
    expect(body).not.toContain('실패')
  })

  it('renders no reader body when there is none, without inventing text', () => {
    const empty = outlook({
      odds: [],
      media: [],
      api_prediction: null,
      reader_body: '',
      reader_sources: [],
      quality: 'insufficient',
      coverage: [
        { topic: '경기 전 승무패 배당', state: 'api_not_provided', detail: 'D0 배당 자료가 비어 있습니다.' },
      ],
    })
    const wrapper = mount(OutlookPanel, { props: { result: empty } })

    expect(wrapper.get('[data-test="outlook-no-reader-body"]').text()).toContain(
      '독자용 본문이 없습니다',
    )
    expect(wrapper.find('[data-test="outlook-reader-body"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="outlook-coverage"]').text()).toContain('제공자 미제공')
  })

  it('labels mock and replay runs as non-live', () => {
    const mock = mount(OutlookPanel, {
      props: { result: outlook({ mode: 'mock', external_calls: 0 }) },
    })
    expect(mock.get('[data-test="outlook-mode"]').text()).toContain('모의 실행')
    expect(mock.get('[data-test="outlook-external-calls"]').text()).toContain('0회')

    const replay = mount(OutlookPanel, {
      props: { result: outlook({ mode: 'replay', external_calls: 0 }) },
    })
    expect(replay.get('[data-test="outlook-mode"]').text()).toContain('저장 응답 재생')
  })

  it('renders an empty state before any run and an error state on failure', () => {
    const empty = mount(OutlookPanel, { props: { result: null } })
    expect(empty.get('[data-test="outlook-empty"]').text()).toContain('아직 R3를 실행하지 않았습니다')

    const failed = mount(OutlookPanel, {
      props: { result: null, errorMessage: 'R3 결과를 불러오지 못했습니다.' },
    })
    expect(failed.get('[data-test="outlook-error"]').text()).toContain('불러오지 못했습니다')
  })

  it('keeps provider search suggestions as inert text', () => {
    const wrapper = mount(OutlookPanel, { props: { result: outlook() } })
    const suggestions = wrapper.get('[data-test="outlook-search-suggestions"]')

    expect(suggestions.text()).toContain('Recorded Football Desk')
    // 제공자 조각은 실행되지 않도록 텍스트로만 보관한다.
    expect(suggestions.find('div').exists()).toBe(false)
  })
})
