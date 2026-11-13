import { apiUrl } from './base'
import { homeRecommendationsSchema } from './homeRecommendationsSchema'
import { homePreviewResponseSchema } from './homePreviewResponse'
import { homePreviewDocumentSchema, type HomePreviewDocument } from './homePreviewDocument'

async function get(path: string, signal?: AbortSignal) {
  const response = await fetch(apiUrl(path), { signal })
  if (!response.ok) throw new Error(`home_preview_http_${response.status}`)
  return response.json()
}
export async function getHomeRecommendations(signal?: AbortSignal, date?: string) {
  return homeRecommendationsSchema.parse(await get(`/api/v1/home/recommendations${date ? `?date=${encodeURIComponent(date)}` : ''}`, signal))
}
export async function getHomePreview(fixtureId: number, signal?: AbortSignal) {
  const response = homePreviewResponseSchema.parse(await get(`/api/v1/home/fixtures/${fixtureId}/prematch`, signal))
  if (response.fixture_id !== fixtureId || response.preview?.is_mock === true) throw new Error('invalid_home_preview_publication')
  return response
}

/**
 * 이 경기의 **최신 공개 가능 저장 문서**(`preview_dev`).
 *
 * 문서 없음은 오류가 아니다. 응답의 `status: 'none'`으로 오고 화면은 그때만 6시간
 * 안내를 보여준다. 조회 실패는 예외로 던져 '문서 없음'과 구분한다. GET만 보낸다.
 */
export async function getHomePreviewDocument(fixtureId: number, signal?: AbortSignal): Promise<HomePreviewDocument> {
  const response = homePreviewDocumentSchema.parse(await get(`/api/v1/home/fixtures/${fixtureId}/document`, signal))
  if (response.fixture_id !== fixtureId) throw new Error('invalid_home_preview_document')
  return response
}
