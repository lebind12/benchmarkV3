import { z } from 'zod'
import { toMatchPreviewView, type MatchPreviewView } from './previewView'
import type { FixtureCandidate } from '@/features/match-preview/fixtures'
import type { ReaderPreview, SectionResultView } from '@/features/match-preview/types'

/**
 * 홈 추천 경기의 **저장 문서** 공개 계약 (`GET /api/v1/home/fixtures/{id}/document`).
 *
 * 서버는 `preview_dev`에 저장된 실행·섹션·구성본에서 표시 가능한 최신 문서 하나를 골라
 * 본문 표시에 필요한 값만 내려준다. 진단·프롬프트·원문·계정·내부 기본키는 계약에 없다.
 *
 * 지키는 것:
 *
 * - `status: 'none'`은 **문서 없음**이다. 조회 실패(HTTP 503)와 구분하며, 이 응답을
 *   오류로 바꾸지 않는다. 화면은 기존 6시간 안내를 그 경우에만 보여준다.
 * - 본문이 없는 섹션은 서버가 이미 뺐다. 화면은 없는 섹션의 빈 카드를 만들지 않는다.
 * - 구조화 값(`structured`)은 서버가 준 것만 쓴다. 없으면 본문 그대로 그린다.
 */

const time = z.string().datetime({ offset: true })

const sourceSchema = z
  .object({
    label: z.string().optional(),
    url: z.string().nullable().optional(),
    kind: z.string().optional(),
    note: z.string().nullable().optional(),
    observed_at: z.string().nullable().optional(),
  })
  .strict()

const sectionSchema = z
  .object({
    section_result_id: z.string().nullable(),
    run_id: z.string().nullable(),
    workflow_id: z.string(),
    workflow_version: z.string(),
    version: z.number().int().nullable(),
    title: z.string(),
    body: z.string(),
    sources: z.array(sourceSchema),
    quality: z.string().nullable(),
    partial: z.boolean(),
    created_at: time.nullable(),
    /** 서버가 저장 payload에서 옮긴 구조 값. 모양은 소비자가 방어적으로 읽는다. */
    structured: z.unknown().optional(),
  })
  .strict()

const teamSchema = z
  .object({
    external_id: z.number().int().positive(),
    name: z.string(),
    logo_url: z.string().nullable(),
  })
  .strict()

export const homePreviewDocumentSchema = z
  .object({
    schema_version: z.literal('1.0'),
    fixture_id: z.number().int().positive(),
    status: z.enum(['available', 'none']),
    reason: z.string().nullable(),
    reason_text: z.string().nullable().optional(),
    /**
     * 문서 없음일 때의 안내 상태. 서버가 킥오프까지 남은 시간으로 한 값만 정한다.
     * 화면이 시간 비교를 다시 하면 클라이언트 시계에 따라 같은 경기가 다른 문구가 된다.
     */
    absence: z
      .object({
        state: z.enum(['upcoming_overdue', 'upcoming', 'past']),
        remaining_seconds: z.number().int().nullable(),
      })
      .strict()
      .nullable()
      .optional(),
    saved_at: time.nullable(),
    run_id: z.string().nullable(),
    complete: z.boolean().nullable(),
    fixture: z
      .object({
        external_id: z.number().int().positive(),
        kickoff_at: time,
        league: z.string().nullable(),
        home: teamSchema.nullable(),
        away: teamSchema.nullable(),
      })
      .strict()
      .nullable(),
    headline: z.string().nullable(),
    sections: z.array(sectionSchema),
  })
  .strict()
  .superRefine((value, ctx) => {
    const fail = (message: string) => ctx.addIssue({ code: 'custom', message })
    if (value.fixture !== null && value.fixture.external_id !== value.fixture_id) fail('Document fixture mismatch')
    if (value.status === 'available') {
      // 본문 있는 섹션이 하나도 없으면 '표시 가능'이 아니다.
      if (value.sections.length === 0) fail('Available document requires at least one section body')
      if (value.saved_at === null) fail('Available document requires its saved time')
      if (value.run_id === null) fail('Available document requires its run id')
      if (value.reason !== null) fail('Available document has no absence reason')
    } else {
      if (value.sections.length > 0) fail('Absent document must not carry sections')
      if (value.saved_at !== null || value.run_id !== null) fail('Absent document has no saved time or run')
      if (value.reason === null) fail('Absent document requires a reason')
    }
  })

