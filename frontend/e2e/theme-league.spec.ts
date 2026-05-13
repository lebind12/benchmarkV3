import { test, expect, type Page } from '@playwright/test'

/**
 * ui-standards §3 + league-palette.md §8 회귀.
 *
 * - 다크/라이트 토글이 html.dark class 와 --theme-* 토큰 변경에 반영.
 * - 5리그 × 다크/라이트 변형이 leagues.css 의 토큰 hex 와 일치.
 * - [data-league] swap 이 --theme-primary 등을 league 토큰으로 매핑.
 */

const EXPECTED = {
  light: {
    'premier-league': { primary: 'rgb(61, 25, 91)', accent: 'rgb(233, 0, 82)' },
    'champions-league': { primary: 'rgb(1, 0, 86)', accent: 'rgb(154, 0, 255)' },
    'europa-league': { primary: 'rgb(255, 109, 0)', accent: 'rgb(255, 204, 0)' },
    'carabao-cup': { primary: 'rgb(215, 40, 47)', accent: 'rgb(0, 0, 0)' },
    'fa-cup': { primary: 'rgb(1, 30, 65)', accent: 'rgb(212, 175, 55)' },
  },
  dark: {
    'premier-league': { primary: 'rgb(107, 58, 140)', accent: 'rgb(255, 61, 127)' },
    'champions-league': { primary: 'rgb(42, 61, 174)', accent: 'rgb(181, 102, 255)' },
    'europa-league': { primary: 'rgb(255, 140, 51)', accent: 'rgb(255, 214, 51)' },
    'carabao-cup': { primary: 'rgb(232, 80, 79)', accent: 'rgb(255, 255, 255)' },
    'fa-cup': { primary: 'rgb(43, 75, 122)', accent: 'rgb(238, 195, 74)' },
  },
} as const

async function setTheme(page: Page, mode: 'light' | 'dark') {
  await page.evaluate((m) => {
    if (m === 'dark') document.documentElement.classList.add('dark')
    else document.documentElement.classList.remove('dark')
    localStorage.setItem('theme', m)
  }, mode)
}

async function tokensFor(page: Page, league: string) {
  return page.evaluate((slug) => {
    const probe = document.createElement('div')
    probe.setAttribute('data-league', slug)
    // Use color / borderColor so the browser computes rgb() from the CSS var.
    probe.style.cssText =
      'color: var(--theme-primary); border-color: var(--theme-accent); border-style: solid; display: none;'
    document.body.appendChild(probe)
    const cs = getComputedStyle(probe)
    const out = { primary: cs.color, accent: cs.borderColor }
    probe.remove()
    return out
  }, league)
}

test.describe('theme — light/dark toggle', () => {
  test('AppHeader toggle adds html.dark + persists', async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => localStorage.removeItem('theme'))
    await page.reload()
    const before = await page.evaluate(() =>
      document.documentElement.classList.contains('dark'),
    )
    await page.getByTestId('theme-toggle').click()
    const after = await page.evaluate(() => ({
      hasDark: document.documentElement.classList.contains('dark'),
      stored: localStorage.getItem('theme'),
    }))
    expect(after.hasDark).toBe(!before)
    expect(after.stored).toBe(after.hasDark ? 'dark' : 'light')
  })
})

test.describe('theme — 5 league variants × light/dark', () => {
  for (const slug of Object.keys(EXPECTED.light) as Array<keyof typeof EXPECTED.light>) {
    test(`${slug} light tokens`, async ({ page }) => {
      await page.goto('/')
      await setTheme(page, 'light')
      const got = await tokensFor(page, slug)
      expect(got.primary).toBe(EXPECTED.light[slug].primary)
      expect(got.accent).toBe(EXPECTED.light[slug].accent)
    })

    test(`${slug} dark tokens`, async ({ page }) => {
      await page.goto('/')
      await setTheme(page, 'dark')
      const got = await tokensFor(page, slug)
      expect(got.primary).toBe(EXPECTED.dark[slug].primary)
      expect(got.accent).toBe(EXPECTED.dark[slug].accent)
    })
  }
})

test.describe('theme — HomeView per-card / per-block data-league', () => {
  test('StandingsBlock root 에 [data-league] 적용', async ({ page }) => {
    await page.goto('/')
    const block = page.getByTestId('standings-block')
    await expect(block).toBeVisible()
    const slug = await block.getAttribute('data-league')
    expect(slug).toMatch(
      /premier-league|champions-league|europa-league|carabao-cup|fa-cup/,
    )
  })

  test('TopPlayersBlock root 에 [data-league] 적용', async ({ page }) => {
    await page.goto('/')
    const block = page.getByTestId('top-players-block')
    await expect(block).toBeVisible()
    const slug = await block.getAttribute('data-league')
    expect(slug).toMatch(
      /premier-league|champions-league|europa-league|carabao-cup|fa-cup/,
    )
  })

  test('FixtureCard 가 fixture.league.slug 를 data-league 로 적용', async ({
    page,
  }) => {
    await page.goto('/')
    await page.waitForSelector('[data-testid^="fixture-card-"]', {
      state: 'visible',
    })
    const cards = page.locator('[data-testid^="fixture-card-"]')
    const count = await cards.count()
    expect(count).toBeGreaterThan(0)
    for (let i = 0; i < Math.min(count, 5); i++) {
      const slug = await cards.nth(i).getAttribute('data-league')
      expect(slug).toMatch(
        /premier-league|champions-league|europa-league|carabao-cup|fa-cup/,
      )
    }
  })
})

test.describe('theme — FixtureDetailView header reflects league', () => {
  test('EPL fixture root sets data-league=premier-league', async ({ page }) => {
    await page.goto('/fixtures/1000001')
    await page.waitForSelector('[data-testid="fixture-detail-root"]')
    const slug = await page
      .getByTestId('fixture-detail-root')
      .getAttribute('data-league')
    expect(slug).toBe('premier-league')
  })

  test('light: MatchHeader border-left uses --theme-primary (EPL 61,25,91)', async ({
    page,
  }) => {
    await page.goto('/fixtures/1000001')
    await setTheme(page, 'light')
    await page.waitForSelector('[data-testid="match-header"]')
    const borderColor = await page.evaluate(() => {
      const h = document.querySelector(
        '[data-testid="match-header"]',
      ) as HTMLElement
      return getComputedStyle(h).borderLeftColor
    })
    expect(borderColor).toBe('rgb(61, 25, 91)')
  })

  test('dark: MatchHeader border-left switches to dark EPL (107,58,140)', async ({
    page,
  }) => {
    await page.goto('/fixtures/1000001')
    await setTheme(page, 'dark')
    await page.waitForSelector('[data-testid="match-header"]')
    const borderColor = await page.evaluate(() => {
      const h = document.querySelector(
        '[data-testid="match-header"]',
      ) as HTMLElement
      return getComputedStyle(h).borderLeftColor
    })
    expect(borderColor).toBe('rgb(107, 58, 140)')
  })
})
