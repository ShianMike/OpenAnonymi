import type { components } from './schema'
import { getSessionScope, subscribeSessionEnded, subscribeSessionScope } from './sessionEvents'

export type ReviewStateView = components['schemas']['ReviewStateView']
type Entry = { value: ReviewStateView; tag: string; size: number; until: number; timer: ReturnType<typeof setTimeout> }

/** Bounded, short-lived RAM. Reading this store never replaces server authorization. */
export class ReviewCache {
  private entries = new Map<string, Entry>()
  private bytes = 0
  epoch = 0
  readonly capacity: number
  readonly maxBytes: number
  readonly ttlMs: number
  constructor(capacity = 4, maxBytes = 8 * 1024 * 1024, ttlMs = 60_000) {
    this.capacity = capacity; this.maxBytes = maxBytes; this.ttlMs = ttlMs
  }
  clear() {
    this.epoch++
    this.entries.forEach(entry => clearTimeout(entry.timer))
    this.entries.clear(); this.bytes = 0
  }
  private remove(key: string) {
    const entry = this.entries.get(key)
    if (!entry) return
    clearTimeout(entry.timer); this.bytes -= entry.size; this.entries.delete(key)
  }
  get(key: string): Entry | undefined {
    const entry = this.entries.get(key)
    if (!entry) return
    if (entry.until <= Date.now() || Date.parse(entry.value.source.expires_at) <= Date.now()) {
      this.remove(key); return
    }
    this.entries.delete(key); this.entries.set(key, entry)
    return entry
  }
  put(key: string, value: ReviewStateView, tag: string) {
    this.remove(key)
    // UTF-16 accounting deliberately overcounts ASCII. No content is persisted.
    const size = JSON.stringify(value).length * 2
    if (size > this.maxBytes || !/^"rs1-[a-f0-9]{64}"$/.test(tag)) return
    const until = Math.min(Date.now() + this.ttlMs, Date.parse(value.source.expires_at))
    if (!Number.isFinite(until) || until <= Date.now()) return
    while (this.entries.size && (this.entries.size >= this.capacity || this.bytes + size > this.maxBytes)) {
      this.remove(this.entries.keys().next().value!)
    }
    const timer = setTimeout(() => this.remove(key), Math.max(0, until - Date.now()))
    this.entries.set(key, { value: structuredClone(value), tag, size, until, timer }); this.bytes += size
  }
}

export const reviewCache = new ReviewCache()
subscribeSessionScope(() => reviewCache.clear())
subscribeSessionEnded(scope => { if (scope === getSessionScope()) reviewCache.clear() })

export function protectReviewCacheLifecycle() {
  const clearHidden = () => { if (document.visibilityState !== 'visible') reviewCache.clear() }
  const clear = () => reviewCache.clear()
  document.addEventListener('visibilitychange', clearHidden)
  window.addEventListener('pagehide', clear)
  return () => {
    document.removeEventListener('visibilitychange', clearHidden)
    window.removeEventListener('pagehide', clear)
    clear()
  }
}
