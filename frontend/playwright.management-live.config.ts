import { defineConfig, devices } from '@playwright/test'
const apiPort = process.env.MANAGEMENT_LIVE_PORT || '8016'
const frontendPort = process.env.MANAGEMENT_LIVE_FRONTEND_PORT || '5187'
export default defineConfig({
  expect: { timeout: 15000 },
  testDir: './e2e', testMatch: 'streamer-management-live.spec.ts', workers: 1, retries: 0,
  outputDir: '../out/management-live/test-results', reporter: [['list']],
  use: { baseURL: `http://127.0.0.1:${frontendPort}`, viewport: {width:1440,height:1000}, trace:'retain-on-failure' },
  projects: [{name:'management-live',use:{...devices['Desktop Chrome']}}],
  webServer: [
    { command: 'cd .. && .venv/bin/python -m tests.support.management_live_server',url:`http://127.0.0.1:${apiPort}/health`,reuseExistingServer:true,timeout:30000 },
    { command: `VITE_USE_MOCK=false VITE_BACKEND_URL=http://127.0.0.1:${apiPort} npm run dev -- --host 127.0.0.1 --port ${frontendPort} --strictPort`,url:`http://127.0.0.1:${frontendPort}`,reuseExistingServer:true,timeout:30000 },
  ],
})
