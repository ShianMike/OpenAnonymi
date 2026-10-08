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
  ['N', 'Next detail', 'Move to the next detail in the current list.'],
  ['P', 'Previous detail', 'Go back to the previous detail in the list.'],
  ['L', 'Replace with a label', 'Use a label such as PERSON_001.'],
  ['R', 'Hide this detail', 'Remove this detail from the reviewed text.'],
  ['K', 'Keep this detail', 'Choose a reason to leave this detail visible.'],
  ['U', 'Undo last choice', 'Undo your last saved review change.'],
  ['M', 'Hide part of a detail', 'Hide some letters or numbers. Its format and length stay visible.'],
  ['F', 'Use a made-up detail', 'Replace it with a consistent fictional name or contact.'],
  ['D', 'Move a date', 'Move dates by the same number of days, keeping the gaps between them.'],
  ['G', 'Show less of a date', 'Keep only the month and year, year, or an age range for a birth date.'],
  ['?', 'Shortcut guide', 'Open this guide. Escape closes dialogs.'],
] as const
