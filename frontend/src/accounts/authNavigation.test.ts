import { describe, expect, it } from 'vitest'
import { authDestination } from './authNavigation'

const origin = 'http://127.0.0.1:5173'
const resolve = (next: string, signUp = false) => authDestination(`?next=${encodeURIComponent(next)}`, signUp, origin)

describe('public auth destination', () => {
  it('returns to an existing document or workspace queue', () => {
    expect(resolve('/continue?workspace=member-workspace')).toBe('/continue?workspace=member-workspace')
    expect(resolve('/documents/a-document/edit#review-approval')).toBe('/documents/a-document/edit#review-approval')
  })
  it('uses sensible sign-in and sign-up defaults', () => {
    expect(authDestination('', false, origin)).toBe('/continue')
    expect(authDestination('', true, origin)).toBe('/new')
  })
  it('rejects external, malformed, unknown and recursive auth destinations', () => {
    for (const path of ['https://evil.example/continue', '//evil.example/continue', '/\\evil.example/new', '/sign-in', '/welcome', '/missing', '/new\n', '/%2f%2fevil.example']) {
      expect(resolve(path)).toBe('/continue')
      expect(resolve(path, true)).toBe('/new')
    }
  })
})
