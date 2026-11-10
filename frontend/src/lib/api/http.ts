/**
 * 관리자 API 공통 전송 계층.
 *
 * 인증은 HttpOnly 세션 쿠키로만 오간다. 토큰을 JS나 URL에 담지 않는다.
 * 모든 오류는 화면이 바로 쓸 수 있는 데이터로 정규화한다.
 */

export type ApiFailureKind = 'unauthenticated' | 'forbidden' | 'server' | 'network' | 'unknown'

export type ApiFailure = {
  ok: false
  kind: ApiFailureKind
  status: number
  message: string
}

export type ApiSuccess<T> = { ok: true; data: T }

export type ApiResult<T> = ApiSuccess<T> | ApiFailure

const DETAIL_MESSAGES: Record<string, string> = {
  'authentication required': '로그인이 필요합니다.',
  'invalid credentials': '이메일 또는 비밀번호가 올바르지 않습니다.',
  'admin role required': '관리자 권한이 없는 계정입니다.',
}

function failureMessage(status: number, detail: string | undefined): string {
  if (detail && DETAIL_MESSAGES[detail]) return DETAIL_MESSAGES[detail]
  if (status === 401) return '로그인이 필요합니다.'
  if (status === 403) return '관리자 권한이 없는 계정입니다.'
  if (status >= 500) return '서버 오류가 발생했습니다. 잠시 후 다시 시도하세요.'
  return '요청을 처리하지 못했습니다.'
}

function classify(status: number): ApiFailureKind {
  if (status === 401) return 'unauthenticated'
  if (status === 403) return 'forbidden'
  if (status >= 500) return 'server'
  return 'unknown'
}

export async function previewRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<ApiResult<T>> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      credentials: 'same-origin',
      headers: {
        ...(init.body ? { 'content-type': 'application/json' } : {}),
        ...init.headers,
      },
    })
  } catch {
    return {
      ok: false,
      kind: 'network',
      status: 0,
      message: '서버에 연결하지 못했습니다. 네트워크 상태를 확인하세요.',
    }
  }

  if (response.status === 204) {
    return { ok: true, data: undefined as T }
  }

  let parsed: unknown = null
  const hasJson = (response.headers.get('content-type') ?? '').includes('application/json')
  if (hasJson) {
    try {
      parsed = await response.json()
    } catch {
      parsed = null
    }
  }

  if (!response.ok) {
    const detail =
      parsed && typeof parsed === 'object' && 'detail' in parsed
        ? String((parsed as { detail: unknown }).detail)
        : undefined
    return {
      ok: false,
      kind: classify(response.status),
      status: response.status,
      message: failureMessage(response.status, detail),
    }
  }

  return { ok: true, data: parsed as T }
}

export const authApi = {
  login(email: string, password: string) {
    return previewRequest<SessionPayload>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
  },
  logout() {
    return previewRequest<void>('/api/v1/auth/logout', { method: 'POST' })
  },
  session() {
    return previewRequest<SessionPayload>('/api/v1/auth/session')
  },
}

export const previewApi = {
  runs() {
    return previewRequest<RunListPayload>('/api/v1/admin/preview/runs')
  },
}

export type SessionPayload = {
  user_id: string
  email: string
  role: string
  session_id: string
  expires_at: string
}

export type RunListPayload = {
  runs: unknown[]
  next_cursor: string | null
}
