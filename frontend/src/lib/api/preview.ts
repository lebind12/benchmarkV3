/**
 * 원래 관리 화면의 프리뷰 탭이 쓰는 API 클라이언트.
 *
 * 이 파일은 **얇은 연결**이다. 응답 모양은 `features/match-preview/types.ts`(BI-02 계약)와
 * `fixtures.ts`(FixtureCandidate)를 그대로 재사용하며, 여기서 새 응답 타입을 만들지 않는다.
 * 전송은 원래 benchmark의 JWT 경로를 쓰는 `features/match-preview/api`를 통해 이뤄진다.
 *
 * 지키는 것:
 *
 * - GET 함수는 GET만 보낸다. 진입·새로고침·다시 읽기·번호 확인이 생성으로 바뀌지 않는다.
 * - `generate`는 사용자가 버튼을 누를 때만 호출된다. 이 모듈은 스스로 재전송하지 않으며,
 *   통신 오류를 재시도로 감싸지 않는다(호출자가 실패를 그대로 표시한다).
 * - 실행 하나를 읽는 `getPreviewRun`은 **저장된 행만** 읽는 세 GET을 묶는다. 기존
 *   `preview(readerPreview)`, `sections(sectionResults)`, `run(detail)` 경로를 재사용한다.
 */
import type { ApiResult } from '@/lib/api/http'
import { previewRunsApi } from '@/features/match-preview/api'
import type { FixtureCandidate } from '@/features/match-preview/fixtures'
import type {
  BundlePreviewRunResponse,
  CompositionView,
  ReaderPreview,
  RunDetail,
  SectionResultView,
  SectionResultsResponse,
} from '@/features/match-preview/types'

const BASE = '/api/v1/admin/preview'

/**
 * 실행 하나를 여는 데 필요한 저장 결과.
 *
 * `preview`가 `null`이면 서버에 독자용 결과가 없거나(404) 읽지 못한 것이다. `sections`는
 * 같은 실행의 섹션 결과 응답이며, 화면은 두 값의 **같은 버전**만 섞어 보여준다.
 */
export type PreviewRunData = {
  run_id: string
  preview: ReaderPreview | null
  /** 독자용 결과가 없을 때의 사유(서버 문장 그대로). 없으면 null. */
  preview_error: string | null
  sections: SectionResultsResponse
  /**
   * 섹션 결과 조회가 실패했을 때의 사유(서버·통신 문장 그대로). 없으면 null.
   *
   * 실패를 빈 목록(`section_results: []`)으로 바꾸면 화면이 "저장된 결과가 없다"로
   * 표시해 조회 실패를 자료 없음으로 위장한다. 그래서 사유를 여기에 남기고, 화면은
   * 실제 빈 목록과 조회 실패를 구분해 보여준다.
   */
  sections_error: string | null
  /** 실행 요약·진단. 접힌 영역에서만 연다. */
  detail: RunDetail | null
  detail_error: string | null
  /**
   * 이 실행의 구성본이 **다른 실행에서 고른** 섹션 결과 행.
   *
   * 재사용 재생성으로 만든 새 run은 자기 `/section-results`에 새로 만든 섹션 1건만 갖고,
   * 나머지 섹션은 구성본이 부모 실행 결과를 가리킨다. 그래서 카드(구조화 값·사진)를
   * 그리려면 **선택된 그 결과 행**을 원 실행에서 읽어야 한다. 구성본이 없거나 조회가
   * 실패하면 빈 배열이며 화면은 기존 reader 본문 fallback을 그대로 쓴다.
   * `getPreviewRun`은 항상 이 값을 채운다(선택 필드인 이유는 그 밖의 호출자가 이 실행
   * 요약을 만들 때 구성본 조회를 하지 않아도 되게 하기 위해서다).
   */
  composed_sections?: SectionResultView[]
  /** 구성본에서 다른 실행 결과를 읽지 못했을 때의 사유(진단용). 없으면 null. */
  composed_error?: string | null
}

/** 서버가 준 경기 번호 하나를 읽는다. 없는 번호는 404, 읽기 불가는 503이다. */
export function getPreviewFixture(fixtureId: number): Promise<ApiResult<FixtureCandidate>> {
  return previewRunsApi.fixture(fixtureId)
}

/** 사용자가 명시적으로 누른 생성 요청. 통신 오류를 자동 재전송하지 않는다. */
export function generatePreview(fixtureId: number): Promise<ApiResult<BundlePreviewRunResponse>> {
  return previewRunsApi.runBundle(fixtureId)
}

/**
 * 저장된 실행 결과를 읽는다(GET만).
 *
 * 독자용 본문과 섹션 결과, 실행 상세를 함께 연다. 본문이 없어도 섹션 결과는 그대로
 * 돌려준다(부분 결과를 숨기지 않는다). 실패한 호출은 사유만 남기고 나머지 값을 살린다.
 */
