import { describe, expect, it } from 'vitest'
import { reviewShortcut, shortcutGuide, shortcutKeys } from './shortcuts'

const key = { key: 'r', altKey: false, ctrlKey: false, metaKey: false, shiftKey: false, repeat: false, isComposing: false, defaultPrevented: false }

describe('review shortcut safeguards', () => {
  it('assigns each key and action once and lists every key in the guide', () => {
    const entries = Object.entries(shortcutKeys)
    expect(new Set(entries.map(([, action]) => action)).size).toBe(entries.length)
    const guideKeys = shortcutGuide.map(([key]) => key.toLowerCase())
    expect(new Set(guideKeys).size).toBe(guideKeys.length)
    expect(new Set(guideKeys)).toEqual(new Set([...Object.keys(shortcutKeys), '?']))
    for (const [name, action] of entries) expect(reviewShortcut({ ...key, key: name })).toBe(action)
  })
  it('never consumes modified shortcuts, IME input, repeats or an event already handled', () => {
    for (const guard of ['altKey', 'ctrlKey', 'metaKey', 'shiftKey', 'repeat', 'isComposing', 'defaultPrevented'] as const) {
      expect(reviewShortcut({ ...key, [guard]: true })).toBeNull()
    }
    expect(reviewShortcut({ ...key, key: '?' , shiftKey: true })).toBe('help')
    expect(reviewShortcut({ ...key, key: '?', ctrlKey: true })).toBeNull()
  })
  it('keeps native editing keys and unsupported keys untouched', () => {
    for (const value of ['Enter', 'Escape', 'ArrowDown', ' ', 'Backspace', 'Dead', 'a']) expect(reviewShortcut({ ...key, key: value })).toBeNull()
    expect(reviewShortcut({ ...key, key: 'L' })).toBe('label')
    expect(reviewShortcut({ ...key, key: 'K' })).toBe('keep')
  })
})
