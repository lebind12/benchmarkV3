import { defineConfig, devices } from '@playwright/test'

// E2E는 실제 백엔드와 실제 DB를 쓴다. 모킹으로 통과시키지 않는다.
const BACKEND_URL = 'http://127.0.0.1:8000'

// trace는 실제 POST 본문(로그인 비밀번호 포함)을 압축 해제 가능한 형태로 남긴다.
// 실패 시 아티팩트가 저장소나 공유 경로에 남을 수 있으므로 끈다. 스크린샷은
// 비밀번호 입력란이 마스킹된 상태만 찍히고, 실패 진단은 error-context로 충분하다.
// 이 결정은 `npm run test:e2e:artifact-safety`로 실제 아티팩트를 검사해 확인한다.
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'off',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command: 'npm run dev',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: true,
      timeout: 60_000,
      env: { VITE_BACKEND_TARGET: BACKEND_URL },
    },
  ],
})
