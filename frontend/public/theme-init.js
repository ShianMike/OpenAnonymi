// Apply the saved appearance before the stylesheet and React can paint.
(() => {
  let preference = 'dark'
  try {
    const saved = localStorage.getItem('openanonymi.appearance')
    if (['light', 'dark', 'system'].includes(saved)) preference = saved
  } catch {
    // Appearance still works when browser storage is unavailable.
  }
  document.documentElement.dataset.themePreference = preference
  document.documentElement.dataset.theme =
    preference === 'system'
      ? matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
      : preference
})()
