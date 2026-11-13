/**
 * PF-F: 저장된 본문(MatchPreviewBody)의 섹션 중복 표시 검사.
 *
 * 사용자가 관리자 화면에서 본 결함: 주목 선수 카드 **뒤에** `주목 선수` 제목과
 * "이번 경기의 주목 선수 4명입니다." 문장이 한 번 더 나오고, AI 전망 카드 뒤에도
 * `AI 경기 전망` 제목과 전망 근거가 다시 나온다.
 *
 * 수용 기준(계획 PF-F): 주목 선수와 AI 전망의 제목·본문이 각각 한 번만 표시되고,
 * 카드가 쓰지 않은 의미 있는 문장(도입 문장)은 같은 섹션 안에 남는다. 배당 값이 없으면
 * 표를 만들지 않고 사유만 관리자 진단에 남기며, 값이 있으면 저장된 1X2 표를 그대로 쓴다.
 *
 * 실패하면 사용자는: 같은 선수·전망을 두 번 읽고, 어느 쪽이 저장된 결론인지 알 수 없다.
 *
 * 서버·DB·모델을 부르지 않는다. 실제 저장본(`run 6c2ce4c2…`, reader/section-results 응답)의
 * 모양을 그대로 옮긴 고정 입력만 쓴다.
 */
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * 구성본 경로(`getPreviewRun`)는 기존 API 함수만 쓴다. 이 검사는 네트워크 없이
 * 그 **호출 횟수와 대상**을 관측해야 하므로 API 표면만 대역으로 바꾼다.
 */
const previewApi = vi.hoisted(() => ({
  readerPreview: vi.fn(),
  sectionResults: vi.fn(),
  detail: vi.fn(),
  composition: vi.fn(),
}))
vi.mock('@/features/match-preview/api', () => ({ previewRunsApi: previewApi }))

import MatchPreviewBody from './MatchPreviewBody.vue'
import { toMatchPreviewView } from '@/lib/api/previewView'
import { getPreviewRun } from '@/lib/api/preview'
import type {
  ReaderPreview,
  SectionResultView,
  SectionResultsResponse,
} from '@/features/match-preview/types'
import type { PreviewRunData } from '@/lib/api/preview'

const RUN_ID = '6c2ce4c2-68c5-4d9b-8863-ac068e063c58'

const PLAYERS_INTRO = '이번 경기의 주목 선수 4명입니다.'
const FORECAST_LINE =
  '맨체스터 시티는 최근 리그에서 주춤한 흐름을 보이고 있으나, 풀럼을 상대로 최근 23경기 무패라는 압도적인 역사적 우위를 점하고 있습니다.'
const REASON_ONE = '맨체스터 시티가 홈에서의 강세와 풀럼 상대 압도적인 전적 우위를 바탕으로 경기를 주도할 것입니다.'
const REASON_TWO = '제레미 도쿠의 결장과 수비진의 일부 전력 누수 우려가 있으나, 엘링 홀란드의 결정력을 앞세워 실점 없이 승리를 가져갈 가능성이 높습니다.'

function row(overrides: Partial<SectionResultView>): SectionResultView {
  return {
    section_result_id: `sr-${overrides.workflow_id ?? 'x'}`,
    run_id: RUN_ID,
    workflow_id: 'section_players',
    workflow_version: 'wfv-1',
    version: 1,
    title: '주목 선수',
    body: '',
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
    output_contract_version: 'ocv-1',
    contract_version: 'cv-1',
    created_at: null,
    supersedes_section_result_id: null,
    approvable: false,
    ...overrides,
  }
}

