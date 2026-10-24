import { expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { SessionView } from '../api/client'
import { RulesPage } from './RulesPage'
import { builtInRules, builtInRuleInput } from '../rules/builtInRules'
import { checkedRuleInput } from '../rules/api'
import { builtInPresets } from './rules/builtInPresets'

const session = { user_id: 'owner', csrf_token: 'synthetic', memberships: [{ workspace_id: 'workspace', workspace_name: 'Local test', role: 'administrator' }] } as SessionView
function render(query = '', value = session) {
  return renderToStaticMarkup(<MemoryRouter initialEntries={['/rules?workspace=workspace' + query]}><RulesPage session={value} /></MemoryRouter>)
}

it('separates ready-made formats, automatic checks, workspace rules and presets', () => {
  const html = render()
  for (const label of ['Rule library', 'Workspace rules', 'Review presets', 'Ready-made rules', 'Automatic checks']) expect(html).toContain(label)
  expect(html.match(/aria-label="Preview /g)).toHaveLength(builtInRules.length)
  expect(html).toContain('ASSET-@@-######')
  expect(html).toContain('They do not verify that an ID exists.')
  expect(html).not.toContain('<table')
  expect(html).not.toContain('Start with a built-in')
})

it('offers every built-in preset through the new-review flow without inventing UUID IDs', () => {
  const html = render('&view=presets')
  for (const preset of builtInPresets) expect(html).toContain(`preset=${preset.id}`)
  expect(html).toContain('Research interviews')
  expect(html).toContain('Technical logs')
  expect(html).toContain('11 detection categories')
  expect(new Set(builtInPresets.map(preset => preset.id)).size).toBe(builtInPresets.length)
})

it('makes the built-in library definitions valid editable identifier rules with unique formats', () => {
  expect(builtInRules).toHaveLength(12)
  expect(new Set(builtInRules.map(rule => rule.id)).size).toBe(builtInRules.length)
  expect(new Set(builtInRules.map(rule => rule.pattern)).size).toBe(builtInRules.length)
  for (const template of builtInRules) {
    const rule = checkedRuleInput(builtInRuleInput(template))
    expect(rule.kind).toBe('identifier')
    expect(rule.whole_word).toBe(true)
    expect(rule.expression).toBe(template.pattern)
  }
})

it('keeps authoring controls out of the member view', () => {
  const html = render('', { ...session, memberships: [{ workspace_id: 'workspace', workspace_name: 'Local test', role: 'member' }] } as SessionView)
  expect(html).not.toContain('Create rule')
  expect(html).toContain('Preview Case references')
  expect(render('&view=presets', { ...session, memberships: [{ workspace_id: 'workspace', role: 'member' }] } as SessionView)).not.toContain('Save a copy')
})
