/**
 * 섹션 워크플로우 화면 브라우저 확인 (MP-05, 실제 Chromium).
 *
 * 확인하는 흐름은 사용자가 실제로 하는 일이다.
 *
 *   저장된 경기 목록 → 경기 선택 → 섹션 선택 → 실행 → **본문·근거 확인**
 *   → 모의 결과는 승인 불가 표시 → 실행 검사 화면의 진단(FormPanel)
 *
 * 이 실행이 실제가 아닌 것:
 * - 합성 관리자 계정과 루프백 테스트 DB를 쓴다. 사용자의 실제 계정이 아니다.
 * - 섹션 실행은 `mode=mock`이며 외부 모델 호출이 0회다. 실제 조사 본문이 아니고
 *   승인 근거도 아니다. 승인 요청을 보내지 않는다.
 *
 * 산출물은 단계별 통과/실패 요약과 스크린샷이다. 비밀번호는 환경변수로만 받는다.
 */
import { chromium, type Browser, type Page } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'

const BASE = process.env.PREVIEW_UI_BASE_URL ?? 'http://localhost:5181'
const EMAIL = process.env.PREVIEW_UI_EMAIL ?? ''
const PASSWORD = process.env.PREVIEW_UI_PASSWORD ?? ''
const OUT_DIR = process.env.PREVIEW_UI_OUT_DIR ?? '/tmp/mp05-browser-evidence'

type Step = { name: string; ok: boolean; detail: string }
const steps: Step[] = []

