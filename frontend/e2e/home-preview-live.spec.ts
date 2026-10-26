import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
const recommendations = JSON.parse(readFileSync(new URL('../src/mocks/home-preview/recommendations.json', import.meta.url), 'utf8'))
const records = JSON.parse(readFileSync(new URL('../src/mocks/home-preview/previews.json', import.meta.url), 'utf8'))

function response(fixtureId: number) {
  const preview = structuredClone((records as Record<string, any>)[String(fixtureId)])
  preview.is_mock = false
  for (const source of preview.sources) if (source.kind !== 'db') source.url = 'https://source.example.test/evidence'
  return { schema_version: '1.0', fixture_id: fixtureId, publication: { state: 'ready', served: 'current', reason: null, generated_at: preview.generated_at, as_of: preview.as_of }, refresh: { state: 'idle', last_attempt_at: null, reason: null }, preview }
}

test('real home loads stored JSON with no mock tools and shows generation time and removes the previous dashboard', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/v1/home/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/recommendations')) await route.fulfill({ json: recommendations })
    else if (path.endsWith('/prematch')) await route.fulfill({ json: response(Number(path.split('/').at(-2))) })
    else await route.fulfill({ json: { items: [], rows: [] } })
  })
  await page.goto('/')
  const home = page.getByTestId('home-preview-real')
  await expect(home.getByRole('heading', { name: '오늘의 매치', exact: true })).toBeVisible()
  await expect(home.locator('.hp-lead')).not.toHaveText('')
  await expect(home.locator('.hp-tools')).toHaveCount(0)
  await expect(page.getByText('일정 타임라인', { exact: true })).toHaveCount(0)
  await expect(home.getByTestId('preview-generation-time')).toContainText('생성')
  const sources = home.getByTestId('preview-sources')
  await expect(sources).not.toHaveAttribute('open', '')
  await sources.locator('summary').first().click()
  await expect(sources).toHaveAttribute('open', '')
  await expect(home.getByTestId('selected-preview')).toHaveAttribute('data-fixture-id', '90002')
  await home.getByRole('button', { name: '다음 추천 경기', exact: true }).click()
  await expect(home.getByTestId('selected-preview')).toHaveAttribute('data-fixture-id', '90001')
  await expect(home.locator('.hp-prediction')).toContainText('아스널')
  expect(errors).toEqual([])
})

test('late preview for an old selection cannot replace the new selection', async ({ page }) => {
  let release: (() => void) | undefined
  await page.route('**/api/v1/home/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/recommendations')) await route.fulfill({ json: recommendations })
    else if (path.endsWith('/prematch')) {
      const id = Number(path.split('/').at(-2))
      if (id === 90002) await new Promise<void>(resolve => { release = resolve })
      await route.fulfill({ json: response(id) }).catch(() => {})
    } else await route.fulfill({ json: { items: [], rows: [] } })
  })
  await page.goto('/')
  const home = page.getByTestId('home-preview-real')
  await expect(home.getByTestId('selected-preview')).toHaveAttribute('data-fixture-id', '90002')
  await home.getByRole('button', { name: '다음 추천 경기', exact: true }).click()
  await expect(home.locator('.hp-prediction')).toContainText('아스널')
  release?.()
  await expect(home.getByTestId('selected-preview')).toHaveAttribute('data-fixture-id', '90001')
  await expect(home.locator('.hp-prediction')).toContainText('아스널')
})

test('unverified mock payload is rejected by the public client', async ({ page }) => {
  await page.route('**/api/v1/home/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/recommendations')) await route.fulfill({ json: recommendations })
    else if (path.endsWith('/prematch')) {
      const value = response(Number(path.split('/').at(-2))); value.preview.is_mock = true
      await route.fulfill({ json: value })
    } else await route.fulfill({ json: { items: [], rows: [] } })
  })
  await page.goto('/')
  await expect(page.getByTestId('home-preview-real').locator('.hp-preview-empty')).toContainText('불러오지 못했습니다')
  await expect(page.getByTestId('home-preview-real').locator('.hp-prediction__score')).toHaveCount(0)
})

