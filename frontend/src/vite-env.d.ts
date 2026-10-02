/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute backend API base ending in /api/v1, set at build time. */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
