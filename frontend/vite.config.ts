import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 로컬 개발에서 프론트(:5173)는 백엔드(:8000)로 프록시한다. 세션 쿠키가
// 같은 오리진에서 오가므로 브라우저 쪽 CORS 설정에 의존하지 않는다.
// `VITE_BACKEND_TARGET`으로 대상만 바꿀 수 있다. 격리된 검증용 백엔드를 띄울 때
// 실제 계정이 연결된 개발 서버를 건드리지 않기 위한 것이다.
const BACKEND_TARGET = process.env.VITE_BACKEND_TARGET ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: BACKEND_TARGET,
        changeOrigin: false,
      },
    },
  },
})
