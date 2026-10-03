import { extraDetection, extras } from '../../detection/categories'
import type { FindingCategory } from '../../api/client'
import { phoneRegions } from '../../ui/phoneRegions'
import { useState, type FormEvent, type ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import type { PresetInput, PresetView } from '../../api/client'
import { GlassSelect } from '../../ui/GlassSelect'
import { ChoiceSwitch, DialogFrame, InlineNotice } from '../../ui/WorkspaceControls'
import type { CategoryDefault } from '../../api/client'
import { PresetDefaults } from './PresetDefaults'
import { choiceKey, presetChoices, tokenChoice } from '../../review/useStyleControls'

export function PresetDialog({
  preset,
  trigger,
  onSave,
}: {
  preset?: PresetView
  trigger: ReactNode
  onSave: (value: PresetInput) => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState(true)
  const [phone, setPhone] = useState(true)
  const [extraCategories, setExtraCategories] = useState<FindingCategory[]>([])
  const [phoneRegion, setPhoneRegion] = useState('PH')
  const [preferredAction, setPreferredAction] = useState<'label' | 'redact'>('label')
  const [isDefault, setIsDefault] = useState(false)
  const [categoryDefaults, setCategoryDefaults] = useState<Record<string, CategoryDefault>>({})
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fieldId = preset?.id ?? 'new'
  function changeOpen(next: boolean) {
    if (pending) return
    if (next) {
      setName(preset?.name ?? '')
      setEmail(preset?.categories.includes('email') ?? true)
      setPhone(preset?.categories.includes('phone') ?? true)
      setExtraCategories(extras(preset?.categories ?? []))
      setPhoneRegion(preset?.phone_region ?? 'PH')
      setPreferredAction(preset?.preferred_action ?? 'label')
      setIsDefault(preset?.is_default ?? false)
      setCategoryDefaults(preset?.category_defaults ?? {})
      setError(null)
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
        categories: [...(email ? ['email' as const] : []), ...(phone ? ['phone' as const] : []), ...extraCategories],
        phone_region: phoneRegion,
        preferred_action: preferredAction,
        is_default: isDefault,
        category_defaults: Object.fromEntries(Object.entries(categoryDefaults).map(([category, choice]) => [category, {
          action: choice.action, ...(presetChoices(category as FindingCategory, choice.action, phoneRegion)
            .find((candidate) => choiceKey(candidate) === choiceKey(choice)) ?? tokenChoice),
        }])),
      })
      setOpen(false)
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
        title={preset ? 'Edit preset' : 'Create a preset'}
        description="A reusable starting point for new reviews. You still decide every finding."
        busy={pending}
      >
        <form onSubmit={save}>
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
            <span className="field-label">Automatic suggestions</span>
            <ChoiceSwitch label="Email addresses" checked={email} onChange={setEmail} disabled={pending} />
            <ChoiceSwitch label="Phone numbers" checked={phone} onChange={setPhone} disabled={pending} />
            {extraDetection.map((choice) => <ChoiceSwitch key={choice.category} label={choice.label} description={choice.description}
              checked={extraCategories.includes(choice.category)} disabled={pending} onChange={(checked) => setExtraCategories((current) =>
                checked ? [...current, choice.category] : current.filter((category) => category !== choice.category))} />)}
          </div>
          <div className="dialog-field-pair">
            <div>
              <label className="field-label" htmlFor={`preset-region-${fieldId}`}>
                Phone region
              </label>
              <GlassSelect
                id={`preset-region-${fieldId}`}
                value={phoneRegion}
                onValueChange={setPhoneRegion}
                disabled={pending || !phone}
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
                  Label
                </option>
                <option value="redact" data-description="Hide the selected text.">
                  Redact
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
          {error && <InlineNotice error>{error}</InlineNotice>}
          <div className="dialog-actions">
            <Dialog.Close asChild>
              <button className="quiet-button" type="button" disabled={pending}>
                Cancel
              </button>
            </Dialog.Close>
            <button type="submit" disabled={pending || !name.trim()}>
              {pending ? 'Saving…' : preset ? 'Save preset' : 'Create preset'}
            </button>
          </div>
        </form>
      </DialogFrame>
    </Dialog.Root>
  )
}