export async function getPreviewRun(runId: string): Promise<PreviewRunData> {
  const [preview, sections, detail] = await Promise.all([
    previewRunsApi.readerPreview(runId),
    previewRunsApi.sectionResults(runId),
    previewRunsApi.detail(runId),
  ])
  const data: PreviewRunData = {
    run_id: runId,
    preview: preview.ok ? preview.data : null,
    preview_error: preview.ok ? null : preview.message,
    sections: sections.ok
      ? sections.data
      : { run_id: runId, section_results: [] },
    // 실패를 빈 목록으로 바꿔 두더라도 사유는 보존한다(화면이 자료 없음과 구분한다).
    sections_error: sections.ok ? null : sections.message,
    detail: detail.ok ? detail.data : null,
    detail_error: detail.ok ? null : detail.message,
    composed_sections: [],
    composed_error: null,
  }
  // 이 실행의 행 목록에 없는 섹션은 구성본이 다른 실행의 결과를 가리킬 수 있다.
  // 그때만 구성본을 조회하고, 선택된 그 결과 행을 원 실행에서 읽는다.
  const composed = await loadComposedSections(runId, data)
  return { ...data, ...composed }
}

/**
 * 구성본이 **다른 실행에서 고른** 섹션 결과 행을 읽는다(저장된 행만, GET만).
 *
 * 새 run은 자기 새 결과 1건만 저장하고 나머지는 구성본이 부모 실행 결과를 가리킨다.
 * 그 행에는 구조화 값(`structured`)이 있어야 카드(사진·배당·AI 제목)가 그려지므로,
 * reader 본문만으로는 카드가 비고 fallback 문단만 남는다(실제 화면에서 관측).
 *
 * 지키는 것:
 *
 * - 구성본이 없거나(`available=false`) 이 실행 행으로 모든 섹션이 채워졌으면 조회하지 않는다.
 * - **선택된 ID만** 읽는다. `result_id`/`run_id`가 있는 항목만 대상이며, 그 섹션의 최신
 *   결과로 바꿔 넣지 않는다(구성본 선택이 정본이다).
 * - 같은 원 실행은 **한 번만** GET한다.
 * - 찾지 못한 항목은 섞지 않고 사유만 남긴다. 화면은 기존 reader 본문 fallback을 유지한다.
 */
async function loadComposedSections(
  runId: string,
  data: PreviewRunData,
): Promise<Pick<PreviewRunData, 'composed_sections' | 'composed_error'>> {
  const local = new Set(
    (data.sections.section_results ?? []).map((row) => row.workflow_id),
  )
  const readerSections = data.preview?.sections ?? []
  // 이 실행에 행이 있고 reader도 본문을 준 섹션은 이미 화면에 있다. 구성본 조회는
  // **행이 없는 섹션**이 구성본에 있을 때만 필요하다.
  const hasReaderOnlyGap = readerSections.some((block) => !local.has(block.section_id))
  if (!hasReaderOnlyGap) return { composed_sections: [], composed_error: null }

  const compositionResponse = await previewRunsApi.composition(runId)
  if (!compositionResponse.ok) {
    return { composed_sections: [], composed_error: compositionResponse.message }
  }
  const composition: CompositionView | null = compositionResponse.data.composition
  if (!compositionResponse.data.available || composition === null) {
    return {
      composed_sections: [],
      composed_error: compositionResponse.data.reason,
    }
  }

  const wanted = (composition.items ?? []).filter(
    (item) => item?.result_id && item?.run_id && !local.has(item.section_id),
  )
  if (wanted.length === 0) return { composed_sections: [], composed_error: null }

  const runIds = [...new Set(wanted.map((item) => item.run_id))]
  const byRun = new Map<string, SectionResultView[]>()
  let failure: string | null = null
  await Promise.all(
    runIds.map(async (sourceRunId) => {
      if (sourceRunId === runId) return
      const response = await previewRunsApi.sectionResults(sourceRunId)
      if (!response.ok) {
        failure ??= response.message
        return
      }
      byRun.set(sourceRunId, response.data.section_results ?? [])
    }),
  )

  const picked: SectionResultView[] = []
  const missing: string[] = []
  for (const item of wanted) {
    const row = (byRun.get(item.run_id) ?? []).find(
      (candidate) => candidate.section_result_id === item.result_id,
    )
    // 선택된 정확한 결과 행만 쓴다. 없으면 그 섹션은 fallback으로 남긴다.
    if (row) picked.push(row)
    else missing.push(item.section_id)
  }
  // 조회는 됐지만 선택된 행을 찾지 못한 경우도 사유를 남긴다(자료 없음으로 숨기지 않는다).
  const reason =
    failure ??
    (missing.length > 0
      ? `구성본이 고른 결과 행을 찾지 못했습니다: ${missing.join(', ')}`
      : null)
  return {
    composed_sections: picked,
    composed_error: picked.length < wanted.length ? reason : null,
  }
}

/** 저장된 실행 목록(최근 순). 실행 이력 확인용 조회다. */
export function listPreviewRuns(): ReturnType<typeof previewRunsApi.list> {
  return previewRunsApi.list()
}

/**
 * 실행 하나의 저장된 구성본. 없으면 서버가 `available=false`와 사유를 준다.
 * 화면은 이 값으로 "어떤 버전을 골라 만들었는지"를 확인한다.
 */
export function getPreviewComposition(runId: string): ReturnType<typeof previewRunsApi.composition> {
  return previewRunsApi.composition(runId)
}

/** 루트 경로 상수. 새 경로를 만들 때 한 곳에서만 쓰도록 노출한다. */
export const PREVIEW_BASE = BASE
