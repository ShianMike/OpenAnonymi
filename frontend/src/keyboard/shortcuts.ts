export type ReviewShortcut = 'next' | 'previous' | 'label' | 'redact' | 'keep' | 'undo' | 'help'
type KeyInput = { key: string; altKey: boolean; ctrlKey: boolean; metaKey: boolean; shiftKey: boolean; repeat: boolean; isComposing: boolean; defaultPrevented: boolean }

export function reviewShortcut(event: KeyInput): ReviewShortcut | null {
  if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.repeat || event.isComposing) return null
  if (event.key === '?') return 'help'
  if (event.shiftKey) return null
  const actions: Record<string, ReviewShortcut> = { n: 'next', p: 'previous', l: 'label', r: 'redact', k: 'keep', u: 'undo' }
  return actions[event.key.toLowerCase()] ?? null
}

export const shortcutGuide = [
  ['N', 'Next finding', 'Move through the visible, filtered findings.'],
  ['P', 'Previous finding', 'Move back through the same list.'],
  ['L', 'Label', 'Give the selected occurrence a consistent placeholder.'],
  ['R', 'Redact', 'Hide the selected occurrence from reviewed output.'],
  ['K', 'Keep', 'Choose an explicit reason before saving.'],
  ['U', 'Undo', 'Undo your last saved review edit.'],
  ['?', 'Shortcut guide', 'Open this guide. Escape closes dialogs.'],
] as const
