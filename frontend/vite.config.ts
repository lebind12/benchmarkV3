import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 로컬 개발에서 프론트(:5173)는 백엔드(:8000)로 프록시한다. 세션 쿠키가
// 같은 오리진에서 오가므로 브라우저 쪽 CORS 설정에 의존하지 않는다.
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
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
})