/** 실제 저장본과 같은 구성: 네 섹션 본문 + 배당 섹션은 값 없이 사유만 저장됐다. */
function savedSections(
  options: { odds?: boolean; oddsTimeKey?: 'observedAt' | 'observed_at' } = {},
): SectionResultsResponse {
  const oddsRow = options.odds
    ? row({
        section_result_id: 'sr-odds',
        workflow_id: 'section_odds',
        title: '배당 현황',
        body: '## 배당 현황\n- Bet365: 홈 1.35 / 무 5.20 / 원정 8.00',
        // 서버가 주는 모양 그대로: 구조 값은 `structured`, 표시 가능 여부는 행의 `available`이다.
        available: true,
        structured: {
          odds: [
            {
              bookmaker: 'Bet365',
              home: '1.35',
              draw: '5.20',
              away: '8.00',
              // 서버 정본은 `observedAt`이다. 저장 payload 표기(`observed_at`)도 함께 온다.
              [options.oddsTimeKey ?? 'observedAt']: ODDS_OBSERVED_AT,
            },
          ],
        },
      })
    : row({
        section_result_id: 'sr-odds',
        workflow_id: 'section_odds',
        title: '배당 현황',
        body: '',
        quality: 'insufficient',
        unavailable: true,
        unavailable_reason: ODDS_REASON,
        available: false,
        structured: {},
      })
  return {
    run_id: RUN_ID,
    section_results: [
      row({
        section_result_id: 'sr-players',
        workflow_id: 'section_players',
        title: '주목 선수',
        body: `${PLAYERS_INTRO}\n\n선정 선수: 엘링 홀란드\n선정 이유: 리그 10경기 9골.\n\n선정 선수: 라얀 셰르키\n선정 이유: 5골 2도움.\n\n선정 선수: 조슈아 킹\n선정 이유: 복귀를 목표로 합니다.\n\n선정 선수: 오스카 보브\n선정 이유: 친정팀 상대.`,
        available: true,
        // 응답 키는 서버가 옮긴 이름(`player`/`reason`)이다. 저장 payload의
        // `selected_player`/`selection_reason`은 서버가 이 이름으로 옮겨 내려준다.
        structured: {
          players: [
            { player: '엘링 홀란드', reason: '리그 10경기 9골.', team: '맨체스터 시티' },
            { player: '라얀 셰르키', reason: '5골 2도움.', team: '맨체스터 시티' },
            { player: '조슈아 킹', reason: '복귀를 목표로 합니다.', team: '풀럼' },
            { player: '오스카 보브', reason: '친정팀 상대.', team: '풀럼' },
          ],
        },
      }),
      row({
        section_result_id: 'sr-availability',
        workflow_id: 'section_availability',
        title: '부상·결장 영향',
        body: '## 부상·결장 영향\n\n확인된 부상·결장 상황만 정리했습니다.',
        available: true,
        structured: {
          injuries: [
            { player: '마크 게히', team: '맨체스터 시티', status: 'doubtful', summary: '엉덩이 부상.' },
          ],
        },
      }),
      row({
        section_result_id: 'sr-outlook',
        workflow_id: 'section_outlook',
        title: '외부 매체 전망',
        body: '## 외부 매체 전망\n- Forebet: 홈 승리 전망.',
        available: true,
        structured: {
          media: [{ publisher: 'Forebet', statement: '홈 승리 전망.' }],
        },
      }),
      row({
        section_result_id: 'sr-forecast',
        workflow_id: 'section_ai_forecast',
        title: 'AI 경기 전망',
        body: `## AI 경기 전망\n${FORECAST_LINE}\n\n### AI 예상 스코어\n2-0\n\n- ${REASON_ONE}\n- ${REASON_TWO}`,
        available: true,
        structured: {
          forecast: { lean: 'home', score: '2-0', reasoning: [REASON_ONE, REASON_TWO] },
        },
      }),
      oddsRow,
    ],
  }
}

const ODDS_OBSERVED_AT = '2026-11-12T09:30:00Z'
const ODDS_REASON = '정규시간 1X2 값이 모두 있는 배당 줄이 없어 이 선택 섹션을 표시하지 않습니다.'

function readerPreview(options: { odds?: boolean } = {}): ReaderPreview {
  return {
    fixture: {
      fixture_id: 1557474,
      home_team_id: 13,
      away_team_id: 4,
      league_id: 39,
      season: 2026,
      kickoff_at: '2026-11-21T12:30:00Z',
      label: '맨체스터 시티 vs 풀럼',
      league: 'Premier League',
      home_team_external_id: 50,
      away_team_external_id: 36,
    },
    headline: '맨체스터 시티 vs 풀럼',
    generated_at: '2026-11-12T10:07:10Z',
    data_as_of: null,
    attribution: { ai_forecast_label: 'AI 전망', ai_forecast_note: '모델 전망' },
    body: '저장된 전체 본문',
    // reader가 고른 섹션. 실제 저장본처럼 값이 없는 배당 섹션은 독자 목록에 없다.
    sections: [
      { section_id: 'section_players', title: '주목 선수', body: '', sources: [], quality: 'ready', partial: false, version: 1 },
      { section_id: 'section_availability', title: '부상·결장 영향', body: '', sources: [], quality: 'ready', partial: false, version: 1 },
      { section_id: 'section_outlook', title: '외부 매체 전망', body: '', sources: [], quality: 'ready', partial: false, version: 1 },
      { section_id: 'section_ai_forecast', title: 'AI 경기 전망', body: '', sources: [], quality: 'ready', partial: false, version: 1 },
      ...(options.odds
        ? [
            {
              section_id: 'section_odds',
              title: '배당 현황',
              body: '## 배당 현황\n- Bet365: 홈 1.35 / 무 5.20 / 원정 8.00',
              sources: [],
              quality: 'ready',
              partial: false,
              version: 1,
            },
          ]
        : []),
    ],
    complete: true,
  }
}

