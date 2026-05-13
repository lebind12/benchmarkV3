import { test, expect } from '@playwright/test'

/**
 * 메인 페이지 날짜 선택 UI (#26).
 * - FixtureFilters 에 date input + ◀/▶/오늘 버튼
 * - 변경 시 store.fixtures.filter.date 갱신
 * - 기본값 = 오늘 KST
 */

test.describe('main-home date picker', () => {
  test('기본값 = 오늘 KST', async ({ page }) => {
    await page.goto('/')
    const input = page.getByTestId('date-input')
    await expect(input).toBeVisible()
    const today = await page.evaluate(() => {
      const parts = new Intl.DateTimeFormat('sv-SE', {
        timeZone: 'Asia/Seoul',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      }).formatToParts(new Date())
      const get = (t: string) => parts.find((p) => p.type === t)?.value
      return `${get('year')}-${get('month')}-${get('day')}`
    })
    await expect(input).toHaveValue(today)
  })

  test('◀ 버튼 1회 → 전날 (-1d)', async ({ page }) => {
    await page.goto('/')
    const input = page.getByTestId('date-input')
    const before = await input.inputValue()
    await page.getByTestId('date-prev').click()
    const after = await input.inputValue()
    const beforeDate = new Date(before + 'T00:00:00Z')
    const afterDate = new Date(after + 'T00:00:00Z')
    expect(afterDate.getUTCTime?.() ?? afterDate.getTime()).toBeLessThan(
      beforeDate.getUTCTime?.() ?? beforeDate.getTime(),
    )
    const diffDays =
      (beforeDate.getTime() - afterDate.getTime()) / (24 * 3600 * 1000)
    expect(Math.round(diffDays)).toBe(1)
  })

  test('▶ 버튼 → 다음날 (+1d)', async ({ page }) => {
    await page.goto('/')
    const input = page.getByTestId('date-input')
    const before = await input.inputValue()
    await page.getByTestId('date-next').click()
    const after = await input.inputValue()
    const diffDays =
      (new Date(after + 'T00:00:00Z').getTime() -
        new Date(before + 'T00:00:00Z').getTime()) /
      (24 * 3600 * 1000)
    expect(Math.round(diffDays)).toBe(1)
  })

  test('오늘 버튼 → 오늘 KST 복원', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('date-prev').click()
    await page.getByTestId('date-prev').click()
    await page.getByTestId('date-today').click()
    const today = await page.evaluate(() => {
      const parts = new Intl.DateTimeFormat('sv-SE', {
        timeZone: 'Asia/Seoul',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      }).formatToParts(new Date())
      const get = (t: string) => parts.find((p) => p.type === t)?.value
      return `${get('year')}-${get('month')}-${get('day')}`
    })
    await expect(page.getByTestId('date-input')).toHaveValue(today)
  })

  test('date input 직접 입력 시 store 갱신 + API 호출 date param 포함', async ({
    page,
  }) => {
    await page.goto('/')
    // capture fixtures requests
    const reqs: string[] = []
    page.on('request', (req) => {
      if (req.url().includes('/api/v1/home/fixtures'))
        reqs.push(new URL(req.url()).search)
    })
    const input = page.getByTestId('date-input')
    await input.fill('2026-01-15')
    await input.dispatchEvent('change')
    // wait for at least one new request
    await page.waitForTimeout(200)
    const hasDate = reqs.some((q) => q.includes('date=2026-01-15'))
    expect(hasDate).toBe(true)
  })
})
