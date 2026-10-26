const CONFIGURED_API_BASE = (import.meta.env.VITE_BACKEND_URL ?? '').replace(/\/+$/, '')
// Local browsers use the Vite proxy so localhost/127.0.0.1 cookies stay same-origin.
const API_BASE_URL = import.meta.env.DEV && /^https?:\/\/(?:localhost|127\.0\.0\.1)(?::\d+)?$/.test(CONFIGURED_API_BASE)
  ? ''
  : CONFIGURED_API_BASE

export function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path
  if (!API_BASE_URL) return path

  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE_URL}${normalizedPath}`
}

export function apiUrlWithQuery(path: string, params: Record<string, string | number | null | undefined>): string {
  const base = API_BASE_URL || (typeof window === 'undefined' ? 'http://localhost' : window.location.origin)
  const url = new URL(path, base)
  Object.entries(params).forEach(([key, value]) => {
    if (value != null && value !== '') url.searchParams.set(key, String(value))
  })

  if (API_BASE_URL) return url.toString()

  const query = url.searchParams.toString()
  return query ? `${url.pathname}?${query}` : url.pathname
}
