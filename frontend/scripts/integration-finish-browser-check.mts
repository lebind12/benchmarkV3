/**
 * 통합 마무리 브라우저 확인 (실제 Chromium).
 *
 * 확인하는 네 가지:
 * 1. 저장된 경기 목록 GET 과 경기 선택 UI — **실제 저장 경기 자료**(읽기 전용 좁은 역할)를
 *    실제 브라우저에서 읽는다. 외부 API 를 호출하지 않는다.
 * 2. 섹션 모의 실행의 **본문 우선** 검사 화면(본문·근거가 노드 진단보다 먼저).
 * 3. 운영 지표 화면 이동과 드릴다운(지표 → 실행 검사).
 * 4. 드릴다운 왕복에서 **조회 필터 유지**(뒤로가기·돌아가기 링크).
 *
 * 이 실행이 실제가 아닌 것:
 * - 로그인 계정은 **합성 테스트 계정**(integration-finish-synthetic@example.test)이다.
 *   사용자의 실제 계정이 아니며, 로컬 루프백 테스트 DB 안에만 있다.
 * - 섹션 실행·모의 실행은 `mode=mock` 이며 외부 모델 호출이 0회다. 실제 조사 본문이
 *   아니고 승인 근거도 아니다.
 *
 * 산출물은 텍스트 요약과 스크린샷뿐이다. 비밀번호는 환경변수로만 받고 출력하지 않는다.
 */
import { chromium, type Browser, type Page } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'

const BASE = process.env.PREVIEW_UI_BASE_URL ?? 'http://127.0.0.1:5174'
const EMAIL = process.env.PREVIEW_UI_EMAIL ?? ''
const PASSWORD = process.env.PREVIEW_UI_PASSWORD ?? ''
const OUT_DIR = process.env.PREVIEW_UI_OUT_DIR ?? '/tmp/mp-browser-evidence'

type Step = { name: string; ok: boolean; detail: string }
const steps: Step[] = []