function runData(options: { odds?: boolean } = {}): PreviewRunData {
  return {
    run_id: RUN_ID,
    preview: readerPreview(options),
    preview_error: null,
    sections: savedSections(options),
    sections_error: null,
    // 이 검사는 팀 이름이 저장 라벨과 같아 번역 별칭표가 필요 없다. 상세 응답을 읽지
    // 않으므로 `null`로 둔다(검사하지 않은 응답을 흉내 내지 않는다).
    detail: null,
    detail_error: null,
  }
}

function mountBody(options: { odds?: boolean; oddsTimeKey?: 'observedAt' | 'observed_at' } = {}) {
  const preview = toMatchPreviewView(runData(options))
  const wrapper = mount(MatchPreviewBody, { props: { preview } })
  return { wrapper, preview }
}

/** 화면에 그 문장이 몇 번 나오는지. */
function occurrences(text: string, needle: string): number {
  return text.split(needle).length - 1
}

describe('저장 본문 — 주목 선수·AI 전망은 각각 한 번', () => {
  it('카드 뒤에 같은 제목의 추가 섹션을 만들지 않고, 도입 문장은 주목 선수 섹션 안에 둔다', () => {
    const { wrapper } = mountBody()
    const text = wrapper.text()

    // 제목은 한 번씩만.
    const titles = wrapper.findAll('.mpv-section__title').map((node) => node.text())
    expect(titles.filter((title) => title === '주목 선수').length).toBe(1)
    expect(titles.filter((title) => title === 'AI 경기 전망').length).toBe(1)
    expect(wrapper.find('[data-testid="preview-body-section-section_players"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="preview-body-section-section_ai_forecast"]').exists()).toBe(false)

    // 문장 본문도 한 번씩. 도입 문장은 버리지 않는다(카드 안에서 읽힌다).
    expect(occurrences(text, PLAYERS_INTRO)).toBe(1)
    expect(occurrences(text, FORECAST_LINE)).toBe(1)
    expect(occurrences(text, REASON_ONE)).toBe(1)
    expect(occurrences(text, REASON_TWO)).toBe(1)

    // 선수 카드의 이름·선정 이유는 그대로 남는다(본문 유실 없음). 사진이 없으므로 이름이
    // 사진 자리에도 한 번 더 그려진다(없는 사진을 만들지 않는 규칙). 그래서 카드마다
    // 이름이 정확히 한 번 나오는 것으로 확인한다.
    for (const name of ['엘링 홀란드', '라얀 셰르키', '조슈아 킹', '오스카 보브']) {
      expect(wrapper.findAll('.mpv-entry__name').filter((node) => node.text() === name).length).toBe(1)
    }
    // 도입 문장은 주목 선수 섹션(카드) 안에 있다.
    const playersSection = wrapper.findAll('section').find((node) => node.text().includes(PLAYERS_INTRO))
    expect(playersSection?.text()).toContain('주목 선수')
    expect(playersSection?.text()).toContain('엘링 홀란드')
  })
})

