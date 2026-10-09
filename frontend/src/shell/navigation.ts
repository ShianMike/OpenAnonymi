import { Activity, Bell, FilePlus2, Files, LayoutDashboard, Palette, Settings2, SlidersHorizontal, Users } from 'lucide-react'

export const pages = [
  { path: '/', name: 'Overview', icon: LayoutDashboard },
  { path: '/new', name: 'New review', icon: FilePlus2 },
  { path: '/documents', name: 'Documents', icon: Files },
  { path: '/notifications', name: 'Notifications', icon: Bell },
  { path: '/rules', name: 'Rules', icon: SlidersHorizontal },
  { path: '/activity', name: 'Activity', icon: Activity },
  { path: '/members', name: 'Members', icon: Users },
  { path: '/settings', name: 'Settings', icon: Settings2 },
  { path: '/preferences', name: 'Preferences', icon: Palette },
]

export const workspacePages = ['/', '/new', '/documents', '/continue', '/rules', '/activity', '/members', '/settings']

export function workspaceHref(path: string, workspaceId?: string) {
  return workspaceId && workspacePages.includes(path) ? `${path}?workspace=${encodeURIComponent(workspaceId)}` : path
}
