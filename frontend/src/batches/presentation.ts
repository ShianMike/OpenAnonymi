import type { BatchDocument } from './api'

export const stateNames: Record<BatchDocument['state'], string> = {
  queued: 'Queued', scanning: 'Scanning', scan_failed: 'Scan failed', needs_review: 'Needs review',
  ready: 'Confirmed', awaiting_approval: 'Awaiting approval', approved: 'Approved',
  exported: 'Exported', expired: 'Expired', deleted: 'Deleted',
}

export const reasonNames: Record<string, string> = {
  not_confirmed: 'Review has not been confirmed', stale_confirmation: 'Review changed since confirmation',
  approval_required: 'Current reviewer approval is required', expired: 'Content expired',
  deleted: 'Document deleted', scan_failed: 'Scan failed',
}

export function fileSelectionError(files: File[], count: number, uploadedBytes: number): string | null {
  if (files.length + count > 20) return `Choose at most ${Math.max(0, 20 - count)} more files for this batch.`
  if (files.some((file) => file.size > 8 * 1024 * 1024)) return 'Each file must be 8 MiB or smaller.'
  if (files.reduce((total, file) => total + file.size, uploadedBytes) > 40 * 1024 * 1024) return 'This batch accepts at most 40 MiB of uploaded files.'
  return null
}
