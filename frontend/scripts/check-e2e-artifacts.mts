/**
 * 실패 아티팩트가 자격 증명을 남기지 않는지 실제로 검사한다.
 *
 * 설정만 읽고 "안전하다"고 주장하지 않는다. 합성 카나리 비밀번호로 로그인한 뒤
 * 일부러 실패시켜 아티팩트를 만들고, 그 파일들에서 카나리를 찾는다. 출력 디렉터리는
 * 저장소 밖 임시 경로라 실제 자격 증명이나 저장소 파일에 영향이 없다.
 *
 * 검사 자체가 실패하면 trace 캡처가 다시 켜졌다는 뜻이므로 종료 코드 1로 알린다.
 */
import { spawnSync } from 'node:child_process'
import { mkdtempSync, readdirSync, readFileSync, rmSync, statSync, unlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const CANARY = `ARTIFACT_CANARY_${Math.random().toString(16).slice(2, 10)}`
const outputDir = mkdtempSync(join(tmpdir(), 'mp01-artifact-safety-'))
const specPath = 'e2e/__artifact_safety_probe.spec.ts'

const PROBE_SPEC = `import { expect, test } from '@playwright/test'

const CANARY = process.env.PROBE_CANARY ?? 'missing-canary'

test('probe: credential must not survive in artifacts', async ({ page }) => {
  await page.goto('/admin/login')
  await page.getByTestId('login-email').fill('probe@example.test')
  await page.getByTestId('login-password').fill(CANARY)
  await page.getByTestId('login-submit').click()
  await page.getByTestId('login-error').waitFor()
  expect(false, 'intentional failure to produce artifacts').toBe(true)
})
`

function writeProbe() {
  writeFileSync(specPath, PROBE_SPEC)
}

function collectFiles(dir: string, found: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) collectFiles(full, found)
    else found.push(full)
  }
  return found
}

function containsCanary(file: string): boolean {
  const raw = readFileSync(file)
  if (raw.includes(CANARY)) return true
  // trace.zip은 압축되어 있으므로 풀어서 확인한다.
  if (file.endsWith('.zip')) {
    const unzip = spawnSync('unzip', ['-p', file], { maxBuffer: 64 * 1024 * 1024 })
    return unzip.stdout?.includes(CANARY) ?? false
  }
  return false
}

writeProbe()
try {
  const run = spawnSync(
    'npx',
    ['playwright', 'test', specPath, `--output=${outputDir}`, '--reporter=list'],
    {
      env: { ...process.env, PROBE_CANARY: CANARY },
      encoding: 'utf8',
      stdio: 'pipe',
    },
  )

  const failedAsExpected = run.status !== 0
  if (!failedAsExpected) {
    console.error('FAIL: the probe was expected to fail but passed; artifacts were not produced')
    process.exitCode = 1
  } else {
    const files = collectFiles(outputDir)
    const leaking = files.filter(containsCanary)

    console.log(`artifacts checked: ${files.length} in ${outputDir}`)
    for (const file of files) {
      console.log(`  ${leaking.includes(file) ? 'LEAK' : 'clean'}  ${file.replace(outputDir, '')}`)
    }

    if (leaking.length > 0) {
      console.error(
        `FAIL: the synthetic password appeared in ${leaking.length} artifact file(s); ` +
          'check the trace and reporter settings in playwright.config.ts',
      )
      process.exitCode = 1
    } else {
      console.log('PASS: no artifact contained the synthetic password')
    }
  }
} finally {
  unlinkSync(specPath)
  rmSync(outputDir, { recursive: true, force: true })
}
