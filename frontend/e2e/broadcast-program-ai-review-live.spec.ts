import { expect, test } from '@playwright/test'

test.describe('broadcast program AI review live backend', () => {
  test.skip(
    process.env.LIVE_AI_REVIEW_E2E !== 'true',
    'Set LIVE_AI_REVIEW_E2E=true to call the local backend and Vertex AI.',
  )

  test('renders AI review generated from fixture 1489371', async ({ page }) => {
    test.setTimeout(120_000)

    await page.addInitScript(() => {
      window.localStorage.setItem('mockRole', 'ADMIN')
    })

    await page.setViewportSize({ width: 1920, height: 1080 })
    await page.goto('/broadcast-program.html?fixtureId=1489371')

    await expect(page.getByTestId('program-stage')).toContainText('브라질', { timeout: 45_000 })
    await expect(page.getByTestId('program-stage')).toContainText('모로코')
    await expect(page.getByTestId('program-stage')).toHaveAttribute(
      'data-active-bottom-view',
      'lineup',
    )

    await page.keyboard.press('Control+X')
    await expect(page.getByTestId('program-stage')).toHaveAttribute(
      'data-active-bottom-view',
      'attack',
    )

    const aiReviewButton = page.getByTestId('program-ai-review-open')
    await expect(aiReviewButton).toBeVisible()
    await expect(aiReviewButton).toBeEnabled()

    const aiReviewResponse = page.waitForResponse(
      (response) =>
        response.url().includes('/api/v1/broadcast/fixtures/1489371/ai-review') &&
        response.request().method() === 'POST',
      { timeout: 90_000 },
    )

    await aiReviewButton.click()
    const response = await aiReviewResponse
    expect(response.status()).toBe(200)

    const panel = page.getByTestId('program-ai-review-panel')
    await expect(panel).toBeVisible()
    await expect(panel).toContainText('AI MATCH REVIEW')
    await expect(panel).not.toContainText('AI 응답 검증 실패', { timeout: 90_000 })
    await expect(panel).toContainText('브라질', { timeout: 90_000 })
    await expect(panel).toContainText('모로코')
    await expect(panel).toContainText('후반 45분 기준')

    const refreshButton = page.getByTestId('program-ai-review-refresh')
    await expect(refreshButton).toBeVisible()
    await expect(refreshButton).toBeEnabled()

    const refreshResponse = page.waitForResponse(
      (refresh) =>
        refresh.url().includes('/api/v1/broadcast/fixtures/1489371/ai-review') &&
        refresh.request().method() === 'POST',
      { timeout: 90_000 },
    )
    await refreshButton.click()
    expect((await refreshResponse).status()).toBe(200)
    await expect(panel).not.toContainText('AI 응답 검증 실패', { timeout: 90_000 })
  })
})
