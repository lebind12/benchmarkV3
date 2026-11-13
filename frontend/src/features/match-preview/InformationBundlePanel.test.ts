/**
 * 정보 원문 패널 검사 (PS-04).
 *
 * 이 파일이 확인하는 것:
 * - 저장된 출처를 **먼저** 보여주고, 전달 구간·DB 스냅샷·전체 응답은 접힌 진단으로 둔다.
 * - 실패한 출처를 "가져온 자료"로 그리지 않는다(사유를 그대로 표시).
 * - 전체 모델 응답은 텍스트로만 보여준다(HTML로 실행하지 않음).
 * - 묶음이 없으면 빈 카드를 만들지 않고 사실대로 알린다.
 * - 이 패널은 조회만 한다(POST·재생성 없음).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const bundleMock = vi.fn()

vi.mock('@/features/match-preview/api', () => ({
  previewRunsApi: {
    informationBundle: (...args: unknown[]) => bundleMock(...args),
  },
}))

import InformationBundlePanel from '@/features/match-preview/InformationBundlePanel.vue'

/**
 * 기록된 실제 묶음(app/preview/information_bundle.py의 InformationBundle.to_dict())의
 * 축약본. `GET /runs/{run_id}/information-bundle` 응답 모양(manifest §4)을 따른다.
 */
function recordedBundle() {
  return {
    run_id: 'run-1',
    availability: { available: true, reason: null, artifact_id: 'artifact-1' },
    summary: { bundle_id: 'bundle-1', source_count: 2, usable_source_count: 1 },
    bundle: {
      bundle_id: 'bundle-1',
      bundle_version: 'mp11-information-bundle-1',
      fixture: { fixture_id: 1557474, label: 'Manchester City vs Fulham' },
      team_id_space: 'internal',
      collected_at: '2026-11-11T00:16:39+00:00',
      as_of: '2026-11-11T00:16:39+00:00',
      mode: 'live',
      sources: [
        {
          source_id: 'src:https-example-article',
          discovery_group: 'players_injury',
          requested_url: 'https://example.com/preview',
          final_url: 'https://example.com/preview',
          nature: 'preview',
          method: 'fresh_http',
          title: 'Manchester City vs Fulham preview',
          captured_at: '2026-11-11T00:15:50+00:00',
          http_status: 200,
          redirects: 0,
          extractor: 'trafilatura',
          body_chars: 2096,
          failure: null,
          notes: [],
          passages: [
            {
              passage_id: 'p-1',
              source_id: 'src:https-example-article',
              ordinal: 1,
              text: '시티는 홈에서 강하다.',
              char_count: 13,
              heading: null,
            },
          ],
          delivered_chars: 13,
          usable: true,
        },
        {
          source_id: 'src:https-blocked',
          discovery_group: 'media_odds',
          requested_url: 'https://blocked.example.com/odds',
          final_url: 'https://blocked.example.com/odds',
          nature: 'unavailable',
          method: 'fresh_http',
          title: 'Blocked bookmaker',
          http_status: 403,
          failure: 'Cloudflare challenge',
          notes: [],
          passages: [],
          delivered_chars: 0,
          usable: false,
        },
      ],
      // 후보 구간이다(실제 전달 아님). 각 항목 delivered 는 후보 표시일 뿐이다.
      available_passages: [
        {
          passage_id: 'p-1',
          source_id: 'src:https-example-article',
          ordinal: 1,
          text: '시티는 홈에서 강하다.',
          char_count: 13,
          heading: null,
          delivered: false,
        },
      ],
      passage_semantics:
        'sources[].passages/available_passages는 수집·정규화된 **전달 후보** 구간입니다.',
      section_deliveries: [
        {
          section_id: 'section_players',
          logical_call_id: 'call-1',
          model_delivered: true,
          passage_ids: ['p-1'],
          source_ids: ['src:https-example-article'],
          payload_sha256: 'deadbeefdeadbeefdeadbeef',
          input_chars: 640,
          available_passage_ids: ['p-1'],
          excluded_passage_ids: [],
          sent_attempts: 1,
          implementation_version: 'mp11-bundle-players-1',
          prompt_version: 'mp11-players-prompt-1',
          created_at: '2026-11-11T00:20:00+00:00',
          note: null,
        },
        {
          section_id: 'section_odds',
          logical_call_id: null,
          model_delivered: false,
          passage_ids: [],
          source_ids: [],
          payload_sha256: null,
          input_chars: 0,
          available_passage_ids: ['p-1'],
          excluded_passage_ids: ['p-1'],
          sent_attempts: 0,
          implementation_version: null,
          prompt_version: null,
          created_at: null,
          note: '배당은 모델 호출이 없습니다.',
        },
      ],
      db_snapshot: {
        fixture: { fixture_id: 1557474, label: 'Manchester City vs Fulham' },
        team_id_space: 'internal',
        collected_at: '2026-11-11T00:16:00+00:00',
        teams: [],
        standings: [{ team_id: 13, rank: 3, played: 10, points: 21, form: 'LLLWW' }],
        injuries: [],
        recent_matches: [],
        roster: [],
        source_tables: ['public.fixture', 'public.standings'],
        coverage: [{ topic: 'injury', state: 'unknown', detail: '저장된 부상 행이 없습니다.' }],
        diagnostics: [],
        readable: true,
      },
      discovery_groups: [
        { group: 'players_injury', status: 'completed', candidate_urls: ['a', 'b'], sent_attempts: 1 },
      ],
      odds: {
        quotes: [
          {
            source_id: 'src:odds',
            site: 'example-book',
            market: '1x2_regulation',
            observed_at: '2026-11-11T00:00:00+00:00',
            home_decimal: '1.72',
            draw_decimal: '3.90',
            away_decimal: '4.60',
            complete: true,
          },
        ],
        collected_at: '2026-11-11T00:16:00+00:00',
        diagnostics: [],
        unsupported_sites: [],
        complete_quotes: 1,
      },
      diagnostics: ['Google search grounding 없이 수집한 본문입니다.'],
      network_usage: { http_used: 6, http_failed: 1, redirects: 0, api_used: 0, http_limit: 24, api_limit: null, note: null },
      delivery_limits: { max_sources_per_section: 6 },
      build_note: null,
      usable_source_count: 1,
      delivered_chars: 13,
      browser_used: false,
      cross_checked_with_db: false,
      requires_grounding_chunks: false,
      bundle_hash: 'abc123',
    },
  }
}

