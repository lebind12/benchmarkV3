/**
 * NS-02 선수·부상 섹션 생성 진단 UI 및 관리자 검사기 통합 검사.
 *
 * 확인 대상:
 * - 고정 4슬롯(home1~away2)·ETC=NULL·저장 예정 값(persisted=false)·mock/live 구분 표시
 * - DB 한글명 우선(db_ko), 미확인 인물 ID=NULL·AI 한글명 후보·본문·미연결 이유 유지
 * - 한글명 누락(missing_name_ko) 번역 결함, 재생성 1회·채택 시도 배지·원문 JSON 조회
 * - 부상 상태(doubtful) 원문 보존 및 RunInspector 조회 중 모델 재호출 없음(GET 전용)
 */
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PlayerSectionProcessingView from '@/features/match-preview/PlayerSectionProcessingView.vue'
import RunInspector from '@/features/match-preview/RunInspector.vue'
import type { PlayerSectionProcessingViewData } from '@/features/match-preview/types'
import { setAccessToken } from '@/lib/api/session'

function makeProcessing(
  overrides: Partial<PlayerSectionProcessingViewData> = {},
): PlayerSectionProcessingViewData {
  return {
    workflow_id: 'section_players',
    fixture_id: 9001,
    home_team_id: 13,
    away_team_id: 4,
    output_contract_version: 'mp11-player-section-1',
    persisted: false,
    storage_status: '저장 예정 값',
    mode: 'live',
    ok: true,
    failed_reason: null,
    home1: {
      slot_key: 'home1',
      team_side: 'home',
      team_id: 13,
      team_name: '맨체스터 시티',
      player_id: 7101,
      external_player_id: 1100,
      resolution_status: 'resolved',
      original_name: 'Erling Haaland',
      name_ko: '엘링 홀란드',
      name_source: 'db_ko',
      body: '박스 안 마무리 능력이 뛰어납니다.',
      unresolved_reason: null,
      evidence: ['src:stats#p1'],
    },
    home2: {
      slot_key: 'home2',
      team_side: 'home',
      team_id: 13,
      team_name: '맨체스터 시티',
      player_id: 7102,
      external_player_id: 47,
      resolution_status: 'resolved',
      original_name: 'Phil Foden',
      name_ko: '필 포든',
      name_source: 'db_ko',
      body: '하프스페이스 전개가 핵심입니다.',
      unresolved_reason: null,
      evidence: ['src:stats#p1'],
    },
    away1: {
      slot_key: 'away1',
      team_side: 'away',
      team_id: 4,
      team_name: '풀럼',
      player_id: null,
      external_player_id: null,
      resolution_status: 'unresolved',
      original_name: 'Academy Prospect',
      name_ko: '아카데미 유망주',
      name_source: 'ai_candidate',
      body: '전방 압박 가담 빈도가 높습니다.',
      unresolved_reason: 'NOT_FOUND',
      evidence: ['src:stats#p1'],
    },
    away2: null,
    home_etc: null,
    away_etc: null,
    regeneration_count: 1,
    regeneration_reason: 'missing_body',
    module_attempt_count: 2,
    adopted_attempt_ordinal: 1,
    attempts: [
      {
        attempt_ordinal: 0,
        logical_call_id: 'section_players',
        parsed_valid: true,
        raw_text: '{"players":[{"selected_player":"Erling Haaland","selection_reason":""}]}',
        parsed_json: {
          players: [{ selected_player: 'Erling Haaland', selection_reason: '' }],
        },
        regeneration_triggered: true,
        regeneration_reason: 'missing_body',
        error_reason: null,
      },
      {
        attempt_ordinal: 1,
        logical_call_id: 'section_players',
        parsed_valid: true,
        raw_text: '{"players":[{"selected_player":"Erling Haaland","selection_reason":"박스 안 마무리 능력이 뛰어납니다."}]}',
        parsed_json: {
          players: [
            {
              selected_player: 'Erling Haaland',
              selection_reason: '박스 안 마무리 능력이 뛰어납니다.',
            },
          ],
        },
        regeneration_triggered: false,
        regeneration_reason: null,
        error_reason: null,
      },
    ],
    unplaced_items: [
      {
        original_name: 'Phil Foden NoKo',
        reason: 'missing_name_ko',
        team_hint: 'Manchester City',
        team_id: 13,
        player_id: null,
        external_player_id: null,
        detail: '사용 가능한 DB·AI 한글명이 없어 번역 결함으로 분리했습니다.',
      },
    ],
    translation_defects: ['missing_name_ko:Phil Foden NoKo'],
    diagnostics: [],
    korean_labels: [{ original: 'Academy Prospect', korean: '아카데미 유망주', kind: 'player' }],
    dropped_evidence_count: 0,
    ...overrides,
  }
}

