import { expect, it } from 'vitest'
import { pageTransition } from './navigation'

it.each([
  ['/documents', '/documents', 'none'],
  ['/documents', '/rules', 'fade'],
  ['/settings', '/notifications', 'fade'],
  ['/documents', '/new', 'forward'],
  ['/documents', '/documents/first/edit', 'forward'],
  ['/documents/first/edit', '/documents', 'back'],
  ['/new', '/documents', 'back'],
  ['/new', '/documents/first/edit', 'forward'],
  ['/documents/first/edit', '/new', 'back'],
  ['/documents/first/edit', '/documents/second/edit', 'fade'],
  ['/documents', '/workspaces/team/documents/first/history', 'forward'],
  ['/documents/first/edit', '/workspaces/team/documents/first/history', 'forward'],
  ['/workspaces/team/documents/first/history', '/documents/first/edit', 'back'],
  ['/workspaces/team/documents/first/history', '/documents', 'back'],
  ['/documents', '/documents/first/edit/', 'forward'],
])('uses %s → %s to communicate navigation depth', (from, to, transition) => {
  expect(pageTransition(from, to)).toBe(transition)
})
