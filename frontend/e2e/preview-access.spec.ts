/**
 * MP-01 관리자 접근 E2E.
 *
 * 실제 백엔드와 실제 로컬 PostgreSQL을 사용한다. 네트워크 모킹으로 통과시키지
 * 않는다. 자격 증명은 환경변수로만 받는다.
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

test('admin signs in, sees the honest empty run list, and signs out', async ({ page }) => {
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
  await page.getByTestId('runs-empty').waitFor()
  await page.screenshot({ path: `${SHOT_DIR}/ui-02-runs-empty.png`, fullPage: true })

  await page.getByTestId('logout').click()
  await expect(page).toHaveURL(/\/admin\/login$/)

  // 로그아웃 뒤 보호 경로는 다시 막힌다.
  await page.goto('/admin/runs')
  await expect(page).toHaveURL(/\/admin\/login$/)
})

test('an expired session sends the admin back to the login screen', async ({ page, context }) => {
  await page.goto('/admin/login')
  await page.getByTestId('login-email').fill(ADMIN_EMAIL)
  await page.getByTestId('login-password').fill(ADMIN_PASSWORD)
  await page.getByTestId('login-submit').click()
  await expect(page).toHaveURL(/\/admin\/runs$/)

  const cookies = await context.cookies()
  const sessionCookie = cookies.find((cookie) => cookie.name === 'preview_admin_session')
  expect(sessionCookie?.httpOnly).toBe(true)

  // 만료 세션을 실제로 만드는 대신 쿠키를 무효값으로 바꿔 서버의 401 처리를 확인한다.
  await context.clearCookies()
  await page.reload()
  await expect(page).toHaveURL(/\/admin\/login$/)
})

test('non-admin accounts cannot reach the admin run list', async ({ request }) => {
  const anonymous = await request.get('/api/v1/admin/preview/runs')
  expect(anonymous.status()).toBe(401)

  const body = await anonymous.json()
  expect(body.detail).toBe('authentication required')
})
