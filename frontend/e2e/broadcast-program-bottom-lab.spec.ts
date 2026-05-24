import { expect, test } from '@playwright/test'

test.describe('broadcast program bottom carousel design lab', () => {
  test('renders twenty distinct world cup bottom carousel prototypes', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 })
    await page.goto('/broadcast-program-bottom-lab.html')

    await expect(page.getByTestId('program-bottom-lab-page')).toBeVisible()
    await expect(page.getByTestId('program-bottom-variant-list')).toBeVisible()
    await expect(page.getByTestId('program-bottom-variant-tile')).toHaveCount(20)

    const variants = await page
      .getByTestId('program-bottom-variant-tile')
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('data-variant')))
    expect(new Set(variants).size).toBe(20)

    await expect(page.getByText('Trophy Seal Band')).toBeVisible()
    await expect(page.getByText('Host Cities Map Strip')).toBeVisible()
    await expect(page.getByText('Knockout Bracket Rail')).toBeVisible()
    await expect(page.getByText('Data Ticker Crest')).toBeVisible()

    const scrollHeight = await page
      .getByTestId('program-bottom-lab-page')
      .evaluate((node) => node.scrollHeight)
    expect(scrollHeight).toBeGreaterThan(1080)
  })
})
