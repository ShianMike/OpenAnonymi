import { useSyncExternalStore } from 'react'
import { getAppearance, setAppearance, subscribeAppearance } from './appearanceStore'

export function useAppearance() {
  const appearance = useSyncExternalStore(subscribeAppearance, getAppearance)
  return { ...appearance, setAppearance }
}
