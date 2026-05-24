import { expect, test } from '@playwright/test'

test.describe('broadcast alert design lab', () => {
  test('renders ten wide alert prototypes in a vertical list', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 })
    await page.goto('/broadcast-alert-lab.html')

    await expect(page.getByTestId('alert-lab-page')).toBeVisible()
    await expect(page.getByTestId('alert-variant-list')).toBeVisible()
    await expect(page.getByTestId('alert-variant-tile')).toHaveCount(10)

    const variants = await page
      .getByTestId('alert-variant-tile')
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('data-variant')))
    expect(new Set(variants).size).toBe(10)

    await expect(page.getByText('Bottom-left Alert Zone')).toBeVisible()
    await expect(page.getByText('Sponsor-tagged Event')).toBeVisible()

    const scrollHeight = await page.getByTestId('alert-lab-page').evaluate((node) => node.scrollHeight)
    expect(scrollHeight).toBeGreaterThan(1080)
  })
})
