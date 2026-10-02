import { Check, CheckCircle2, Monitor, Moon, Palette, Sun } from 'lucide-react'
import { PageHeader } from '../ui/PageHeader'
import { useAppearance } from './useAppearance'
import { ThemePreview } from './ThemePreview'
import './preferences.css'

const choices = [
  { value: 'light', name: 'Light', description: 'Warm ivory & sage', icon: Sun },
  { value: 'dark', name: 'Dark', description: 'Deep forest & mint', icon: Moon },
  { value: 'system', name: 'System', description: 'Follow your device', icon: Monitor },
] as const

export function PreferencesPage() {
  const { preference, theme, saved, setAppearance } = useAppearance()
  const ActiveIcon = theme === 'light' ? Sun : Moon
  return (
    <section className="preferences-page" aria-labelledby="preferences-title">
      <PageHeader
        title="Preferences"
        titleId="preferences-title"
        description="Make a little space for your own style."
      />
      <section className="appearance-panel" aria-labelledby="appearance-title">
        <header className="appearance-heading">
          <span className="appearance-icon"><Palette size={21} strokeWidth={1.6} aria-hidden="true" /></span>
          <div>
            <h2 id="appearance-title">Appearance</h2>
            <p>Choose the light you work in.</p>
          </div>
          <span className="appearance-current">
            <ActiveIcon size={14} aria-hidden="true" /> {theme === 'light' ? 'Light' : 'Dark'} mode
          </span>
        </header>
        <fieldset className="appearance-choices">
          <legend className="sr-only">Color theme</legend>
          {choices.map(({ value, name, description, icon: Icon }) => (
            <label className="theme-choice" key={value}>
              <input
                type="radio"
                name="appearance"
                value={value}
                aria-label={name}
                checked={preference === value}
                onChange={() => setAppearance(value)}
              />
              <ThemePreview mode={value} />
              <span className="theme-choice-caption">
                <span className="theme-choice-title"><Icon size={16} aria-hidden="true" /> {name}</span>
                <span className="theme-choice-check" aria-hidden="true">
                  {preference === value && <Check size={12} strokeWidth={2.5} />}
                </span>
                <span className="theme-choice-description">{description}</span>
              </span>
            </label>
          ))}
        </fieldset>
        <footer className="appearance-footer">
          <p role="status" aria-live="polite">
            <CheckCircle2 size={15} aria-hidden="true" />
            {saved ? 'Changes apply instantly and are saved on this device.' : 'Applied for this visit. Your browser is not allowing saved preferences.'}
          </p>
          <span>{preference === 'system' ? `Your device is currently using ${theme} mode.` : 'Your space, your preference.'}</span>
        </footer>
      </section>
      <p className="preferences-note">A softer canvas. The same care for your content.</p>
    </section>
  )
}
