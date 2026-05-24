/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_USE_MOCK?: string
  readonly VITE_BACKEND_URL?: string
  readonly VITE_BROADCAST_USE_API_FOOTBALL?: string
  readonly VITE_API_FOOTBALL_KEY?: string
  readonly VITE_API_FOOTBALL_BASE_URL?: string
  readonly VITE_API_FOOTBALL_POLL_MS?: string
  readonly VITE_API_FOOTBALL_LINEUPS_REFRESH_MS?: string
  readonly APIKEY?: string
  readonly API_FOOTBALL_KEY?: string
  readonly API_FOOTBALL_HOST?: string
}
interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const component: DefineComponent<{}, {}, any>
  export default component
}
