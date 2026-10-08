import { Activity, Bell, FilePlus2, Files, LayoutDashboard, Palette, Settings2, SlidersHorizontal } from 'lucide-react'

export const pages = [
  { path: '/', name: 'Overview', icon: LayoutDashboard },
  { path: '/new', name: 'New review', icon: FilePlus2 },
  { path: '/documents', name: 'Documents', icon: Files },
  { path: '/notifications', name: 'Notifications', icon: Bell },
  { path: '/rules', name: 'Rules', icon: SlidersHorizontal },
  { path: '/activity', name: 'Activity', icon: Activity },
  { path: '/settings', name: 'Settings', icon: Settings2 },
  { path: '/preferences', name: 'Preferences', icon: Palette },
]
