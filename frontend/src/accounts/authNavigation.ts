import { matchPath } from 'react-router-dom'

const destinations = ['/', '/continue', '/new', '/documents', '/activity', '/rules', '/preferences', '/settings',
  '/documents/:documentId/edit', '/workspaces/:workspaceId/documents/:documentId/history']

/** Public auth links accept only an existing, same-app destination. */
export function authDestination(search: string, signingUp: boolean, origin = window.location.origin) {
  const fallback = signingUp ? '/new' : '/continue'
  const next = new URLSearchParams(search).get('next')
  if (!next || !next.startsWith('/') || next.startsWith('//') || Array.from(next).some((character) => character === '\\' || character.charCodeAt(0) <= 32)) return fallback
  const url = new URL(next, origin)
  if (url.origin !== origin || !destinations.some((path) => matchPath(path, url.pathname))) return fallback
  return url.pathname + url.search + url.hash
}
