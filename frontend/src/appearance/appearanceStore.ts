export type AppearancePreference = 'light' | 'dark' | 'system'
export type ColorTheme = 'light' | 'dark'

const STORAGE_KEY = 'openanonymi.appearance'
const media = window.matchMedia('(prefers-color-scheme: dark)')
const listeners = new Set<() => void>()

function isPreference(value: unknown): value is AppearancePreference {
  return value === 'light' || value === 'dark' || value === 'system'
}

function readPreference(): AppearancePreference {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    return isPreference(stored) ? stored : 'dark'
  } catch {
    return 'dark'
  }
}

function resolveTheme(preference: AppearancePreference): ColorTheme {
  return preference === 'system' ? (media.matches ? 'dark' : 'light') : preference
}

let snapshot = {
  preference: readPreference(),
  theme: 'dark' as ColorTheme,
  saved: true,
}
snapshot.theme = resolveTheme(snapshot.preference)

function applyTheme() {
  document.documentElement.dataset.theme = snapshot.theme
  document.documentElement.dataset.themePreference = snapshot.preference
}
applyTheme()

function update(preference: AppearancePreference, saved = snapshot.saved) {
  const theme = resolveTheme(preference)
  if (snapshot.preference === preference && snapshot.theme === theme && snapshot.saved === saved) return
  snapshot = { preference, theme, saved }
  applyTheme()
  listeners.forEach((listener) => listener())
}

function onSystemChange() {
  update(snapshot.preference)
}

function onStorage(event: StorageEvent) {
  if (event.key !== STORAGE_KEY && event.key !== null) return
  update(isPreference(event.newValue) ? event.newValue : 'dark', true)
}

export function getAppearance() {
  return snapshot
}

export function subscribeAppearance(listener: () => void) {
  listeners.add(listener)
  if (listeners.size === 1) {
    media.addEventListener('change', onSystemChange)
    window.addEventListener('storage', onStorage)
    onSystemChange()
  }
  return () => {
    listeners.delete(listener)
    if (listeners.size === 0) {
      media.removeEventListener('change', onSystemChange)
      window.removeEventListener('storage', onStorage)
    }
  }
}

export function setAppearance(preference: AppearancePreference) {
  let saved = true
  try {
    window.localStorage.setItem(STORAGE_KEY, preference)
  } catch {
    saved = false
  }
  update(preference, saved)
}
