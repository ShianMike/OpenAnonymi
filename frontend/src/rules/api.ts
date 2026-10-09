import { get, sendJson } from '../api/client'
import type { components } from '../api/schema'

export type RuleInput = components['schemas']['RuleInput']
export type RuleView = components['schemas']['RuleView']
export type RuleSnapshot = components['schemas']['RuleSnapshotView']
export type RuleTestView = components['schemas']['RuleTestView']

export function checkedRuleInput(body: RuleInput): RuleInput {
  if (body.kind === 'identifier' && !/[#@]/.test(body.expression))
    throw new Error('Add # for a digit or @ for an A–Z letter in your pattern.')
  return { ...body, name: body.name.trim() || Array.from(body.expression.trim()).slice(0, 80).join('') }
}

export const getRules = (workspace: string, signal?: AbortSignal) => get<RuleView[]>(`/workspaces/${workspace}/rules`, signal)
export const saveRule = (workspace: string, body: RuleInput, csrf: string, existing?: RuleView) =>
  sendJson<RuleView>(existing ? 'PUT' : 'POST', `/workspaces/${workspace}/rules${existing ? `/${existing.id}` : ''}`,
    existing ? { ...checkedRuleInput(body), expected_version: existing.version } : checkedRuleInput(body), csrf)
export const testRule = (workspace: string, rule: RuleInput, text: string, csrf: string) =>
  sendJson<RuleTestView>('POST', `/workspaces/${workspace}/rules/test`, { rule: checkedRuleInput(rule), text }, csrf)
export const getRuleSnapshot = (document: string, signal?: AbortSignal) => get<RuleSnapshot>(`/documents/${document}/rules`, signal)
export const refreshRules = (document: string, expected: RuleSnapshot['version'], csrf: string) =>
  sendJson<RuleSnapshot>('PUT', `/documents/${document}/rules`, { expected }, csrf)
