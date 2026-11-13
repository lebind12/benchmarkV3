import { describe, expect, it } from 'vitest'
import { homePreviewDocumentSchema, toStoredPreviewView } from '@/lib/api/homePreviewDocument'

/**
 * 홈 저장 문서 계약 검사.
 *
 * 검사 이유(실패 시 사용자 영향): 서버가 문서 없음과 오류를 구분해 보내는데 프론트가
 * 그 둘을 같은 값으로 읽으면, 저장 문서가 없을 때나 조회가 실패했을 때 홈이 엉뚱한
 * 안내를 보여주거나 빈 본문을 그린다. 본문·점수·사진을 표시하려면 섹션과 구조 값이
 * 계약대로 도착해야 한다.
 */

const savedAt = '2026-11-12T12:00:00Z'
const document = {
  schema_version: '1.0' as const,
  fixture_id: 90001,
  status: 'available' as const,
  reason: null,
  reason_text: null,
  saved_at: savedAt,
  run_id: 'run-1',
  complete: true,
  fixture: {
    external_id: 90001,
    kickoff_at: '2026-11-13T11:00:00Z',
    league: '프리미어리그',
    home: { external_id: 50, name: '맨체스터 시티', logo_url: 'https://media.api-sports.io/football/teams/50.png' },
    away: { external_id: 36, name: '풀럼', logo_url: null },
  },
  headline: '주목 선수',
  sections: [
    {
      section_result_id: 's1',
      run_id: 'run-1',
      workflow_id: 'section_players',
      workflow_version: 'v1',
      version: 1,
      title: '주목 선수',
      body: '선정 선수: 홀란드\n선정 이유: 최근 5경기 6골',
      sources: [{ label: '경기 기록', url: 'https://example.test/a' }],
      quality: 'ready',
      partial: false,
      created_at: savedAt,
    },
  ],
}

describe('stored home preview document contract', () => {
  it('accepts a displayable document and keeps the saved clock and body', () => {
    const parsed = homePreviewDocumentSchema.parse(document)
    expect(parsed.status).toBe('available')
    expect(parsed.saved_at).toBe(savedAt)
    expect(parsed.sections[0]!.body).toContain('홀란드')
  })

  it('accepts an explicit absence with its reason and no body', () => {
    const absent = homePreviewDocumentSchema.parse({
      ...document,
      status: 'none',
      reason: 'no_stored_run',
      reason_text: '이 경기의 저장 실행이 없습니다.',
      saved_at: null,
      run_id: null,
      complete: null,
      headline: null,
      sections: [],
    })
    expect(absent.status).toBe('none')
    expect(absent.reason).toBe('no_stored_run')
    expect(absent.sections).toHaveLength(0)
  })

  it('rejects an available document with no body, no clock, or an absence reason', () => {
    const noBody = { ...document, sections: [] }
    const noClock = { ...document, saved_at: null }
    const withReason = { ...document, reason: 'no_stored_run' }
    for (const invalid of [noBody, noClock, withReason]) {
      expect(homePreviewDocumentSchema.safeParse(invalid).success).toBe(false)
    }
  })

  it('rejects absence that smuggles sections, a clock, or no reason', () => {
    const smuggled = { ...document, status: 'none' as const }
    const clocked = { ...document, status: 'none' as const, reason: 'no_stored_run', sections: [], headline: null, complete: null }
    const reasonless = { ...absentDocument(), reason: null }
    for (const invalid of [smuggled, clocked, reasonless]) {
      expect(homePreviewDocumentSchema.safeParse(invalid).success).toBe(false)
    }
  })

  it('rejects a crossed fixture id', () => {
    const crossed = { ...document, fixture_id: 90002 }
    expect(homePreviewDocumentSchema.safeParse(crossed).success).toBe(false)
  })

  it('projects the stored document into the reader view the body component consumes', () => {
    const view = toStoredPreviewView(homePreviewDocumentSchema.parse(document))
    expect(view.fixture.external_id).toBe(90001)
    expect(view.fixture.home.name).toBe('맨체스터 시티')
    expect(view.fixture.away.name).toBe('풀럼')
    expect(view.fixture.home.badge_url).toBe('https://media.api-sports.io/football/teams/50.png')
    // 서버가 주지 않은 로고 주소를 만들지 않는다.
    expect(view.fixture.away.badge_url).toBeNull()
    expect(view.sections.section_players?.body).toContain('홀란드')
    // 저장 본문의 기록된 라벨만 읽어 선수 카드 값을 만든다(다른 문장은 해석하지 않는다).
    expect(view.players.map((row) => row.player)).toEqual(['홀란드'])
  })

  it('keeps the labelled score and saves no empty card for missing sections', () => {
    const withForecast = {
      ...document,
      sections: [
        ...document.sections,
        {
          ...document.sections[0]!,
          section_result_id: 's2',
          workflow_id: 'section_ai_forecast',
          title: 'AI 경기 전망',
          body: '2-2',
          structured: { forecast: { score: '2-2', lean: 'draw', reasoning: ['근거'] } },
        },
      ],
    }
    const view = toStoredPreviewView(homePreviewDocumentSchema.parse(withForecast))
    expect(view.forecast.score).toEqual({ home: 2, away: 2 })
    // 저장되지 않은 섹션의 카드를 만들지 않는다.
    expect(view.sections.section_odds).toBeUndefined()
    expect(view.odds).toHaveLength(0)
  })
})

function absentDocument() {
  return {
    ...document,
    status: 'none' as const,
    reason: 'no_stored_run',
    reason_text: '이 경기의 저장 실행이 없습니다.',
    saved_at: null,
    run_id: null,
    complete: null,
    headline: null,
    sections: [],
  }
}
