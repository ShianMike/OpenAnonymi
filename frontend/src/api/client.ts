import { API_CREDENTIALS, apiUrl } from './base'
import { trackedRequest } from './requestActivity'
import type { components } from './schema'

export type ServiceMetadata = components['schemas']['ServiceMetadata']
export type HealthResponse = components['schemas']['HealthResponse']
export type SessionView = components['schemas']['SessionView']
export type ChallengeView = components['schemas']['ChallengeView']
export type EnrollmentView = components['schemas']['EnrollmentView']
export type SecondFactorState = components['schemas']['SecondFactorState']
export type DeviceView = components['schemas']['DeviceView']
export type RecoveryMessage = components['schemas']['RecoveryMessage']
export type MemberView = components['schemas']['MemberView']
export type WorkspaceSettingsView = components['schemas']['WorkspaceSettingsView']
export type CleanupHealthView = components['schemas']['CleanupHealthView']
export type IntakeDefaultsView = components['schemas']['IntakeDefaultsView']
export type SavedDraftView = components['schemas']['SavedDraftView']
export type SourceView = components['schemas']['SourceView']
export type VersionRef = components['schemas']['VersionRef']
export type CreateDraftRequest = components['schemas']['CreateDraftRequest']
export type ScanView = components['schemas']['ScanView']
export type ScanSettingsView = components['schemas']['ScanSettingsView']
export type FindingsView = components['schemas']['FindingsView']
export type PreviewView = components['schemas']['PreviewView']
export type CompletionView = components['schemas']['CompletionView']
export type ReviewSummaryView = components['schemas']['ReviewSummaryView']
export type DocumentIndexView = components['schemas']['DocumentIndexView']
export type OverviewView = components['schemas']['OverviewView']
export type DeletedView = components['schemas']['DeletedView']
export type ActivityView = components['schemas']['ActivityView']
export type PresetView = components['schemas']['PresetView']
export type PresetInput = components['schemas']['PresetInput']
export type DocumentHistoryView = components['schemas']['DocumentHistoryView']
export type CopyPayloadView = components['schemas']['CopyPayloadView']
export type ExportEventView = components['schemas']['ExportEventView']
export type ExactMatchesView = components['schemas']['ExactMatchesView']
export type SourceSpan = components['schemas']['SourceSpan']
export type FindingCategory = components['schemas']['FindingCategory']
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

export async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  return trackedRequest(apiUrl(path), {
    method: 'GET',
    credentials: API_CREDENTIALS,
    cache: 'no-store',
    signal,
    headers: { Accept: 'application/json' },
  }, async (response) => {
    await requireSuccess(response)
    return response.json() as Promise<T>
  })
}

