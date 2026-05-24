import { expect, test } from '@playwright/test'

test.describe('broadcast scoreboard design lab', () => {
  test('renders ten wide scoreboard prototypes in a vertical list', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 })
    await page.goto('/broadcast-scoreboard-lab.html')

    await expect(page.getByTestId('scoreboard-lab-page')).toBeVisible()
    await expect(page.getByTestId('scoreboard-variant-list')).toBeVisible()
    await expect(page.getByTestId('scoreboard-variant-tile')).toHaveCount(10)

    const variants = await page
      .getByTestId('scoreboard-variant-tile')
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('data-variant')))
    expect(new Set(variants).size).toBe(10)

    await expect(page.getByText('Center Broadcast Bar')).toBeVisible()
    await expect(page.getByText('World Cup Logo Pod')).toBeVisible()
    await expect(page.getByTestId('s6-worldcup-scoreboard')).toContainText('ADDED TIME')
    await expect(page.getByText('VAR/Card Attached')).toBeVisible()

    const scrollHeight = await page.getByTestId('scoreboard-lab-page').evaluate((node) => node.scrollHeight)
    expect(scrollHeight).toBeGreaterThan(1080)
  })
})
