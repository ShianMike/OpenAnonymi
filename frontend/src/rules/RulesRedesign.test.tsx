import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { builtInPresets, findIntakePreset, workspacePresetId } from '../workspace/rules/builtInPresets'
import { RuleTestPreview } from './RuleDialog'
import { checkedRuleInput } from './api'
import type { PresetView } from '../api/client'
import { DetectionRuleCard } from './DetectionRuleCard'
import { recoveryCandidate } from '../recovery/useProtectedDraft'

it('uses built-in label settings without sending a virtual ID to the UUID preset API', () => {
  for (const preset of builtInPresets) {
    expect(findIntakePreset(preset.id, [])).toBe(preset)
    expect(workspacePresetId(preset.id)).toBeNull()
    expect(preset.preferred_action).toBe('label')
    expect(preset.is_default).toBe(false)
    expect(preset.categories).not.toContain('custom')
  }
  const saved: PresetView = { id: 'c50bb83c-b992-4305-9f0e-65c907d2ba58', name: 'Team setup',
    categories: ['email'], phone_region: 'US', preferred_action: 'redact', is_default: true,
    version: 4, category_defaults: {}, column_rules: [] }
  expect(findIntakePreset(saved.id, [saved])).toBe(saved)
  expect(workspacePresetId(saved.id)).toBe(saved.id)
  expect(findIntakePreset('unknown', [saved])).toBeUndefined()
  expect(workspacePresetId('')).toBeNull()
})

it('explains incomplete ID patterns and derives a valid Unicode rule name', () => {
  const options = { category: 'custom' as const, case_sensitive: false, whole_word: true, enabled: true }
  expect(() => checkedRuleInput({ ...options, name: '', kind: 'identifier', expression: 'CASE' })).toThrow('Add # for a digit')
  expect(checkedRuleInput({ ...options, name: '', kind: 'identifier', expression: 'CASE-######' }).name).toBe('CASE-######')
  const expression = 'A'.repeat(79) + '🙂extra'
  expect(checkedRuleInput({ ...options, name: ' ', kind: 'phrase', expression }).name).toBe('A'.repeat(79) + '🙂')
})

it('highlights rule matches at Unicode code point offsets and preserves the surrounding text', () => {
  const html = renderToStaticMarkup(<RuleTestPreview text="🙂 Before Atlas. Next Atlas!" result={{ match_count: 2, matches: [
    { span: { start: 9, end: 14 }, text: 'Atlas' }, { span: { start: 21, end: 26 }, text: 'Atlas' },
  ] }} />)
  expect(html).toContain('🙂 Before <mark>Atlas</mark>. Next <mark>Atlas</mark>!')
  expect(html).toContain('2 matches found')
  expect(renderToStaticMarkup(<RuleTestPreview text="<script>" result={{ match_count: 1,
    matches: [{ span: { start: 0, end: 8 }, text: '<script>' }] }} />)).toContain('<mark>&lt;script&gt;</mark>')
})

it('lets members test a saved rule without exposing editing or enable controls', () => {
  const html = renderToStaticMarkup(<DetectionRuleCard rule={{ id: 'synthetic-rule', version: 2, name: 'Synthetic rule',
    kind: 'phrase', expression: 'Project Atlas', category: 'custom', enabled: true, case_sensitive: false,
    whole_word: true, updated_at: '2026-10-08T10:00:00Z' }} workspace="synthetic-workspace" csrf="synthetic"
    administrator={false} saved={() => {}} />)
  expect(html).toContain('aria-label="Test Synthetic rule"')
  expect(html).not.toContain('role="switch"')
  expect(html).not.toContain('aria-label="Edit Synthetic rule"')
})

it('keeps earlier backups available when a preset starts a fresh draft and resumes its own slot on refresh', () => {
  const older = { id: 'older', workspace_id: 'workspace', document_id: null, version: 3,
    updated_at: '2026-10-08T10:00:00Z', expires_at: '2026-10-15T10:00:00Z' }
  const current = { ...older, id: 'current', version: 1 }
  const copies = [older, current]
  expect(recoveryCandidate(copies, 'new-slot', true)).toBeUndefined()
  expect(recoveryCandidate(copies, 'current', false)).toBe(current)
  expect(recoveryCandidate(copies, 'current', true)).toBe(current)
  expect(recoveryCandidate(copies, 'new-slot', false)).toBe(older)
  expect(copies).toEqual([older, current])
})
