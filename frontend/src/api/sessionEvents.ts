export const SESSION_ENDED_EVENT = 'openanonymi:session-ended'

let activeScope = ''
const scopeListeners = new Set<() => void>()
const endedListeners = new Set<(scope: string) => void>()
const responseScopes = new WeakMap<Response, string>()
export function setSessionScope(scope: string) {
  if (activeScope === scope) return
  activeScope = scope
  scopeListeners.forEach(listener => listener())
}
export const getSessionScope = () => activeScope
export function subscribeSessionScope(listener: () => void) {
  scopeListeners.add(listener)
  return () => { scopeListeners.delete(listener) }
}
export function subscribeSessionEnded(listener: (scope: string) => void) {
  endedListeners.add(listener)
  return () => { endedListeners.delete(listener) }
}
export function requestSessionScope(init: RequestInit) { return new Headers(init.headers).get('X-CSRF-Token') ?? activeScope }
export function bindResponseScope(response: Response, scope: string) { responseScopes.set(response, scope) }
export function reportSessionEnded(response: Response, code: string) {
  const scope = responseScopes.get(response)
  if (response.status === 401 && code === 'sign_in_required' && scope) reportEndedScope(scope)
}
export function reportEndedScope(scope: string) {
  endedListeners.forEach(listener => listener(scope))
  window.dispatchEvent(new CustomEvent(SESSION_ENDED_EVENT, { detail: { scope } }))
}
export function matchesSessionScope(event: Event, scope: string) { return !!scope && (event as CustomEvent<{ scope: string }>).detail?.scope === scope }
