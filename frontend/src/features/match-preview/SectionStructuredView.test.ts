/**
 * 섹션 구조화 표시 검사 (PS-04).
 *
 * 이 파일이 확인하는 것:
 * - 선정 선수와 선정 이유를 분리해 보여주고, 팀별로 묶는다.
 * - 부상 상태 표기를 확정 부상으로 바꾸지 않는다.
 * - 매체 예상 스코어가 없는 기사에 점수를 만들어 채우지 않는다.
 * - 배당은 정규시간 1X2 표로만 보여주고, 누락값을 추정하지 않는다.
 * - 구조화 값이 없으면 블록 자체를 만들지 않는다.
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SectionStructuredView from '@/features/match-preview/SectionStructuredView.vue'
import {
  EMPTY_STRUCTURED,
  playersFromBody,
  scoreText,
  structuredFromSectionResult,
  injuryStatusLabel,
} from '@/features/match-preview/sectionStructured'

function structured(overrides: Partial<typeof EMPTY_STRUCTURED> = {}) {
  return { ...EMPTY_STRUCTURED, ...overrides }
}

describe('SectionStructuredView', () => {
  it('keeps player name and selection reason separate, grouped by team', () => {
    const wrapper = mount(SectionStructuredView, {
      props: {
        structured: structured({
          players: [
            { player: '엘링 홀란드', reason: '리그 10경기 9골.', team: 'Manchester City' },
            { player: '오스카 보브', reason: '친정팀 상대 경기력.', team: 'Fulham' },
          ],
        }),
      },
    })

    const rows = wrapper.findAll('[data-testid="structured-player"]')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('엘링 홀란드')
    expect(rows[0].text()).toContain('리그 10경기 9골.')
    expect(rows[1].text()).toContain('오스카 보브')
    // 팀 이름은 별도 표시이며 선수 이름과 합쳐지지 않는다.
    const teams = wrapper.findAll('[data-testid="structured-players-team"]').map((row) => row.text())
    expect(teams).toEqual(['Manchester City', 'Fulham'])
  })

  it('does not turn an unknown injury status into a confirmed absence', () => {
    const wrapper = mount(SectionStructuredView, {
      props: {
        structured: structured({
          injuries: [
            {
              player: '케빈 더브라위너',
              team: 'Manchester City',
              status: 'unknown',
              summary: '보도에 따라 상태가 다릅니다.',
            },
          ],
        }),
      },
    })

    const status = wrapper.get('[data-testid="structured-injury-status"]').text()
    expect(status).toBe('상태 미확인')
    expect(status).not.toContain('결장')
  })

  it('leaves the score cell empty when a media forecast has no score', () => {
    const wrapper = mount(SectionStructuredView, {
      props: {
        structured: structured({
          media: [
            {
              publisher: 'BBC Sport',
              statement: '홈팀이 우세할 것으로 봤습니다.',
              predictedScore: null,
              publishedAt: '2026-11-09',
              url: 'https://www.bbc.com/sport/football/preview',
            },
          ],
        }),
      },
    })

    const row = wrapper.get('[data-testid="structured-media-row"]').text()
    expect(row).toContain('BBC Sport')
    expect(row).toContain('홈팀이 우세')
    // 점수 미제시 기사에 점수를 만들어 넣지 않는다.
    expect(row).not.toContain('예상')
    expect(wrapper.find('[data-testid="structured-odds"]').exists()).toBe(false)
  })

  it('renders only regular-time 1X2 odds and leaves missing values blank', () => {
    const wrapper = mount(SectionStructuredView, {
      props: {
        structured: structured({
          odds: [
            {
              bookmaker: 'example-book',
              observedAt: '2026-11-11T00:00:00+00:00',
              home: '1.72',
              draw: '3.90',
              away: '4.60',
              market: '1X2 full time',
            },
            {
              bookmaker: 'other-book',
              observedAt: null,
              home: '1.80',
              draw: null,
              away: null,
              market: '1X2 full time',
            },
          ],
        }),
      },
    })

    const rows = wrapper.findAll('[data-testid="structured-odds-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('1.72')
    expect(rows[0].text()).toContain('3.90')
    expect(rows[1].text()).toContain('1.80')
    // 없는 무·원정 배당은 대시로 두고 추정하지 않는다.
    expect(rows[1].findAll('td')[1].text()).toBe('—')
    expect(rows[1].findAll('td')[2].text()).toBe('—')
  })

  it('draws nothing when there is no structured value', () => {
    const wrapper = mount(SectionStructuredView, {
      props: { structured: structured() },
    })
    expect(wrapper.find('[data-testid="section-structured"]').exists()).toBe(false)
  })

  it('shows the AI forecast apart from media forecasts', () => {
    const wrapper = mount(SectionStructuredView, {
      props: {
        structured: structured({
          media: [
            {
              publisher: 'BBC Sport',
              statement: '홈팀 우세.',
              predictedScore: '2-0',
              publishedAt: null,
              url: null,
            },
          ],
          forecast: { lean: 'home', score: '2-1', reasoning: ['홈 이점이 있습니다.'], note: null },
        }),
      },
    })

    expect(wrapper.get('[data-testid="structured-media"]').text()).toContain('BBC Sport')
    const forecast = wrapper.get('[data-testid="structured-forecast"]').text()
    expect(forecast).toContain('AI 예상')
    expect(forecast).toContain('홈팀 우세')
    expect(forecast).toContain('2-1')
  })
})

describe('sectionStructured parsers', () => {
  it('reads the recorded player body labels only', () => {
    const body =
      '이번 경기의 주목 선수 2명입니다.\n\n선정 선수: 엘링 홀란드\n선정 이유: 리그 10경기 9골.\n\n선정 선수: 오스카 보브\n선정 이유: 친정팀 상대.'
    expect(playersFromBody(body)).toEqual([
      { player: '엘링 홀란드', reason: '리그 10경기 9골.', team: null },
      { player: '오스카 보브', reason: '친정팀 상대.', team: null },
    ])
  })

  it('does not invent players from an unrelated body', () => {
    expect(playersFromBody('홈팀이 우세합니다.')).toEqual([])
  })

  it('prefers structured payload values over body parsing', () => {
    const view = structuredFromSectionResult({
      body: '선정 선수: 본문선수\n선정 이유: 본문이유',
      structured: {
        players: [{ player: '구조선수', reason: '구조이유', team: 'Manchester City' }],
      },
    })
    expect(view.players).toEqual([
      { player: '구조선수', reason: '구조이유', team: 'Manchester City' },
    ])
  })

  it('keeps unknown injury wording instead of mapping it to absence', () => {
    expect(injuryStatusLabel('unknown')).toBe('상태 미확인')
    expect(injuryStatusLabel('out')).toBe('결장')
    expect(injuryStatusLabel('Questionable')).toBe('출전 불투명')
    expect(injuryStatusLabel('독감')).toBe('독감')
  })

  it('normalizes a score only when it is a real score', () => {
    expect(scoreText('2 - 1')).toBe('2-1')
    expect(scoreText('2:0')).toBe('2-0')
    expect(scoreText(null)).toBeNull()
  })
})
