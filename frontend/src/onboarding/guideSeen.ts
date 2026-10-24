const key = (userId: string) => `openanonymi.quick-guide.${userId}`

export function hasSeenGuide(userId: string) {
  try { return window.localStorage.getItem(key(userId)) === 'seen' } catch { return false }
}

export function rememberGuide(userId: string) {
  try { window.localStorage.setItem(key(userId), 'seen') } catch { /* The guide still dismisses for this visit. */ }
}
