import { defineConfig, devices } from '@playwright/test'

// MP-02 검사 화면 확인용 격리 설정.
//
// MP-01의 `playwright.config.ts`는 :5173 개발 서버를 재사용한다. 그 서버는 실제
// 개발 DB(preview_dev)를 보므로, 이 파일은 프록시 대상과 포트를 분리해 전용 로컬
// 테스트 DB만 보는 백엔드(:8010)와 프론트(:5273)를 쓴다. 서버는 미리 띄워 둔 것을
// 재사용하며, 여기서 새로 시작하지 않는다.
const FRONTEND_URL = process.env.PREVIEW_UI_FRONTEND_URL ?? 'http://127.0.0.1:5273'

export default defineConfig({
  testDir: './e2e',
  testMatch: 'match-preview-inspector.spec.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: FRONTEND_URL,
    // trace는 로그인 POST 본문을 남긴다. 합성 계정이지만 실패 아티팩트에 자격 증명을
    // 남기지 않는다는 기존 결정을 그대로 따른다.
    trace: 'off',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
