import { Moon, Sun } from 'lucide-react'
import { useAppearance } from '../../appearance/useAppearance'

export function StudioTheme() {
  const { theme, setAppearance } = useAppearance()
  return <button type="button" className="studio-icon" aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'} onClick={() => setAppearance(theme === 'dark' ? 'light' : 'dark')}>
    {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
  </button>
}
