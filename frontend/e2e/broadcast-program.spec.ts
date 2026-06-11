import { expect, type Page, test } from '@playwright/test'

function closeTo(actual: number, expected: number, tolerance = 2) {
  expect(Math.abs(actual - expected)).toBeLessThanOrEqual(tolerance)
}

function lineupPlayers(team: 'home' | 'away') {
  const home = [
    ['Kim Seung-Gyu', 1],
    ['Kim Min-Jae', 4],
    ['Lee Jae-Sung', 10],
    ['Son Heung-Min', 7],
    ['Hwang Hee-Chan', 11],
    ['Cho Gue-Sung', 9],
    ['Lee Kang-In', 18],
    ['Jung Woo-Young', 5],
    ['Hwang In-Beom', 6],
    ['Kim Jin-Su', 3],
    ['Kim Moon-Hwan', 2],
  ] as const
  const away = [
    ['Alisson', 1],
    ['Marquinhos', 4],
    ['Thiago Silva', 3],
    ['Casemiro', 5],
    ['Neymar', 10],
    ['Raphinha', 11],
    ['Vinicius Junior', 20],
    ['Richarlison', 9],
    ['Lucas Paqueta', 8],
    ['Danilo', 2],
    ['Alex Sandro', 6],
  ] as const

  return (team === 'home' ? home : away).map(([name, number], index) => ({
    player: {
      id: team === 'home' ? 100 + index : 200 + index,
      name,
      number,
      pos: index === 0 ? 'G' : index < 4 ? 'D' : index < 8 ? 'M' : 'F',
      grid: `${Math.floor(index / 4) + 1}:${(index % 4) + 1}`,
    },
  }))
}

async function mockBroadcastProgramApi(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem('mockRole', 'ADMIN')
  })

  await page.route('**/api/v1/broadcast/translations', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        leagues: { 1: { name_ko: '월드컵', short_name_ko: '월드컵' } },
        teams: {
          10: { name_ko: '대한민국', short_name_ko: '한국' },
          20: { name_ko: '브라질', short_name_ko: '브라질' },
        },
        players: {
          100: { name_ko: '김승규', short_name_ko: '김승규' },
          101: { name_ko: '김민재', short_name_ko: '김민재' },
          102: { name_ko: '이재성', short_name_ko: '이재성' },
          103: { name_ko: '손흥민', short_name_ko: '손흥민' },
          104: { name_ko: '황희찬', short_name_ko: '황희찬' },
          105: { name_ko: '조규성', short_name_ko: '조규성' },
          106: { name_ko: '이강인', short_name_ko: '이강인' },
          107: { name_ko: '정우영', short_name_ko: '정우영' },
          108: { name_ko: '황인범', short_name_ko: '황인범' },
          109: { name_ko: '김진수', short_name_ko: '김진수' },
          110: { name_ko: '김문환', short_name_ko: '김문환' },
          111: { name_ko: '홍현석', short_name_ko: '홍현석' },
          204: { name_ko: '네이마르 주니오르', short_name_ko: '네이마르' },
        },
        coaches: {
          1000: { name_ko: '홍명보', short_name_ko: '홍명보' },
          2000: { name_ko: '카를로 안첼로티', short_name_ko: '안첼로티' },
        },
      }),
    })
  })

  await page.route('**/fixtures?**', async (route) => {
    const url = new URL(route.request().url())
    if (!url.searchParams.has('id')) {
      await route.fallback()
      return
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        response: [{
          fixture: {
            id: Number(url.searchParams.get('id')),
            status: { short: '2H', elapsed: 72, extra: 2 },
            venue: { name: 'Live Stadium' },
          },
          league: { id: 1, name: 'FIFA World Cup', season: 2026 },
          teams: {
            home: { id: 10, name: 'Korea Republic', code: 'KOR', logo: 'https://example.com/korea.png' },
            away: { id: 20, name: 'Brazil', code: 'BRA', logo: 'https://example.com/brazil.png' },
          },
          goals: { home: 1, away: 1 },
        }],
      }),
    })
  })

  await page.route('**/fixtures/events?**', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        response: [
          {
            time: { elapsed: 67 },
            team: { id: 10, name: 'Korea Republic', code: 'KOR' },
            player: { id: 106, name: 'Lee Kang-In' },
            assist: { id: 111, name: 'Hong Hyun-Seok' },
            type: 'subst',
            detail: 'Substitution',
          },
          {
            time: { elapsed: 70 },
            team: { id: 20, name: 'Brazil', code: 'BRA' },
            player: { id: 204, name: 'Neymar' },
            type: 'Card',
            detail: 'Yellow Card',
          },
        ],
      }),
    })
  })

  await page.route('**/fixtures/lineups?**', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        response: [
          {
            team: { id: 10, name: 'Korea Republic', code: 'KOR' },
            coach: { id: 1000, name: 'Hong Myung-Bo' },
            formation: '4-2-3-1',
            startXI: lineupPlayers('home'),
            substitutes: [
              { player: { id: 111, name: 'Hong Hyun-Seok', number: 17 } },
            ],
          },
          {
            team: { id: 20, name: 'Brazil', code: 'BRA' },
            coach: { id: 2000, name: 'Carlo Ancelotti' },
            formation: '4-3-3',
            startXI: lineupPlayers('away'),
            substitutes: [],
          },
        ],
      }),
    })
  })

  await page.route('**/fixtures/statistics?**', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        response: [
          {
            team: { id: 10, name: 'Korea Republic', code: 'KOR' },
            statistics: [
              { type: 'Ball Possession', value: '61%' },
              { type: 'Total Shots', value: 11 },
              { type: 'Shots on Goal', value: 5 },
              { type: 'Corner Kicks', value: 6 },
              { type: 'Offsides', value: 2 },
              { type: 'Passes %', value: '86%' },
              { type: 'Yellow Cards', value: 1 },
              { type: 'Red Cards', value: 0 },
              { type: 'Fouls', value: 8 },
            ],
          },
          {
            team: { id: 20, name: 'Brazil', code: 'BRA' },
            statistics: [
              { type: 'Ball Possession', value: '39%' },
              { type: 'Total Shots', value: 8 },
              { type: 'Shots on Goal', value: 3 },
              { type: 'Corner Kicks', value: 4 },
              { type: 'Offsides', value: 1 },
              { type: 'Passes %', value: '79%' },
              { type: 'Yellow Cards', value: 3 },
              { type: 'Red Cards', value: 1 },
              { type: 'Fouls', value: 12 },
            ],
          },
        ],
      }),
    })
  })

  await page.route('**/fixtures/players?**', async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ response: [] }) })
  })

  await page.route('**/teams?**', async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ response: [] }) })
  })
}

