export type ReviewShortcut = 'next' | 'previous' | 'label' | 'redact' | 'keep' | 'undo' | 'help' | 'mask' | 'fictional' | 'shift' | 'generalize'
export const shortcutKeys: Record<string, ReviewShortcut> = { n: 'next', p: 'previous', l: 'label', r: 'redact', k: 'keep', u: 'undo', m: 'mask', f: 'fictional', d: 'shift', g: 'generalize' }
type KeyInput = { key: string; altKey: boolean; ctrlKey: boolean; metaKey: boolean; shiftKey: boolean; repeat: boolean; isComposing: boolean; defaultPrevented: boolean }

export function reviewShortcut(event: KeyInput): ReviewShortcut | null {
  if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.repeat || event.isComposing) return null
  if (event.key === '?') return 'help'
  if (event.shiftKey) return null
  return shortcutKeys[event.key.toLowerCase()] ?? null
}

export const shortcutGuide = [
  ['N', 'Next finding', 'Move through the visible, filtered findings.'],
  ['P', 'Previous finding', 'Move back through the same list.'],
  ['L', 'Label', 'Give the selected occurrence a consistent placeholder.'],
  ['R', 'Redact', 'Hide the selected occurrence from reviewed output.'],
  ['K', 'Keep', 'Choose an explicit reason before saving.'],
  ['U', 'Undo', 'Undo your last saved review edit.'],
  ['M', 'Partial mask', 'Use the category’s default mask pattern, or mask all letters and digits. Format and length stay visible.'],
  ['F', 'Fictional stand-in', 'Use a consistent fictional replacement where this category and region support it.'],
  ['D', 'Shift date', 'Move a parsed date by this document’s private offset. Intervals stay unchanged.'],
  ['G', 'Generalize date', 'Choose month and year, year only, or an age band for a birth date.'],
  ['?', 'Shortcut guide', 'Open this guide. Escape closes dialogs.'],
] as const