export type HomePreviewDocument = z.infer<typeof homePreviewDocumentSchema>
export type HomePreviewDocumentSection = HomePreviewDocument['sections'][number]

/** 경기 이름. 서버가 준 두 팀 이름만 쓴다(이름을 만들지 않는다). */
function labelOf(document: HomePreviewDocument): string {
  const home = document.fixture?.home?.name
  const away = document.fixture?.away?.name
  return home && away ? `${home} 대 ${away}` : ''
}

/**
 * 저장 문서를 `MatchPreviewBody`가 읽는 표시 모델로 옮긴다.
 *
 * 기존 관리자 경로의 투영(`toMatchPreviewView`)을 **그대로 재사용**해 두 번째 본문
 * 규칙을 만들지 않는다. 그래서 이 함수는 값을 만들지 않고, 공개 응답을 그 투영이 읽는
 * 모양으로 옮기기만 한다. 투영이 읽지 않는 필드(내부 팀 ID·리전 ID·시즌 등)는 내보내지
 * 않으므로 여기서 자리표시자로 채우지 않고 타입 경계에서만 맞춘다.
 */
export function toStoredPreviewView(document: HomePreviewDocument): MatchPreviewView {
  // 공개 계약에는 내부 리그/팀 기본키와 시즌이 **없다**(계약에 넣지 않는다). 투영은 이
  // 값들을 읽지 않고 표시 이름·외부 ID·로고·킥오프만 읽으므로, 값을 지어내지 않고
  // 타입 경계에서만 맞춘다. 내부 ID를 흉내 내는 숫자를 만들면 다른 팀 로고가 나온다.
  const candidate = {
    fixture_id: document.fixture_id,
    league_name: document.fixture?.league ?? null,
    home_team_name: document.fixture?.home?.name ?? null,
    away_team_name: document.fixture?.away?.name ?? null,
    label: labelOf(document),
    kickoff_at: document.fixture?.kickoff_at ?? '',
    status_short: null,
    origin: 'stored_db',
    origin_note: '저장된 프리뷰 문서',
    run_id: document.run_id,
    mode: null,
    selectable: false,
  } as unknown as FixtureCandidate
  const rows = document.sections as unknown as SectionResultView[]
  return toMatchPreviewView({
    run_id: document.run_id ?? '',
    // 공개 응답에는 내부 ID·시즌·귀속 정보가 없다. 아래 투영은 `fixture`의 표시 값
    // (외부 ID·이름·로고·킥오프)과 `sections`만 읽으므로 내부 값은 요구되지 않는다.
    preview: {
      fixture: {
        fixture_id: document.fixture_id,
        kickoff_at: document.fixture?.kickoff_at ?? '',
        label: candidate.label,
        league: document.fixture?.league ?? null,
        home_team_external_id: document.fixture?.home?.external_id ?? null,
        away_team_external_id: document.fixture?.away?.external_id ?? null,
        home_team_logo_url: document.fixture?.home?.logo_url ?? null,
        away_team_logo_url: document.fixture?.away?.logo_url ?? null,
      },
      headline: document.headline ?? '',
      generated_at: document.saved_at ?? '',
      data_as_of: null,
      body: document.sections.map((section) => section.body).join('\n\n'),
      complete: document.complete,
    } as unknown as ReaderPreview,
    preview_error: null,
    sections: { run_id: document.run_id ?? '', section_results: rows },
    sections_error: null,
    detail: null,
    detail_error: null,
    composed_sections: [],
    composed_error: null,
    fixture: candidate,
  })
}
