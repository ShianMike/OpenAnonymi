export type BootTone = 'light' | 'dark'

const HOME_KEY = 'openanonymi.home'

/** The tone index.html painted first, chosen by public/theme-init.js. */
export function firstPaintTone(): BootTone | undefined {
  const tone = document.documentElement.dataset.bootTone
  return tone === 'light' || tone === 'dark' ? tone : undefined
}

/** Remembers whether "/" opens the workspace on this browser, so the first paint can match. Display only. */
export function rememberHome(home: 'workspace' | 'welcome') {
  try {
    if (localStorage.getItem(HOME_KEY) !== home) localStorage.setItem(HOME_KEY, home)
  } catch { /* The first paint falls back to the saved theme. */ }
}

let showing = 0
let closedAt = Number.NEGATIVE_INFINITY

/** True while a full-screen loader is up or one just closed, so its replacement skips the entrance. */
export function replacesLoadingScreen() {
  return showing > 0 || performance.now() - closedAt < 300 || document.getElementById('startup-loading') !== null
}

/** Use as an effect while a full-screen loader is mounted. */
export function trackLoadingScreen() {
  showing += 1
  return () => {
    showing -= 1
    closedAt = performance.now()
  }
}
