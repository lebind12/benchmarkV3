import { apiUrl } from './base'
import { homeRecommendationsSchema } from './homeRecommendationsSchema'
import { homePreviewResponseSchema } from './homePreviewResponse'

async function get(path: string, signal?: AbortSignal) {
  const response = await fetch(apiUrl(path), { signal })
  if (!response.ok) throw new Error(`home_preview_http_${response.status}`)
  return response.json()
}
export async function getHomeRecommendations(signal?: AbortSignal) {
  return homeRecommendationsSchema.parse(await get('/api/v1/home/recommendations', signal))
}
export async function getHomePreview(fixtureId: number, signal?: AbortSignal) {
  const response = homePreviewResponseSchema.parse(await get(`/api/v1/home/fixtures/${fixtureId}/prematch`, signal))
  if (response.fixture_id !== fixtureId || response.preview?.is_mock === true) throw new Error('invalid_home_preview_publication')
  return response
}
