// Apply saved display settings, and choose the loading screen's tone, before anything paints.
(() => {
  const root = document.documentElement
  let preference = 'dark'
  let home = ''
  let display = null
  try {
    const saved = localStorage.getItem('openanonymi.appearance')
    if (['light', 'dark', 'system'].includes(saved)) preference = saved
    home = localStorage.getItem('openanonymi.home') || ''
    display = JSON.parse(localStorage.getItem('openanonymi.display') || 'null')
  } catch {
    // Appearance still works when browser storage is unavailable.
  }
  const theme = preference === 'system'
    ? matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    : preference
  root.dataset.themePreference = preference
  root.dataset.theme = theme
  // Public entry pages are light. "/" opens the landing unless this browser was last signed in.
  const path = location.pathname
  root.dataset.bootTone = ['/welcome', '/sign-in', '/sign-up'].includes(path) || (path === '/' && home !== 'workspace') ? 'light' : theme
  if (display && typeof display === 'object') {
    if (display.motion === 'reduced') root.dataset.motion = 'reduced'
    if (display.fontSize === 'large') root.dataset.fontSize = 'large'
  }
})()
