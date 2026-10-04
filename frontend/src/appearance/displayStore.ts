export type DisplayPreferences = {
  density: 'comfortable' | 'compact'
  fontSize: 'standard' | 'large'
  motion: 'system' | 'reduced'
}
const STORAGE_KEY = 'openanonymi.display'
const defaults: DisplayPreferences = { density: 'comfortable', fontSize: 'standard', motion: 'system' }
const media = window.matchMedia('(prefers-reduced-motion: reduce)')
const listeners = new Set<() => void>()

function read(): DisplayPreferences {
  try {
    const value: unknown = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? 'null')
    if (!value || typeof value !== 'object') return defaults
    return {
      density: 'density' in value && value.density === 'compact' ? 'compact' : 'comfortable',
      fontSize: 'fontSize' in value && value.fontSize === 'large' ? 'large' : 'standard',
      motion: 'motion' in value && value.motion === 'reduced' ? 'reduced' : 'system',
    }
  } catch { return defaults }
}

let snapshot = { ...read(), reducedMotion: media.matches, saved: true }
function apply() {
  snapshot = { ...snapshot, reducedMotion: snapshot.motion === 'reduced' || media.matches }
  const root = document.documentElement
  root.dataset.density = snapshot.density
  root.dataset.fontSize = snapshot.fontSize
  root.dataset.motion = snapshot.reducedMotion ? 'reduced' : 'full'
}
apply()
function publish() { apply(); listeners.forEach(listener => listener()) }
function systemChanged() { if (snapshot.reducedMotion !== (snapshot.motion === 'reduced' || media.matches)) publish() }
function storageChanged(event: StorageEvent) {
  if (event.key !== STORAGE_KEY && event.key !== null) return
  try { if (event.storageArea !== window.localStorage) return } catch { return }
  snapshot = { ...read(), reducedMotion: media.matches, saved: true }
  publish()
}
export const getDisplayPreferences = () => snapshot
export function subscribeDisplayPreferences(listener: () => void) {
  listeners.add(listener)
  if (listeners.size === 1) {
    media.addEventListener('change', systemChanged)
    window.addEventListener('storage', storageChanged)
    systemChanged()
  }
  return () => {
    listeners.delete(listener)
    if (!listeners.size) {
      media.removeEventListener('change', systemChanged)
      window.removeEventListener('storage', storageChanged)
    }
  }
}
export function setDisplayPreference<K extends keyof DisplayPreferences>(key: K, value: DisplayPreferences[K]) {
  const next = { density: snapshot.density, fontSize: snapshot.fontSize, motion: snapshot.motion, [key]: value }
  let saved = true
  try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next)) } catch { saved = false }
  snapshot = { ...next, reducedMotion: snapshot.reducedMotion, saved }
  publish()
}
