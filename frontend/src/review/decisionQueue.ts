import type { FindingsView, PreviewView, StyleChoice, VersionRef } from '../api/client'
import { sameVersion } from './reviewState'

export type QueuedDecision = {
  findingId: string
  ids: string[]
  action: 'label' | 'redact' | 'keep'
  keepReason: 'false_match' | 'intended_disclosure' | null
  groupScope: boolean
  choice: StyleChoice
}
type Callbacks = {
  render: (findings: FindingsView, pendingIds: string[], pending: boolean, acknowledged: boolean) => void
  preview: (preview: PreviewView) => void
  failed: (cause: unknown) => void
}

/** Serial real writes; versions and preview text always come from the server. */
export class DecisionQueue {
  private jobs: QueuedDecision[] = []
  private confirmed: FindingsView | null = null
  private running = false
  private closed = false
  private controller = new AbortController()
  private waiters: ((saved: boolean) => void)[] = []
  private send: (job: QueuedDecision, expected: VersionRef, signal: AbortSignal) => Promise<FindingsView>
  private readPreview: (expected: VersionRef, signal: AbortSignal) => Promise<PreviewView>
  private callbacks: Callbacks
  constructor(
    send: (job: QueuedDecision, expected: VersionRef, signal: AbortSignal) => Promise<FindingsView>,
    readPreview: (expected: VersionRef, signal: AbortSignal) => Promise<PreviewView>,
    callbacks: Callbacks,
  ) { this.send = send; this.readPreview = readPreview; this.callbacks = callbacks }
  enqueue(base: FindingsView, job: QueuedDecision): boolean {
    if (this.closed || this.jobs.length >= 50 || !job.ids.length ||
      this.jobs.some(pending => pending.ids.some(id => job.ids.includes(id)))) return false
    if (!this.running) this.confirmed = base
    if (!this.confirmed || job.ids.some(id => !this.confirmed!.findings.some(item => item.finding_id === id))) return false
    this.jobs.push(job)
    this.publish(false)
    if (!this.running) { this.running = true; void this.run() }
    return true
  }
  private publish(acknowledged: boolean) {
    if (this.closed || !this.confirmed) return
    const decisions = new Map(this.jobs.flatMap(job => job.ids.map(id => [id, job] as const)))
    this.callbacks.render({ ...this.confirmed, findings: this.confirmed.findings.map(item => {
      const job = decisions.get(item.finding_id)
      return job ? { ...item, action: job.action, keep_reason: job.keepReason,
        style: job.action === 'keep' ? 'token' : job.choice.style ?? 'token',
        style_option: job.action === 'keep' ? null : job.choice.style_option ?? null } : item
    }) }, [...decisions.keys()], this.running || this.jobs.length > 0, acknowledged)
  }
  private settle(saved: boolean) { this.waiters.splice(0).forEach(resolve => resolve(saved)) }
  flush(): Promise<boolean> {
    return this.closed ? Promise.resolve(false) : !this.running ? Promise.resolve(true)
      : new Promise(resolve => this.waiters.push(resolve))
  }
  close() {
    this.closed = true; this.controller.abort(); this.jobs = []; this.confirmed = null; this.settle(false)
  }
  private async run() {
    try {
      while (!this.closed && this.confirmed) {
        while (this.jobs.length) {
          const job = this.jobs[0]
          const result = await this.send(job, this.confirmed.version, this.controller.signal)
          if (this.closed) return
          if (result.version.document_id !== this.confirmed.version.document_id ||
            result.version.source_revision_id !== this.confirmed.version.source_revision_id ||
            result.version.settings_version !== this.confirmed.version.settings_version ||
            result.version.decision_version < this.confirmed.version.decision_version)
            throw new Error('The review changed while saving. Reload the saved review.')
          this.confirmed = result; this.jobs.shift(); this.publish(true)
        }
        const expected = this.confirmed.version
        const preview = await this.readPreview(expected, this.controller.signal)
        if (this.closed) return
        // A decision queued during this read supersedes its output. Never display it.
        if (this.jobs.length) continue
        if (!sameVersion(preview.version, expected))
          throw new Error('The review changed while loading output. Reload the saved review.')
        this.callbacks.preview(preview)
        this.running = false; this.publish(false); this.settle(true)
        return
      }
    } catch (cause) {
      if (this.closed) return
      // Acknowledged earlier writes remain; only unsaved optimistic edits are removed.
      this.jobs = []; this.running = false; this.publish(false); this.settle(false)
      this.callbacks.failed(cause)
    }
  }
}
