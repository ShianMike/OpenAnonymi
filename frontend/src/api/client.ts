import type { components } from './schema'

export type ServiceMetadata = components['schemas']['ServiceMetadata']
export type HealthResponse = components['schemas']['HealthResponse']
export type SessionView = components['schemas']['SessionView']
export type RecoveryMessage = components['schemas']['RecoveryMessage']
export type MemberView = components['schemas']['MemberView']
export type WorkspaceSettingsView = components['schemas']['WorkspaceSettingsView']
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

async function sendJson<T>(
  method: 'POST' | 'PATCH' | 'PUT', path: string, body?: object, csrfToken?: string,
): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method,
    credentials: 'same-origin',
    cache: 'no-store',
    headers: {
      Accept: 'application/json',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  await requireSuccess(response)
  return response.json() as Promise<T>
}

function post<T>(path: string, body: object, csrfToken?: string): Promise<T> {
  return sendJson<T>('POST', path, body, csrfToken)
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

export function getWorkspaceSettings(
  workspaceId: string, signal?: AbortSignal,
): Promise<WorkspaceSettingsView> {
  return get<WorkspaceSettingsView>(`/workspaces/${encodeURIComponent(workspaceId)}/settings`, signal)
}

export function getMembers(workspaceId: string, signal?: AbortSignal): Promise<MemberView[]> {
  return get<MemberView[]>(`/workspaces/${encodeURIComponent(workspaceId)}/members`, signal)
}

export function updateWorkspaceSettings(
  workspaceId: string, expectedVersion: number, contentDays: number,
  activityDays: number, csrfToken: string,
): Promise<WorkspaceSettingsView> {
  return sendJson<WorkspaceSettingsView>(
    'PUT', `/workspaces/${encodeURIComponent(workspaceId)}/settings`,
    { expected_version: expectedVersion, content_retention_days: contentDays,
      activity_retention_days: activityDays }, csrfToken,
  )
}

export function inviteMember(
  workspaceId: string, email: string, role: 'member' | 'administrator', csrfToken: string,
): Promise<MemberView> {
  return post<MemberView>(
    `/workspaces/${encodeURIComponent(workspaceId)}/members/invitations`,
    { email, role }, csrfToken,
  )
}

export function changeMemberRole(
  workspaceId: string, userId: string, role: 'member' | 'administrator', csrfToken: string,
): Promise<MemberView> {
  return sendJson<MemberView>(
    'PATCH', `/workspaces/${encodeURIComponent(workspaceId)}/members/${encodeURIComponent(userId)}/role`,
    { role }, csrfToken,
  )
}

export function revokeMember(
  workspaceId: string, userId: string, csrfToken: string,
): Promise<MemberView> {
  return sendJson<MemberView>(
    'POST', `/workspaces/${encodeURIComponent(workspaceId)}/members/${encodeURIComponent(userId)}/revoke`,
    undefined, csrfToken,
  )
}

export function restoreMember(
  workspaceId: string, userId: string, csrfToken: string,
): Promise<MemberView> {
  return sendJson<MemberView>(
    'POST', `/workspaces/${encodeURIComponent(workspaceId)}/members/${encodeURIComponent(userId)}/restore`,
    undefined, csrfToken,
  )
}
