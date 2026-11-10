/**
 * MP-02 검사 화면 브라우저 확인 (격리 환경).
 *
 * 실제 백엔드(:8010)와 전용 로컬 테스트 DB를 쓴다. 응답을 모킹하지 않는다.
 * 계정은 이 테스트 DB에만 만든 합성 관리자이며, 운영 계정이나 사용자의 실제 로그인
 * 세션은 쓰지 않는다. 비밀번호는 환경변수로만 받고 로그에 남기지 않는다.
 *
 * 실행:
 *   PREVIEW_UI_ADMIN_EMAIL=... PREVIEW_UI_ADMIN_PASSWORD=... \
 *   npx playwright test e2e/match-preview-inspector.spec.ts --project=chromium
 */
import { expect, test } from '@playwright/test'

const ADMIN_EMAIL = process.env.PREVIEW_UI_ADMIN_EMAIL ?? ''
const ADMIN_PASSWORD = process.env.PREVIEW_UI_ADMIN_PASSWORD ?? ''
const SHOT_DIR =
  process.env.PREVIEW_UI_SHOT_DIR ?? '../docs/implementation/match-preview/evidence'

test.beforeAll(() => {
  if (!ADMIN_EMAIL || !ADMIN_PASSWORD) {
    throw new Error(
      'PREVIEW_UI_ADMIN_EMAIL and PREVIEW_UI_ADMIN_PASSWORD are required; run scripts/preview_ui_fixture.py against the isolated test database first',
    )
  }
})

async function login(page: import('@playwright/test').Page) {
  await page.goto('/admin/login')
  await page.getByTestId('login-email').fill(ADMIN_EMAIL)
  await page.getByTestId('login-password').fill(ADMIN_PASSWORD)
  await page.getByTestId('login-submit').click()
  await expect(page).toHaveURL(/\/admin\/runs$/)
}

test('the mock run is created by an explicit action and opens in the inspector', async ({
  page,
}) => {
  await login(page)

  // 첫 화면: 저장된 실행 목록. 목록 조회만으로는 실행이 생기지 않는다.
  const before = await page.request.get('/api/v1/admin/preview/runs')
  expect(before.status()).toBe(200)
  const beforeCount = (await before.json()).runs.length

  await page.getByTestId('create-mock-run').click()
  await expect(page.getByTestId('create-notice')).toContainText('외부 호출 0회')

  const after = await page.request.get('/api/v1/admin/preview/runs')
  const afterRuns = (await after.json()).runs
  expect(afterRuns.length).toBe(beforeCount + 1)

  const latest = afterRuns[0]
  expect(latest.mode).toBe('mock')
  expect(latest.operation_kind).toBe('mock_demo')
  expect(latest.label).toContain('mock')

  await expect(page.getByTestId('runs-table')).toBeVisible()
  await page.getByTestId(`open-run-${latest.run_id}`).click()
  await expect(page.getByTestId('run-inspector')).toBeVisible()

  // 실행 방식이 화면에 분명히 표시된다.
  const banner = page.getByTestId('mode-banner')
  await expect(banner).toContainText('모의 실행 (mock, 외부 호출 없음)')
  await expect(banner).toContainText('환경 dev')

  // 요청 탭: 비밀값이 지워진 실제 전송 본문.
  await expect(page.getByTestId('request-body')).toContainText('[REDACTED]')
  await expect(page.getByTestId('request-body')).not.toContainText('mock-token-value')

  // 원문 응답 탭.
  await page.getByTestId('tab-response').click()
  await expect(page.getByTestId('panel-response')).toContainText('recorded_mock_response')
  await expect(page.getByTestId('response-usage')).toContainText('input_tokens=412')

  // 정규화 변환 탭.
  await page.getByTestId('tab-transform').click()
  await expect(page.getByTestId('transform-version')).toHaveText('v2')
  await expect(page.getByTestId('transform-claims')).toContainText('excluded')
  await expect(page.getByTestId('transform-coverage')).toContainText('not_run')

  // 다음 입력 탭.
  await page.getByTestId('tab-next_input').click()
  await expect(page.getByTestId('panel-next-input')).toContainText('adopted_claim_ids')

  await page.screenshot({ path: `${SHOT_DIR}/ui-06-inspector-next-input.png`, fullPage: true })

  // 승인 패널: 승인 단위가 섹션이며, 모의 실행은 승인 근거가 아님을 밝힌다.
  await expect(page.getByTestId('inspector-approval')).toBeVisible()
  await expect(page.getByTestId('section-approvals')).toContainText('section_form')
  await expect(page.getByTestId('inspector-approval')).toContainText('승인 전')
  await expect(page.getByTestId('approval-no-evidence')).toContainText(
    '승인 근거로 쓸 섹션 결과가 아직 없습니다',
  )

  // 버전 비교: 이전 버전이 남아 있다.
  await expect(page.getByTestId('compare-base')).toBeVisible()
  await expect(page.getByTestId('compare-target')).toContainText('v2')

  await page.getByTestId('tab-request').click()
  await page.screenshot({ path: `${SHOT_DIR}/ui-07-inspector-request.png`, fullPage: true })
})

