import { defineConfig, devices } from '@playwright/test'

// E2E는 실제 백엔드와 실제 DB를 쓴다. 모킹으로 통과시키지 않는다.
const BACKEND_URL = 'http://127.0.0.1:8000'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
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
