import { apiUrl } from '@/lib/api/base'

export type AuthUser = {
  id: number
  email: string
  role: 'USER' | 'STREAMER' | 'ADMIN'
  nickname: string | null
  is_active: boolean
}

export type SignupPayload = {
  email: string
  password: string
  nickname?: string
}

export type LoginPayload = {
  email: string
  password: string
}

export type AuthUserResponse = {
  user: AuthUser
}

async function postAuth(path: string, payload: SignupPayload | LoginPayload, fallbackDetail: string): Promise<AuthUserResponse> {
  const response = await fetch(apiUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = typeof body.detail === 'string' ? body.detail : fallbackDetail
    throw new Error(detail)
  }

  return response.json()
}

export async function signup(payload: SignupPayload): Promise<AuthUserResponse> {
  return postAuth('/api/v1/auth/signup', payload, 'signup_failed')
}

export async function login(payload: LoginPayload): Promise<AuthUserResponse> {
  return postAuth('/api/v1/auth/login', payload, 'login_failed')
}