test('key absences are capped per team, full list expands, and odds follow the selected teams', async ({ page }) => {
  const payload = response(90002)
  const preview = payload.preview
  preview.sources.push(...['injury-test', 'usage-test'].map((id, i) => ({ id, fixture_id: 90002, kind: i ? 'db' : 'api', title: id, url: i ? null : 'https://source.example.test/injuries', published_at: null, retrieved_at: preview.as_of })))
  const rows: any[] = [preview.fixture.home, preview.fixture.away].flatMap((team: any, side: number) => [0, 1, 2].map(i => ({ team_id: team.external_id, player_id: 1000 + side * 10 + i, player_name: `${team.name} 선수 ${i + 1}`, photo_url: `https://media.api-sports.io/football/players/${1000 + side * 10 + i}.png`, availability: 'out', detail: i === 1 ? 'Red Card' : 'Injury', impact: '출전 불가', source_ids: ['injury-test'], importance_evidence: { eligible: true, recent_games: 10, lineup_games: 10, player_games: 10, recent_starts: 5, recent_minutes: 450, seasons: [], source_ids: ['usage-test'] } })))
  preview.facts.player_spotlights = { status: 'available', reason: null, as_of: preview.as_of, source_ids: ['usage-test'], data: [{ team_id: preview.fixture.home.external_id, player_id: 2000, player_name: '기록 선수', canonical_name: 'Player', photo_url: 'https://media.api-sports.io/football/players/2000.png', season_year: 2026, appearances: 7, goals: 5, assists: 1, minutes: 500, recent_match_count: 3, scoring_streak: 3, assist_streak: 0, involvement_streak: 3, record_notes: { season_contribution: '2026시즌 7경기 · 5골 · 1도움', scoring_streak: '확인된 최근 팀 3경기에서 연속 득점', assist_streak: null, involvement_streak: '확인된 최근 팀 3경기에서 연속 공격포인트' }, source_ids: ['usage-test'] }] }
  preview.analysis.player_watchpoints = { status: 'available', reason: null, as_of: preview.as_of, source_ids: ['usage-test'], data: [{ team_id: preview.fixture.home.external_id, player_id: 2000, focus: 'scoring_streak', reason: '득점 흐름이 이어지고 있어 이번 경기의 공격 기여를 눈여겨볼 선수입니다.', evidence_ids: ['usage-test'] }] }
  await page.route('https://media.api-sports.io/football/players/**', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="gray"/></svg>' }))
  preview.sources.push({ id:'cause-test', fixture_id:90002,kind:'web',title:'구단 발표',url:'https://www.liverpoolfc.com/news/club',published_at:null,retrieved_at:preview.as_of })
  rows[0].cause = { status:'available', reason:null,as_of:preview.as_of,source_ids:['cause-test'],data:{code:'hamstring',label:'햄스트링 부상',occurred_on:'2026-10-18',occurred_month:null} }
  rows[3].cause = { status:'available', reason:null,as_of:preview.as_of,source_ids:['cause-test'],data:{code:'knee',label:'무릎 부상',occurred_on:null,occurred_month:'2026-09'} }
  preview.facts.injuries = { status: 'available', reason: null, as_of: preview.as_of, source_ids: ['injury-test'], data: rows }
  preview.analysis.key_absences = { status: 'available', reason: null, as_of: preview.as_of, source_ids: ['injury-test', 'usage-test'], data: rows.filter((_: any, i: number) => i % 3 < 2).map((row: any) => ({ team_id: row.team_id, player_id: row.player_id, reason: '최근 10경기 중 선발 5회', evidence_ids: ['injury-test', 'usage-test'] })) }
  await page.route('**/api/v1/home/**', async route => {
    const path = new URL(route.request().url()).pathname
    await route.fulfill({ json: path.endsWith('/recommendations') ? recommendations : path.endsWith('/90002/prematch') ? payload : path.endsWith('/prematch') ? response(Number(path.split('/').at(-2))) : { items: [], rows: [] } })
  })
  await page.goto('/')
  const home = page.getByTestId('home-preview-real')
  await expect(home.getByTestId('preview-detail-link')).toHaveAttribute('href','/fixtures/90002')
  await expect(home.getByTestId('key-absence')).toHaveCount(4)
  await expect(home.getByTestId('key-absence').first()).toContainText('햄스트링 부상')
  await expect(home.getByTestId('key-absence').first()).toContainText('10월 18일 발생')
  await expect(home.getByTestId('key-absence').nth(1)).toContainText('9월 발생')
  await expect(home.getByTestId('key-absence').locator('a')).toHaveCount(0)
  await expect(home.getByTestId('key-absence').first()).not.toContainText('DB 기준')
  await expect(home.getByTestId('key-absence').locator('img')).toHaveCount(4)
  const watched = home.getByTestId('player-watchpoint')
  await expect(watched).toHaveCount(1)
  await expect(watched.locator('img')).toHaveAttribute('src', 'https://media.api-sports.io/football/players/2000.png')
  const info = watched.getByTestId('player-watchpoint-details')
  await expect(info).not.toHaveAttribute('open', '')
  await info.locator('summary').click()
  await expect(info).toHaveAttribute('open', '')
  await expect(info).toContainText('왜 눈여겨볼까요?')
  await expect(info).toContainText('최근 팀 3경기에서 연속 득점')
  await expect(info).toContainText('2026시즌 7경기 · 5골 · 1도움')
  await info.locator('summary').click()
  await expect(info).not.toHaveAttribute('open', '')

  for (const size of [{width:1440,height:1000},{width:390,height:844}]) {
    await page.setViewportSize(size)
    const boxes = await home.getByTestId('key-absence').evaluateAll(cards => cards.map(card => { const rect = card.getBoundingClientRect(); return { x: rect.x, y: rect.y, right: rect.right } }))
    expect(boxes[0]!.y).toBe(boxes[1]!.y)
    expect(boxes[2]!.y).toBe(boxes[3]!.y)
    expect(boxes[0]!.x).toBe(boxes[2]!.x)
    expect(boxes[1]!.x).toBe(boxes[3]!.x)
    expect(boxes[0]!.x).toBeLessThan(boxes[1]!.x)
    expect(boxes.every(box => box.right <= size.width)).toBe(true)
  }

  const full = home.getByTestId('all-injuries')
  await expect(full).not.toHaveAttribute('open', '')
  await full.locator('summary').click()
  await expect(full).toHaveAttribute('open', '')
  await expect(full.locator('article')).toHaveCount(6)
  const odds = home.locator('#preview-odds .hp-odds').first()
  await expect(odds.locator('span')).toHaveText([`${preview.fixture.home.name} 승`, '무승부', `${preview.fixture.away.name} 승`])
  await expect(odds.locator('b')).toHaveText([preview.external.odds.data[0].home.toFixed(2), preview.external.odds.data[0].draw.toFixed(2), preview.external.odds.data[0].away.toFixed(2)])
  await home.locator('.hp-match-strip button[data-fixture-id="90001"]').click()
  await expect(home.getByTestId('selected-preview')).toHaveAttribute('data-fixture-id', '90001')
  const next = response(90001).preview
  await expect(home.locator('#preview-odds .hp-odds').first().locator('span')).toHaveText([`${next.fixture.home.name} 승`, '무승부', `${next.fixture.away.name} 승`])
  await expect(home.getByTestId('key-absence')).toHaveCount(0)
  await expect(home.getByTestId('player-watchpoint')).toHaveCount(0)
  await expect(home.getByTestId('preview-detail-link')).toHaveAttribute('href','/fixtures/90001')
  await expect(full).not.toHaveAttribute('open', '')
  await home.getByTestId('preview-detail-link').click()
  await expect(page).toHaveURL(/\/fixtures\/90001$/)
})


test('pending preview displays the scheduled collection time', async ({ page }) => {
  await page.route('**/api/v1/home/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/recommendations')) return route.fulfill({ json: recommendations })
    if (!path.endsWith('/prematch')) return route.fulfill({ json: { items: [], rows: [] } })
    const value: any = response(Number(path.split('/').at(-2)))
    value.preview = null
    value.generation_due_at = '2026-10-25T03:00:00Z'
    value.publication = { state: 'pending', served: null, reason: 'generation_pending', generated_at: null, as_of: null }
    await route.fulfill({ json: value })
  })
  await page.goto('/')
  const time = page.getByTestId('preview-generation-time')
  await expect(time).toContainText('프리뷰 생성 예정')
  await expect(time).toContainText('12:00 KST')
  await expect(time).toContainText('정기 수집 완료 후')
  await expect(page.locator('.candidate-home, .home-toolbar')).toHaveCount(0)
})

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  for (const state of ['ready', 'pending'] as const) {
    test(`home has one scroll owner without decoration overflow: ${viewport.width} ${state}`, async ({ page }) => {
      await page.setViewportSize(viewport)
      const homeRequests: string[] = []
      await page.route('**/api/v1/home/**', async route => {
        const path = new URL(route.request().url()).pathname
        homeRequests.push(path)
        if (path.endsWith('/recommendations')) return route.fulfill({ json: recommendations })
        if (!path.endsWith('/prematch')) return route.fulfill({ json: { items: [], rows: [] } })
        const value = response(Number(path.split('/').at(-2)))
        if (state === 'pending') {
          value.preview = null
          value.publication = { state: 'pending', served: null, reason: 'generation_pending', generated_at: null, as_of: null } as any
        }
        return route.fulfill({ json: value })
      })
      await page.goto('/')
      const home = page.getByTestId('home-preview-real')
      if (state === 'pending') await expect(home.locator('.hp-preview-empty')).toBeVisible()
      else await expect(home.locator('.hp-lead')).not.toHaveText('')
      await expect(page.locator('main')).toHaveCount(1)
      const metrics = await page.getByTestId('ui-review-home-page').evaluate(root => {
        const section = root.querySelector<HTMLElement>('.hp-live-section')!
        const stage = root.querySelector<HTMLElement>('.hp-preview-stage')!
        const backdrop = root.querySelector<HTMLElement>('.hp-preview-backdrop')!
        const box = root.getBoundingClientRect()
        const scrollOwners = [root, ...root.querySelectorAll<HTMLElement>('*')].filter(el => el.clientHeight > 0 && el.scrollHeight > el.clientHeight + 1 && ['auto', 'scroll'].includes(getComputedStyle(el).overflowY))
        return { bottom: box.bottom, viewportHeight: innerHeight, scrollOwners: scrollOwners.map(el => el === root ? 'home' : el.className), scrollbar: getComputedStyle(root).scrollbarWidth,
          extraX: section.scrollWidth - section.clientWidth, extraY: section.scrollHeight - section.clientHeight,
          clip: getComputedStyle(backdrop).overflow, decorationHeight: backdrop.getBoundingClientRect().height, stageHeight: stage.getBoundingClientRect().height }
      })
      expect(metrics.bottom).toBeLessThanOrEqual(metrics.viewportHeight + 1)
      expect(metrics.scrollOwners).toEqual(['home'])
      expect(metrics.scrollbar).toBe('none')
      expect(metrics.extraX).toBeLessThanOrEqual(1)
      expect(metrics.extraY).toBeLessThanOrEqual(24) // reveal translation may extend the last element by 20px
      expect(metrics.clip).toBe('clip')
      expect(metrics.decorationHeight).toBeLessThanOrEqual(metrics.stageHeight)
      expect(homeRequests.every(path => path.endsWith('/recommendations') || path.endsWith('/prematch'))).toBe(true)
      const owner = page.getByTestId('ui-review-home-page')
      await owner.focus()
      await page.keyboard.press('PageDown')
      await expect.poll(() => owner.evaluate(el => el.scrollTop)).toBeGreaterThan(0)
      await home.getByTestId('preview-detail-link').scrollIntoViewIfNeeded()
      await expect(home.getByTestId('preview-detail-link')).toBeVisible()
      await page.screenshot({ path: `../out/home-preview/scroll-diagnosis/fixed-${viewport.width}-${state}.png` })
    })
  }
}

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test(`empty home has no unnecessary scrolling: ${viewport.width}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await page.route('**/api/v1/home/recommendations', route => route.fulfill({ json: {
      ...recommendations, display_date: recommendations.requested_date, fallback_reason: null, items: [], today_results: [],
    } }))
    await page.goto('/')
    await expect(page.getByRole('heading', { name: '아직 추천할 경기가 없습니다', exact: true })).toBeVisible()
    const metrics = await page.getByTestId('ui-review-home-page').evaluate(el => ({ extraY: el.scrollHeight - el.clientHeight, extraX: el.scrollWidth - el.clientWidth }))
    expect(metrics.extraY).toBe(0)
    expect(metrics.extraX).toBe(0)
  })
}
