import { test, expect, type Page } from '@playwright/test'

/**
 * component-regression-plan.md §2 Size axis.
 * 1280×720 baseline / 1440×900 fit / 1920×1080 generous.
 *
 * 측정은 getBoundingClientRect (border 포함). tolerance 는 box-sizing /
 * 1px 보더 / 서브픽셀 반올림을 흡수하기 위해 ±2-6px.
 */

const VIEWPORTS = [
  { name: '1280', w: 1280, h: 720 },
  { name: '1440', w: 1440, h: 900 },
  { name: '1920', w: 1920, h: 1080 },
] as const

async function rect(page: Page, sel: string) {
  await page.locator(sel).first().waitFor({ state: 'visible' })
  return page.evaluate((s) => {
    const el = document.querySelector(s) as HTMLElement
    const r = el.getBoundingClientRect()
    return { w: Math.round(r.width), h: Math.round(r.height), top: Math.round(r.top), left: Math.round(r.left) }
  }, sel)
}

for (const v of VIEWPORTS) {
  test.describe(`size @ ${v.name}`, () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize({ width: v.w, height: v.h })
    })

    test('AppHeader = 56px content + 1px border', async ({ page }) => {
      await page.goto('/')
      const h = await rect(page, '[role="banner"]')
      // CSS height 56px + border-bottom 1px (content-box default) → 57
      expect(h.h).toBeGreaterThanOrEqual(56)
      expect(h.h).toBeLessThanOrEqual(57)
      expect(h.top).toBe(0)
    })

    test('HomeView grid 25/50/25 (content area, after app-container padding)', async ({
      page,
    }) => {
      await page.goto('/')
      const home = await rect(page, '[data-testid="home-view"]')
      const left = await rect(page, '[data-testid="left-panel"]')
      const center = await rect(page, '[data-testid="center-panel"]')
      const right = await rect(page, '[data-testid="right-panel"]')
      // height: ui-standards §2.3 calc(100vh - 56). border 등 흡수 위해 ±2
      expect(Math.abs(home.h - (v.h - 56))).toBeLessThanOrEqual(2)
      // app-container 의 padding 만큼 panel 합 < home.w 이므로 ratio 로 검증
      // left ≈ right (대칭)
      expect(Math.abs(left.w - right.w)).toBeLessThanOrEqual(2)
      // center ≈ 2 × left
      expect(Math.abs(center.w - left.w * 2)).toBeLessThanOrEqual(2)
      // 합이 home.w 와 정확히 padding-inline × 2 만큼 차이
      const padInline =
        v.w >= 1920 ? 48 : v.w >= 1440 ? 32 : 16
      expect(
        Math.abs(left.w + center.w + right.w - (home.w - padInline * 2)),
      ).toBeLessThanOrEqual(2)
    })

    test('LeftPanel = logo 30% + cube 70% vertical', async ({ page }) => {
      await page.goto('/')
      const panel = await rect(page, '[data-testid="left-panel"]')
      const logo = await rect(page, '[data-testid="left-logo"]')
      const cube = await rect(page, '[data-testid="left-cube"]')
      // logo 30% + cube 70% ≈ panel.h (border-bottom 1px 흡수 위해 ±2)
      expect(Math.abs(logo.h + cube.h - panel.h)).toBeLessThanOrEqual(2)
      const ratio = logo.h / panel.h
      expect(ratio).toBeGreaterThan(0.28)
      expect(ratio).toBeLessThan(0.32)
    })

    test('FixtureDetailView root height + MatchHeader ≈ 25vh', async ({
      page,
    }) => {
      await page.goto('/fixtures/1000001')
      await page.waitForSelector('[data-testid="match-header"]')
      const root = await rect(page, '[data-testid="fixture-detail-root"]')
      const header = await rect(page, '[data-testid="match-header"]')
      // root: calc(100vh - 56), ±2 tolerance
      expect(Math.abs(root.h - (v.h - 56))).toBeLessThanOrEqual(2)
      // header 25vh: 콘텐츠 자연 높이 / line-height 로 실제 다소 클 수 있음.
      // 0.2*vh ~ 0.35*vh 범위 안에 있는지 확인 (intent 가 ~25vh)
      const ratio = header.h / v.h
      expect(ratio).toBeGreaterThan(0.2)
      expect(ratio).toBeLessThan(0.35)
    })
  })
}