export async function requireSuccess(response: Response): Promise<void> {
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

export async function sendJson<T>(
  method: 'POST' | 'PATCH' | 'PUT', path: string, body?: object, csrfToken?: string,
): Promise<T> {
  return trackedRequest(apiUrl(path), {
    method,
    credentials: API_CREDENTIALS,
    cache: 'no-store',
    headers: {
      Accept: 'application/json',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  }, async (response) => {
    await requireSuccess(response)
    if (response.status === 204) return undefined as T
    return response.json() as Promise<T>
  })
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
  return trackedRequest(apiUrl('/health/ready'), {
    credentials: API_CREDENTIALS,
    cache: 'no-store',
    signal,
  }, async (response) => {
    if (response.status !== 200 && response.status !== 503) {
      throw new ApiRequestError(response.status, 'readiness_failed', 'Database readiness could not be checked.')
    }
    return response.json() as Promise<HealthResponse>
  })
}

export function getSession(signal?: AbortSignal): Promise<SessionView> {
  return get<SessionView>('/auth/session', signal)
}

export function getCleanupHealth(workspaceId: string, signal?: AbortSignal): Promise<CleanupHealthView> {
  return get(`/workspaces/${encodeURIComponent(workspaceId)}/cleanup-health`, signal)
}

export function signIn(email: string, password: string): Promise<SessionView | ChallengeView> {
  return post('/auth/sign-in', { email, password })
}

export function finishSecondFactor(code: string): Promise<SessionView> {
  return post('/auth/sign-in/second-factor', { code })
}

export function startForcedEnrollment(): Promise<EnrollmentView> {
  return post('/auth/sign-in/enrollment/start', {})
}

export function finishForcedEnrollment(code: string): Promise<components['schemas']['ForcedEnrollmentView']> {
  return post('/auth/sign-in/enrollment/confirm', { code })
}

export function getSecondFactor(signal?: AbortSignal): Promise<SecondFactorState> {
  return get('/auth/second-factor', signal)
}

export function startEnrollment(csrfToken: string): Promise<EnrollmentView> {
  return post('/auth/second-factor/enrollment/start', {}, csrfToken)
}

export function confirmEnrollment(code: string, csrfToken: string): Promise<components['schemas']['BackupCodesView']> {
  return post('/auth/second-factor/enrollment/confirm', { code }, csrfToken)
}

export function changeSecondFactor(password: string, code: string, disable: boolean, csrfToken: string): Promise<components['schemas']['BackupCodesView'] | void> {
  return post(`/auth/second-factor/${disable ? 'disable' : 'backup-codes'}`, { password, code }, csrfToken)
}

export function getDevices(signal?: AbortSignal): Promise<DeviceView[]> {
  return get('/auth/sessions', signal)
}

export function revokeDevice(id: string, csrfToken: string): Promise<void> {
  return post(`/auth/sessions/${encodeURIComponent(id)}/revoke`, {}, csrfToken)
}

export function revokeOtherDevices(csrfToken: string): Promise<void> {
  return post('/auth/sessions/revoke-others', {}, csrfToken)
}

export function resetMemberSecondFactor(workspaceId: string, userId: string, csrfToken: string): Promise<void> {
  return post(`/workspaces/${encodeURIComponent(workspaceId)}/members/${encodeURIComponent(userId)}/second-factor/reset`, {}, csrfToken)
}

export function signUp(email: string, password: string, workspaceName: string): Promise<components['schemas']['RegistrationMessage']> {
  return post('/auth/sign-up', { email, password, workspace_name: workspaceName })
}

export function verifySignUp(email: string, code: string, password: string): Promise<SessionView> {
  return post('/auth/sign-up/verify', { email, code, password })
}

export function requestEmailVerification(csrfToken: string): Promise<components['schemas']['RegistrationMessage']> {
  return post('/auth/email-verification', {}, csrfToken)
}

export function confirmEmailVerification(code: string, csrfToken: string): Promise<void> {
  return post('/auth/email-verification/confirm', { code }, csrfToken)
}

export async function signOut(csrfToken: string): Promise<void> {
  return trackedRequest(apiUrl('/auth/sign-out'), {
    method: 'POST',
    credentials: API_CREDENTIALS,
    cache: 'no-store',
    headers: { 'X-CSRF-Token': csrfToken },
  }, async (response) => {
    await requireSuccess(response)
  })
}

export async function changePassword(
  currentPassword: string, newPassword: string, csrfToken: string,
): Promise<void> {
  return trackedRequest(apiUrl('/auth/change-password'), {
    method: 'POST',
    credentials: API_CREDENTIALS,
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      'X-CSRF-Token': csrfToken,
    },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  }, async (response) => {
    await requireSuccess(response)
  })
}

export function requestRecovery(email: string): Promise<RecoveryMessage> {
  return post<RecoveryMessage>('/auth/recovery/request', { email })
}

export async function completeRecovery(
  email: string, code: string, newPassword: string,
): Promise<void> {
  return trackedRequest(apiUrl('/auth/recovery/complete'), {
    method: 'POST',
    credentials: API_CREDENTIALS,
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ email, code, new_password: newPassword }),
  }, async (response) => {
    await requireSuccess(response)
  })
}

export function getWorkspaceSettings(
  workspaceId: string, signal?: AbortSignal,
): Promise<WorkspaceSettingsView> {
  return get<WorkspaceSettingsView>(`/workspaces/${encodeURIComponent(workspaceId)}/settings`, signal)
}

export function getWorkspaceDocuments(
  workspaceId: string, signal?: AbortSignal,
): Promise<DocumentIndexView[]> {
  return get<DocumentIndexView[]>(`/workspaces/${encodeURIComponent(workspaceId)}/documents`, signal)
}

export function getWorkspaceOverview(
  workspaceId: string, signal?: AbortSignal,
): Promise<OverviewView> {
  return get<OverviewView>(`/workspaces/${encodeURIComponent(workspaceId)}/overview`, signal)
}

export function getWorkspaceActivity(
  workspaceId: string, signal?: AbortSignal,
): Promise<ActivityView> {
  return get<ActivityView>(`/workspaces/${encodeURIComponent(workspaceId)}/activity`, signal)
}

export function getWorkspacePresets(
  workspaceId: string, signal?: AbortSignal,
): Promise<PresetView[]> {
  return get<PresetView[]>(`/workspaces/${encodeURIComponent(workspaceId)}/presets`, signal)
}

