import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type Plugin } from 'vite'

const DEFAULT_API_BASE = '/api/v1'
const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]'])

/**
 * Only the API base URL is explicitly compiled into public JavaScript. Other user-supplied
 * VITE_* variables fail the build; provider observability metadata is discarded below.
 */
function apiBaseFrom(env: Record<string, string>, onVercel: boolean): string {
  const unexpected = Object.keys(env).filter(
    (key) => key !== 'VITE_API_BASE_URL',
  )
  if (unexpected.length > 0) {
    throw new Error(`Only VITE_API_BASE_URL may use the VITE_ prefix. Remove: ${unexpected.join(', ')}.`)
  }
  const raw = env.VITE_API_BASE_URL?.trim() ?? ''
  if (!raw) {
    if (onVercel) {
      throw new Error('Set VITE_API_BASE_URL (https://<backend-host>/api/v1) for this Vercel environment.')
    }
    return DEFAULT_API_BASE
  }
  if (raw.startsWith('/') && !raw.startsWith('//')) {
    const path = raw.replace(/\/+$/, '')
    if (onVercel || path !== DEFAULT_API_BASE) {
      throw new Error('Vercel requires an absolute HTTPS API URL; local paths must be /api/v1.')
    }
    return path
  }
  let url: URL
  try {
    url = new URL(raw)
  } catch {
    throw new Error('VITE_API_BASE_URL must be an absolute URL such as https://api.example.com/api/v1.')
  }
  const localHttp = url.protocol === 'http:' && LOOPBACK_HOSTS.has(url.hostname) && !onVercel
  if (url.protocol !== 'https:' && !localHttp) throw new Error('VITE_API_BASE_URL must use https.')
  if (url.username || url.password || url.search || url.hash) {
    throw new Error('VITE_API_BASE_URL must not contain credentials, a query or a fragment.')
  }
  const path = url.pathname.replace(/\/+$/, '')
  if (path !== DEFAULT_API_BASE) throw new Error('VITE_API_BASE_URL path must be /api/v1.')
  return `${url.origin}${path}`
}

/**
 * Production builds carry a Content-Security-Policy whose connect-src names the configured
 * API origin. frame-ancestors is sent by the API host's HTTP security headers.
 */
function contentSecurityPolicy(apiBase: string): Plugin {
  const apiOrigin = apiBase.startsWith('/') ? '' : ` ${new URL(apiBase).origin}`
  const policy = [
    "default-src 'self'",
    "script-src 'self'",
    // Radix scroll locking and Motion presence animations insert <style> elements.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    `connect-src 'self'${apiOrigin}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "worker-src 'none'",
  ].join('; ')
  return {
    name: 'openanonymi-content-security-policy',
    apply: 'build',
    transformIndexHtml(html) {
      const charset = /<meta charset=[^>]*>/i
      if (!charset.test(html)) throw new Error('index.html needs a charset meta element.')
      return html.replace(
        charset,
        (tag) => `${tag}\n    <meta http-equiv="Content-Security-Policy" content="${policy}" />`,
      )
    },
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  // Vercel injects this even when automatic system-env exposure is disabled. It is never
  // used by this static app and must not become part of its public environment.
  if (process.env.VERCEL) delete env.VITE_VERCEL_OBSERVABILITY_CLIENT_CONFIG
  const apiBase = apiBaseFrom(env, Boolean(process.env.VERCEL))
  return {
    plugins: [react(), contentSecurityPolicy(apiBase)],
    // Disable Vite's implicit public-env injection. API_BASE is defined explicitly.
    envPrefix: [],
    // Bundle the validated, normalized value rather than the raw environment string.
    define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify(apiBase) },
    build: {
      rolldownOptions: {
        output: {
          codeSplitting: {
            groups: [
              { name: 'react', test: /node_modules[\\/](?:react|react-dom|scheduler)[\\/]/, priority: 40 },
              { name: 'router', test: /node_modules[\\/]react-router(?:-dom)?[\\/]/, priority: 30 },
              { name: 'radix', test: /node_modules[\\/]@radix-ui[\\/]/, priority: 20 },
              { name: 'icons', test: /node_modules[\\/]lucide-react[\\/]/, priority: 10 },
            ],
          },
        },
      },
    },
    server: {
      proxy: { '/api': 'http://127.0.0.1:8000' },
    },
  }
})
