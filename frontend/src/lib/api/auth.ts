import { apiUrl } from '@/lib/api/base'
import { setAccessToken } from './session'

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
  access_token?: string
}

async function postAuth(path: string, payload: SignupPayload | LoginPayload, fallbackDetail: string): Promise<AuthUserResponse> {
  const response = await fetch(apiUrl(path), {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = typeof body.detail === 'string' ? body.detail : fallbackDetail
    throw new Error(detail)
  }

  const result = await response.json() as AuthUserResponse
  if (result.access_token) setAccessToken(result.access_token)
  return result
}

export async function signup(payload: SignupPayload): Promise<AuthUserResponse> {
  return postAuth('/api/v1/auth/signup', payload, 'signup_failed')
}

export async function login(payload: LoginPayload): Promise<AuthUserResponse> {
  return postAuth('/api/v1/auth/login', payload, 'login_failed')
}
