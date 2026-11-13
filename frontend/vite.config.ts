import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import { resolve } from 'node:path'

/**
 * 원래 benchmark 프론트의 multi-entry 구성을 그대로 두고, 로컬 통합 backend로만 향하게 한다.
 *
 * - `envPrefix`는 `VITE_`만: 루트 `.env`의 다른 값(원격 preview API 주소·키)을 브라우저로
 *   내보내지 않는다. 그래서 화면이 Koyeb 등 원격으로 우회하지 않는다.
 * - `/api`는 기본 `http://127.0.0.1:8000`(로컬 통합 backend). 다른 곳으로 붙일 때만
 *   `BENCHMARK_BACKEND_URL`로 바꾼다.
 * - `changeOrigin: false`는 로컬 개발용 origin 유지(서버의 Origin 검사를 깨지 않는다).
 * - `timeout: 0`은 한 경기 생성이 요청당 300초까지 걸릴 수 있어 프록시가 먼저 끊지 않게 한다.
 * - `strictPort: true`는 5173이 이미 쓰이면 조용히 다른 포트로 옮겨가지 않게 한다(증거 혼동 방지).
 */
export default defineConfig({
  plugins: [vue()],
  envDir: resolve(__dirname, '..'),
  envPrefix: ['VITE_'],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: process.env.BENCHMARK_BACKEND_URL ?? 'http://127.0.0.1:8000',
        changeOrigin: false,
        timeout: 0,
        proxyTimeout: 0,
      },
    },
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        broadcast: resolve(__dirname, 'broadcast.html'),
        broadcastProgram: resolve(__dirname, 'broadcast-program.html'),
        programBottomLab: resolve(__dirname, 'broadcast-program-bottom-lab.html'),
        statsLab: resolve(__dirname, 'broadcast-stats-lab.html'),
        scoreboardLab: resolve(__dirname, 'broadcast-scoreboard-lab.html'),
        formationLab: resolve(__dirname, 'broadcast-formation-lab.html'),
        alertLab: resolve(__dirname, 'broadcast-alert-lab.html'),
      },
    },
  },
})
