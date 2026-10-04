import { expect, it, vi } from 'vitest'
import { DecisionQueue, type QueuedDecision } from './decisionQueue'
import type { FindingsView, PreviewView } from '../api/client'

const base = { version: { document_id: 'document', source_revision_id: 'revision', settings_version: 1, decision_version: 0 },
  findings: ['first', 'second', 'third'].map(finding_id => ({ finding_id, action: null, style: 'token', keep_reason: null })),
  overlaps: [], undo_available: 0 } as unknown as FindingsView
const job = (id: string): QueuedDecision => ({ findingId: id, ids: [id], action: 'redact', keepReason: null,
  groupScope: false, choice: { style: 'token', style_option: null } })
const preview = (value: FindingsView): PreviewView => ({ version: value.version, text: 'Actual acknowledged output' } as PreviewView)
function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (cause: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
function saved(value: FindingsView, id: string): FindingsView {
  return { ...value, version: { ...value.version, decision_version: value.version.decision_version + 1 },
    findings: value.findings.map(item => item.finding_id === id ? { ...item, action: 'redact' } : item) }
}

it('renders several choices immediately, sends serial acknowledged versions, and refreshes output once', async () => {
  const first = deferred<FindingsView>(), second = deferred<FindingsView>()
  const send = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
  const output = vi.fn(async () => preview(saved(saved(base, 'first'), 'second')))
  const render = vi.fn(), ready = vi.fn(), failed = vi.fn()
  const queue = new DecisionQueue(send, output, { render, preview: ready, failed })
  expect(queue.enqueue(base, job('first'))).toBe(true)
  expect(queue.enqueue(base, job('second'))).toBe(true)
  expect(render.mock.lastCall?.[0].findings.slice(0, 2).every((item: { action: string }) => item.action === 'redact')).toBe(true)
  expect(send).toHaveBeenCalledTimes(1)
  expect(queue.enqueue(base, job('first'))).toBe(false)
  first.resolve(saved(base, 'first'))
  await vi.waitFor(() => expect(send).toHaveBeenCalledTimes(2))
  expect(send.mock.calls[1][1].decision_version).toBe(1)
  expect(ready).not.toHaveBeenCalled()
  second.resolve(saved(saved(base, 'first'), 'second'))
  expect(await queue.flush()).toBe(true)
  expect(output).toHaveBeenCalledTimes(1)
  expect(render.mock.lastCall?.[1]).toEqual([])
  expect(render.mock.lastCall?.[2]).toBe(false)
  expect(failed).not.toHaveBeenCalled()
  queue.close()
})

it('preserves acknowledged writes and rolls back every unsaved choice on conflict', async () => {
  const first = deferred<FindingsView>(), second = deferred<FindingsView>()
  const send = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
  const render = vi.fn(), ready = vi.fn(), failed = vi.fn()
  const queue = new DecisionQueue(send, vi.fn(), { render, preview: ready, failed })
  queue.enqueue(base, job('first')); queue.enqueue(base, job('second')); queue.enqueue(base, job('third'))
  first.resolve(saved(base, 'first'))
  await vi.waitFor(() => expect(send).toHaveBeenCalledTimes(2))
  const wait = queue.flush()
  second.reject(new Error('Actual conflict'))
  expect(await wait).toBe(false)
  expect(render.mock.lastCall?.[0].findings.map((item: { action: unknown }) => item.action)).toEqual(['redact', null, null])
  expect(send).toHaveBeenCalledTimes(2)
  expect(ready).not.toHaveBeenCalled()
  expect(failed).toHaveBeenCalledTimes(1)
  queue.close()
})

it('drops a stale preview when another decision is queued during its real request', async () => {
  let value = base
  const old = deferred<PreviewView>(), ready = vi.fn(), failed = vi.fn()
  const output = vi.fn().mockReturnValueOnce(old.promise).mockImplementation(async () => preview(value))
  const queue = new DecisionQueue(async item => { value = saved(value, item.findingId); return value }, output,
    { render: vi.fn(), preview: ready, failed })
  queue.enqueue(base, job('first'))
  await vi.waitFor(() => expect(output).toHaveBeenCalledTimes(1))
  queue.enqueue(value, job('second'))
  old.resolve(preview(saved(base, 'first')))
  expect(await queue.flush()).toBe(true)
  expect(ready).toHaveBeenCalledTimes(1)
  expect(ready.mock.calls[0][0].version.decision_version).toBe(2)
  expect(failed).not.toHaveBeenCalled()
  queue.close()
})

it('cancels queued writes and ignores late content when the mounted session/review closes', async () => {
  const first = deferred<FindingsView>(), send = vi.fn((_job: QueuedDecision, _expected: FindingsView['version'], _signal: AbortSignal) => first.promise)
  const render = vi.fn(), ready = vi.fn(), failed = vi.fn()
  const queue = new DecisionQueue(send, vi.fn(), { render, preview: ready, failed })
  queue.enqueue(base, job('first')); queue.enqueue(base, job('second'))
  const calls = render.mock.calls.length, wait = queue.flush()
  queue.close()
  expect(await wait).toBe(false)
  expect(send.mock.calls[0][2].aborted).toBe(true)
  first.resolve(saved(base, 'first'))
  await Promise.resolve(); await Promise.resolve()
  expect(send).toHaveBeenCalledTimes(1)
  expect(render).toHaveBeenCalledTimes(calls)
  expect(ready).not.toHaveBeenCalled(); expect(failed).not.toHaveBeenCalled()
  expect(queue.enqueue(base, job('third'))).toBe(false)
})
