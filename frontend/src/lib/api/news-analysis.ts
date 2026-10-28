import { authenticatedFetch } from './session'

export const ARTICLE_LIMIT = 20000
export const SOURCE_URL_LIMIT = 2048

export interface NewsAnalysisInput { article_text: string; source_url: string }
export interface NewsMention {
  mention: string
  evidence: string
  entity_type: 'team' | 'player'
  status: 'linked' | 'ambiguous' | 'unresolved'
  reason: string
  entity: { id: number; name: string; detail_path: string } | null
}
export interface NewsAnalysisResult { source_url: string; mentions: NewsMention[] }
export type NewsAnalyzer = (input: NewsAnalysisInput, signal: AbortSignal) => Promise<NewsAnalysisResult>

export function validateNewsInput(input: NewsAnalysisInput): string {
  if (!input.article_text.trim()) return '기사 텍스트를 입력하세요.'
  if (input.article_text.length > ARTICLE_LIMIT) return '기사 텍스트는 20,000자까지 입력할 수 있습니다.'
  if (!input.source_url.trim()) return '출처 URL을 입력하세요.'
  if (input.source_url.length > SOURCE_URL_LIMIT) return '출처 URL은 2,048자까지 입력할 수 있습니다.'
  if (/[\u0000-\u0020\u007f\\]/.test(input.source_url)) return '공백·제어문자 없는 HTTP(S) 출처 URL을 입력하세요.'
  try {
    const url = new URL(input.source_url)
    if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password) throw new Error()
  } catch { return 'HTTP 또는 HTTPS 출처 URL을 입력하세요.' }
  return ''
}

export const analyzeNews: NewsAnalyzer = async (input, signal) => {
  const controller = new AbortController()
  const abort = () => controller.abort()
  signal.addEventListener('abort', abort, { once: true })
  if (signal.aborted) controller.abort()
  const timeout = setTimeout(abort, 65000)
  try {
    const response = await authenticatedFetch('/api/v1/admin/management/news/analyze', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(input), signal: controller.signal,
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok) throw new Error(typeof payload?.detail === 'string' ? payload.detail : '입력 내용을 확인하고 다시 시도하세요.')
    return payload as NewsAnalysisResult
  } catch (err) {
    if (controller.signal.aborted) throw new Error('분석을 중단했습니다. 입력을 확인하고 다시 시도하세요.')
    throw err
  } finally {
    clearTimeout(timeout)
    signal.removeEventListener('abort', abort)
  }
}