test('stored runs keep secrets out of the trace and reopen with the same id', async ({
  page,
}) => {
  await login(page)

  // `request` 픽스처는 브라우저와 쿠키를 공유하지 않는다. 세션 쿠키를 가진
  // `page.request`로 조회해야 관리자 경계를 통과한다.
  const listing = await page.request.get('/api/v1/admin/preview/runs')
  const runs = (await listing.json()).runs
  expect(runs.length).toBeGreaterThan(0)
  const target = runs[0]

  // 실행 상세 원문에 비밀값 문자열이 없다.
  const detail = await page.request.get(`/api/v1/admin/preview/runs/${target.run_id}`)
  expect(detail.status()).toBe(200)
  const text = await detail.text()
  expect(text).not.toContain('mock-token-value-for-redaction-check')
  expect(text).not.toContain('mock-api-key-value-for-redaction-check')
  expect(text).toContain('[REDACTED]')

  await page.goto('/admin/runs')
  await page.getByTestId(`open-run-${target.run_id}`).click()
  await expect(page.getByTestId('inspector-run-id')).toHaveText(target.run_id)
})

test('a recorded mock run cannot be approved as a real section result', async ({ page }) => {
  await login(page)

  const listing = await page.request.get('/api/v1/admin/preview/runs')
  const target = (await listing.json()).runs[0]

  const attempt = await page.request.post(
    `/api/v1/admin/preview/sections/section_form/approvals`,
    {
      data: {
        run_id: target.run_id,
        section_result_id: '00000000-0000-4000-8000-000000000000',
      },
    },
  )
  expect(attempt.status()).toBe(422)

  const approvals = await page.request.get('/api/v1/admin/preview/approvals')
  const body = await approvals.json()
  // 모의 실행으로는 어떤 섹션도 승인되지 않는다.
  expect(body.approved).toEqual([])
  expect(body.unapproved).toContain('section_form')
  expect(body.scope_note).toContain('섹션 워크플로우')
})

test('the inspector read path makes no external calls from the browser', async ({ page }) => {
  await login(page)

  const calls: string[] = []
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (!['127.0.0.1', 'localhost'].includes(url.hostname)) {
      calls.push(request.url())
    }
  })

  const listing = await page.request.get('/api/v1/admin/preview/runs')
  const target = (await listing.json()).runs[0]
  await page.goto('/admin/runs')
  await page.getByTestId(`open-run-${target.run_id}`).click()
  await expect(page.getByTestId('run-inspector')).toBeVisible()
  await page.getByTestId('tab-transform').click()

  expect(calls).toEqual([])
})