describe('PlayerSectionProcessingView', () => {
  afterEach(() => {
    setAccessToken(null)
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('renders fixed 4 slots, DB vs AI korean labels, null IDs, unplaced defects, and attempt traces', () => {
    const wrapper = mount(PlayerSectionProcessingView, {
      props: {
        processing: makeProcessing(),
      },
    })

    expect(wrapper.find('[data-testid="player-section-processing"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ns02-storage-status"]').text()).toContain('저장 예정 값')
    expect(wrapper.find('[data-testid="ns02-mode-badge"]').text()).toContain('실제 실행 (live)')
    expect(wrapper.find('[data-testid="ns02-pending-note"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ns02-etc-null"]').text()).toContain('home_etc = NULL')
    expect(wrapper.find('[data-testid="ns02-etc-null"]').text()).toContain('away_etc = NULL')
    expect(wrapper.find('[data-testid="ns02-adopted-attempt"]').text()).toContain('attempt_ordinal=1')
    expect(wrapper.find('[data-testid="ns02-regeneration"]').text()).toContain('1회')
    expect(wrapper.find('[data-testid="ns02-regeneration"]').text()).toContain('설명 누락')

    const home1 = wrapper.find('[data-testid="ns02-slot-home1"]')
    expect(home1.text()).toContain('엘링 홀란드')
    expect(home1.text()).toContain('7101')
    expect(home1.text()).toContain('1100')
    expect(home1.text()).toContain('DB 한글')

    const away1 = wrapper.find('[data-testid="ns02-slot-away1"]')
    expect(away1.text()).toContain('아카데미 유망주')
    expect(away1.text()).toContain('AI 한글명 후보')
    expect(away1.text()).toContain('NULL')
    expect(away1.text()).toContain('NOT_FOUND')
    expect(away1.text()).toContain('전방 압박 가담 빈도가 높습니다.')

    expect(wrapper.find('[data-testid="ns02-translation-defects"]').text()).toContain(
      'missing_name_ko:Phil Foden NoKo',
    )
    expect(wrapper.find('[data-testid="ns02-unplaced-list"]').text()).toContain('Phil Foden NoKo')
    expect(wrapper.find('[data-testid="ns02-attempt-0"]').text()).toContain('재생성 유발')
    expect(wrapper.find('[data-testid="ns02-attempt-1"]').text()).toContain('채택')
  })

  it('preserves uncertain injury status and clearly labels mock mode runs', () => {
    const wrapper = mount(PlayerSectionProcessingView, {
      props: {
        processing: makeProcessing({
          workflow_id: 'section_availability',
          mode: 'mock',
          home1: {
            slot_key: 'home1',
            team_side: 'home',
            team_id: 13,
            team_name: '맨체스터 시티',
            player_id: 7101,
            external_player_id: 1100,
            resolution_status: 'resolved',
            original_name: 'Rodri',
            name_ko: '로드리',
            name_source: 'db_ko',
            body: '무릎 점검 · 경기 전 확인 필요',
            unresolved_reason: null,
            evidence: ['src:inj#p1'],
            status: 'doubtful',
            injury: '무릎',
            importance: '중원 핵심',
          },
          home2: null,
          away1: null,
          away2: null,
          regeneration_count: 0,
          regeneration_reason: null,
          adopted_attempt_ordinal: 0,
          unplaced_items: [],
          translation_defects: [],
        }),
      },
    })

    expect(wrapper.find('[data-testid="ns02-mode-badge"]').text()).toContain('모의 시연 (실제 AI 호출 아님)')
    expect(wrapper.find('[data-testid="ns02-slot-home1"]').text()).toContain('doubtful')
    expect(wrapper.find('[data-testid="ns02-slot-home1"]').text()).not.toContain('확정 결장')
  })

  it('renders NS-02 panel and attempt badges inside RunInspector using GET-only requests', async () => {
    const processing = makeProcessing()
    const runDetail = {
      summary: {
        run_id: 'run-ns02-1',
        operation_kind: 'preview',
        environment: 'dev',
        mode: 'live',
        status: 'succeeded',
        quality: 'ready',
        fixture_label: '맨체스터 시티 vs 풀럼',
        requested_at: '2026-11-16T09:00:00+00:00',
        finished_at: '2026-11-16T09:00:05+00:00',
        module_count: 1,
        attempt_count: 2,
        retry_count: 1,
        failure_code: null,
        label: '실제 모델 호출 (live)',
        cancelled_at: null,
      },
      actor_id: '1',
      config_version: 'mp11-v1',
      limits: { model_requests: 18, api_requests: 24 },
      fixture: {
        fixture_id: 9001,
        home_team_id: 13,
        away_team_id: 4,
        home_team_name: '맨체스터 시티',
        away_team_name: '풀럼',
        kickoff_at: '2026-11-20T15:00:00+00:00',
        status_short: 'NS',
        referee: null,
        updated_at: null,
        label: '맨체스터 시티 vs 풀럼',
      },
      modules: [],
      results: [],
      sources: [],
      attempts: [],
      artifacts: [],
      contract_versions: {
        contract: 'mp04-1',
        provider: 'mp02-provider-1',
        module_input: 'mp02-module-input-1',
        preview_document: 'mp04-preview-1',
        inspector: 'mp02-inspector-1',
      },
      inspector_version: 'mp02-inspector-1',
      mode_detail: {
        mode: 'live',
        label: '실제 모델 호출 (live)',
        note: '실제 공급자 응답입니다.',
      },
      approval_note: '테스트 승인 안내',
      section_approvals: [],
      section_result_id: 'sec-res-1',
      section_results: [
        {
          result_id: 'sec-res-1',
          workflow_id: 'section_players',
          workflow_version: 'mp11-section-players-1',
          module_execution_ids: ['mod-exec-1'],
          result_ids: ['mod-res-1'],
          title: '주목 선수',
          body: '이번 경기의 주목 선수 3명입니다.\n\n선정 선수: 엘링 홀란드\n선정 이유: 박스 안 마무리 능력이 뛰어납니다.',
          version: 1,
          mode: 'live',
          quality: 'ready',
          unavailable_reason: null,
          diagnostics: [],
          sources: [],
          structured: { processing },
          player_section_processing: processing,
          created_at: '2026-11-16T09:00:05+00:00',
        },
      ],
      inspector_modules: [
        {
          inspector_version: 'mp02-inspector-1',
          module_execution_id: 'mod-exec-1',
          module_id: 'bundle_section_players',
          panel: {
            panel: 'generic',
            registered: true,
            display_name: '주목 선수 작성기',
            mode_scope: ['live', 'mock'],
            available: true,
            unrunnable_reason: null,
          },
          run_mode: {
            mode: 'live',
            label: '실제 모델 호출 (live)',
            note: '실제 공급자 응답입니다.',
          },
          status: 'succeeded',
          quality: 'ready',
          attempt_count: 2,
          retry_count: 1,
          result_versions: [1],
          started_at: '2026-11-16T09:00:00+00:00',
          finished_at: '2026-11-16T09:00:05+00:00',
          player_section_processing: processing,
          tabs_meta: [
            { id: 'request', label: '요청', description: '' },
            { id: 'response', label: '원문 응답', description: '' },
            { id: 'transform', label: '정규화 변환', description: '' },
            { id: 'next_input', label: '다음 입력', description: '' },
          ],
          tabs: {
            request: { available: true, attempts: [], note: null },
            response: {
              available: true,
              attempts: [
                {
                  attempt_id: 'att-0',
                  logical_call_id: 'section_players',
                  attempt_ordinal: 0,
                  outcome: 'ok',
                  http_status: 200,
                  error_class: null,
                  error_message: null,
                  usage: { input_tokens: 100, output_tokens: 50, search_queries: null },
                  content: {
                    artifact_id: 'art-0',
                    kind: 'raw_response',
                    sha256: '0'.repeat(64),
                    size_bytes: 64,
                    truncated: false,
                    body: '{"players":[{"selected_player":"Erling Haaland","selection_reason":""}]}',
                    created_at: '2026-11-16T09:00:01+00:00',
                  },
                },
                {
                  attempt_id: 'att-1',
                  logical_call_id: 'section_players',
                  attempt_ordinal: 1,
                  outcome: 'ok',
                  http_status: 200,
                  error_class: null,
                  error_message: null,
                  usage: { input_tokens: 120, output_tokens: 80, search_queries: null },
                  content: {
                    artifact_id: 'art-1',
                    kind: 'raw_response',
                    sha256: '1'.repeat(64),
                    size_bytes: 96,
                    truncated: false,
                    body: '{"players":[{"selected_player":"Erling Haaland","selection_reason":"박스 안 마무리 능력이 뛰어납니다."}]}',
                    created_at: '2026-11-16T09:00:04+00:00',
                  },
                },
              ],
              note: null,
            },
            transform: {
              available: true,
              result_id: 'mod-res-1',
              version: 1,
              status: 'succeeded',
              quality: 'ready',
              failure_code: null,
              claims: [],
              diagnostics: [],
              payload: { processing },
              note: null,
            },
            next_input: {
              available: false,
              target_module_id: null,
              selected_result_ids: [],
              uses_latest_version: false,
              latest_result_id: null,
              latest_result_version: null,
              values: [],
              note: null,
            },
          },
          result_versions_retained: true,
          raw_unavailable_reason: null,
        },
      ],
      registry: {
        registry_version: 'mp02-registry-1',
        contract_version: 'mp02-1',
        inspector_version: 'mp02-inspector-1',
        modules: [],
        implemented: ['bundle_section_players'],
        unavailable: [],
      },
      approvals: {
        contract_version: 'mp02-approval-1',
        workflows: {},
        approved: [],
        unapproved: ['section_players'],
        scope_note: '승인 단위는 섹션 워크플로우입니다.',
      },
      section_workflows: {
        workflows: [],
        implemented: ['section_players'],
        unavailable: [],
        approval_scope_note: '승인 단위는 섹션 워크플로우입니다.',
      },
      mock_demo_module_id: 'mock_demo',
      availability_note: '테스트 가용 안내',
      undo: {
        state: 'cancellable',
        cancelled_at: null,
        cancelled_by_actor_id: null,
        reason: null,
        can_cancel: false,
        blocked_reason: null,
      },
    }

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      const method = (init?.method ?? 'GET').toUpperCase()
      expect(method).toBe('GET')
      if (url.includes('/versions')) {
        return new Response(
          JSON.stringify({ detail: 'not needed in test' }),
          { status: 404, headers: { 'Content-Type': 'application/json' } },
        )
      }
      return new Response(JSON.stringify(runDetail), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    setAccessToken('test-token')

    const wrapper = mount(RunInspector, {
      props: { runId: 'run-ns02-1' },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="player-section-processing"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ns02-slot-home1"]').text()).toContain('엘링 홀란드')

    const responseTab = wrapper.find('[data-testid="tab-response"]')
    expect(responseTab.exists()).toBe(true)
    await responseTab.trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="attempt-regeneration-badge"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="attempt-adopted-badge"]').exists()).toBe(true)
    expect(
      fetchMock.mock.calls.every((call) => ((call[1]?.method ?? 'GET').toUpperCase() === 'GET')),
    ).toBe(true)
  })
})
