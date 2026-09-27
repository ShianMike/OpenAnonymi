import type { components } from './schema'

export type ServiceMetadata = components['schemas']['ServiceMetadata']
export type HealthResponse = components['schemas']['HealthResponse']
export type SessionView = components['schemas']['SessionView']
export type RecoveryMessage = components['schemas']['RecoveryMessage']
type ErrorResponse = components['schemas']['ErrorResponse']

export class ApiRequestError extends Error {
  readonly status: number
  readonly code: string

  constructor(
    status: number,
    code: string,
    message: string,
  ) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
    this.code = code
  }
}

function isErrorResponse(value: unknown): value is ErrorResponse {
  return typeof value === 'object' && value !== null &&
    'code' in value && typeof value.code === 'string' &&
    'message' in value && typeof value.message === 'string'
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method: 'GET',
    credentials: 'same-origin',
    cache: 'no-store',
    signal,
    headers: { Accept: 'application/json' },
  })
  await requireSuccess(response)
  return response.json() as Promise<T>
}

async function requireSuccess(response: Response): Promise<void> {
  if (response.ok) return
  const body: unknown = await response.json().catch(() => null)
  if (isErrorResponse(body)) {
    throw new ApiRequestError(response.status, body.code, body.message)
  }
  throw new ApiRequestError(response.status, 'request_failed', `Request failed (${response.status}).`)
}

async function post<T>(path: string, body: object, csrfToken?: string): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method: 'POST',
    credentials: 'same-origin',
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
    },
    body: JSON.stringify(body),
  })
  await requireSuccess(response)
  return response.json() as Promise<T>
}

export function getMetadata(signal?: AbortSignal): Promise<ServiceMetadata> {
  return get<ServiceMetadata>('/meta', signal)
}

export function getLiveness(signal?: AbortSignal): Promise<HealthResponse> {
  return get<HealthResponse>('/health/live', signal)
}

export async function getReadiness(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch('/api/v1/health/ready', {
    credentials: 'same-origin',
    cache: 'no-store',
    signal,
  })
  if (response.status !== 200 && response.status !== 503) {
    throw new ApiRequestError(response.status, 'readiness_failed', 'Database readiness could not be checked.')
  }
  return response.json() as Promise<HealthResponse>
}

export function getSession(signal?: AbortSignal): Promise<SessionView> {
  return get<SessionView>('/auth/session', signal)
}

export function signIn(email: string, password: string): Promise<SessionView> {
  return post<SessionView>('/auth/sign-in', { email, password })
}

export async function signOut(csrfToken: string): Promise<void> {
  const response = await fetch('/api/v1/auth/sign-out', {
    method: 'POST',
    credentials: 'same-origin',
    cache: 'no-store',
    headers: { 'X-CSRF-Token': csrfToken },
  })
  await requireSuccess(response)
}

export function requestRecovery(email: string): Promise<RecoveryMessage> {
  return post<RecoveryMessage>('/auth/recovery/request', { email })
}

export async function completeRecovery(
  email: string, code: string, newPassword: string,
): Promise<void> {
  const response = await fetch('/api/v1/auth/recovery/complete', {
    method: 'POST',
    credentials: 'same-origin',
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ email, code, new_password: newPassword }),
  })
  await requireSuccess(response)
}