export function getDocumentHistory(
  workspaceId: string, documentId: string, signal?: AbortSignal,
): Promise<DocumentHistoryView> {
  return get<DocumentHistoryView>(
    `/workspaces/${encodeURIComponent(workspaceId)}/documents/${encodeURIComponent(documentId)}/history`,
    signal,
  )
}

export function createWorkspacePreset(
  workspaceId: string, value: PresetInput, csrfToken: string,
): Promise<PresetView> {
  return post<PresetView>(
    `/workspaces/${encodeURIComponent(workspaceId)}/presets`, value, csrfToken,
  )
}

export function updateWorkspacePreset(
  workspaceId: string, presetId: string, value: PresetInput,
  expectedVersion: number, csrfToken: string,
): Promise<PresetView> {
  return sendJson<PresetView>(
    'PUT', `/workspaces/${encodeURIComponent(workspaceId)}/presets/${encodeURIComponent(presetId)}`,
    { ...value, expected_version: expectedVersion }, csrfToken,
  )
}

export async function deleteDocument(documentId: string, csrfToken: string): Promise<DeletedView> {
  return trackedRequest(apiUrl(`/documents/${encodeURIComponent(documentId)}`), {
    method: 'DELETE',
    credentials: API_CREDENTIALS,
    cache: 'no-store',
    headers: { Accept: 'application/json', 'X-CSRF-Token': csrfToken },
  }, async (response) => {
    await requireSuccess(response)
    return response.json() as Promise<DeletedView>
  })
}

export function getMembers(workspaceId: string, signal?: AbortSignal): Promise<MemberView[]> {
  return get<MemberView[]>(`/workspaces/${encodeURIComponent(workspaceId)}/members`, signal)
}

