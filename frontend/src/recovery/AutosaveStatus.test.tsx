import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { AutosaveStatus } from './AutosaveStatus'
import type { ProtectedDraftController } from './useProtectedDraft'

const recovery: ProtectedDraftController = {
  phase: 'error', error: 'Server error details', errorCode: 'recovery_limit',
  savedAt: null, recoveredAt: null, loading: false, protected: false,
  copies: [{ id: 'backup', workspace_id: 'workspace', updated_at: '2026-10-07T12:00:00Z', expires_at: '2026-10-14T12:00:00Z', version: 1, document_id: null }],
  retry: () => {}, clear: async () => {}, restore: async () => {},
  saveNow: async () => {}, flush: async () => false, discardCopy: async () => {},
}

it('offers an actionable quota message while other failures remain retryable', () => {
  const render = (controller: ProtectedDraftController) => renderToStaticMarkup(<AutosaveStatus recovery={controller} dirty />)
  const full = render(recovery)
  expect(full).toContain('Backup space is full')
  expect(full).toContain('Manage backups (1)')
  expect(full).not.toContain('Retry backup')
  expect(full).not.toContain('Server error details')
  expect(full).not.toContain('Draft backed up')
  const retryable = render({ ...recovery, errorCode: 'request_failed', error: 'There are too many working drafts.' })
  expect(retryable).toContain('Retry backup')
  expect(retryable).toContain('What happened?')
  expect(retryable).not.toContain('Backup space is full')
  expect(render({ ...recovery, copies: [] })).toContain('Retry backup')
})

it('shows one current backup status without a restored badge or hover tooltip', () => {
  const pending: ProtectedDraftController = { ...recovery, error: null, errorCode: null, phase: 'idle', recoveredAt: '2026-10-24T04:00:00Z' }
  const render = (controller: ProtectedDraftController) => renderToStaticMarkup(<AutosaveStatus recovery={controller} dirty />)
  const html = render(pending)
  expect(html).toContain('Waiting for backup')
  expect(html).not.toContain('Draft backed up at')
  expect(html).not.toContain('title="Text restored from a backup"')
  expect(html).not.toContain('autosave-restored')
  expect(html).not.toContain('>Restored</small>')
  expect(html).toContain('Manage backups (1)')
  const saved = render({ ...pending, protected: true, savedAt: '2026-10-24T04:01:00Z', phase: 'saved' })
  expect(saved).toContain('Draft backed up at')
  expect(saved).not.toContain('Waiting for backup')
  expect(saved).not.toContain('>Restored</small>')
  expect(saved.match(/role="status"/g)).toHaveLength(1)
  expect(render({ ...pending, error: 'Connection interrupted', phase: 'error' })).not.toContain('>Restored</small>')
  expect(render({ ...pending, recoveredAt: null })).not.toContain('autosave-restored')
})
