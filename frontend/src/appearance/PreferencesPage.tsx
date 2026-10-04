import { Check, CheckCircle2, Monitor, Moon, Palette, Sun, Settings2 } from 'lucide-react'
import { PageHeader } from '../ui/PageHeader'
import { useAppearance } from './useAppearance'
import { ThemePreview } from './ThemePreview'
import { useDisplayPreferences } from './useDisplayPreferences'
import './preferences.css'

const choices = [
  { value: 'light', name: 'Light', description: 'Warm ivory & sage', icon: Sun },
  { value: 'dark', name: 'Dark', description: 'Deep forest & mint', icon: Moon },
  { value: 'system', name: 'System', description: 'Follow your device', icon: Monitor },
] as const

export function PreferencesPage() {
  const { preference, theme, saved, setAppearance } = useAppearance()
  const ActiveIcon = theme === 'light' ? Sun : Moon
  const display = useDisplayPreferences()
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
      <section className="appearance-panel display-panel" aria-labelledby="display-title">
        <header className="appearance-heading">
          <span className="appearance-icon"><Settings2 size={21} aria-hidden="true" /></span>
          <div><h2 id="display-title">Reading and movement</h2><p>Set the spacing, text size and motion that suit you.</p></div>
        </header>
        <div className="display-choice-groups">
          <fieldset><legend>Density</legend>
            {(['comfortable', 'compact'] as const).map(value => <label key={value} className="display-choice">
              <input type="radio" name="density" aria-label={value === 'comfortable' ? 'Comfortable' : 'Compact'} checked={display.density === value}
                onChange={() => display.setDisplayPreference('density', value)} />
              <span><strong>{value === 'comfortable' ? 'Comfortable' : 'Compact'}</strong>
                <small>{value === 'comfortable' ? 'Room between controls and findings' : 'Closer rows with the same touch targets'}</small></span>
            </label>)}
          </fieldset>
          <fieldset><legend>Text size</legend>
            {(['standard', 'large'] as const).map(value => <label key={value} className="display-choice">
              <input type="radio" name="font-size" aria-label={value === 'standard' ? 'Standard' : 'Large'} checked={display.fontSize === value}
                onChange={() => display.setDisplayPreference('fontSize', value)} />
              <span><strong>{value === 'standard' ? 'Standard' : 'Large'}</strong>
                <small>{value === 'standard' ? 'Default text size' : 'Larger text throughout the workspace'}</small></span>
            </label>)}
          </fieldset>
          <fieldset><legend>Motion</legend>
            {(['system', 'reduced'] as const).map(value => <label key={value} className="display-choice">
              <input type="radio" name="motion" aria-label={value === 'system' ? 'Follow device' : 'Reduce motion'} checked={display.motion === value}
                onChange={() => display.setDisplayPreference('motion', value)} />
              <span><strong>{value === 'system' ? 'Follow device' : 'Reduce motion'}</strong>
                <small>{value === 'system' ? 'Honor your device’s reduced motion setting' : 'Pause decorative motion and transitions'}</small></span>
            </label>)}
          </fieldset>
        </div>
        <footer className="appearance-footer"><p role="status"><CheckCircle2 size={15} aria-hidden="true" />
          {display.saved ? 'Display choices are saved on this device.' : 'Applied for this visit. Your browser is not allowing saved preferences.'}
        </p><span>{display.reducedMotion ? 'Reduced motion is active.' : 'Your device allows motion.'}</span></footer>
      </section>
      <p className="preferences-note">Only display choices are saved here. Your document content stays in the review.</p>
    </section>
  )
}