async function mountWith(runId = 'run-1') {
  const wrapper = mount(InformationBundlePanel, { props: { runId } })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  bundleMock.mockReset()
})

describe('InformationBundlePanel', () => {
  it('shows stored sources first and keeps passages behind a disclosure', async () => {
    bundleMock.mockResolvedValue({ ok: true, data: recordedBundle() })
    const wrapper = await mountWith()

    // 출처는 접히지 않고 바로 보인다.
    const sources = wrapper.get('[data-testid="bundle-sources"]')
    expect(sources.text()).toContain('Manchester City vs Fulham preview')
    expect(sources.text()).toContain('fresh_http')
    expect(sources.text()).toContain('HTTP 200')

    // 수집 구간은 접힌 영역이다(라벨도 '전달'이 아니라 '수집 구간(전달 후보)').
    const passages = wrapper.get('[data-testid="bundle-passages"]')
    expect(passages.attributes('open')).toBeUndefined()
    expect(passages.get('summary').text()).toContain('전달 후보')
    expect(wrapper.html()).toContain('시티는 홈에서 강하다.')

    // DB 스냅샷·전체 응답도 접힌 진단이다.
    expect(wrapper.get('[data-testid="bundle-database"]').attributes('open')).toBeUndefined()
    expect(wrapper.get('[data-testid="bundle-id"]').text()).toBe('bundle-1')
    expect(wrapper.get('[data-testid="bundle-network"]').text()).toContain('HTTP 6회')
  })

  it('separates failed sources from collected ones without hiding the reason', async () => {
    bundleMock.mockResolvedValue({ ok: true, data: recordedBundle() })
    const wrapper = await mountWith()

    const failed = wrapper.get('[data-testid="bundle-failed-sources"]')
    expect(failed.text()).toContain('Blocked bookmaker')
    expect(failed.text()).toContain('HTTP 403')
    expect(failed.text()).toContain('Cloudflare challenge')

    // 성공 출처 목록에는 실패 출처가 섞이지 않는다.
    const okSources = wrapper.get('[data-testid="bundle-sources"]').text()
    expect(okSources).not.toContain('Blocked bookmaker')
  })

  it('renders odds and DB coverage as collapsed diagnostics', async () => {
    bundleMock.mockResolvedValue({ ok: true, data: recordedBundle() })
    const wrapper = await mountWith()

    // 배당·DB·조사 상태는 모두 접힌 진단이다(본문·근거가 먼저).
    expect(wrapper.get('[data-testid="bundle-odds"]').attributes('open')).toBeUndefined()
    expect(wrapper.get('[data-testid="bundle-discovery"]').attributes('open')).toBeUndefined()

    const odds = wrapper.get('[data-testid="bundle-odds"]').text()
    expect(odds).toContain('example-book')
    expect(odds).toContain('1.72')
    expect(wrapper.get('[data-testid="bundle-db-coverage"]').text()).toContain('injury')

    // 부상 행 0건을 '부상자 없음'으로 쓰지 않는다.
    expect(wrapper.get('[data-testid="bundle-database"]').text()).toContain(
      "'부상자 없음'의 증거가 아닙니다",
    )
  })

  it('shows the server reason when the run has no bundle', async () => {
    bundleMock.mockResolvedValue({
      ok: true,
      data: {
        run_id: 'run-1',
        availability: {
          available: false,
          reason: '이 실행에는 정보 원문 묶음이 없습니다.',
          artifact_id: null,
        },
        summary: {},
        bundle: null,
      },
    })
    const wrapper = await mountWith()

    const empty = wrapper.get('[data-testid="bundle-empty"]').text()
    expect(empty).toContain('정보 원문 묶음이 없습니다')
    // 빈 묶음을 만들어 출처 카드를 그리지 않는다.
    expect(wrapper.find('[data-testid="bundle-sources"]').exists()).toBe(false)
  })

  it('surfaces a contract-breaking honesty flag instead of hiding it', async () => {
    bundleMock.mockResolvedValue({
      ok: true,
      data: {
        ...recordedBundle(),
        bundle: { ...recordedBundle().bundle, browser_used: true },
      },
    })
    const wrapper = await mountWith()

    expect(wrapper.get('[data-testid="bundle-honesty-warning"]').text()).toContain('브라우저 렌더')
  })

  it('separates candidates from what was actually delivered to the model', async () => {
    bundleMock.mockResolvedValue({ ok: true, data: recordedBundle() })
    const wrapper = await mountWith()

    // 후보 수와 실제 모델 전달 섹션 수를 다른 값으로 보여준다.
    expect(wrapper.get('[data-testid="bundle-candidate-count"]').text()).toContain('구간 1개')
    expect(wrapper.get('[data-testid="bundle-delivery-count"]').text()).toContain('1개 섹션')

    const deliveries = wrapper.findAll('[data-testid="bundle-delivery-row"]')
    expect(deliveries).toHaveLength(2)
    expect(deliveries[0].get('[data-testid="bundle-delivery-model"]').text()).toContain('전달 1구간')
    // 배당은 모델을 쓰지 않는다: '전달됨'이 아니라 '모델 호출 없음'으로 표시한다.
    expect(deliveries[1].get('[data-testid="bundle-delivery-no-model"]').text()).toContain(
      '모델 호출 없음',
    )
    expect(deliveries[1].find('[data-testid="bundle-delivery-model"]').exists()).toBe(false)
  })

  it('marks only passages listed in a model delivery as actually delivered', async () => {
    bundleMock.mockResolvedValue({ ok: true, data: recordedBundle() })
    const wrapper = await mountWith()

    // p-1은 section_players 전달에 들어 있으므로 '실제 전달됨'.
    expect(wrapper.find('[data-testid="bundle-passage-delivered"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="bundle-passage-candidate"]').exists()).toBe(false)
  })

  it('shows collected passages as candidates when no delivery covers them', async () => {
    const data = recordedBundle()
    bundleMock.mockResolvedValue({
      ok: true,
      // 배당(model_delivered=false)만 있고 이 구간을 실제로 받은 섹션이 없는 경우.
      data: {
        ...data,
        bundle: {
          ...data.bundle,
          section_deliveries: [
            {
              section_id: 'section_odds',
              model_delivered: false,
              passage_ids: [],
              excluded_passage_ids: ['p-1'],
            },
          ],
        },
      },
    })
    const wrapper = await mountWith()

    // 후보를 '실제 전달됨'으로 승격하지 않는다.
    expect(wrapper.find('[data-testid="bundle-passage-delivered"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="bundle-passage-candidate"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="bundle-delivery-count"]').exists()).toBe(false)
  })

  it('says so when the bundle has no section delivery records at all', async () => {
    const data = recordedBundle()
    bundleMock.mockResolvedValue({
      ok: true,
      data: { ...data, bundle: { ...data.bundle, section_deliveries: [] } },
    })
    const wrapper = await mountWith()

    const note = wrapper.get('[data-testid="bundle-no-delivery"]').text()
    expect(note).toContain('저장된 섹션 전달 기록이 없습니다')
    // 전달 기록이 없으면 후보 구간에 '전달됨/후보' 표시를 만들지 않는다.
    expect(wrapper.find('[data-testid="bundle-passage-delivered"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="bundle-passage-candidate"]').exists()).toBe(false)
    // 서버가 주는 구분 문장은 그대로 보여준다.
    expect(wrapper.get('[data-testid="bundle-passage-semantics"]').text()).toContain('전달 후보')
  })

  it('reports an empty bundle instead of drawing an empty card', async () => {
    bundleMock.mockResolvedValue({ ok: true, data: {} })
    const wrapper = await mountWith()

    expect(wrapper.get('[data-testid="bundle-empty"]').text()).toContain('저장된 정보 원문이 없습니다')
    expect(wrapper.find('[data-testid="bundle-sources"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="bundle-odds"]').exists()).toBe(false)
  })

  it('shows the query failure as-is and does not start any write', async () => {
    bundleMock.mockResolvedValue({
      ok: false,
      kind: 'server',
      status: 500,
      message: '서버 오류가 발생했습니다. 잠시 후 다시 시도하세요.',
    })
    const wrapper = await mountWith()

    expect(wrapper.get('[data-testid="bundle-error"]').text()).toContain('서버 오류')
    // 조회만 한다: 한 번 호출, 쓰기 메서드 없음.
    expect(bundleMock).toHaveBeenCalledTimes(1)
    expect(bundleMock).toHaveBeenCalledWith('run-1')
  })

  it('does not query without a run id', async () => {
    const wrapper = await mountWith('')
    expect(bundleMock).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="bundle-sources"]').exists()).toBe(false)
  })
})