describe('저장 본문 — 배당', () => {
  it('저장된 배당이 없으면 표를 만들지 않고 사유만 관리자 진단 값에 남긴다', () => {
    const { wrapper, preview } = mountBody()

    expect(wrapper.findAll('.mpv-odds__cells').length).toBe(0)
    expect(wrapper.text()).not.toContain('무승부')
    // 사유는 본문이 아니라 진단(표시 모델의 빈 항목)으로 간다.
    expect(preview.missing.join(' / ')).toContain(ODDS_REASON)
    expect(wrapper.text()).not.toContain(ODDS_REASON)
  })

  it('두 선수 섹션의 팀 로고는 같은 값을 쓰되 한쪽이 깨져도 다른 쪽을 지우지 않는다', async () => {
    const preview = toMatchPreviewView({
      run_id: RUN_ID,
      preview: {
        ...readerPreview(),
        fixture: {
          ...readerPreview().fixture,
          home_team_external_id: 50,
          away_team_external_id: 36,
          home_team_logo_url: 'https://media.api-sports.io/football/teams/50.png',
          away_team_logo_url: 'https://media.api-sports.io/football/teams/36.png',
        },
        sections: [
          { section_id: 'section_players', title: '주목 선수', body: '', sources: [], quality: 'ready', partial: false, version: 1 },
          { section_id: 'section_availability', title: '부상·결장', body: '', sources: [], quality: 'ready', partial: false, version: 1 },
        ],
      },
      preview_error: null,
      sections: {
        run_id: RUN_ID,
        section_results: [
          row({
            section_result_id: 'sr-teams-players',
            workflow_id: 'section_players',
            title: '주목 선수',
            body: '주목 선수 본문',
            available: true,
            structured: {
              players: [{ player: '엘링 홀란드', reason: '리그 10경기 9골.', team: '맨체스터 시티' }],
            },
          }),
          row({
            section_result_id: 'sr-teams-injuries',
            workflow_id: 'section_availability',
            title: '부상·결장',
            body: '## 부상·결장 영향',
            available: true,
            structured: {
              injuries: [
                {
                  player: '마크 게히',
                  team: '맨체스터 시티',
                  status: 'doubtful',
                  summary: '엉덩이 부상.',
                  team_external_id: 50,
                },
              ],
            },
          }),
        ],
      },
      sections_error: null,
      detail: null,
      detail_error: null,
    })
    const wrapper = mount(MatchPreviewBody, { props: { preview } })

    // 두 선수 섹션(주목·부상)이 같은 팀 로고를 그린다.
    const before = wrapper.findAll('.mpv-team__head img')
    expect(before.length).toBe(2)

    // 한 섹션 로고의 로드 실패가 다른 섹션 로고를 지우지 않는다.
    // (실패 시 사용자는 주목 선수 카드에서 팀 로고를 보지 못한다.)
    await before[0].trigger('error')
    const after = wrapper.findAll('.mpv-team__head img')
    expect(after.length).toBe(1)
    expect(after[0].attributes('src')).toContain('/teams/50.png')
  })

  it('우세 문구는 확인된 실제 팀명을 쓰고, 확인 불가면 팀명을 지어내지 않는다', () => {
    // 실제 저장본 모양: 경기 라벨에 팀명이 없고 fixture 이름도 홈팀/원정팀 fallback 이다.
    // 구조화 행이 함께 저장한 team + team_external_id 쌍에서 **ID로만** 이름을 찾는다.
    const base = readerPreview()
    const previewData = {
      run_id: RUN_ID,
      preview: {
        ...base,
        fixture: {
          ...base.fixture,
          label: 'fixture 1557474',
          home_team_external_id: 50,
          away_team_external_id: 36,
        },
        sections: [
          { section_id: 'section_availability', title: '부상·결장', body: '', sources: [], quality: 'ready', partial: false, version: 1 },
          { section_id: 'section_ai_forecast', title: 'AI 경기 전망', body: '', sources: [], quality: 'ready', partial: false, version: 1 },
        ],
      },
      preview_error: null,
      sections: {
        run_id: RUN_ID,
        section_results: [
          row({
            section_result_id: 'sr-names',
            workflow_id: 'section_availability',
            title: '부상·결장',
            body: '부상 본문',
            available: true,
            structured: {
              injuries: [
                { player: '마크 게히', team: '맨체스터 시티', status: 'doubtful', summary: '엉덩이.', team_external_id: 50 },
              ],
            },
          }),
          row({
            section_result_id: 'sr-lean',
            workflow_id: 'section_ai_forecast',
            title: 'AI 경기 전망',
            body: `## AI 경기 전망\n${FORECAST_LINE}\n\n### AI 예상 스코어\n2-0\n\n- ${REASON_ONE}`,
            available: true,
            structured: { forecast: { lean: 'home', score: '2-0', reasoning: [REASON_ONE] } },
          }),
        ],
      },
      sections_error: null,
      detail: null,
      detail_error: null,
    }
    const withName = toMatchPreviewView(previewData as never)
    // 외부 ID 50 = 저장된 '맨체스터 시티'. 홈(50)과 정확히 일치하는 행의 이름만 쓴다.
    expect(withName.forecast.lean_label).toBe('맨체스터 시티 우세')

    // 그 팀의 저장 행이 없으면 이름을 지어내지 않고 기존 중립 문구를 유지한다.
    const withoutRow = toMatchPreviewView({
      ...(previewData as never as Record<string, unknown>),
      sections: {
        run_id: RUN_ID,
        section_results: [
          row({
            section_result_id: 'sr-lean-only',
            workflow_id: 'section_ai_forecast',
            title: 'AI 경기 전망',
            body: '## AI 경기 전망\n본문',
            available: true,
            structured: { forecast: { lean: 'home', score: '2-0', reasoning: [] } },
          }),
        ],
      },
    } as never)
    expect(withoutRow.forecast.lean_label).toBe('홈팀 우세')
  })

  it('저장된 1X2 값과 서버가 준 관측 시각을 그대로 표시한다', () => {
    const { wrapper } = mountBody({ odds: true })

    const cells = wrapper.findAll('.mpv-odds__cell dd').map((node) => node.text())
    expect(cells).toEqual(['1.35', '5.20', '8.00'])
    expect(wrapper.text()).toContain('Bet365')

    // 수용 기준: 실제 배당은 출처·관측 시각을 함께 보존한다. 서버 정본 키는 `observedAt`이며
    // 화면은 그 값을 `observed_at` 출력으로 옮긴다.
    // 실패하면 사용자는 배당이 언제 것인지 알 수 없어 현재성을 판단할 수 없다.
    expect(wrapper.get('.mpv-odds__source').text()).toBe(ODDS_OBSERVED_AT)
  })

  it('저장 payload 표기(snake-case)로 온 관측 시각도 계속 읽는다', () => {
    const { wrapper } = mountBody({ odds: true, oddsTimeKey: 'observed_at' })

    expect(wrapper.get('.mpv-odds__source').text()).toBe(ODDS_OBSERVED_AT)
  })
})

