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

export type SignupResponse = {
  user: AuthUser
}

export async function signup(payload: SignupPayload): Promise<SignupResponse> {
  const response = await fetch(apiUrl('/api/v1/auth/signup'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = typeof body.detail === 'string' ? body.detail : 'signup_failed'
    throw new Error(detail)
  }

  return response.json()
}
