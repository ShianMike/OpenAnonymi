import { get } from '../api/client'
import type { components } from '../api/schema'

export type ComparisonView = components['schemas']['ComparisonView']

export function compareRevisions(document: string, before: string, after: string, signal?: AbortSignal) {
  const query = new URLSearchParams({ before, after })
  return get<ComparisonView>(`/documents/${encodeURIComponent(document)}/compare?${query}`, signal)
}
