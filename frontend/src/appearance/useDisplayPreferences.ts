import { useSyncExternalStore } from 'react'
import { getDisplayPreferences, setDisplayPreference, subscribeDisplayPreferences } from './displayStore'

export function useDisplayPreferences() {
  return { ...useSyncExternalStore(subscribeDisplayPreferences, getDisplayPreferences), setDisplayPreference }
}