export function updateWorkspaceSettings(
  workspaceId: string, expectedVersion: number, contentDays: number,
  activityDays: number, csrfToken: string, requireSecondFactor?: boolean,
): Promise<WorkspaceSettingsView> {
  return sendJson<WorkspaceSettingsView>(
    'PUT', `/workspaces/${encodeURIComponent(workspaceId)}/settings`,
    { expected_version: expectedVersion, content_retention_days: contentDays,
      activity_retention_days: activityDays,
      ...(requireSecondFactor === undefined ? {} : { require_second_factor: requireSecondFactor }) }, csrfToken,
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
  phoneRegion: string, retentionDays: number, csrfToken: string, presetId?: string,
): Promise<SavedDraftView> {
  const form = new FormData()
  form.append('workspace_id', workspaceId)
  form.append('file', file)
  form.append('title', title)
  form.append('categories', categories.join(','))
  form.append('phone_region', phoneRegion)
  form.append('retention_days', String(retentionDays))
  if (presetId) form.append('preset_id', presetId)
  return trackedRequest(apiUrl('/documents/from-file'), {
    method: 'POST',
    credentials: API_CREDENTIALS,
    cache: 'no-store',
    headers: { 'X-CSRF-Token': csrfToken, Accept: 'application/json' },
    body: form,
  }, async (response) => {
    await requireSuccess(response)
    return response.json() as Promise<SavedDraftView>
  })
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
  documentId: string, expected: VersionRef, categories: FindingCategory[],
  phoneRegion: string, csrfToken: string, language?: string,
): Promise<ScanSettingsView> {
  return sendJson<ScanSettingsView>(
    'PUT', `/documents/${encodeURIComponent(documentId)}/scan-settings`,
    { expected, categories, phone_region: phoneRegion, language }, csrfToken,
  )
}

export function getFindings(
  documentId: string, signal?: AbortSignal,
): Promise<FindingsView> {
  return get<FindingsView>(`/documents/${encodeURIComponent(documentId)}/findings`, signal)
}

export function getPreview(
  documentId: string, signal?: AbortSignal,
): Promise<PreviewView> {
  return get<PreviewView>(`/documents/${encodeURIComponent(documentId)}/preview`, signal)
}

export function addManualFinding(
  documentId: string, expected: VersionRef, span: SourceSpan,
  category: FindingCategory, csrfToken: string,
): Promise<FindingsView> {
  return post<FindingsView>(
    `/documents/${encodeURIComponent(documentId)}/findings`,
    { expected, span, category }, csrfToken,
  )
}

export function reviseFinding(
  documentId: string, findingId: string, expected: VersionRef,
  span: SourceSpan, category: FindingCategory, csrfToken: string,
): Promise<FindingsView> {
  return sendJson<FindingsView>(
    'PUT', `/documents/${encodeURIComponent(documentId)}/findings/${encodeURIComponent(findingId)}`,
    { expected, span, category }, csrfToken,
  )
}

export function removeFinding(
  documentId: string, findingId: string, expected: VersionRef, csrfToken: string,
): Promise<FindingsView> {
  return post<FindingsView>(
    `/documents/${encodeURIComponent(documentId)}/findings/${encodeURIComponent(findingId)}/remove`,
    { expected }, csrfToken,
  )
}

export function getExactMatches(
  documentId: string, findingId: string, signal?: AbortSignal,
): Promise<ExactMatchesView> {
  return get<ExactMatchesView>(
    `/documents/${encodeURIComponent(documentId)}/findings/${encodeURIComponent(findingId)}/exact-matches`,
    signal,
  )
}

export function addExactMatch(
  documentId: string, findingId: string, expected: VersionRef,
  span: SourceSpan, csrfToken: string,
): Promise<FindingsView> {
  return post<FindingsView>(
    `/documents/${encodeURIComponent(documentId)}/findings/${encodeURIComponent(findingId)}/exact-matches`,
    { expected, span }, csrfToken,
  )
}

export function mergeFindings(
  documentId: string, findingId: string, targetFindingId: string,
  expected: VersionRef, csrfToken: string,
): Promise<FindingsView> {
  return post<FindingsView>(
    `/documents/${encodeURIComponent(documentId)}/findings/${encodeURIComponent(findingId)}/merge`,
    { expected, target_finding_id: targetFindingId }, csrfToken,
  )
}

export function splitFinding(
  documentId: string, findingId: string, expected: VersionRef, csrfToken: string,
): Promise<FindingsView> {
  return post<FindingsView>(
    `/documents/${encodeURIComponent(documentId)}/findings/${encodeURIComponent(findingId)}/split`,
    { expected }, csrfToken,
  )
}

export function decideFindings(
  documentId: string, findingId: string, expected: VersionRef,
  action: 'label' | 'redact' | 'keep', keepReason: 'false_match' | 'intended_disclosure' | null,
  groupScope: boolean, affectedFindingIds: string[], csrfToken: string,
): Promise<FindingsView> {
  return post<FindingsView>(
    `/documents/${encodeURIComponent(documentId)}/findings/${encodeURIComponent(findingId)}/decision`,
    { expected, action, keep_reason: keepReason, group_scope: groupScope,
      affected_finding_ids: affectedFindingIds }, csrfToken,
  )
}

export function undoReviewEdit(
  documentId: string, expected: VersionRef, csrfToken: string,
): Promise<FindingsView> {
  return post<FindingsView>(
    `/documents/${encodeURIComponent(documentId)}/review/undo`,
    { expected }, csrfToken,
  )
}

export function confirmReview(
  documentId: string, expected: VersionRef, csrfToken: string,
): Promise<CompletionView> {
  return post<CompletionView>(
    `/documents/${encodeURIComponent(documentId)}/complete`,
    { expected, confirmed_preview: true }, csrfToken,
  )
}

export function getReviewSummary(
  documentId: string, signal?: AbortSignal,
): Promise<ReviewSummaryView> {
  return get<ReviewSummaryView>(`/documents/${encodeURIComponent(documentId)}/summary`, signal)
}

export function getCopyPayload(
  documentId: string, expected: VersionRef, csrfToken: string,
): Promise<CopyPayloadView> {
  return post<CopyPayloadView>(
    `/documents/${encodeURIComponent(documentId)}/exports/copy-payload`,
    { expected }, csrfToken,
  )
}

export function recordCopySuccess(
  documentId: string, expected: VersionRef, completionId: string,
  eventId: string, csrfToken: string,
): Promise<ExportEventView> {
  return post<ExportEventView>(
    `/documents/${encodeURIComponent(documentId)}/exports/copy-success`,
    { expected, completion_id: completionId, event_id: eventId }, csrfToken,
  )
}

export async function downloadReviewedTxt(
  documentId: string, expected: VersionRef, eventId: string, csrfToken: string,
): Promise<Blob> {
  return trackedRequest(apiUrl(`/documents/${encodeURIComponent(documentId)}/exports/txt`), {
    method: 'POST',
    credentials: API_CREDENTIALS,
    cache: 'no-store',
    headers: {
      Accept: 'text/plain',
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrfToken,
    },
    body: JSON.stringify({ expected, event_id: eventId }),
  }, async (response) => {
    await requireSuccess(response)
    return response.blob()
  })
}
