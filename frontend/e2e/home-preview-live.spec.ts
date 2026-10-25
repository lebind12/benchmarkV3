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

test('real home loads stored JSON with no mock tools and retains the existing dashboard', async ({ page }) => {
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
  await expect(page.getByText('일정 타임라인', { exact: true })).toHaveCount(1)
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
  const rows = [preview.fixture.home, preview.fixture.away].flatMap((team: any, side: number) => [0, 1, 2].map(i => ({ team_id: team.external_id, player_id: 1000 + side * 10 + i, player_name: `${team.name} 선수 ${i + 1}`, availability: 'out', detail: 'Injury', impact: '출전 불가', source_ids: ['injury-test'], importance_evidence: { eligible: true, recent_games: 10, lineup_games: 10, player_games: 10, recent_starts: 5, recent_minutes: 450, seasons: [], source_ids: ['usage-test'] } })))
  preview.facts.injuries = { status: 'available', reason: null, as_of: preview.as_of, source_ids: ['injury-test'], data: rows }
  preview.analysis.key_absences = { status: 'available', reason: null, as_of: preview.as_of, source_ids: ['injury-test', 'usage-test'], data: rows.filter((_: any, i: number) => i % 3 < 2).map((row: any) => ({ team_id: row.team_id, player_id: row.player_id, reason: '최근 10경기 중 선발 5회', evidence_ids: ['injury-test', 'usage-test'] })) }
  await page.route('**/api/v1/home/**', async route => {
    const path = new URL(route.request().url()).pathname
    await route.fulfill({ json: path.endsWith('/recommendations') ? recommendations : path.endsWith('/90002/prematch') ? payload : path.endsWith('/prematch') ? response(Number(path.split('/').at(-2))) : { items: [], rows: [] } })
  })
  await page.goto('/')
  const home = page.getByTestId('home-preview-real')
  await expect(home.getByTestId('key-absence')).toHaveCount(4)
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
  await expect(full).not.toHaveAttribute('open', '')
})
