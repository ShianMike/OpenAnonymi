import { useEffect, useState } from 'react'
import { useLoadingMotion } from './useLoadingMotion'

export function useLoadingAwareness() {
  const ref = useLoadingMotion<HTMLDivElement>()
  const [slow, setSlow] = useState(false)
  const [offline, setOffline] = useState(() => !navigator.onLine)
  useEffect(() => {
    const timer = window.setTimeout(() => setSlow(true), 8000)
    const connection = () => setOffline(!navigator.onLine)
    window.addEventListener('online', connection)
    window.addEventListener('offline', connection)
    return () => {
      clearTimeout(timer)
      window.removeEventListener('online', connection)
      window.removeEventListener('offline', connection)
    }
  }, [])
  return { ref, slow, offline }
}
