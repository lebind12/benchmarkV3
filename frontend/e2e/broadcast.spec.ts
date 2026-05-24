import { expect, test } from '@playwright/test'

test.describe('broadcast match overlay (mock)', () => {
  test('BMO-E-01 renders 1920x1080 overlay slots', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 })
    await page.goto('/broadcast.html?fixture=260506&league=world-cup-2026')

    await expect(page.getByTestId('broadcast-stage')).toHaveAttribute(
      'data-league',
      'world-cup-2026',
    )
    await expect(page.getByTestId('broadcast-scoreboard')).toBeVisible()
    await expect(page.getByTestId('worldcup-score-strip')).toBeVisible()
    await expect(page.getByTestId('worldcup-added-time')).toContainText('+0')
    await expect(page.getByTestId('country-badge')).toHaveCount(2)
    await expect(page.getByTestId('broadcast-left-column')).toBeVisible()
    await expect(page.getByTestId('worldcup-formation-band')).toHaveCount(2)
    await expect(page.getByTestId('worldcup-formation-band').first()).toBeVisible()
    await expect(page.getByTestId('character-safe-zone')).toBeVisible()
    await expect(page.getByTestId('broadcast-right-column')).toBeVisible()
    await expect(page.getByTestId('event-toast')).toBeVisible()
    await expect(page.getByTestId('stats-country-badge')).toHaveCount(2)
    await expect(page.getByTestId('chat-reserve')).toHaveText('')

    const stageBackground = await page
      .getByTestId('broadcast-stage')
      .evaluate((node) => getComputedStyle(node).backgroundColor)
    expect(stageBackground).toBe('rgb(0, 177, 64)')
  })

  test('BMO-E-02 fixture route bridges to broadcast entry', async ({ page }) => {
    await page.goto('/broadcast/fixtures/1000001?league=champions-league')
    await page.waitForURL('**/broadcast.html?fixture=1000001&league=champions-league')

    await expect(page.getByTestId('broadcast-stage')).toHaveAttribute(
      'data-league',
      'champions-league',
    )
    await expect(page.getByTestId('broadcast-scoreboard')).toContainText('PSG')
  })
})
