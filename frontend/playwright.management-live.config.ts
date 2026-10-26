import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  expect: { timeout: 15000 },
  testDir: './e2e', testMatch: 'streamer-management-live.spec.ts', workers: 1, retries: 0,
  outputDir: '../out/management-live/test-results', reporter: [['list']],
  use: { baseURL: 'http://127.0.0.1:5187', viewport: {width:1440,height:1000}, trace:'retain-on-failure' },
  projects: [{name:'management-live',use:{...devices['Desktop Chrome']}}],
  webServer: [
    { command: 'cd .. && .venv/bin/python -m tests.support.management_live_server',url:'http://127.0.0.1:8016/health',reuseExistingServer:true,timeout:30000 },
    { command: 'VITE_USE_MOCK=false VITE_BACKEND_URL=http://127.0.0.1:8016 npm run dev -- --host 127.0.0.1 --port 5187 --strictPort',url:'http://127.0.0.1:5187',reuseExistingServer:true,timeout:30000 },
  ],
})