test.describe('broadcast match program (lineup/stats)', () => {
  test.beforeEach(async ({ page }) => {
    await mockBroadcastProgramApi(page)
  })

  test('BMP-E-01 renders 1920x1080 lineup program layout', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 })
    await page.goto('/broadcast-program.html?fixture=260506')

    await expect(page.getByTestId('program-stage')).toHaveAttribute(
      'data-league',
      'world-cup-2026',
    )
    await expect(page.getByTestId('program-stage')).toHaveAttribute(
      'data-active-bottom-view',
      'lineup',
    )
    await expect(page.getByTestId('program-bottom-panel')).toBeVisible()
    await expect(page.getByTestId('program-lineup-view')).toBeVisible()
    await expect(page.getByTestId('program-bottom-carousel')).toHaveCount(0)
    await expect(page.getByTestId('program-info-card')).toHaveCount(0)
    await expect(page.getByTestId('program-event-splash-image')).toHaveCount(0)
    await expect(page.getByTestId('program-chat-slot')).toBeVisible()
    await expect(page.getByTestId('program-character-slot')).toBeVisible()
    await expect(page.getByTestId('program-scorebug')).toHaveCount(0)
    await expect(page.getByTestId('program-lower-third')).toHaveCount(0)

    const stage = await page.getByTestId('program-stage').boundingBox()
    const left = await page.getByTestId('program-left').boundingBox()
    const right = await page.getByTestId('program-right').boundingBox()
    const feed = await page.getByTestId('program-feed-surface').boundingBox()
    const bottom = await page.getByTestId('program-bottom-panel').boundingBox()
    const chat = await page.getByTestId('program-chat-slot').boundingBox()
    const character = await page.getByTestId('program-character-slot').boundingBox()

    expect(stage).not.toBeNull()
    expect(left).not.toBeNull()
    expect(right).not.toBeNull()
    expect(feed).not.toBeNull()
    expect(bottom).not.toBeNull()
    expect(chat).not.toBeNull()
    expect(character).not.toBeNull()

    closeTo(left!.width, 1920 * 0.78)
    closeTo(right!.width, 1920 * 0.22)
    closeTo(feed!.height, 1080 * 0.78)
    closeTo(bottom!.height, 1080 * 0.22)
    closeTo(chat!.height, 1080 * 0.78)
    closeTo(character!.height, 1080 * 0.22)
    closeTo(feed!.width / feed!.height, 16 / 9, 0.02)

    const chatBackground = await page
      .getByTestId('program-chat-slot')
      .evaluate((node) => getComputedStyle(node).backgroundColor)
    const characterBackground = await page
      .getByTestId('program-character-slot')
      .evaluate((node) => getComputedStyle(node).backgroundColor)
    expect(chatBackground).toBe('rgb(0, 177, 64)')
    expect(characterBackground).toBe('rgb(0, 177, 64)')

    await expect(page.getByTestId('program-lineup-team')).toHaveCount(2)
    await expect(page.getByTestId('program-lineup-player')).toHaveCount(22)
    await expect(page.getByTestId('program-lineup-coach')).toHaveCount(2)
    await expect(page.getByTestId('program-lineup-substitution-animation')).toHaveCount(1)
    await expect(page.getByTestId('program-lineup-substitution-animation')).toContainText('OUT')
    await expect(page.getByTestId('program-lineup-substitution-animation')).toContainText('IN')
    await expect(page.getByTestId('program-lineup-view')).toContainText('홍현석')
    await expect(page.getByTestId('program-lineup-view')).toContainText('홍명보')
    await expect(page.getByTestId('program-lineup-view')).toContainText('안첼로티')
    await expect(page.getByTestId('program-lineup-view')).toContainText('이강인')

    await page.waitForTimeout(3050)

    await expect(page.getByTestId('program-lineup-substitution-animation')).toHaveCount(1)
    const substitutedInPlayer = page.locator('[data-testid=program-lineup-player][data-sub-in="true"]')
    await expect(substitutedInPlayer).toContainText('홍현석')
    await expect(substitutedInPlayer).toContainText('IN')

    await page.waitForTimeout(5100)

    await expect(page.getByTestId('program-lineup-substitution-animation')).toHaveCount(0)
    await expect(page.getByTestId('program-lineup-view')).toContainText('홍현석')
    await expect(page.getByTestId('program-lineup-view')).not.toContainText('이강인')
    await expect(substitutedInPlayer).toContainText('홍현석')
    await expect(substitutedInPlayer).toContainText('IN')
  })

  test('BMP-E-02 toggles stats views with shortcuts', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 })
    await page.goto('/broadcast-program.html?fixture=260506')
    await expect(page.getByTestId('program-lineup-view')).toBeVisible()

    await page.keyboard.press('Control+X')
    await expect(page.getByTestId('program-stage')).toHaveAttribute('data-active-bottom-view', 'attack')
    const attackStats = page.locator('[data-testid=program-stats-view][data-stats-view="attack"]')
    await expect(attackStats).toHaveCount(1)
    await expect(attackStats).toContainText('공격 지표')
    await expect(attackStats).toContainText('점유율')
    await expect(page.locator('[data-testid=program-stat-metric][data-graph="pie"]')).toHaveCount(1)
    await expect(page.locator('[data-testid=program-stat-metric][data-graph="bar"]')).toHaveCount(2)
    await expect(attackStats.getByTestId('program-stat-home-badge')).toHaveCount(3)
    await expect(attackStats.getByTestId('program-stat-away-badge')).toHaveCount(3)
    await expect(attackStats.getByTestId('program-stat-home-badge').first().locator('img')).toHaveAttribute('src', 'https://example.com/korea.png')
    await expect(attackStats.getByTestId('program-stat-away-badge').first().locator('img')).toHaveAttribute('src', 'https://example.com/brazil.png')

    await page.keyboard.press('Control+X')
    await expect(page.getByTestId('program-stage')).toHaveAttribute('data-active-bottom-view', 'lineup')
    await expect(page.getByTestId('program-lineup-view')).toBeVisible()

    await page.keyboard.press('Control+C')
    await expect(page.getByTestId('program-stage')).toHaveAttribute('data-active-bottom-view', 'chance')
    await expect(page.locator('[data-testid=program-stats-view][data-stats-view="chance"]')).toContainText('찬스 지표')

    await page.keyboard.press('Control+V')
    await expect(page.getByTestId('program-stage')).toHaveAttribute('data-active-bottom-view', 'control')
    await expect(page.locator('[data-testid=program-stats-view][data-stats-view="control"]')).toContainText('경기 운영')
    await expect(page.locator('[data-testid=program-stat-metric][data-graph="share"]')).toHaveCount(0)

    await page.keyboard.press('Control+B')
    await expect(page.getByTestId('program-stage')).toHaveAttribute('data-active-bottom-view', 'discipline')
    await expect(page.locator('[data-testid=program-stats-view][data-stats-view="discipline"]')).toContainText('징계/수비')
    await expect(page.locator('[data-testid=program-stat-metric][data-graph="discipline"]')).toHaveCount(2)

    await page.keyboard.press('Escape')
    await expect(page.getByTestId('program-stage')).toHaveAttribute('data-active-bottom-view', 'lineup')
  })

  test('BMP-E-03 fixture route bridges to broadcast program entry', async ({ page }) => {
    await page.goto('/broadcast/program/fixtures/1000001?league=champions-league')
    await page.waitForURL(/\/broadcast-program\.html\?.*league=champions-league/)

    await expect(page.getByTestId('program-stage')).toHaveAttribute(
      'data-league',
      'champions-league',
    )
    await expect(page.getByTestId('program-bottom-panel')).toContainText('홍현석')
  })
})
