import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type Plugin } from 'vite'

const DEFAULT_API_BASE = '/api/v1'
const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]'])

/**
 * Every VITE_* value is compiled into public JavaScript. Only the API base URL is allowed,
 * plus the VITE_VERCEL_* build metadata Vercel exposes automatically, so database URLs,
 * keys or SMTP settings can never be bundled by mistake.
 */
function apiBaseFrom(env: Record<string, string>, onVercel: boolean): string {
  const unexpected = Object.keys(env).filter(
    (key) => key !== 'VITE_API_BASE_URL' && !key.startsWith('VITE_VERCEL_'),
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
    if (!path.endsWith('/api/v1')) throw new Error('VITE_API_BASE_URL must end with /api/v1.')
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
  if (!path.endsWith('/api/v1')) throw new Error('VITE_API_BASE_URL must end with /api/v1.')
  return `${url.origin}${path}`
}

/**
 * Production builds carry a Content-Security-Policy whose connect-src names the configured
 * API origin. frame-ancestors cannot be set from a meta element; vercel.json sends it.
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
  const apiBase = apiBaseFrom(loadEnv(mode, process.cwd(), 'VITE_'), Boolean(process.env.VERCEL))
  return {
    plugins: [react(), contentSecurityPolicy(apiBase)],
    // Bundle the validated, normalized value rather than the raw environment string.
    define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify(apiBase) },
    server: {
      proxy: { '/api': 'http://127.0.0.1:8000' },
    },
  }
})
