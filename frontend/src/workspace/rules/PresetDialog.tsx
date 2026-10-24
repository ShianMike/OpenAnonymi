import { defaultDetectionCategories, detectionChoices, extras } from '../../detection/categories'
import type { FindingCategory } from '../../api/client'
import { phoneRegions } from '../../ui/phoneRegions'
import { useId, useRef, useState, type FormEvent, type ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import type { PresetInput, PresetView } from '../../api/client'
import { GlassSelect } from '../../ui/GlassSelect'
import { ChoiceSwitch, DialogFrame, InlineNotice } from '../../ui/WorkspaceControls'
import type { CategoryDefault } from '../../api/client'
import { PresetDefaults } from './PresetDefaults'
import { choiceKey, presetChoices, tokenChoice } from '../../review/useStyleControls'

export function PresetDialog({
  preset,
  initial,
  trigger,
  onSave,
}: {
  preset?: PresetView
  initial?: PresetInput
  trigger: ReactNode
  onSave: (value: PresetInput) => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState(defaultDetectionCategories.includes('email'))
  const [phone, setPhone] = useState(defaultDetectionCategories.includes('phone'))
  const [extraCategories, setExtraCategories] = useState<FindingCategory[]>(extras(defaultDetectionCategories))
  const [phoneRegion, setPhoneRegion] = useState('PH')
  const [preferredAction, setPreferredAction] = useState<'label' | 'redact'>('label')
  const [isDefault, setIsDefault] = useState(false)
  const [categoryDefaults, setCategoryDefaults] = useState<Record<string, CategoryDefault>>({})
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fieldId = useId()
  const loaded = useRef<string | null>(null)
  const categories: FindingCategory[] = [...(email ? ['email' as const] : []), ...(phone ? ['phone' as const] : []), ...extraCategories]
  function changeOpen(next: boolean) {
    if (pending) return
    const origin = preset ? `${preset.id}:${preset.version}` : 'new'
    if (next && loaded.current !== origin) {
      const setup = preset ?? initial
      setName(setup?.name ?? '')
      const categories = setup?.categories ?? defaultDetectionCategories
      setEmail(categories.includes('email'))
      setPhone(categories.includes('phone'))
      setExtraCategories(extras(categories))
      setPhoneRegion(setup?.phone_region ?? 'PH')
      setPreferredAction(setup?.preferred_action ?? 'label')
      setIsDefault(setup?.is_default ?? false)
      setCategoryDefaults(setup?.category_defaults ?? {})
      setError(null)
      loaded.current = origin
    }
    setOpen(next)
  }
  async function save(event: FormEvent) {
    event.preventDefault()
    if (pending || !name.trim()) return
    setPending(true)
    setError(null)
    try {
      await onSave({
        name: name.trim(),
        categories,
        phone_region: phoneRegion,
        preferred_action: preferredAction,
        is_default: isDefault,
        category_defaults: Object.fromEntries(Object.entries(categoryDefaults).map(([category, choice]) => [category, {
          action: choice.action, ...(presetChoices(category as FindingCategory, choice.action, phoneRegion)
            .find((candidate) => choiceKey(candidate) === choiceKey(choice)) ?? tokenChoice),
        }])),
      })
      loaded.current = null; setOpen(false)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Preset could not be saved.')
    } finally {
      setPending(false)
    }
  }
  return (
    <Dialog.Root open={open} onOpenChange={changeOpen}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <DialogFrame
        title={preset ? 'Edit review preset' : initial ? 'Save a preset copy' : 'New review preset'}
        description="A reusable starting point for new reviews. You still decide every finding."
        busy={pending}
        className="workspace-side-dialog preset-editor-dialog"
      >
        <form onSubmit={save} className="preset-form">
          <div className="preset-editor-body">
          <div>
            <label className="field-label" htmlFor={`preset-name-${fieldId}`}>
              Preset name
            </label>
            <input
              id={`preset-name-${fieldId}`}
              required
              maxLength={100}
              placeholder="e.g. External sharing"
              value={name}
              onChange={(event) => setName(event.target.value)}
              disabled={pending}
            />
          </div>
          <div className="preset-detection-group">
            <div className="preset-coverage-heading"><span className="field-label">Detection categories</span><span>{categories.length} selected</span></div>
            <div className="preset-coverage-grid">{detectionChoices.map(choice => <label key={choice.category} title={choice.description}>
              <input type="checkbox" checked={categories.includes(choice.category)} disabled={pending} onChange={event => {
                const next = event.target.checked ? [...categories, choice.category] : categories.filter(category => category !== choice.category)
                setEmail(next.includes('email')); setPhone(next.includes('phone')); setExtraCategories(extras(next))
              }} /><span>{choice.label}</span></label>)}</div>
            <p className="rule-field-note">Only selected categories are scanned. Workspace detection rules are added separately.</p>
          </div>
          <div className="dialog-field-pair">
            <div>
              <label className="field-label" htmlFor={`preset-region-${fieldId}`}>
                {extraCategories.includes('date') ? 'Phone and date region' : 'Phone region'}
              </label>
              <GlassSelect
                id={`preset-region-${fieldId}`}
                value={phoneRegion}
                onValueChange={setPhoneRegion}
                disabled={pending || (!phone && !extraCategories.includes('date'))}
              >
                {phoneRegions.map(([code, label]) => (
                  <option value={code} key={code}>
                    {label}
                  </option>
                ))}
              </GlassSelect>
            </div>
            <div>
              <label className="field-label" htmlFor={`preset-action-${fieldId}`}>
                Preferred action
              </label>
              <GlassSelect
                id={`preset-action-${fieldId}`}
                value={preferredAction}
                onValueChange={(value) => setPreferredAction(value as 'label' | 'redact')}
                disabled={pending}
              >
                <option value="label" data-description="Replace with a category label.">
                  Readable labels
                </option>
                <option value="redact" data-description="Hide the selected text.">
                  Redacted text
                </option>
              </GlassSelect>
            </div>
          </div>
          <ChoiceSwitch
            label="Workspace default"
            description="Select this preset automatically for new reviews."
            checked={isDefault}
            onChange={setIsDefault}
            disabled={pending}
          />
          <PresetDefaults value={categoryDefaults} onChange={setCategoryDefaults} region={phoneRegion} disabled={pending} />
          </div>
          <footer className="preset-editor-footer">
          {error && <InlineNotice error>{error}</InlineNotice>}
          <p>Applies to new reviews. Existing reviews keep their saved settings.</p>
          <div className="dialog-actions">
            <Dialog.Close asChild>
              <button className="quiet-button" type="button" disabled={pending}>
                Close
              </button>
            </Dialog.Close>
            <button type="submit" className="button-primary" disabled={pending || !name.trim()}>
              {pending ? 'Saving…' : preset ? 'Save preset' : 'Create preset'}
            </button>
          </div>
          </footer>
        </form>
      </DialogFrame>
    </Dialog.Root>
  )
}
