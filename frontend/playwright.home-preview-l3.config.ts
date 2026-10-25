import { defineConfig, devices } from '@playwright/test'
process.env.HOME_PREVIEW_L3 = '1'
export default defineConfig({
  testDir: './e2e', testMatch: 'home-preview-l3.spec.ts', workers: 1, retries: 0,
  outputDir: '../out/home-preview/l3-test-results', reporter: [['list']],
  use: { baseURL: 'http://127.0.0.1:5191', viewport: { width: 1440, height: 1000 }, trace: 'retain-on-failure' },
  projects: [{ name: 'home-preview-real-db', use: { ...devices['Desktop Chrome'] } }],
})
