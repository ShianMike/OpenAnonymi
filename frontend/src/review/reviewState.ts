import type { SourceView, SourceSpan, VersionRef } from '../api/client'

export type DraftState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string; retryable?: boolean }
  | { kind: 'ready'; saved: SourceView }

export type GroupConfirmation = {
  findingId: string
  action: 'label' | 'redact' | 'keep'
  affectedIds: string[]
  spans: SourceSpan[]
  version: VersionRef
}

export function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : 'The request could not be completed.'
}

export function sameVersion(left: VersionRef, right: VersionRef): boolean {
  return (
    left.document_id === right.document_id &&
    left.source_revision_id === right.source_revision_id &&
    left.decision_version === right.decision_version &&
    left.settings_version === right.settings_version
  )
}

export function sameScanVersion(left: VersionRef, right: VersionRef): boolean {
  return (
    left.document_id === right.document_id &&
    left.source_revision_id === right.source_revision_id &&
    left.settings_version === right.settings_version
  )
}
