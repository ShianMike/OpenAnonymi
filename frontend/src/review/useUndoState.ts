import type { FindingsView, VersionRef } from '../api/client'
import { sameVersion } from './reviewState'

// Availability comes from persisted history for the current actor and version.
// Stale findings may remain visible while a request loads; they cannot enable Undo.
export function useUndoState(findings: FindingsView | null, version: VersionRef | null): number {
  if (!findings || !version || !sameVersion(findings.version, version)) return 0
  return Math.max(0, Math.min(20, findings.undo_available ?? 0))
}
