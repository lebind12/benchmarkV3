/**
 * MP-01 관리자 접근 E2E.
 *
 * 실제 백엔드와 실제 로컬 PostgreSQL을 사용한다. 네트워크 모킹으로 통과시키지
 * 않는다. 자격 증명은 환경변수로만 받는다.
 *
 * 케이스 이름은 실제로 검사하는 범위와 일치시킨다. USER/STREAMER 거부는 백엔드
 * 테스트(test_admin_access.py)가 서버 판정으로 검사한다. 여기서는 프론트가 실제
 * 401/403 응답을 올바로 처리하는지만 본다.
 */
import { expect, test } from '@playwright/test'

const ADMIN_EMAIL = process.env.PREVIEW_E2E_ADMIN_EMAIL ?? 'admin@local.test'
const ADMIN_PASSWORD = process.env.PREVIEW_E2E_ADMIN_PASSWORD ?? ''
const SHOT_DIR = process.env.PREVIEW_E2E_SHOT_DIR ?? '../docs/implementation/match-preview/evidence'

test.beforeAll(() => {
  if (!ADMIN_PASSWORD) {
    throw new Error(
      'PREVIEW_E2E_ADMIN_PASSWORD is required; run the local admin tool first and export the password',
    )
  }
})

test('admin logs in through the form, sees the empty run list, and logs out', async ({ page }) => {
  await page.goto('/admin/runs')
  await expect(page).toHaveURL(/\/admin\/login$/)

  await page.screenshot({ path: `${SHOT_DIR}/ui-01-login.png`, fullPage: true })

  await page.getByTestId('login-email').fill(ADMIN_EMAIL)
  await page.getByTestId('login-password').fill('wrong-password-value')
  await page.getByTestId('login-submit').click()
  await expect(page.getByTestId('login-error')).toHaveText(
    '이메일 또는 비밀번호가 올바르지 않습니다.',
  )

  await page.getByTestId('login-password').fill(ADMIN_PASSWORD)
  await page.getByTestId('login-submit').click()
  await expect(page).toHaveURL(/\/admin\/runs$/)

  await expect(page.getByTestId('runs-empty')).toBeVisible()
  await expect(page.getByTestId('runs-empty')).toContainText('아직 실행 기록이 없습니다')
  await page.screenshot({ path: `${SHOT_DIR}/ui-02-runs-empty.png`, fullPage: true })

  await page.getByTestId('logout').click()
  await expect(page).toHaveURL(/\/admin\/login$/)

  await page.goto('/admin/runs')
  await expect(page).toHaveURL(/\/admin\/login$/)
})

test('a cleared session cookie sends the admin back to the login screen', async ({
  page,
  context,
}) => {
  test.info().annotations.push({
    type: 'coverage',
    description:
      'Browser-side handling of a missing session. Server-side expiry is covered by test_expired_session_is_denied.',
  })

  await page.goto('/admin/login')
  await page.getByTestId('login-email').fill(ADMIN_EMAIL)
  await page.getByTestId('login-password').fill(ADMIN_PASSWORD)
  await page.getByTestId('login-submit').click()
  await expect(page).toHaveURL(/\/admin\/runs$/)

  const cookies = await context.cookies()
  const sessionCookie = cookies.find((cookie) => cookie.name === 'preview_admin_session')
  expect(sessionCookie?.httpOnly).toBe(true)

  await context.clearCookies()
  await page.reload()
  await expect(page).toHaveURL(/\/admin\/login$/)
})

test('the app renders the server 403 for a non-admin role instead of an empty list', async ({
  page,
}) => {
  test.info().annotations.push({
    type: 'coverage',
    description:
      'Browser handling of a 403 response. The response is stubbed because MP-01 has no account-creating UI; real USER/STREAMER denial is proven server-side in tests/preview/test_admin_access.py.',
  })

  await page.route('**/api/v1/auth/session', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        user_id: '00000000-0000-4000-8000-000000000001',
        email: 'streamer@example.test',
        role: 'streamer',
        session_id: '00000000-0000-4000-8000-000000000002',
        expires_at: new Date(Date.now() + 3600_000).toISOString(),
      }),
    })
  })
  await page.route('**/api/v1/admin/preview/runs', async (route) => {
    await route.fulfill({
      status: 403,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'admin role required' }),
    })
  })

  await page.goto('/admin/runs')
  await expect(page.getByTestId('runs-error')).toBeVisible()
  await expect(page.getByTestId('runs-error')).toContainText('관리자 권한이 없는 계정입니다')
})

test('anonymous requests to the protected endpoint are rejected by the server', async ({
  request,
}) => {
  const anonymous = await request.get('/api/v1/admin/preview/runs')
  expect(anonymous.status()).toBe(401)
  expect((await anonymous.json()).detail).toBe('authentication required')
})