function record(name: string, ok: boolean, detail: string) {
  steps.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}: ${detail}`)
}

async function shot(page: Page, name: string) {
  await mkdir(OUT_DIR, { recursive: true })
  await page.screenshot({ path: path.join(OUT_DIR, `${name}.png`), fullPage: true })
}

async function login(page: Page) {
  await page.goto(`${BASE}/admin/login`, { waitUntil: 'networkidle' })
  await page.fill('input[type="email"]', EMAIL)
  await page.fill('input[type="password"]', PASSWORD)
  await page.click('button[type="submit"]')
  await page.waitForURL('**/admin/runs', { timeout: 20_000 })
  await page.waitForLoadState('networkidle')
}

async function main() {
  if (!EMAIL || !PASSWORD) {
    throw new Error('PREVIEW_UI_EMAIL / PREVIEW_UI_PASSWORD are required')
  }
  let browser: Browser | undefined
  try {
    browser = await chromium.launch()
    const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
    const page = await context.newPage()
    await login(page)
    record('login', true, '합성 관리자 로그인 후 /admin/runs')

    // 1. 섹션 목록이 실제 구현 여부를 숨기지 않는지.
    const sectionsResponse = await page.request.get(`${BASE}/api/v1/admin/preview/sections`)
    const sectionsBody = await sectionsResponse.json()
    const formAvailability = sectionsBody?.availability?.section_form ?? null
    record(
      '섹션 목록 API',
      sectionsResponse.status() === 200 && Boolean(formAvailability),
      `status=${sectionsResponse.status()} section_form.real=${formAvailability?.real_generation_available}`,
    )
    record(
      '섹션 목록이 모델 설정 상태를 함께 준다',
      Boolean(formAvailability?.model),
      `configured=${formAvailability?.model?.configured}`,
    )

    // 2. 섹션 실행 화면에서 저장 경기 목록을 읽는다(외부 호출 0회).
    await page.goto(`${BASE}/admin/sections`, { waitUntil: 'networkidle' })
    const fixtureRows = page.locator('[data-test="fixture-row"]')
    const rowCount = await fixtureRows.count()
    record('경기 선택 목록 렌더', rowCount > 0, `저장 경기 행 ${rowCount}개`)
    await shot(page, '01-section-workspace')

    const fixturesApi = await page.request.get(`${BASE}/api/v1/admin/preview/fixtures`)
    const fixturesBody = await fixturesApi.json()
    record(
      '경기 목록 조회는 외부 호출 0회',
      (fixturesBody?.external_calls ?? 0) === 0,
      `external_calls=${fixturesBody?.external_calls}`,
    )

    // 3. 경기 선택 → 섹션 선택.
    await fixtureRows.first().locator('[data-test="select-fixture"]').click()
    const chosen = page.locator('[data-testid="workspace-chosen-fixture"]')
    await chosen.waitFor({ timeout: 10_000 })
    const chosenText = (await chosen.textContent())?.trim() ?? ''
    record('경기 선택', chosenText.length > 0, chosenText.slice(0, 80))

    const formSection = page.locator('[data-testid="workspace-section-section_form"]')
    await formSection.click()
    await shot(page, '02-section-selected')

    // 4. 모의 실행 → 본문·근거가 먼저 보이는지.
    const bodyBefore = await page.locator('[data-testid="workspace-result"]').count()
    record('실행 전에는 결과 영역이 없다', bodyBefore === 0, `result blocks=${bodyBefore}`)

    await page.locator('[data-testid="workspace-run"]').click()
    const resultBody = page.locator('[data-testid="workspace-result-body"]')
    await resultBody.waitFor({ timeout: 60_000 })
    const bodyText = (await resultBody.textContent())?.trim() ?? ''
    record('실행 후 본문이 보인다', bodyText.length > 0, `본문 ${bodyText.length}자`)

    const modeText = (await page.locator('[data-testid="workspace-result-mode"]').textContent())?.trim()
    record('실행 방식이 화면에 표시된다', Boolean(modeText), `mode=${modeText}`)

    const sources = await page.locator('[data-testid="workspace-result-sources"]').count()
    record('근거 영역이 함께 있다', sources === 1, `sources blocks=${sources}`)
    await shot(page, '03-section-result')

    // 5. 모의 결과는 승인 버튼을 열지 않는다.
    const approveButton = await page.locator('[data-testid="workspace-approve"]').count()
    const blocked = await page.locator('[data-testid="workspace-approval-blocked"]').count()
    record(
      '모의 결과는 승인 불가로 표시',
      approveButton === 0 && blocked === 1,
      `approve button=${approveButton} blocked note=${blocked}`,
    )

    // 6. 실행 검사 화면에서 R1 진단 패널이 보인다.
    await page.locator('[data-testid="workspace-open-inspector"]').click()
    await page.waitForURL('**/admin/runs**', { timeout: 20_000 })
    await page.waitForLoadState('networkidle')
    // 실행 상세 조회가 끝나기를 기다린다. 기다리지 않으면 탭 목록이 비어 보인다.
    await page
      .locator('[data-testid="inspector-summary"], [data-testid="module-list"]')
      .first()
      .waitFor({ timeout: 20_000 })
    // 검사 화면은 첫 모듈 탭(D0)을 먼저 연다. R1 진단 패널은 R1 탭을 골라야 보인다.
    const r1Tab = page.locator('[data-testid="module-tab-R1"]')
    await r1Tab.first().waitFor({ timeout: 20_000 }).catch(() => undefined)
    const r1TabCount = await r1Tab.count()
    if (r1TabCount > 0) {
      await r1Tab.first().click()
    }
    const nodeDiagnostics = page.locator('[data-testid="node-diagnostics"]')
    const diagCount = await nodeDiagnostics.count()
    if (diagCount > 0) {
      await nodeDiagnostics.first().locator('summary').click()
    }
    const formPanel = await page.locator('[data-testid="form-panel"]').count()
    record(
      '실행 검사에 R1 전용 진단 패널',
      formPanel === 1,
      `form panel=${formPanel} r1 tabs=${r1TabCount} diagnostics=${diagCount}`,
    )
    await shot(page, '04-run-inspector-form-panel')

    const results = {
      base: BASE,
      steps,
      passed: steps.filter((step) => step.ok).length,
      total: steps.length,
    }
    await mkdir(OUT_DIR, { recursive: true })
    await writeFile(
      path.join(OUT_DIR, 'browser-checks.json'),
      JSON.stringify(results, null, 2),
      'utf-8',
    )
    console.log(`\n${results.passed}/${results.total} 통과`)
    if (results.passed !== results.total) process.exitCode = 1
  } finally {
    await browser?.close()
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
