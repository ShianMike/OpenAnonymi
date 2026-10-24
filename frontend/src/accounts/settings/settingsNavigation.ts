import { ApiRequestError } from '../../api/client'

export const settingsSections = [
  { id: 'account', label: 'Account', title: 'Account', description: 'Your sign-in email and workspace memberships.', group: 'personal' },
  { id: 'security', label: 'Security', title: 'Security', description: 'Manage your password and two-step verification.', group: 'personal' },
  { id: 'devices', label: 'Devices & sessions', title: 'Devices & sessions', description: 'See where you’re signed in and manage active sessions.', group: 'personal' },
  { id: 'notifications', label: 'Notifications', title: 'Notifications', description: 'Choose how review updates reach you.', group: 'personal' },
  { id: 'appearance', label: 'Appearance & preferences', title: 'Appearance & preferences', description: 'Theme, reading and motion preferences for this device.', group: 'personal' },
  { id: 'workspace', label: 'Review & access policies', title: 'Review & access policies', description: 'Set workspace requirements for sign-in and independent review.', group: 'workspace' },
  { id: 'retention', label: 'Data retention', title: 'Data retention', description: 'Choose how long review content and activity records are kept.', group: 'workspace' },
] as const

export function settingsHref(section: string, workspace: string | null) {
  const params = new URLSearchParams({ section })
  if (workspace) params.set('workspace', workspace)
  return `/settings?${params}`
}

export function validRetention(content: string, activity: string) {
  return [content, activity].every(value => value.trim() !== '' && Number.isInteger(Number(value))) &&
    Number(content) >= 1 && Number(content) <= 30 && Number(activity) >= 1 && Number(activity) <= 365
}
export function workspaceSettingsError(cause: unknown) {
  if (cause instanceof ApiRequestError && cause.status === 401) return {
    title: 'Your session needs to be refreshed',
    message: 'Your sign-in session could not be verified. Check again, or return to your account to continue.',
    retryLabel: 'Check session again',
  }
  if (cause instanceof ApiRequestError && cause.code === 'workspace_not_found') return {
    title: 'Workspace access unavailable',
    message: 'Administrator access is required for these settings. Your access may have changed, or this workspace may no longer be available.',
    retryLabel: 'Check access again',
  }
  return {
    title: 'Workspace settings couldn’t be loaded',
    message: cause instanceof ApiRequestError ? cause.message : 'The request didn’t finish. Check your connection and try again.',
    retryLabel: 'Try again',
  }
}