/**
 * PF-F-CARDS: 구성본이 고른 **다른 실행의 섹션 결과**로 카드를 그리는 검사.
 *
 * 실제 화면 결함: 재사용 재생성으로 만든 run `493ef4a9…`는 배당 3행은 그려지지만 다른 네
 * 섹션이 reader 본문만 남아 사진 0장·일반 본문 fallback·AI 제목 중복이 재발했다. 그 run의
 * `/section-results`에는 새 배당 1행만 있고, 나머지는 구성본이 원 run `d96fe824…`에서 골랐다.
 *
 * 실패하면 사용자는 새 실행에서 사진·AI 카드를 잃고 같은 본문을 문단으로만 다시 읽는다.
 * 서버·DB·모델을 부르지 않는다(API 대역 + 고정 입력).
 */
describe('저장 본문 — 구성본이 고른 다른 실행의 섹션으로 카드 복구', () => {
  const NEW_RUN = '493ef4a9-0e14-4436-8a97-d6de7ce034a7'
  const OLD_RUN = 'd96fe824-bc38-4402-bb2c-9f16fdee4b3b'

  function ok<T>(data: T) {
    return { ok: true as const, data }
  }

  /** 원 run이 가진 네 섹션 결과(구조화 값 포함). */
  function sourceRows(): SectionResultView[] {
    return [
      row({
        section_result_id: 'src-players',
        run_id: OLD_RUN,
        workflow_id: 'section_players',
        title: '주목 선수',
        body: `${PLAYERS_INTRO}\n\n선정 선수: 엘링 홀란드\n선정 이유: 리그 10경기 9골.`,
        available: true,
        structured: {
          players: [
            {
              player: '엘링 홀란드',
              reason: '리그 10경기 9골.',
              team: '맨체스터 시티',
              team_external_id: 50,
              external_player_id: 1100,
              photo_url: 'https://media.api-sports.io/football/players/1100.png',
            },
          ],
        },
      }),
      row({
        section_result_id: 'src-availability',
        run_id: OLD_RUN,
        workflow_id: 'section_availability',
        title: '부상·결장',
        body: '## 부상·결장 영향',
        available: true,
        structured: {
          injuries: [
            {
              player: '마크 게히',
              team: '맨체스터 시티',
              status: 'doubtful',
              summary: '엉덩이 부상.',
              team_external_id: 50,
              external_player_id: 67971,
              photo_url: 'https://media.api-sports.io/football/players/67971.png',
            },
          ],
        },
      }),
      row({
        section_result_id: 'src-outlook',
        run_id: OLD_RUN,
        workflow_id: 'section_outlook',
        title: '외부 매체 전망',
        body: '## 외부 매체 전망\n- Forebet: 홈 승리 전망.',
        available: true,
        structured: { media: [{ publisher: 'Forebet', statement: '홈 승리 전망.' }] },
      }),
      row({
        section_result_id: 'src-forecast',
        run_id: OLD_RUN,
        workflow_id: 'section_ai_forecast',
        title: 'AI 경기 전망',
        body: `## AI 경기 전망\n${FORECAST_LINE}\n\n### AI 예상 스코어\n2-0\n\n- ${REASON_ONE}`,
        available: true,
        structured: { forecast: { lean: 'home', score: '2-0', reasoning: [REASON_ONE] } },
      }),
    ]
  }

  /** 새 run은 자기 배당 1행만 갖는다(실제 저장 모양). */
  function newRunRows(): SectionResultView[] {
    return [
      row({
        section_result_id: 'new-odds',
        run_id: NEW_RUN,
        workflow_id: 'section_odds',
        title: '배당 현황',
        body: '## 배당 현황',
        available: true,
        structured: {
          odds: [
            { bookmaker: 'Bet365', home: '1.35', draw: '5.20', away: '8.00', observedAt: '2026-11-12' },
            { bookmaker: 'Unibet', home: '1.34', draw: '5.25', away: '8.20', observedAt: '2026-11-12' },
            { bookmaker: 'Pinnacle', home: '1.36', draw: '5.10', away: '8.40', observedAt: '2026-11-12' },
          ],
        },
      }),
    ]
  }

  const SECTION_IDS = [
    'section_players',
    'section_availability',
    'section_outlook',
    'section_ai_forecast',
    'section_odds',
  ]

  function readerForComposedRun(): ReaderPreview {
    return {
      ...readerPreview(),
      sections: SECTION_IDS.map((id) => ({
        section_id: id,
        title: id,
        body: '독자 본문',
        sources: [],
        quality: 'ready',
        partial: false,
        version: 1,
      })),
    }
  }

  function compositionResponse() {
    return ok({
      run_id: NEW_RUN,
      available: true,
      reason: null,
      composition: {
        composition_id: 'cmp-new',
        fixture_id: 1557474,
        items: [
          { section_id: 'section_players', result_id: 'src-players', run_id: OLD_RUN, fixture_id: 1557474, version: 3, workflow_version: 'w3', quality: 'ready', unavailable: false, unavailable_reason: null, body_chars: 100, mode: 'live', created_at: null },
          { section_id: 'section_availability', result_id: 'src-availability', run_id: OLD_RUN, fixture_id: 1557474, version: 1, workflow_version: 'w1', quality: 'ready', unavailable: false, unavailable_reason: null, body_chars: 100, mode: 'live', created_at: null },
          { section_id: 'section_outlook', result_id: 'src-outlook', run_id: OLD_RUN, fixture_id: 1557474, version: 2, workflow_version: 'w2', quality: 'ready', unavailable: false, unavailable_reason: null, body_chars: 100, mode: 'live', created_at: null },
          { section_id: 'section_ai_forecast', result_id: 'src-forecast', run_id: OLD_RUN, fixture_id: 1557474, version: 1, workflow_version: 'w1', quality: 'ready', unavailable: false, unavailable_reason: null, body_chars: 100, mode: 'live', created_at: null },
          { section_id: 'section_odds', result_id: 'new-odds', run_id: NEW_RUN, fixture_id: 1557474, version: 1, workflow_version: 'w1', quality: 'ready', unavailable: false, unavailable_reason: null, body_chars: 100, mode: 'live', created_at: null },
        ],
        refused: [],
        diagnostics: [],
        section_result_ids: ['src-players', 'src-availability', 'src-outlook', 'src-forecast', 'new-odds'],
      },
    })
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('원 실행 행을 정확히 이어받아 사진·AI 카드·배당 3행을 유지하고 AI 제목은 한 번만 그린다', async () => {
    previewApi.readerPreview.mockResolvedValue(ok(readerForComposedRun()))
    previewApi.sectionResults.mockImplementation((runId: string) =>
      Promise.resolve(ok({ run_id: runId, section_results: runId === NEW_RUN ? newRunRows() : sourceRows() })),
    )
    previewApi.composition.mockResolvedValue(compositionResponse())
    previewApi.detail.mockResolvedValue(ok({ results: [] }))

    const data = await getPreviewRun(NEW_RUN)
    const wrapper = mount(MatchPreviewBody, { props: { preview: toMatchPreviewView(data) } })

    const html = wrapper.html()
    // 사진이 카드에 그려진다(reader 본문만 남으면 0장).
    expect(html).toContain('https://media.api-sports.io/football/players/1100.png')
    expect(html).toContain('https://media.api-sports.io/football/players/67971.png')

    // 제목 중복 없음.
    const titles = wrapper.findAll('.mpv-section__title').map((node) => node.text())
    expect(titles.filter((title) => title === 'AI 경기 전망').length).toBe(1)
    expect(titles.filter((title) => title === '주목 선수').length).toBe(1)

    // AI 카드와 배당 3행(새 run의 값).
    expect(wrapper.get('.mpv-prediction__score').text().replace(/\s+/g, '')).toBe('2:0')
    expect(wrapper.findAll('.mpv-odds__cells').length).toBe(3)

    // 같은 원 실행은 한 번만 읽는다.
    expect(previewApi.sectionResults.mock.calls.filter((call) => call[0] === OLD_RUN).length).toBe(1)
  })

  it('선택된 결과 행을 찾지 못하면 기존 reader 본문으로 남기고 사유를 진단에 남긴다', async () => {
    previewApi.readerPreview.mockResolvedValue(ok(readerForComposedRun()))
    previewApi.sectionResults.mockImplementation((runId: string) =>
      Promise.resolve(ok({ run_id: runId, section_results: runId === NEW_RUN ? newRunRows() : [] })),
    )
    previewApi.composition.mockResolvedValue(compositionResponse())
    previewApi.detail.mockResolvedValue(ok({ results: [] }))

    const data = await getPreviewRun(NEW_RUN)
    const view = toMatchPreviewView(data)
    const wrapper = mount(MatchPreviewBody, { props: { preview: view } })

    // 본문 유실 없음 — reader 본문 fallback이 그대로 보인다.
    expect(wrapper.text()).toContain('독자 본문')
    // 사유는 본문이 아니라 표시 모델의 진단 값으로 간다.
    expect(view.missing.join(' / ')).toContain('카드 대신 저장 본문으로')
    expect(wrapper.text()).not.toContain('카드 대신 저장 본문으로')
  })

  it('구성본 조회가 실패해도 본문은 그대로 두고 사유를 진단에 남긴다', async () => {
    previewApi.readerPreview.mockResolvedValue(ok(readerForComposedRun()))
    previewApi.sectionResults.mockImplementation((runId: string) =>
      Promise.resolve(ok({ run_id: runId, section_results: runId === NEW_RUN ? newRunRows() : [] })),
    )
    previewApi.composition.mockResolvedValue({
      ok: false as const,
      kind: 'server' as const,
      status: 503,
      message: '구성본 조회 실패(503)',
    })
    previewApi.detail.mockResolvedValue(ok({ results: [] }))

    const data = await getPreviewRun(NEW_RUN)
    const view = toMatchPreviewView(data)

    expect(view.missing.join(' / ')).toContain('구성본 조회 실패(503)')
    expect(mount(MatchPreviewBody, { props: { preview: view } }).text()).toContain('독자 본문')
  })

  it('이 실행의 행이 모든 섹션을 채우면 구성본을 조회하지 않는다', async () => {
    previewApi.readerPreview.mockResolvedValue(ok(readerPreview()))
    previewApi.sectionResults.mockResolvedValue(ok(savedSections({ odds: true })))
    previewApi.detail.mockResolvedValue(ok({ results: [] }))

    await getPreviewRun(NEW_RUN)

    expect(previewApi.composition).not.toHaveBeenCalled()
  })
})
