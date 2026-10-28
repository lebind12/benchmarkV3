// Run only after operator supplies final commit/revision and starts testing.
// Actual POST + detail GET from fixture_server.py; no DEV preview button.
import { chromium } from '../../../../../frontend/node_modules/playwright/index.mjs'
import { writeFileSync } from 'node:fs'
import assert from 'node:assert/strict'

const output = new URL('./', import.meta.url)
const results = []
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
const page = await context.newPage()
page.setDefaultTimeout(6000)
const externalRequests = []
page.on('request', request => {
  if (!new URL(request.url()).hostname.match(/^(127\.0\.0\.1|localhost)$/)) externalRequests.push(request.url())
})
const reset = () => fetch('http://127.0.0.1:8027/__fixture/reset', { method: 'POST' })
const observe = async () => (await fetch('http://127.0.0.1:8027/__fixture/observations')).json()
const run = async (name, criterion, test) => {
  try { await test(); results.push({ name, criterion, status: 'PASS' }) }
  catch (error) { results.push({ name, criterion, status: 'FAIL', error: String(error) }); await page.screenshot({ path: new URL(`failure-${results.length}.png`, output).pathname }).catch(() => {}) }
}
const analyze = async text => {
  await reset()
  await page.locator('#na-source').fill('https://source.example.invalid/community-post')
  await page.locator('#na-article').fill(text)
  await page.getByRole('button', { name: '글 분석하기', exact: true }).click()
  await page.getByText(/분석 완료 ·/).waitFor()
}
const card = page.locator('#news-entity-card')
const article = '⚽  Arsenal의 Bukayo Saka가 축구 경기에 출전했다.\n  부카요 사카는 동료다. <img src=x onerror="window.__newsXss=1">\nArsenal은 닉네임이다.'

await page.goto('http://127.0.0.1:5197/admin/news-analysis')
await page.getByRole('heading', { name: '글 속 축구 정보' }).waitFor()
await run('real analysis and exact original text', ['AC-3','AC-4','AC-7','AC-10'], async () => {
  await analyze(article)
  assert.equal(await page.locator('.annotated-article').textContent(), article)
  assert.equal(await page.locator('.annotated-article img').count(), 0)
  assert.equal(await page.evaluate(() => window.__newsXss), undefined)
  assert.equal(await page.locator('.annotated-name').filter({ hasText: /^Arsenal$/ }).count(), 1)
  assert.equal(await page.getByRole('link', { name: '입력한 출처 열기' }).getAttribute('href'), 'https://source.example.invalid/community-post')
})
await run('team hover actual DB GET, card movement and cache', ['AC-11','AC-12'], async () => {
  const anchor = page.locator('.annotated-name').filter({ hasText: /^Arsenal$/ })
  await anchor.hover()
  await card.getByText('Fixture Stadium').waitFor()
  assert.match(await card.textContent(), /0 : 1/)
  await card.hover()
  await page.waitForTimeout(350)
  assert.equal(await card.isVisible(), true)
  await page.getByRole('heading', { name: '글에서 확인하기' }).click()
  await anchor.hover()
  await card.getByText('Fixture Stadium').waitFor()
  assert.equal((await observe()).detail_gets['/api/v1/teams/arsenal'], 1)
})
await run('player latest DB rows and NULL versus zero', ['AC-12'], async () => {
  await page.locator('.annotated-name').filter({ hasText: /^Bukayo Saka$/ }).hover()
  await card.getByText('최신 시즌 기록').waitFor()
  await card.getByText('2026 · Premier League').waitFor()
  const text = await card.textContent()
  assert.match(text, /출전 0 · 골 0 · 도움 정보 없음/)
  assert.match(text, /2026 · FA Cup/)
  assert.match(text, /Manchester City/)
  assert.doesNotMatch(text, /2025|99|88|77/)
})
await run('keyboard enters teleported card and Escape restores focus', ['AC-11'], async () => {
  await page.keyboard.press('Escape')
  const anchor = page.locator('.annotated-name').filter({ hasText: /^Arsenal$/ })
  await anchor.focus()
  await page.keyboard.press('ArrowDown')
  assert.equal(await card.evaluate(el => el.contains(document.activeElement)), true)
  await page.keyboard.press('Tab')
  assert.equal(await card.getByRole('link', { name: '팀 상세 보기' }).evaluate(el => el === document.activeElement), true)
  await page.keyboard.press('Escape')
  assert.equal(await card.count(), 0)
  assert.equal(await anchor.evaluate(el => el === document.activeElement), true)
})
await run('plain article click closes card', ['AC-11'], async () => {
  await page.locator('.annotated-name').first().hover()
  await card.waitFor()
  await page.locator('.annotated-article').click({ position: { x: 5, y: 10 } })
  await page.waitForTimeout(220)
  assert.equal(await card.count(), 0)
})
await run('mobile tap viewport bounds', ['AC-11'], async () => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.locator('.annotated-name').filter({ hasText: /^Arsenal$/ }).click()
  await card.getByText('Fixture Stadium').waitFor()
  const box = await card.boundingBox()
  assert(box && box.x >= 0 && box.y >= 0 && box.x + box.width <= 390 && box.y + box.height <= 844)
  await page.screenshot({ path: new URL('mobile-hover.png', output).pathname })
  await page.setViewportSize({ width: 1440, height: 1000 })
})
await run('non football and uncertain have no annotations', ['AC-9'], async () => {
  for (const marker of ['[NOT_FOOTBALL]','[UNCERTAIN]','[NO_EVIDENCE]']) {
    await analyze(`${marker} Arsenal and Bukayo Saka are fictional game nicknames.`)
    assert.equal(await page.locator('.annotated-name').count(), 0)
  }
})
await run('failure retains inputs and retry works', ['AC-5'], async () => {
  await reset()
  await page.locator('#na-article').fill('[FAIL] Arsenal football')
  await page.getByRole('button', { name: '글 분석하기', exact: true }).click()
  await page.locator('.na-error').waitFor()
  assert.equal(await page.locator('#na-article').inputValue(), '[FAIL] Arsenal football')
  assert.equal(await page.locator('#na-source').inputValue(), 'https://source.example.invalid/community-post')
  await page.locator('#na-article').fill('Arsenal football')
  await page.getByRole('button', { name: '글 분석하기', exact: true }).click()
  await page.getByText(/분석 완료 ·/).waitFor()
})
await run('late analyze result ignored after input change', ['AC-6'], async () => {
  await reset()
  await page.locator('#na-article').fill('[SLOW] Arsenal football')
  await page.getByRole('button', { name: '글 분석하기', exact: true }).click()
  await page.getByRole('button', { name: '분석 중…', exact: true }).waitFor()
  await page.locator('#na-article').fill('changed article')
  await page.waitForTimeout(900)
  assert.equal(await page.locator('.annotated-article').count(), 0)
  assert.equal(await page.locator('#na-article').inputValue(), 'changed article')
})
await run('no source fetch and no runtime DB writes', ['AC-7','AC-8'], async () => {
  assert.equal((await observe()).writes, 0)
  assert.deepEqual(externalRequests, [])
})
writeFileSync(new URL('browser-results.json', output), JSON.stringify({ timestamp: new Date().toISOString(), environment: 'chromium + localhost FastAPI + isolated SQLite + model stub; actual routers and DB detail services; not live Vertex', results, externalRequests }, null, 2))
await browser.close()
console.log(JSON.stringify(results, null, 2))
process.exitCode = results.some(result => result.status === 'FAIL') ? 1 : 0
