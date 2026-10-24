import { beforeEach, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { LoadingState, type LoadingShape } from './LoadingState'
import { RouteLoading } from './RouteLoading'
import { useLoadingPresence } from './foregroundLoading'
import { LoadingMark } from './LoadingMark'

const connection = vi.hoisted(() => ({ slow: false, offline: false }))
vi.mock('./useLoadingAwareness', () => ({ useLoadingAwareness: () => ({ ...connection, ref: { current: null } }) }))
vi.mock('./foregroundLoading', () => ({ useLoadingPresence: vi.fn() }))
beforeEach(() => Object.assign(connection, { slow: false, offline: false }))

it('announces loading once and keeps every skeleton decorative and unfocusable', () => {
  const shapes: LoadingShape[] = ['list', 'gallery', 'cards', 'document', 'page', 'form', 'timeline', 'members', 'comparison']
  for (const shape of shapes) {
    const html = renderToStaticMarkup(<LoadingState label="Loading reviews…" description="Checking your access." shape={shape} />)
    expect(html.match(/role="status"/g)).toHaveLength(1)
    expect(html).toContain(`loading-skeleton-${shape}" aria-hidden="true" inert=""`)
    expect(html).toContain('Checking your access.')
    expect(html).not.toMatch(/<(?:button|input|a|select)\b|tabindex|role="progressbar"/i)
  }
})

it.each([
  { slow: false, offline: false, message: null },
  { slow: true, offline: false, message: 'Still waiting for your documents.' },
  { slow: true, offline: true, message: 'You’re offline. Reconnect to continue loading.' },
])('offers recovery only when needed and prioritizes offline feedback ($slow, $offline)', ({ slow, offline, message }) => {
  Object.assign(connection, { slow, offline })
  const html = renderToStaticMarkup(<LoadingState label="Loading reviews…" slowMessage="Still waiting for your documents." onRetry={() => {}} />)
  expect(html.includes('Try again')).toBe(!!message)
  if (message) {
    expect(html).toContain(message)
    expect(html.indexOf('Try again')).toBeLessThan(html.indexOf('loading-skeleton'))
  }
  if (offline) expect(html).not.toContain('Still waiting for your documents.')
})

it('keeps compact requests small while preserving their accessible status', () => {
  const html = renderToStaticMarkup(<LoadingState label="Saving your review…" compact />)
  expect(html).toContain('role="status"')
  expect(html).toContain('Saving your review…')
  expect(html).not.toContain('loading-skeleton')
  expect(html).not.toContain('Please wait')
})

it('suppresses duplicate global feedback for inline loaders without making the background indicator suppress itself', () => {
  const presence = vi.mocked(useLoadingPresence)
  presence.mockClear()
  const inline = renderToStaticMarkup(<LoadingState label="Loading your reviews…" description="Checking available reviews." compact />)
  expect(presence).toHaveBeenLastCalledWith(expect.anything(), true)
  expect(inline).toContain('class="loading-description"')
  expect(inline.match(/role="status"/g)).toHaveLength(1)
  renderToStaticMarkup(<LoadingState label="Checking review updates…" compact background />)
  expect(presence).toHaveBeenLastCalledWith(expect.anything(), false)
})

it('keeps the activity animation decorative and out of the focus order', () => {
  const html = renderToStaticMarkup(<LoadingMark small />)
  expect(html).toContain('aria-hidden="true"')
  expect(html).not.toMatch(/tabindex|role="progressbar"|<svg/i)
})

it('uses the destination layout during route loading', () => {
  const routes = [['/', 'cards'], ['/documents', 'gallery'], ['/rules', 'gallery'], ['/documents/review/edit', 'document'],
    ['/new', 'document'], ['/settings', 'form'], ['/preferences', 'form'], ['/members', 'members'], ['/activity', 'timeline'],
    ['/workspaces/workspace/documents/review/history', 'timeline'], ['/notifications', 'list']]
  for (const [pathname, shape] of routes) {
    const html = renderToStaticMarkup(<RouteLoading pathname={pathname} title="Workspace" />)
    expect(html).toContain(`loading-skeleton-${shape}`)
    expect(html).toContain('<h1>Workspace</h1>')
  }
})
