import { Check, CheckCircle2, Monitor, Moon, Sun } from 'lucide-react'
import { GlassSelect } from '../ui/GlassSelect'
import { useAppearance } from './useAppearance'
import { ThemePreview } from './ThemePreview'
import { useDisplayPreferences } from './useDisplayPreferences'
import './preferences.css'

const choices = [
  { value: 'light', name: 'Light', description: 'Light surfaces', icon: Sun },
  { value: 'dark', name: 'Dark', description: 'Charcoal surfaces', icon: Moon },
  { value: 'system', name: 'System', description: 'Match your device', icon: Monitor },
] as const

export function PreferencesPage() {
  const { preference, theme, saved, setAppearance } = useAppearance()
  const display = useDisplayPreferences()
  return <div className="preferences-page">
    <section className="settings-section" aria-labelledby="appearance-title"><header className="settings-section-heading"><h3 id="appearance-title">Color theme</h3><p>Choose light, dark, or follow your device. Currently using {theme} mode.</p></header>
      <fieldset className="appearance-choices"><legend className="sr-only">Color theme</legend>{choices.map(({ value, name, description, icon: Icon }) => <label className="theme-choice" key={value}>
        <input type="radio" name="appearance" value={value} aria-label={name} checked={preference === value} onChange={() => setAppearance(value)} />
        <ThemePreview mode={value} /><span className="theme-choice-caption"><span className="theme-choice-title"><Icon size={15} aria-hidden="true" />{name}</span><span className="theme-choice-check" aria-hidden="true">{preference === value && <Check size={12} />}</span><span className="theme-choice-description">{description}</span></span>
      </label>)}</fieldset>
    </section>
    <section className="settings-section" aria-labelledby="display-title"><header className="settings-section-heading"><h3 id="display-title">Reading & interaction</h3><p>Adjust the workspace to the way you read and work.</p></header>
      <div className="settings-value-row"><div><label htmlFor="display-spacing">Spacing</label><p>Room between controls and findings. Touch targets stay the same size.</p></div><GlassSelect id="display-spacing" value={display.density} onValueChange={value => display.setDisplayPreference('density', value === 'compact' ? 'compact' : 'comfortable')}><option value="comfortable">Comfortable</option><option value="compact">Compact</option></GlassSelect></div>
      <div className="settings-value-row"><div><label htmlFor="display-font-size">Text size</label><p>Use standard text or increase the base text size.</p></div><GlassSelect id="display-font-size" value={display.fontSize} onValueChange={value => display.setDisplayPreference('fontSize', value === 'large' ? 'large' : 'standard')}><option value="standard">Standard</option><option value="large">Large</option></GlassSelect></div>
      <div className="settings-value-row"><div><label htmlFor="display-motion">Motion</label><p>Follow your device’s reduced motion setting or reduce decorative motion.</p></div><GlassSelect id="display-motion" value={display.motion} onValueChange={value => display.setDisplayPreference('motion', value === 'reduced' ? 'reduced' : 'system')}><option value="system">Follow device</option><option value="reduced">Reduce motion</option></GlassSelect></div>
    </section>
    <p className="settings-footnote preferences-note" role="status"><CheckCircle2 size={15} aria-hidden="true" />{saved && display.saved ? 'Changes apply immediately and are saved on this device.' : 'Applied for this visit. Your browser is not allowing saved preferences.'}</p>
  </div>
}
