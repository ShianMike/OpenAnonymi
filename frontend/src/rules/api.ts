import { get, sendJson } from '../api/client'
import type { components } from '../api/schema'

export type RuleInput = components['schemas']['RuleInput']
export type RuleView = components['schemas']['RuleView']
export type RuleSnapshot = components['schemas']['RuleSnapshotView']
export type RuleTestView = components['schemas']['RuleTestView']

export const getRules = (workspace: string, signal?: AbortSignal) => get<RuleView[]>(`/workspaces/${workspace}/rules`, signal)
export const saveRule = (workspace: string, body: RuleInput, csrf: string, existing?: RuleView) =>
  sendJson<RuleView>(existing ? 'PUT' : 'POST', `/workspaces/${workspace}/rules${existing ? `/${existing.id}` : ''}`,
    existing ? { ...body, expected_version: existing.version } : body, csrf)
export const testRule = (workspace: string, rule: RuleInput, text: string, csrf: string) =>
  sendJson<RuleTestView>('POST', `/workspaces/${workspace}/rules/test`, { rule, text }, csrf)
export const getRuleSnapshot = (document: string, signal?: AbortSignal) => get<RuleSnapshot>(`/documents/${document}/rules`, signal)
export const refreshRules = (document: string, expected: RuleSnapshot['version'], csrf: string) =>
  sendJson<RuleSnapshot>('PUT', `/documents/${document}/rules`, { expected }, csrf)