function record(name: string, ok: boolean, detail: string) {
  steps.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}: ${detail}`)
}

async function login(page: Page) {
  await page.goto(`${BASE}/admin/login`, { waitUntil: 'networkidle' })
  await page.fill('input[type="email"]', EMAIL)
  await page.fill('input[type="password"]', PASSWORD)
  await page.click('button[type="submit"]')
  await page.waitForURL('**/admin/runs', { timeout: 20_000 })
  await page.waitForLoadState('networkidle')
}

async function shot(page: Page, name: string) {
  await mkdir(OUT_DIR, { recursive: true })
  await page.screenshot({ path: path.join(OUT_DIR, `${name}.png`), fullPage: true })
}

async function apiJson(page: Page, url: string) {
  const response = await page.request.get(`${BASE}${url}`)
  return { status: response.status(), body: await response.json() }
}

async function main() {
  if (!EMAIL || !PASSWORD) {
    throw new Error('PREVIEW_UI_EMAIL / PREVIEW_UI_PASSWORD are required')
  }
  let browser: Browser | undefined
  try {
    browser = await chromium.launch()
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
    const page = await context.newPage()
    await login(page)
    record('login', true, '합성 테스트 관리자로 로그인하고 /admin/runs 에 도착')

    // --- 1. 저장된 경기 GET + 경기 선택 UI ---
    const fixturesApi = await apiJson(page, '/api/v1/admin/preview/fixtures')
    const stored = fixturesApi.body?.stored_access ?? null
    const candidates = fixturesApi.body?.fixtures ?? []
    record(
      'fixtures API GET',
      fixturesApi.status === 200 && Boolean(stored?.readable) && candidates.length > 0,
      `status=${fixturesApi.status} readable=${stored?.readable} role=${stored?.role} ` +
        `candidates=${candidates.length} external_calls=${fixturesApi.body?.external_calls}`,
    )
    record(
      'fixtures API 는 외부 호출 0회',
      (fixturesApi.body?.external_calls ?? 0) === 0,
      `external_calls=${fixturesApi.body?.external_calls}`,
    )

    await page.goto(`${BASE}/admin/runs`, { waitUntil: 'networkidle' })
    await shot(page, '01-runs-list')

    // 경기 선택 화면: 저장된 목록을 실제 브라우저에서 렌더한다.
    await page.goto(`${BASE}/admin/fixtures`, { waitUntil: 'networkidle' })
    const fixtureTable = page.locator('[data-test="fixture-table"]')
    const tableVisible = await fixtureTable.isVisible().catch(() => false)
    const fixtureRows = page.locator('[data-test="fixture-row"]')
    const rowCount = tableVisible ? await fixtureRows.count() : 0
    const firstRowText = rowCount > 0 ? await fixtureRows.first().innerText() : ''
    const accessBlocked = await page.locator('[data-test="access-blocked"]').count()
    record(
      'fixture selection UI renders stored fixtures',
      tableVisible && rowCount > 0 && accessBlocked === 0,
      `rows=${rowCount} access_blocked=${accessBlocked} first="${firstRowText.replace(/\n/g, ' | ').slice(0, 160)}"`,
    )
    await shot(page, '01b-fixture-selection')

    const first = candidates[0]
    record(
      'stored fixture identity',
      Boolean(first?.fixture_id) && first?.origin === 'stored_db',
      `fixture_id=${first?.fixture_id} label=${first?.label} origin=${first?.origin} ` +
        `kickoff=${first?.kickoff_at}`,
    )

    // --- 2. 섹션 모의 실행 + 본문 우선 검사 ---
    const create = await page.request.post(`${BASE}/api/v1/admin/preview/section-runs`, {
      data: { workflow_id: 'section_form', mode: 'mock' },
    })
    const created = await create.json()
    record(
      'section run (mock)',
      create.status() === 200 && created.mode === 'mock',
      `status=${create.status()} run=${created.run_id} mode=${created.mode} ` +
        `external_calls=${created.external_calls} section_result=${created.section_result_id}`,
    )

    await page.goto(`${BASE}/admin/runs?run=${created.run_id}`, { waitUntil: 'networkidle' })
    await page.waitForSelector('[data-testid="run-inspector"]', { timeout: 20_000 })
    const bodyBox = page.locator('[data-testid="section-result"]')
    const diagnosticsBox = page.locator('[data-testid="node-diagnostics"]')
    const bodyText = (await bodyBox.innerText()).slice(0, 400)
    const bodyY = (await bodyBox.boundingBox())?.y ?? 0
    const diagY = (await diagnosticsBox.boundingBox())?.y ?? 0
    const modeBanner = await page.locator('[data-testid="mode-banner"]').innerText()
    record(
      'section body before node diagnostics',
      bodyY < diagY,
      `body_y=${Math.round(bodyY)} diagnostics_y=${Math.round(diagY)} ` +
        `banner="${modeBanner.replace(/\n/g, ' ').slice(0, 80)}"`,
    )
    record('section body text', bodyText.length > 0, bodyText.replace(/\n/g, ' ').slice(0, 200))
    await shot(page, '02-section-body-first')

    // --- 3. 운영 지표 이동 + 드릴다운 ---
    await page.click('a[href="/admin/metrics"]')
    await page.waitForSelector('[data-testid="metrics-filters"]', { timeout: 20_000 })
    await page.waitForLoadState('networkidle')
    const windowText = await page.locator('[data-testid="metrics-window"]').innerText()
    record('metrics route', true, windowText.replace(/\n/g, ' ').slice(0, 120))

    // 기본 조회는 운영·실호출이다. 저장된 기록은 dev·mock 이므로 필터를 켜야 보인다.
    await page.click('[data-testid="env-dev"]')
    await page.click('[data-testid="mode-mock"]')
    await page.click('[data-testid="apply-filters"]')
    await page.waitForLoadState('networkidle')
    await page.waitForSelector('[data-testid="metrics-table"]', { timeout: 20_000 })
    const filterUrl = page.url()
    record('metrics filters applied', filterUrl.includes('environment=dev') && filterUrl.includes('mode=mock'), filterUrl)
    const contextText = await page.locator('[data-testid="metrics-drilldown-context"]').innerText()
    record('drilldown context', contextText.includes('dev') && contextText.includes('mock'), contextText)

    const drilldownButtons = page.locator('[data-testid^="drilldown-"]')
    const drilldownCount = await drilldownButtons.count()
    record('drilldown available', drilldownCount > 0, `지표 행의 내려가기 버튼 ${drilldownCount}개`)
    await drilldownButtons.first().click()
    const openButtons = page.locator('[data-testid^="open-run-"]')
    await openButtons.first().waitFor({ timeout: 10_000 })
    await shot(page, '03-metrics-drilldown')

    // --- 4. 실행 열기 + 필터 유지 왕복 ---
    await page.locator('[data-testid="metrics-drilldown"] [data-testid^="open-run-"]').first().click()
    await page.waitForURL('**/admin/runs**', { timeout: 20_000 })
    await page.waitForLoadState('networkidle')
    const runsUrl = page.url()
    record(
      'drilldown opens run with filters in query',
      runsUrl.includes('run=') && runsUrl.includes('environment=dev') && runsUrl.includes('mode=mock') && runsUrl.includes('from=metrics'),
      runsUrl,
    )
    await page.waitForSelector('[data-testid="run-inspector"]', { timeout: 20_000 })
    await shot(page, '04-run-from-metrics')

    const returnLink = page.locator('[data-testid="metrics-return"] a')
    const returnHref = await returnLink.getAttribute('href')
    record(
      'metrics return link keeps filters',
      Boolean(returnHref?.includes('environment=dev') && returnHref?.includes('mode=mock')),
      String(returnHref),
    )
    await returnLink.click()
    await page.waitForURL('**/admin/metrics**', { timeout: 20_000 })
    await page.waitForLoadState('networkidle')
    await page.waitForSelector('[data-testid="metrics-table"]', { timeout: 20_000 })
    const backUrl = page.url()
    const pressedEnv = await page.locator('[data-testid="env-dev"]').getAttribute('aria-pressed')
    const pressedMode = await page.locator('[data-testid="mode-mock"]').getAttribute('aria-pressed')
    record(
      'return keeps effective query',
      backUrl.includes('environment=dev') && backUrl.includes('mode=mock') && pressedEnv === 'true' && pressedMode === 'true',
      `url=${backUrl} env_pressed=${pressedEnv} mode_pressed=${pressedMode}`,
    )
    await shot(page, '05-metrics-returned')

    // 브라우저 뒤로가기로도 같은 조건이 남는지 확인한다.
    await page.goBack({ waitUntil: 'networkidle' })
    await page.goBack({ waitUntil: 'networkidle' })
    await page.waitForSelector('[data-testid="metrics-filters"]', { timeout: 20_000 })
    await page.waitForLoadState('networkidle')
    await page.waitForSelector('[data-testid="metrics-table"]', { timeout: 20_000 })
    const afterBackUrl = page.url()
    const backEnv = await page.locator('[data-testid="env-dev"]').getAttribute('aria-pressed')
    const backMode = await page.locator('[data-testid="mode-mock"]').getAttribute('aria-pressed')
    record(
      'browser back keeps effective query',
      afterBackUrl.includes('environment=dev') && afterBackUrl.includes('mode=mock') && backEnv === 'true' && backMode === 'true',
      `url=${afterBackUrl} env_pressed=${backEnv} mode_pressed=${backMode}`,
    )
    await shot(page, '06-metrics-after-back')

    await context.close()
    return steps
  } finally {
    await browser?.close()
  }
}

main()
  .then(async (result) => {
    await mkdir(OUT_DIR, { recursive: true })
    await writeFile(path.join(OUT_DIR, 'summary.json'), JSON.stringify(result, null, 2), 'utf8')
    const failed = result.filter((step) => !step.ok)
    console.log(`\n${result.length - failed.length}/${result.length} checks passed`)
    process.exit(failed.length === 0 ? 0 : 1)
  })
  .catch(async (error: unknown) => {
    const message = error instanceof Error ? error.stack ?? error.message : String(error)
    console.error('BROWSER CHECK FAILED:', message)
    await mkdir(OUT_DIR, { recursive: true })
    await writeFile(path.join(OUT_DIR, 'failure.txt'), message, 'utf8')
    process.exit(2)
  })
