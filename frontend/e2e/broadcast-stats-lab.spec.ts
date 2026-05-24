import { expect, test } from '@playwright/test'

test.describe('broadcast stats design lab', () => {
  test('renders ten structurally distinct stat board prototypes', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 })
    await page.goto('/broadcast-stats-lab.html')

    await expect(page.getByTestId('stats-lab-page')).toBeVisible()
    await expect(page.getByTestId('stats-variant-tile')).toHaveCount(10)

    const variants = await page
      .getByTestId('stats-variant-tile')
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('data-variant')))
    expect(new Set(variants).size).toBe(10)

    await expect(page.getByText('Ribbon Crest')).toBeVisible()
    await expect(page.getByText('Broadcast Tower')).toBeVisible()
  })
})
