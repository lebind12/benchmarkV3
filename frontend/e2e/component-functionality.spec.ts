import { test, expect } from '@playwright/test'

/**
 * component-regression-plan.md §2 Functionality axis.
 * 기존 main-home.spec.ts / fixture-detail.spec.ts 가 안 다룬 상호작용.
 */

test.describe('AppHeader navigation', () => {
  test('nav 클릭 시 route 이동', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL('/')
    await page.getByTestId('nav-순위').click()
    await expect(page).toHaveURL(/\/standings/)
    await page.getByTestId('nav-홈').click()
    await expect(page).toHaveURL('/')
  })

  test('theme 토글 → localStorage 즉시 반영', async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => localStorage.removeItem('theme'))
    await page.getByTestId('theme-toggle').click()
    const after = await page.evaluate(() => ({
      hasDark: document.documentElement.classList.contains('dark'),
      stored: localStorage.getItem('theme'),
    }))
    // toggle 직후 localStorage 와 classList 가 일치해야 한다
    expect(after.stored).toBe(after.hasDark ? 'dark' : 'light')
    // localStorage 가 set 됐는지 확인
    expect(after.stored === 'dark' || after.stored === 'light').toBe(true)
  })
})

test.describe('FixtureFilters → store', () => {
  test('league 탭 클릭 시 aria-selected + active 적용', async ({ page }) => {
    await page.goto('/')
    await page
      .waitForSelector('[data-testid^="fixture-card-"]', { state: 'visible' })
      .catch(() => {})
    const eplTab = page.getByTestId('league-tab-39')
    await eplTab.click()
    await expect(eplTab).toHaveAttribute('aria-selected', 'true')
    const allTab = page.getByTestId('league-tab-all')
    await expect(allTab).toHaveAttribute('aria-selected', 'false')
  })

  test('period 토글 클릭 시 active 전환', async ({ page }) => {
    await page.goto('/')
    const day = page.getByTestId('period-day')
    await day.click()
    await expect(day).toHaveAttribute('aria-selected', 'true')
    const week = page.getByTestId('period-week')
    await expect(week).toHaveAttribute('aria-selected', 'false')
    await week.click()
    await expect(week).toHaveAttribute('aria-selected', 'true')
    await expect(day).toHaveAttribute('aria-selected', 'false')
  })
})

test.describe('StandingsBlock / TopPlayersBlock select', () => {
  test('StandingsBlock league select 변경 → [data-league] 갱신', async ({ page }) => {
    await page.goto('/')
    const block = page.getByTestId('standings-block')
    await expect(block).toBeVisible()
    await block.scrollIntoViewIfNeeded()
    const initial = await block.getAttribute('data-league')
    expect(initial).not.toBeNull()
    const target =
      initial === 'premier-league' ? 'champions-league' : 'premier-league'
    const targetId = target === 'champions-league' ? '2' : '39'
    // select 가 panel-scroll 내부라 visible 판정이 까다로움 — force click + dispatch change
    await page.evaluate(
      ({ id }) => {
        const sel = document.querySelector(
          '[data-testid="standings-league-select"]',
        ) as HTMLSelectElement
        sel.value = id
        sel.dispatchEvent(new Event('change', { bubbles: true }))
      },
      { id: targetId },
    )
    await expect(block).toHaveAttribute('data-league', target)
  })

  test('TopPlayersBlock metric/league select 동작', async ({ page }) => {
    await page.goto('/')
    const block = page.getByTestId('top-players-block')
    await expect(block).toBeVisible()
    await page.evaluate(() => {
      const lsel = document.querySelector(
        '[data-testid="topp-league-select"]',
      ) as HTMLSelectElement
      lsel.value = '2'
      lsel.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await expect(block).toHaveAttribute('data-league', 'champions-league')
    await page.evaluate(() => {
      const msel = document.querySelector(
        '[data-testid="topp-metric-select"]',
      ) as HTMLSelectElement
      msel.value = 'assists'
      msel.dispatchEvent(new Event('change', { bubbles: true }))
    })
    const val = await page.evaluate(
      () =>
        (document.querySelector(
          '[data-testid="topp-metric-select"]',
        ) as HTMLSelectElement).value,
    )
    expect(val).toBe('assists')
  })
})

test.describe('CubeCarousel dot navigation', () => {
  test('dot 클릭 시 큐브 회전 (transform 변화)', async ({ page }) => {
    await page.goto('/')
    const cube = page.getByTestId('cube')
    await expect(cube).toBeVisible()
    const before = await cube.evaluate((el) => (el as HTMLElement).style.transform)
    await page.getByTestId('cube-dot-2').click()
    const after = await cube.evaluate((el) => (el as HTMLElement).style.transform)
    expect(after).not.toBe(before)
    await expect(page.getByTestId('cube-dot-2')).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })
})
