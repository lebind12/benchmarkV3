/**
 * bundle_pipeline 섹션 실행 결과를 RunInspector의 R4/R2 패널과
 * 미승인 관리자 카드 미리보기(MatchPreviewBody)로 투영하는 통합 검사.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import RunInspector from '@/features/match-preview/RunInspector.vue'
import { setAccessToken } from '@/lib/api/session'

const RUN_ID = '86a2408c-5696-4d93-8140-ca9ac26a2af9'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('BundlePanelAdapters inside RunInspector', () => {
  afterEach(() => {
    setAccessToken(null)
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('mounts R4 PlayersPanel, R2 AvailabilityPanel, and explicit unapproved MatchPreviewBody card preview', async () => {
    const detail = {
      summary: {
        run_id: RUN_ID,
        operation_kind: 'section_workflow',
        environment: 'dev',
        mode: 'live',
        status: 'succeeded',
        quality: 'ready',
        fixture_label: '맨체스터 시티 vs 풀럼',
        requested_at: '2026-11-16T10:00:00+00:00',
        finished_at: '2026-11-16T10:00:10+00:00',
        is_demo: false,
        external_calls: 2,
      },
      actor_id: '1',
      config_version: 'cfg-1',
      limits: {},
      fixture: {
        fixture_id: 1557474,
        league_id: 39,
        season: 2025,
        home_team_id: 50,
        away_team_id: 36,
        kickoff_at: '2026-11-18T19:00:00Z',
      },
      modules: [],
      results: [
        {
          result_id: 'res-r4',
          run_id: RUN_ID,
          module_execution_id: 'mod-r4',
          section_id: 'section_players',
          version: 1,
          status: 'succeeded',
          quality: 'ready',
          failure_code: null,
          payload: {
            payload: {
              module_id: 'R4',
              section_id: 'section_players',
              mode: 'live',
              body: '주목 선수 본문',
              external_calls: 1,
              implementation_version: 'r4-bundle-1',
              prompt_version: 'p4-1',
              structured: { players: [] },
              sources: [{ label: '프리미어리그', url: 'https://example.com/pl', kind: 'search' }],
            },
          },
          contract_version: 'mp05p-r4-players-output-1',
          prompt_version: 'p4-1',
          implementation_version: 'r4-bundle-1',
          input_hash: 'h-r4',
          created_at: '2026-11-16T10:00:05+00:00',
        },
        {
          result_id: 'res-r2',
          run_id: RUN_ID,
          module_execution_id: 'mod-r2',
          section_id: 'section_availability',
          version: 1,
          status: 'succeeded',
          quality: 'ready',
          failure_code: null,
          payload: {
            payload: {
              module_id: 'R2',
              section_id: 'section_availability',
              mode: 'live',
              body: '부상 본문',
              external_calls: 1,
              implementation_version: 'r2-bundle-1',
              prompt_version: 'p2-1',
              structured: { injuries: [] },
              sources: [{ label: '부상 속보', url: 'https://example.com/inj', kind: 'search' }],
            },
          },
          contract_version: 'mp06-availability-output-2',
          prompt_version: 'p2-1',
          implementation_version: 'r2-bundle-1',
          input_hash: 'h-r2',
          created_at: '2026-11-16T10:00:08+00:00',
        },
      ],
      sources: [],
      attempts: [],
      artifacts: [],
      contract_versions: { run: 'c', section_result: 's' },
      inspector_version: 'mp02-1',
      mode_detail: { mode: 'live', label: '실호출 (live)', note: '실호출' },
      inspector_modules: [
        {
          inspector_version: 'mp02-1',
          module_execution_id: 'mod-r4',
          module_id: 'R4',
          panel: {
            panel: 'players',
            registered: true,
            display_name: 'R4 주목 선수',
            description: '주목 선수 선정',
            mode_scope: ['live'],
            available: true,
            unrunnable_reason: null,
          },
          run_mode: { mode: 'live', label: '실호출 (live)', note: '실호출' },
          status: 'succeeded',
          quality: 'ready',
          attempt_count: 1,
          retry_count: 0,
          result_versions: [1],
          started_at: null,
          finished_at: null,
          tabs: {
            request: { available: false, input: {}, attempts: [], note: null },
            response: { available: false, attempts: [], note: null },
            transform: {
              available: true,
              result_id: 'res-r4',
              version: 1,
              status: 'succeeded',
              quality: 'ready',
              failure_code: null,
              claims: [],
              coverage: [],
              diagnostics: [],
              contract_version: 'mp05p-r4-players-output-1',
              prompt_version: 'p4-1',
              implementation_version: 'r4-bundle-1',
              input_hash: 'h-r4',
              artifacts: [],
              note: null,
            },
            next_input: {
              available: false,
              target_module_id: null,
              selected_result_ids: [],
              uses_latest_version: false,
              latest_result_id: 'res-r4',
              latest_result_version: 1,
              values: [],
              note: null,
            },
          },
          tabs_meta: [],
          player_section_processing: {
            workflow_id: 'section_players',
            fixture_id: 1557474,
            home_team_id: 50,
            away_team_id: 36,
            output_contract_version: 'mp05p-r4-players-output-1',
            persisted: true,
            storage_status: 'canonical',
            mode: 'live',
            ok: true,
            failed_reason: null,
            home1: {
              slot_key: 'home1',
              team_side: 'home',
              team_id: 50,
              team_name: '맨체스터 시티',
              player_id: 88,
              external_player_id: 19281,
              photo_url: 'https://media.api-sports.io/football/players/19281.png',
              resolution_status: 'resolved',
              original_name: 'Antoine Semenyo',
              name_ko: '앙투안 세메뇨',
              name_source: 'db_ko',
              body: '측면 돌파의 핵심입니다.',
              unresolved_reason: null,
              evidence: ['ev-1'],
            },
            home2: null,
            away1: {
              slot_key: 'away1',
              team_side: 'away',
              team_id: 36,
              team_name: '풀럼',
              player_id: null,
              external_player_id: null,
              photo_url: null,
              resolution_status: 'unresolved',
              original_name: 'Joshua King',
              name_ko: '조슈아 킹',
              name_source: 'ai_candidate',
              body: '역습 연결을 책임집니다.',
              unresolved_reason: 'player_not_matched',
              evidence: ['ev-2'],
            },
            away2: null,
            home_etc: null,
            away_etc: null,
            regeneration_count: 0,
            regeneration_reason: null,
            module_attempt_count: 1,
            adopted_attempt_ordinal: 0,
            attempts: [
              {
                attempt_ordinal: 0,
                logical_call_id: 'section_players',
                parsed_valid: true,
                raw_text: '{"home1":{"name":"앙투안 세메뇨"}}',
                parsed_json: { home1: { name: '앙투안 세메뇨' } },
                regeneration_triggered: false,
                regeneration_reason: null,
                error_reason: null,
              },
            ],
            unplaced_items: [],
            translation_defects: [],
            diagnostics: [],
            korean_labels: [],
            dropped_evidence_count: 0,
          },
        },
        {
          inspector_version: 'mp02-1',
          module_execution_id: 'mod-r2',
          module_id: 'R2',
          panel: {
            panel: 'availability',
            registered: true,
            display_name: 'R2 부상·결장',
            description: '부상·결장',
            mode_scope: ['live'],
            available: true,
            unrunnable_reason: null,
          },
          run_mode: { mode: 'live', label: '실호출 (live)', note: '실호출' },
          status: 'succeeded',
          quality: 'ready',
          attempt_count: 1,
          retry_count: 0,
          result_versions: [1],
          started_at: null,
          finished_at: null,
          tabs: {
            request: { available: false, input: {}, attempts: [], note: null },
            response: { available: false, attempts: [], note: null },
            transform: {
              available: true,
              result_id: 'res-r2',
              version: 1,
              status: 'succeeded',
              quality: 'ready',
              failure_code: null,
              claims: [],
              coverage: [],
              diagnostics: [],
              contract_version: 'mp06-availability-output-2',
              prompt_version: 'p2-1',
              implementation_version: 'r2-bundle-1',
              input_hash: 'h-r2',
              artifacts: [],
              note: null,
            },
            next_input: {
              available: false,
              target_module_id: null,
              selected_result_ids: [],
              uses_latest_version: false,
              latest_result_id: 'res-r2',
              latest_result_version: 1,
              values: [],
              note: null,
            },
          },
          tabs_meta: [],
          player_section_processing: {
            workflow_id: 'section_availability',
            fixture_id: 1557474,
            home_team_id: 50,
            away_team_id: 36,
            output_contract_version: 'mp06-availability-output-2',
            persisted: true,
            storage_status: 'canonical',
            mode: 'live',
            ok: true,
            failed_reason: null,
            home1: {
              slot_key: 'home1',
              team_side: 'home',
              team_id: 50,
              team_name: '맨체스터 시티',
              player_id: 549,
              external_player_id: 67971,
              photo_url: 'https://media.api-sports.io/football/players/67971.png',
              resolution_status: 'resolved',
              original_name: 'Marc Guehi',
              name_ko: '마크 게히',
              name_source: 'db_ko',
              body: '햄스트링 점검 중입니다.',
              unresolved_reason: null,
              evidence: ['ev-r2'],
              status: 'doubtful',
              injury: '햄스트링',
            },
            home2: null,
            away1: null,
            away2: null,
            home_etc: null,
            away_etc: null,
            regeneration_count: 0,
            regeneration_reason: null,
            module_attempt_count: 1,
            adopted_attempt_ordinal: 0,
            attempts: [],
            unplaced_items: [],
            translation_defects: [],
            diagnostics: [],
            korean_labels: [],
            dropped_evidence_count: 0,
          },
        },
      ],
      registry: {
        registry_version: '1',
        contract_version: '1',
        inspector_version: 'mp02-1',
        modules: [],
        implemented: ['R1', 'R2', 'R3', 'R4', 'S1'],
        unavailable: ['D0'],
      },
      approvals: null,
      section_result_id: 'sr-r4',
      section_results: [
        {
          section_result_id: 'sr-r4',
          run_id: RUN_ID,
          workflow_id: 'section_players',
          version: 1,
          mode: 'live',
          mode_label: '실제 생성',
          title: '주목 선수',
          body: '앙투안 세메뇨와 조슈아 킹이 맞붙습니다.',
          quality: 'ready',
          unavailable: false,
          unavailable_reason: null,
          sources: [],
          result_ids: ['res-r4'],
          implementation_version: 'r4-bundle-1',
          prompt_version: 'p4-1',
          contract_version: 'mp05p-r4-players-output-1',
          created_at: null,
          supersedes_section_result_id: null,
          approvable: true,
          persisted: true,
          structured: {
            structured_version: 'mp04-structured-1',
            workflow_id: 'section_players',
            players: [
              {
                player: '앙투안 세메뇨',
                reason: '측면 돌파의 핵심입니다.',
                team: '맨체스터 시티',
                team_side: 'home',
                photo_url: 'https://media.api-sports.io/football/players/19281.png',
                unresolved: false,
              },
              {
                player: '조슈아 킹',
                reason: '역습 연결을 책임집니다.',
                team: '풀럼',
                team_side: 'away',
                photo_url: null,
                unresolved: true,
              },
            ],
            injuries: [],
            media: [],
            odds: [],
            forecast: null,
          },
        },
      ],
      section_approvals: [],
      section_workflows: null,
      approval_note: '',
      mock_demo_module_id: 'mock_demo',
      availability_note: '실제 실행 구현이 등록된 모듈: R1·R2·R3·R4·S1.',
      undo: {
        cancelled: false,
        cancelled_at: null,
        cancelled_by_actor_id: null,
        reason: null,
        can_cancel: false,
        blocked_reason: null,
      },
    }

    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/versions')) return Promise.resolve(jsonResponse({ detail: 'none' }, 404))
      if (url.includes('/section-results')) {
        return Promise.resolve(jsonResponse({ detail: 'none' }, 404))
      }
      if (url.endsWith(`/runs/${RUN_ID}`)) return Promise.resolve(jsonResponse(detail))
      return Promise.resolve(jsonResponse({ detail: 'not found' }, 404))
    })
    vi.stubGlobal('fetch', fetchMock)
    setAccessToken('test-token')

    const wrapper = mount(RunInspector, {
      props: { runId: RUN_ID },
      attachTo: document.body,
    })
    await flushPromises()

    const previewBox = wrapper.get('[data-testid="unapproved-card-preview"]')
    expect(previewBox.text()).toContain('미승인 관리자 카드 미리보기')
    const imgs = previewBox.findAll('img')
    expect(
      imgs.some((img) => img.attributes('src') === 'https://media.api-sports.io/football/players/19281.png'),
    ).toBe(true)
    expect(previewBox.text()).toContain('조슈아 킹')

    expect(wrapper.get('[data-testid="players-panel-selected"]').text()).toContain('선정 결과 (2명)')
    expect(wrapper.get('[data-testid="players-panel"]').text()).toContain('앙투안 세메뇨')

    await wrapper.get('[data-testid="module-tab-R2"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="r2-attempts"]').text()).toBe('1회')
    expect(wrapper.get('[data-test="r2-summary"]').text()).toContain('API 부상 자료 수신')
  })
})
