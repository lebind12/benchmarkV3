import { test, expect } from '@playwright/test'

/**
 * ui-standards §2.1.1 회귀 — 좌우 padding / max-width SSOT.
 *
 * viewport | max-width | padding-inline
 * <1440    | 100%      | 16px
 * 1440-1919| 1376px    | 32px
 * >=1920   | 1632px    | 48px
 */

const ROUTES = [
  { name: 'home', url: '/', selector: '[data-testid="home-view"]' },
  {
    name: 'fixture-detail',
    url: '/fixtures/1000001',
    selector: '[data-testid="fixture-detail-root"]',
  },
] as const

async function readContainer(page: import('@playwright/test').Page, sel: string) {
  await page.locator(sel).waitFor({ state: 'visible' })
  return page.evaluate((s) => {
    const el = document.querySelector(s) as HTMLElement | null
    if (!el) return null
    const cs = getComputedStyle(el)
    const rect = el.getBoundingClientRect()
    return {
      paddingLeft: cs.paddingLeft,
      paddingRight: cs.paddingRight,
      width: Math.round(rect.width),
      maxWidth: cs.maxWidth,
    }
  }, sel)
}

for (const route of ROUTES) {
  test.describe(`responsive-padding @ ${route.name}`, () => {
    test('1280px baseline → padding 16px, full width', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 720 })
      await page.goto(route.url)
      const m = await readContainer(page, route.selector)
      expect(m).not.toBeNull()
      expect(m!.paddingLeft).toBe('16px')
      expect(m!.paddingRight).toBe('16px')
      // max-width not constrained below 1440
      expect(m!.maxWidth === 'none' || m!.maxWidth.endsWith('px') === false).toBe(
        true,
      )
      // width fills viewport (allow ~1px scrollbar tolerance)
      expect(m!.width).toBeGreaterThanOrEqual(1278)
      expect(m!.width).toBeLessThanOrEqual(1280)
    })

    test('1440px → padding 32px, max-width 1376px', async ({ page }) => {
      await page.setViewportSize({ width: 1440, height: 900 })
      await page.goto(route.url)
      const m = await readContainer(page, route.selector)
      expect(m!.paddingLeft).toBe('32px')
      expect(m!.paddingRight).toBe('32px')
      expect(m!.maxWidth).toBe('1376px')
      expect(m!.width).toBeLessThanOrEqual(1376)
    })

    test('1920px generous → padding 48px, max-width 1632px, centered', async ({
      page,
    }) => {
      await page.setViewportSize({ width: 1920, height: 1080 })
      await page.goto(route.url)
      const m = await readContainer(page, route.selector)
      expect(m!.paddingLeft).toBe('48px')
      expect(m!.paddingRight).toBe('48px')
      expect(m!.maxWidth).toBe('1632px')
      expect(m!.width).toBeLessThanOrEqual(1632)
      // centered: (1920 - 1632) / 2 = 144px each side margin
      const left = await page.evaluate((s) => {
        const el = document.querySelector(s) as HTMLElement
        return Math.round(el.getBoundingClientRect().left)
      }, route.selector)
      expect(left).toBeGreaterThanOrEqual(140)
      expect(left).toBeLessThanOrEqual(148)
    })
  })
}
