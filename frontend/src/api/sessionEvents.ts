export const SESSION_ENDED_EVENT = 'openanonymi:session-ended'

let activeScope = ''
const responseScopes = new WeakMap<Response, string>()
export function setSessionScope(scope: string) { activeScope = scope }
export function requestSessionScope(init: RequestInit) { return new Headers(init.headers).get('X-CSRF-Token') ?? activeScope }
export function bindResponseScope(response: Response, scope: string) { responseScopes.set(response, scope) }
export function reportSessionEnded(response: Response, code: string) {
  const scope = responseScopes.get(response)
  if (response.status === 401 && code === 'sign_in_required' && scope) reportEndedScope(scope)
}
export function reportEndedScope(scope: string) { window.dispatchEvent(new CustomEvent(SESSION_ENDED_EVENT, { detail: { scope } })) }
export function matchesSessionScope(event: Event, scope: string) { return !!scope && (event as CustomEvent<{ scope: string }>).detail?.scope === scope }
