import { test, expect, type Page } from '@playwright/test'

/**
 * #23 회귀: 다크 모드에서 컴포넌트 배경이 흰색이 아니어야 함.
 * 원인: FixtureDetailView 가 `background: var(--background, #fff)` 로
 * 정의되지 않은 --background 변수에 폴백 → 항상 #fff 렌더.
 * 수정: `var(--color-bg)` 사용 → html.dark 에서 #0b0f17 적용.
 */

async function setDark(page: Page) {
  await page.evaluate(() => {
    document.documentElement.classList.add('dark')
    localStorage.setItem('theme', 'dark')
  })
}

function parseRgb(s: string): [number, number, number] {
  const m = s.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/)
  if (!m) return [255, 255, 255]
  return [Number(m[1]), Number(m[2]), Number(m[3])]
}

function isDarkColor(rgb: string): boolean {
  const [r, g, b] = parseRgb(rgb)
  // 밝기 평균 < 80 이면 어두운 톤
  return (r + g + b) / 3 < 80
}

function isWhiteColor(rgb: string): boolean {
  const [r, g, b] = parseRgb(rgb)
  return r > 240 && g > 240 && b > 240
}

test.describe('dark mode — 컴포넌트 배경 누수 회귀', () => {
  test('FixtureDetailView root 다크모드에서 어두운 배경', async ({ page }) => {
    await page.goto('/fixtures/1000001')
    await setDark(page)
    await page.waitForSelector('[data-testid="fixture-detail-root"]')
    const bg = await page.evaluate(() => {
      const el = document.querySelector(
        '[data-testid="fixture-detail-root"]',
      ) as HTMLElement
      return getComputedStyle(el).backgroundColor
    })
    expect(isWhiteColor(bg)).toBe(false)
    expect(isDarkColor(bg)).toBe(true)
  })

  test('HomeView root 다크모드 어두운 배경', async ({ page }) => {
    await page.goto('/')
    await setDark(page)
    const bg = await page.evaluate(() => {
      // HomeView 자체는 transparent — 페이지 배경은 html / body
      return getComputedStyle(document.body).backgroundColor
    })
    expect(isWhiteColor(bg)).toBe(false)
  })

  test('MatchHeader 다크모드에서 league gradient subtle (border-left = theme-primary)', async ({
    page,
  }) => {
    await page.goto('/fixtures/1000001')
    await setDark(page)
    await page.waitForSelector('[data-testid="match-header"]')
    const borderColor = await page.evaluate(() => {
      const h = document.querySelector(
        '[data-testid="match-header"]',
      ) as HTMLElement
      return getComputedStyle(h).borderLeftColor
    })
    // dark EPL primary = rgb(107, 58, 140)
    expect(borderColor).toBe('rgb(107, 58, 140)')
  })

  test('MatchHeader border-left 두께 ≥ 6px (#24 강도 상향)', async ({ page }) => {
    await page.goto('/fixtures/1000001')
    await page.waitForSelector('[data-testid="match-header"]')
    const w = await page.evaluate(() => {
      const h = document.querySelector(
        '[data-testid="match-header"]',
      ) as HTMLElement
      return parseFloat(getComputedStyle(h).borderLeftWidth)
    })
    expect(w).toBeGreaterThanOrEqual(6)
  })
})
