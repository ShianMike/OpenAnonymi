import { bindResponseScope, requestSessionScope } from './sessionEvents'

export type RequestActivity = { id: number; label: string; startedAt: number }
const listeners = new Set<() => void>()
let sequence = 0
let snapshot: readonly RequestActivity[] = []
export const requestSnapshot = () => snapshot
export const subscribeRequests = (listener: () => void) => {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}
function publish(next: readonly RequestActivity[]) {
  snapshot = next
  listeners.forEach(listener => listener())
}

/** Labels are static. URLs, source text, identifiers and credentials never enter the store. */
export function requestLabel(path: string, method: string) {
  const read = method === 'GET'
  if (path.includes('/auth/session')) return 'Checking your session'
  if (path.includes('/auth/sign-in')) return 'Signing you in'
  if (path.includes('/auth/sign-up')) return 'Creating your workspace'
  if (path.includes('/auth/sign-out')) return 'Signing you out'
  if (path.includes('/auth/recovery')) return 'Processing account recovery'
  if (path.includes('/auth/change-password')) return 'Updating your password'
  if (path.includes('/import-preview')) return 'Extracting document text'
  if (path.includes('/copy')) return 'Preparing reviewed text'
  if (path.includes('/exports')) return 'Preparing your reviewed download'
  if (path.includes('/recovery')) return read ? 'Checking working drafts' : 'Updating your draft backup'
  if (path.includes('/compare')) return 'Comparing saved revisions'
  if (path.includes('/comments')) return read ? 'Loading finding discussion' : 'Updating finding discussion'
  if (path.includes('/teammates')) return 'Loading active teammates'
  if (path.includes('/handoff') || path.includes('/approval')) return read ? 'Checking team review' : 'Updating team review'
  if (path.includes('/scan-settings')) return read ? 'Loading suggestion settings' : 'Saving suggestion settings'
  if (path.endsWith('/scan')) return read ? 'Checking suggestion status' : 'Checking for sensitive details'
  if (path.includes('/findings')) return read ? 'Loading review findings' : 'Saving your decision'
  if (path.includes('/completion') || path.endsWith('/complete')) return read ? 'Checking review confirmation' : 'Confirming your reviewed version'
  if (path.includes('/intake-defaults')) return 'Loading review defaults'
  if (path.endsWith('/source')) return read ? 'Loading saved source text' : 'Saving a new source revision'
  if (path.endsWith('/preview')) return 'Preparing reviewed output'
  if (path.endsWith('/summary')) return 'Loading your review summary'
  if (path.includes('/overview')) return 'Loading review counts'
  if (path.includes('/activity')) return 'Loading workspace activity'
  if (path.includes('/history')) return 'Loading review history'
  if (path.includes('/rules/test')) return 'Checking the rule against your example'
  if (path.includes('/presets') || path.includes('/rules')) return read ? 'Loading review rules' : 'Updating review rules'
  if (path.includes('/settings')) return read ? 'Loading workspace settings' : 'Saving workspace settings'
  if (path.includes('/members')) return read ? 'Loading workspace members' : 'Updating workspace membership'
  if (path.includes('/from-paste') || path.includes('/from-file') || (path.endsWith('/documents') && method === 'POST')) return 'Creating your saved review'
  if (path.includes('/documents')) return read ? 'Loading your reviews' : method === 'DELETE' ? 'Removing the review' : 'Saving your review'
  return read ? 'Loading workspace data' : 'Saving your changes'
}

/** Pathname only, so an absolute API origin or query string never affects the label. */
export function requestPath(url: string) {
  try { return new URL(url, 'http://relative.invalid').pathname }
  catch { return url.split(/[?#]/)[0] }
}

/** Keep the operation active through response consumption, including an export's bytes. */
export async function trackedRequest<T>(input: RequestInfo | URL, init: RequestInit, consume: (response: Response) => Promise<T>): Promise<T> {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
  const path = requestPath(url)
  if (path.includes('/health/') || path.endsWith('/meta')) return consume(await fetch(input, init))
  const id = ++sequence
  const scope = requestSessionScope(init)
  const method = init?.method ?? (input instanceof Request ? input.method : 'GET')
  publish([...snapshot, { id, label: requestLabel(path, method.toUpperCase()), startedAt: Date.now() }])
  try { const response = await fetch(input, init); bindResponseScope(response, scope); return await consume(response) }
  finally { publish(snapshot.filter(item => item.id !== id)) }
}
