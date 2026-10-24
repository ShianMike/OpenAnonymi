import { expect, it } from 'vitest'
import type { DocumentSearchView, SessionView } from '../api/client'
import { mergeSearchResults, searchPages, searchWorkspace, titleParts } from './searchPresentation'

const session = { memberships: [
  { workspace_id: 'member', workspace_name: 'Member workspace', role: 'member' },
  { workspace_id: 'admin', workspace_name: 'Admin workspace', role: 'administrator' },
] } as SessionView

it('keeps navigation in an authorized workspace and respects explicit scope before route and preference', () => {
  expect(searchWorkspace(session, 'admin', 'member', 'member')?.workspace_id).toBe('admin')
  expect(searchWorkspace(session, '', 'member', 'admin')?.workspace_id).toBe('member')
  expect(searchWorkspace(session, 'unknown', 'unknown', 'admin')?.workspace_id).toBe('admin')
  expect(searchWorkspace(session, '', null, 'unknown')?.workspace_id).toBe('member')
  expect(searchWorkspace({ ...session, memberships: [] }, '', null, null)).toBeUndefined()
})

it('offers a short initial navigation list and all pages on demand without exposing member management', () => {
  expect(searchPages('', 'all', true).map(page => page.path)).toEqual(['/new', '/documents', '/settings'])
  expect(searchPages('', 'pages', true)).toHaveLength(9)
  expect(searchPages('', 'pages', false).some(page => page.path === '/members')).toBe(false)
  expect(searchPages('member', 'pages', false)).toEqual([])
  expect(searchPages('settings', 'reviews', true)).toEqual([])
})

it('finds destinations by their labels and common settings terms', () => {
  expect(searchPages('  APPEARANCE  ', 'all', true).map(page => page.name)).toEqual(['Appearance & preferences'])
  expect(searchPages('dark', 'pages', true).map(page => page.path)).toEqual(['/preferences'])
  expect(searchPages('theme', 'pages', true).map(page => page.path)).toEqual(['/preferences'])
  expect(searchPages('account security', 'pages', true).map(page => page.path)).toEqual(['/settings'])
  expect(searchPages('qzx-unmatched', 'all', true)).toEqual([])
})

it('appends sparse cursor batches without duplicate results or discarding earlier matches', () => {
  const item = (id: string) => ({ id, title: id, workspace_id: 'admin', workspace_name: 'Admin workspace',
    status: 'draft' as const, is_owner: true, favorite: false, pinned: false })
  const previous: DocumentSearchView = { items: [item('one')], next_cursor: { created_at: '2026-10-23T00:00:00Z', id: 'one' }, scanned_count: 500 }
  const next: DocumentSearchView = { items: [item('one'), item('two'), item('two')], next_cursor: null, scanned_count: 2 }
  expect(mergeSearchResults(previous, next)).toEqual({ ...next, items: [item('one'), item('two')] })
  const sparse = { ...next, items: [], next_cursor: previous.next_cursor }
  expect(mergeSearchResults(previous, sparse).items).toEqual(previous.items)
  expect(mergeSearchResults(null, next).items.map(row => row.id)).toEqual(['one', 'two'])
  expect(previous.items).toHaveLength(1)
})

it('highlights literal title matches while retaining original case and Unicode', () => {
  expect(titleParts('PDF layout • PDF verification', 'pdf')).toEqual(['', 'PDF', ' layout • ', 'PDF', ' verification'])
  expect(titleParts('Case [a+b].txt', '[a+b]')).toEqual(['Case ', '[a+b]', '.txt'])
  expect(titleParts('Café 😀 notes', '😀')).toEqual(['Café ', '😀', ' notes'])
  expect(titleParts('Source title', '')).toEqual(['Source title'])
  expect(titleParts('Source title', '  ')).toEqual(['Source title'])
  expect(titleParts('Source title', '(.*)')).toEqual(['Source title'])
})
