/**
 * NS-03/04 선수·부상 섹션 통합 저장·조회·카드 표시 검사.
 *
 * 확인 대상:
 * - 정본 DB 저장 확인(`persisted=true`) 시 '저장됨' 배지, 미저장 안내 비표시, 사진 URL·번역 후보 상태 표시
 * - 신규 계약 행 누락(`storage_mismatch=true`) 시 '저장 불일치' 배지·경고 표시(기존 payload 숨김 대체 없음)
 * - MatchPreviewBody / toStoredPreviewView: 확정 선수 사진(img), 미확정 선수 한글명 플레이스홀더(사진 URL 없음),
 *   빈 슬롯 생략, `team_side` fallback 좌우 분리, 부상 상태·사유 카드 표시, 레거시 문서 호환
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import MatchPreviewBody from '@/components/home-preview/MatchPreviewBody.vue'
import PlayerSectionProcessingView from '@/features/match-preview/PlayerSectionProcessingView.vue'
import type {
  PlayerSectionProcessingViewData,
  ReaderPreview,
  SectionResultView,
} from '@/features/match-preview/types'
import { homePreviewDocumentSchema, toStoredPreviewView } from '@/lib/api/homePreviewDocument'
import { toMatchPreviewView } from '@/lib/api/previewView'

function baseProcessing(
  overrides: Partial<PlayerSectionProcessingViewData> = {},
): PlayerSectionProcessingViewData {
  return {
    workflow_id: 'section_players',
    fixture_id: 1557474,
    home_team_id: 13,
    away_team_id: 4,
    output_contract_version: 'ns01-watch-players-1',
    persisted: true,
    storage_status: '저장됨',
    storage_mismatch: false,
    storage_error: null,
    mode: 'live',
    ok: true,
    failed_reason: null,
    home1: {
      slot_key: 'home1',
      team_side: 'home',
      team_id: 13,
      team_name: '맨체스터 시티',
      player_id: 533,
      external_player_id: 1100,
      photo_url: 'https://media.api-sports.io/football/players/1100.png',
      translation_candidate_id: null,
      candidate_review_status: null,
      resolution_status: 'resolved',
      original_name: 'Erling Haaland',
      name_ko: '엘링 홀란드',
      name_source: 'db_ko',
      body: '최근 5경기 6골로 박스 안 결정력이 높습니다.',
      unresolved_reason: null,
      evidence: ['src:stats#p1'],
    },
    home2: null,
    away1: {
      slot_key: 'away1',
      team_side: 'away',
      team_id: 4,
      team_name: '풀럼',
      player_id: null,
      external_player_id: null,
      photo_url: null,
      translation_candidate_id: 'cand-1',
      candidate_review_status: 'pending',
      resolution_status: 'unresolved',
      original_name: 'Academy Prospect',
      name_ko: '아카데미 유망주',
      name_source: 'ai_candidate',
      body: '측면 돌파가 활발합니다.',
      unresolved_reason: 'NOT_FOUND',
      evidence: ['src:stats#p2'],
    },
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
    ...overrides,
  }
}

describe('PlayerSectionProcessingView canonical storage states', () => {
  it('renders persisted=true status, photo_url, and candidate_review_status without pending note', () => {
    const wrapper = mount(PlayerSectionProcessingView, {
      props: { processing: baseProcessing() },
    })

    expect(wrapper.find('[data-testid="ns02-storage-status"]').text()).toBe('저장됨')
    expect(wrapper.find('[data-testid="ns02-pending-note"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="ns02-storage-mismatch"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="ns02-slot-home1"]').text()).toContain(
      'https://media.api-sports.io/football/players/1100.png',
    )
    expect(wrapper.find('[data-testid="ns02-slot-away1"]').text()).toContain('pending')
    expect(wrapper.find('[data-testid="ns02-slot-home2"]').text()).toContain('비어 있음 (NULL)')
  })

  it('renders explicit storage mismatch alert without falling back to legacy payload', () => {
    const wrapper = mount(PlayerSectionProcessingView, {
      props: {
        processing: baseProcessing({
          persisted: false,
          storage_status: 'storage_mismatch',
          storage_mismatch: true,
          storage_error: '정본 테이블(preview_watch_player_sections) 행을 찾지 못했습니다.',
          home1: null,
          away1: null,
        }),
      },
    })

    expect(wrapper.find('[data-testid="ns02-storage-status"]').text()).toBe('저장 불일치')
    expect(wrapper.find('[data-testid="ns02-storage-mismatch"]').text()).toContain(
      '정본 테이블(preview_watch_player_sections) 행을 찾지 못했습니다.',
    )
    expect(wrapper.find('[data-testid="ns02-pending-note"]').exists()).toBe(false)
  })
})

describe('Player/Injury canonical card projection and public document', () => {
  it('renders resolved photo, Korean placeholder without photo URL, omits empty slots, and separates sides via team_side', () => {
    const rawDoc = {
      schema_version: '1.0' as const,
      fixture_id: 1557474,
      status: 'available' as const,
      reason: null,
      saved_at: '2026-11-16T12:00:00Z',
      run_id: '11111111-1111-1111-1111-111111111111',
      complete: true,
      fixture: {
        external_id: 1557474,
        kickoff_at: '2026-11-21T12:30:00Z',
        league: '프리미어리그',
        home: { external_id: 50, name: '홈 표기 불일치', logo_url: null },
        away: { external_id: 36, name: '원정 표기 불일치', logo_url: null },
      },
      headline: '테스트 프리뷰',
      sections: [
        {
          section_result_id: 'sr-players',
          run_id: '11111111-1111-1111-1111-111111111111',
          workflow_id: 'section_players',
          workflow_version: 'ns01-wf',
          version: 1,
          title: '주목 선수',
          body: '선정 선수: 엘링 홀란드\n선정 이유: 최근 5경기 6골\n\n선정 선수: 아카데미 유망주\n선정 이유: 측면 돌파가 활발합니다.',
          sources: [],
          quality: 'ready',
          partial: false,
          created_at: '2026-11-16T12:00:00Z',
          structured: {
            workflow_id: 'section_players',
            players: [
              {
                slot_key: 'home1',
                team_side: 'home',
                team: '맨체스터 시티',
                player: '엘링 홀란드',
                reason: '최근 5경기 6골',
                external_player_id: 1100,
                photo_url: 'https://media.api-sports.io/football/players/1100.png',
                unresolved: false,
              },
              {
                slot_key: 'away1',
                team_side: 'away',
                team: '풀럼',
                player: '아카데미 유망주',
                reason: '측면 돌파가 활발합니다.',
                external_player_id: null,
                photo_url: null,
                unresolved: true,
              },
            ],
          },
        },
        {
          section_result_id: 'sr-injury',
          run_id: '11111111-1111-1111-1111-111111111111',
          workflow_id: 'section_availability',
          workflow_version: 'ns01-wf',
          version: 1,
          title: '부상 및 출전 불확실',
          body: '로드리 (맨체스터 시티): 무릎 점검으로 출전 여부가 불투명합니다.',
          sources: [],
          quality: 'ready',
          partial: false,
          created_at: '2026-11-16T12:00:00Z',
          structured: {
            workflow_id: 'section_availability',
            injuries: [
              {
                slot_key: 'home1',
                team_side: 'home',
                team: '맨체스터 시티',
                player: '로드리',
                status: 'doubtful',
                summary: '무릎 점검 · 중원 영향',
                external_player_id: 44,
                photo_url: 'https://media.api-sports.io/football/players/44.png',
                unresolved: false,
              },
            ],
          },
        },
      ],
    }

    const parsed = homePreviewDocumentSchema.parse(rawDoc)
    const view = toStoredPreviewView(parsed)
    expect(view.players).toHaveLength(2)
    expect(view.injuries).toHaveLength(1)

    const wrapper = mount(MatchPreviewBody, {
      props: { preview: view },
    })

    const imgs = wrapper.findAll('img')
    expect(imgs.map((node) => node.attributes('src'))).toEqual([
      'https://media.api-sports.io/football/players/1100.png',
      'https://media.api-sports.io/football/players/44.png',
    ])
    expect(wrapper.find('[role="img"][aria-label="아카데미 유망주 사진 없음"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('맨체스터 시티')
    expect(wrapper.text()).toContain('풀럼')
    expect(wrapper.text()).toContain('출전 불투명')
    expect(wrapper.text()).toContain('무릎 점검 · 중원 영향')
  })

  it('preserves legacy section projection without adding synthetic team_side', () => {
    const legacyRow: SectionResultView = {
      section_result_id: 'sr-legacy',
      run_id: 'run-legacy',
      workflow_id: 'section_players',
      workflow_version: 'wf-legacy',
      version: 1,
      title: '주목 선수',
      body: '선정 선수: 엘링 홀란\n선정 이유: 골 결정력',
      sources: [],
      mode: 'live',
      mode_label: '실호출',
      environment: 'dev',
      quality: 'ready',
      module_execution_ids: [],
      result_ids: [],
      diagnostics: [],
      unavailable_reason: null,
      unavailable: false,
      output_contract_version: 'mp11-player-picks-1',
      contract_version: 'mp04-section-result-1',
      created_at: null,
      supersedes_section_result_id: null,
      approvable: false,
      available: true,
      structured: {
        players: [{ team: '맨체스터 시티', player: '엘링 홀란', reason: '골 결정력' }],
      },
    }
    const view = toMatchPreviewView({
      run_id: 'run-legacy',
      preview: {
        fixture: {
          fixture_id: 1557474,
          kickoff_at: '2026-11-21T12:30:00Z',
          label: '맨체스터 시티 vs 풀럼',
          league: '프리미어리그',
          home_team_external_id: 50,
          away_team_external_id: 36,
          home_team_logo_url: null,
          away_team_logo_url: null,
        },
        headline: '레거시',
        generated_at: '2026-11-16T12:00:00Z',
        data_as_of: null,
        body: legacyRow.body,
        complete: true,
      } as unknown as ReaderPreview,
      preview_error: null,
      sections: { run_id: 'run-legacy', section_results: [legacyRow] },
      sections_error: null,
      detail: null,
      detail_error: null,
      composed_sections: [],
      composed_error: null,
      fixture: null,
    })
    expect(view.players[0]).toEqual({
      team: '맨체스터 시티',
      player: '엘링 홀란',
      reason: '골 결정력',
      photo_url: null,
      team_external_id: null,
    })
  })
})
