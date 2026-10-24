import definitions from './builtInRules.json'
import type { RuleInput } from './api'

export const builtInRules = definitions
export type BuiltInRule = typeof definitions[number]
export const ruleGroups = ['All use cases', ...new Set(definitions.map(rule => rule.group))]

export function builtInRuleInput(rule: BuiltInRule): RuleInput {
  return { name: rule.name, kind: 'identifier', expression: rule.pattern, category: 'identifier',
    case_sensitive: false, whole_word: true, enabled: true }
}
