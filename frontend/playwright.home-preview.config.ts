import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  testDir: './e2e', testMatch: ['home-preview-mock.spec.ts', 'home-preview-live.spec.ts'], workers: 1, retries: 0,
  outputDir: '../out/home-preview/test-results', reporter: [['list']],
  use: { baseURL: 'http://127.0.0.1:5192', viewport: { width: 1440, height: 1000 }, trace: 'retain-on-failure' },
  projects: [{ name: 'home-preview', use: { ...devices['Desktop Chrome'] } }],
  webServer: { command: 'VITE_BACKEND_URL=http://127.0.0.1:8017 VITE_USE_MOCK=false npm run dev -- --host 127.0.0.1 --port 5192 --strictPort', url: 'http://127.0.0.1:5192', reuseExistingServer: !process.env.CI, timeout: 60000 },
})
