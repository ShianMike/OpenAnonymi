import type { components } from './schema'

export type ServiceMetadata = components['schemas']['ServiceMetadata']
export type HealthResponse = components['schemas']['HealthResponse']
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
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    if (isErrorResponse(body)) {
      throw new ApiRequestError(response.status, body.code, body.message)
    }
    throw new ApiRequestError(response.status, 'request_failed', `Request failed (${response.status}).`)
  }
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
