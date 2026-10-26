import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import { resolve } from 'node:path'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const environment = loadEnv(mode, resolve(__dirname, '..'), 'VITE_')
  return {
  plugins: [vue()],
  envDir: resolve(__dirname, '..'),
  envPrefix: ['VITE_', 'API_FOOTBALL_', 'APIKEY'],
  server: {
    proxy: {
      '/api': {
        target: environment.VITE_BACKEND_URL ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
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
  }
})
