import type { components } from './schema'

export type ServiceMetadata = components['schemas']['ServiceMetadata']
export type HealthResponse = components['schemas']['HealthResponse']
export type SessionView = components['schemas']['SessionView']
export type RecoveryMessage = components['schemas']['RecoveryMessage']
export type MemberView = components['schemas']['MemberView']
export type WorkspaceSettingsView = components['schemas']['WorkspaceSettingsView']
export type IntakeDefaultsView = components['schemas']['IntakeDefaultsView']
export type SavedDraftView = components['schemas']['SavedDraftView']
export type SourceView = components['schemas']['SourceView']
export type VersionRef = components['schemas']['VersionRef']
export type CreateDraftRequest = components['schemas']['CreateDraftRequest']
export type ScanView = components['schemas']['ScanView']
export type ScanSettingsView = components['schemas']['ScanSettingsView']
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

export class ApiConflictError extends ApiRequestError {
  readonly currentVersion: VersionRef

  constructor(currentVersion: VersionRef, message: string) {
    super(409, 'version_conflict', message)
    this.name = 'ApiConflictError'
    this.currentVersion = currentVersion
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
  if (
    response.status === 409 && typeof body === 'object' && body !== null &&
    'code' in body && body.code === 'version_conflict' &&
    'message' in body && typeof body.message === 'string' &&
    'current_version' in body && typeof body.current_version === 'object' &&
    body.current_version !== null
  ) {
    throw new ApiConflictError(body.current_version as VersionRef, body.message)
  }
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

export function getIntakeDefaults(
  workspaceId: string, signal?: AbortSignal,
): Promise<IntakeDefaultsView> {
  return get<IntakeDefaultsView>(
    `/documents/intake-defaults/${encodeURIComponent(workspaceId)}`, signal,
  )
}

export function createPastedDraft(
  draft: CreateDraftRequest, csrfToken: string,
): Promise<SavedDraftView> {
  return post<SavedDraftView>('/documents', draft, csrfToken)
}

export async function createFileDraft(
  workspaceId: string, file: File, title: string, categories: string[],
  phoneRegion: string, retentionDays: number, csrfToken: string,
): Promise<SavedDraftView> {
  const form = new FormData()
  form.append('workspace_id', workspaceId)
  form.append('file', file)
  form.append('title', title)
  form.append('categories', categories.join(','))
  form.append('phone_region', phoneRegion)
  form.append('retention_days', String(retentionDays))
  const response = await fetch('/api/v1/documents/from-file', {
    method: 'POST',
    credentials: 'same-origin',
    cache: 'no-store',
    headers: { 'X-CSRF-Token': csrfToken, Accept: 'application/json' },
    body: form,
  })
  await requireSuccess(response)
  return response.json() as Promise<SavedDraftView>
}

export function getDraft(documentId: string, signal?: AbortSignal): Promise<SourceView> {
  return get<SourceView>(`/documents/${encodeURIComponent(documentId)}/source`, signal)
}

export function saveDraftSource(
  documentId: string, expected: VersionRef, source: string, csrfToken: string,
): Promise<SavedDraftView> {
  return sendJson<SavedDraftView>(
    'PUT', `/documents/${encodeURIComponent(documentId)}/source`,
    { expected, source }, csrfToken,
  )
}

export function getScan(documentId: string, signal?: AbortSignal): Promise<ScanView> {
  return get<ScanView>(`/documents/${encodeURIComponent(documentId)}/scan`, signal)
}

export function startScan(
  documentId: string, expected: VersionRef, csrfToken: string,
): Promise<ScanView> {
  return post<ScanView>(
    `/documents/${encodeURIComponent(documentId)}/scan`, { expected }, csrfToken,
  )
}

export function updateScanSettings(
  documentId: string, expected: VersionRef, categories: Array<'email' | 'phone'>,
  phoneRegion: string, csrfToken: string,
): Promise<ScanSettingsView> {
  return sendJson<ScanSettingsView>(
    'PUT', `/documents/${encodeURIComponent(documentId)}/scan-settings`,
    { expected, categories, phone_region: phoneRegion }, csrfToken,
  )
}
