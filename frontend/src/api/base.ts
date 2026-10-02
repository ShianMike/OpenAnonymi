/** Same-origin default, used with the development proxy or a same-origin deployment. */
export const DEFAULT_API_BASE = '/api/v1'

/**
 * Normalize the build-time API base. vite.config.ts validates the value; this keeps the
 * runtime tolerant of an empty value or trailing slashes.
 */
export function resolveApiBase(raw: string | undefined): string {
  const value = raw?.trim() ?? ''
  return value ? value.replace(/\/+$/, '') : DEFAULT_API_BASE
}

/** e.g. https://<backend-host>/api/v1 in production, `/api/v1` locally. */
export const API_BASE = resolveApiBase(import.meta.env.VITE_API_BASE_URL)

/** Join an API path such as `/auth/session` onto the configured base. */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}

/**
 * The session cookie belongs to the API origin, which can differ from the website's origin
 * in production, so every API request includes credentials.
 */
export const API_CREDENTIALS: RequestCredentials = 'include'
