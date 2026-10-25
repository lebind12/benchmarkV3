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
