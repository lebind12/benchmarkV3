import { apiUrl } from './base'
import type { AuthUser } from './auth'
let accessToken: string | null = null
let refreshPromise: Promise<AuthUser> | null = null
export const setAccessToken = (value: string | null) => { accessToken = value }
export async function refreshSession(): Promise<AuthUser> {
  if (!refreshPromise) refreshPromise = (async () => {
    const response = await fetch(apiUrl('/api/v1/auth/refresh'), { method: 'POST', credentials: 'include' })
    const body = await response.json()
    if (!response.ok) { accessToken = null; throw new Error(typeof body.detail === 'string' ? body.detail : '다시 로그인하세요.') }
    accessToken = body.access_token
    return body.user as AuthUser
  })().finally(() => { refreshPromise = null })
  return refreshPromise
}
export async function authenticatedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  if (!accessToken) await refreshSession()
  const send = () => fetch(apiUrl(path), { ...init, credentials: 'include', headers: { ...Object.fromEntries(new Headers(init.headers)), Authorization: `Bearer ${accessToken}` } })
  let response = await send()
  if (response.status === 401) { await refreshSession(); response = await send() }
  return response
}
export async function logoutSession() {
  try {
    const response = await fetch(apiUrl('/api/v1/auth/logout'), { method: 'POST', credentials: 'include' })
    if (!response.ok) throw new Error('로그아웃에 실패했습니다. 다시 시도하세요.')
  } finally { accessToken = null }
}
