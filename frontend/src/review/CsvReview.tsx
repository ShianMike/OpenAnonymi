import { useEffect, useId, useState } from 'react'
import { getWorkspacePresets, type ColumnDecisionRequest, type ColumnRule, type CsvDelimiter,
  type CsvInfo, type FindingCategory, type PresetView } from '../api/client'
import { findingCategories, categoryPresentation } from '../rules/categoryPresentation'
import { GlassSelect } from '../ui/GlassSelect'
import { GlassCheckbox } from '../ui/GlassCheckbox'
import { columnFindings } from './csvColumns'
import { sameVersion } from './reviewState'
import { availableChoices, choiceKey, presetChoices, styleDisclosure, styleLabel, tokenChoice,
  type ReviewAction } from './useStyleControls'
import type { ReviewController } from './useReviewController'
import './csv-review.css'

const delimiters = [[',', 'Comma'], [';', 'Semicolon'], ['\t', 'Tab'], ['|', 'Pipe']] as const
const reasons = [['false_match', 'False match'], ['intended_disclosure', 'Intended disclosure']] as const
type KeepReason = typeof reasons[number][0]

function blockedReason(review: ReviewController): string | undefined {
  if (!review.canEdit) return 'The document owner manages CSV settings and column decisions.'
  if (review.conflict) return 'Reload the saved review before making changes.'
  if (review.dirty || review.settingsDirty) return 'Save or discard your text and suggestion setting changes first.'
  if (review.actionPending) return 'Wait for the current request to finish.'
}

export function CsvReview({ review }: { review: ReviewController }) {
  if (review.state.kind !== 'ready' || !review.state.saved.csv) return null
  return <CsvPanel review={review} csv={review.state.saved.csv} />
}

function CsvPanel({ review, csv }: { review: ReviewController; csv: CsvInfo }) {
  const id = useId()
  const [column, setColumn] = useState(0)
  const rule = csv.rules.find((item) => item.column === column)
  const version = review.state.kind === 'ready' ? review.state.saved.version : null
  const key = `${version?.source_revision_id}:${version?.settings_version}`
  const name = csv.has_header ? csv.headers[column] : ''
  const reason = blockedReason(review)
  return <details className="csv-review">
    <summary>CSV columns <span>{csv.columns} columns · {csv.data_rows} data rows</span></summary>
    <div className="csv-review-body">
      <p className="field-note">Header cells always use normal detection. Column rules create suggestions; every finding still needs your decision.</p>
      <CsvFormat key={key} csv={csv} review={review} />
      <label className="field-label" htmlFor={`${id}-column`}>CSV column</label>
      <GlassSelect id={`${id}-column`} value={String(column)} disabled={review.actionPending}
        onValueChange={(value) => setColumn(Number(value))}>
        {Array.from({ length: csv.columns }, (_, index) => <option key={index} value={String(index)}>
          {index + 1}{csv.headers[index] ? ` · ${csv.headers[index]}` : ''}
        </option>)}
      </GlassSelect>
      <p className="field-note">Saved mode: {rule?.mode === 'category' ? `Category · ${categoryPresentation[rule.category!].label}` : rule?.mode === 'keep' ? `Keep · ${rule.keep_reason === 'false_match' ? 'False match' : 'Intended disclosure'}` : 'Normal detection'}.</p>
      {reason && <p className="field-note" role="status">{reason}</p>}
      <ColumnRuleEditor key={`${key}:${column}`} csv={csv} column={column} header={name} review={review} rule={rule} />
      <ColumnDecision key={`${key}:${column}:${version?.decision_version}`} csv={csv} column={column} review={review} rule={rule} />
      {review.canManagePresets && <ColumnPreset key={key} csv={csv} review={review} />}
    </div>
  </details>
}

function CsvFormat({ csv, review }: { csv: CsvInfo; review: ReviewController }) {
  const id = useId()
  const [delimiter, setDelimiter] = useState<CsvDelimiter>(csv.delimiter)
  const [hasHeader, setHasHeader] = useState(csv.has_header)
  const reason = blockedReason(review)
  const changed = delimiter !== csv.delimiter || hasHeader !== csv.has_header
  return <fieldset className="csv-fields"><legend>CSV format</legend>
    <label className="field-label" htmlFor={`${id}-delimiter`}>Review delimiter</label>
    <GlassSelect id={`${id}-delimiter`} value={delimiter} disabled={Boolean(reason)} onValueChange={(value) => setDelimiter(value as CsvDelimiter)}>
      {delimiters.map(([value, name]) => <option key={value} value={value}>{name}</option>)}
    </GlassSelect>
    <GlassCheckbox label="First row is a header" checked={hasHeader} disabled={Boolean(reason)} onCheckedChange={setHasHeader} />
    <p className="field-note">Changing the format reparses the saved text and requires a fresh scan and review.</p>
    <button type="button" disabled={Boolean(reason) || !changed} title={reason ?? (!changed ? 'The format matches the saved review.' : undefined)}
      onClick={() => void review.saveCsvFormat(delimiter, hasHeader)}>Save CSV format</button>
  </fieldset>
}

function ColumnRuleEditor({ csv, column, header, review, rule }: {
  csv: CsvInfo; column: number; header: string; review: ReviewController; rule?: ColumnRule;
}) {
  const id = useId()
  const [mode, setMode] = useState<ColumnRule['mode']>(rule?.mode ?? 'scan')
  const [category, setCategory] = useState<FindingCategory>(rule?.category ?? 'person')
  const [action, setAction] = useState<ReviewAction>(rule?.default_action ?? 'label')
  const [selected, setSelected] = useState(choiceKey(rule ?? tokenChoice))
  const [keepReason, setKeepReason] = useState<KeepReason>(rule?.keep_reason ?? 'false_match')
  const region = review.state.kind === 'ready' ? review.state.saved.phone_region : 'PH'
  const choices = presetChoices(category, action, region)
  const choice = choices.find((item) => choiceKey(item) === selected) ?? tokenChoice
  const reason = blockedReason(review) ?? (Array.from(header).length > 1000 ? 'Column rule header names must contain at most 1,000 characters.' : undefined)
  const disclosure = mode === 'category' ? styleDisclosure(choice) : null
  function save() {
    const next: ColumnRule = { column, header, mode, category: mode === 'category' ? category : null,
      default_action: mode === 'category' ? action : 'label',
      style: mode === 'category' ? choice.style : 'token', style_option: mode === 'category' ? choice.style_option : null,
      keep_reason: mode === 'keep' || (mode === 'category' && action === 'keep') ? keepReason : null }
    void review.saveColumnRules([...csv.rules.filter((item) => item.column !== column), next])
  }
  return <fieldset className="csv-fields"><legend>Column suggestion rule</legend>
    <label className="field-label" htmlFor={`${id}-mode`}>Column mode</label>
    <GlassSelect id={`${id}-mode`} value={mode} disabled={Boolean(reason)} onValueChange={(value) => setMode(value as ColumnRule['mode'])}>
      <option value="scan">Normal detection</option><option value="category">Category for each nonempty cell</option><option value="keep">Keep without automatic suggestions</option>
    </GlassSelect>
    {mode === 'category' && <>
      <label className="field-label" htmlFor={`${id}-category`}>Column category</label>
      <GlassSelect id={`${id}-category`} value={category} disabled={Boolean(reason)} onValueChange={(value) => { setCategory(value as FindingCategory); setSelected(choiceKey(tokenChoice)) }}>
        {findingCategories.map((value) => <option key={value} value={value}>{categoryPresentation[value].label}</option>)}
      </GlassSelect>
      <label className="field-label" htmlFor={`${id}-default-action`}>Default column action</label>
      <GlassSelect id={`${id}-default-action`} value={action} disabled={Boolean(reason)} onValueChange={(value) => { setAction(value as ReviewAction); setSelected(choiceKey(tokenChoice)) }}>
        <option value="label">Label</option><option value="redact">Redact</option><option value="keep">Keep</option>
      </GlassSelect>
      <label className="field-label" htmlFor={`${id}-default-style`}>Default column style</label>
      <GlassSelect id={`${id}-default-style`} value={choiceKey(choice)} disabled={Boolean(reason)} onValueChange={setSelected}>
        {choices.map((item) => <option key={choiceKey(item)} value={choiceKey(item)}>{styleLabel(item, action)}</option>)}
      </GlassSelect>
      {disclosure && <p className="field-note">{disclosure}</p>}
      <p className="field-note">Defaults preselect a choice. They do not approve or decide any finding.</p>
    </>}
    {(mode === 'keep' || (mode === 'category' && action === 'keep')) && <KeepReasonSelect id={`${id}-reason`} value={keepReason} blocked={Boolean(reason)} onChange={setKeepReason} />}
    {mode === 'keep' && <p className="field-note">Manual marking remains available. Review the full column before sharing.</p>}
    {reason && <p className="field-note">{reason}</p>}
    <button type="button" disabled={Boolean(reason)} title={reason} onClick={save}>Save column rule</button>
  </fieldset>
}

function KeepReasonSelect({ id, value, blocked, onChange }: { id: string; value: KeepReason; blocked: boolean; onChange: (value: KeepReason) => void }) {
  return <><label className="field-label" htmlFor={id}>Column Keep reason</label>
    <GlassSelect id={id} value={value} disabled={blocked} onValueChange={(value) => onChange(value as KeepReason)}>
      {reasons.map(([key, name]) => <option key={key} value={key}>{name}</option>)}
    </GlassSelect></>
}

function ColumnDecision({ csv, column, review, rule }: { csv: CsvInfo; column: number; review: ReviewController; rule?: ColumnRule }) {
  const id = useId()
  const findings = columnFindings(csv, review.activeFindings, column)
  const [action, setAction] = useState<ReviewAction>(rule?.mode === 'category' ? rule.default_action : 'label')
  const [selected, setSelected] = useState(choiceKey(rule?.mode === 'category' ? rule : tokenChoice))
  const [keepReason, setKeepReason] = useState<KeepReason>(rule?.keep_reason ?? 'false_match')
  const [sameEntity, setSameEntity] = useState(false)
  const [confirmation, setConfirmation] = useState<ColumnDecisionRequest | null>(null)
  const choices = findings.length ? availableChoices(review.preview, findings[0], action).filter((choice) =>
    findings.every((finding) => availableChoices(review.preview, finding, action).some((item) => choiceKey(item) === choiceKey(choice)))) : [tokenChoice]
  const choice = choices.find((item) => choiceKey(item) === selected) ?? tokenChoice
  const reason = blockedReason(review) ?? (review.scan?.status !== 'completed' ? 'Run a fresh scan before deciding the column.' :
    !findings.length ? 'This column has no active data-cell findings.' : !review.preview ? 'Wait for the current preview to load.' : undefined)
  const disclosure = styleDisclosure(choice)
  function inspect() {
    if (review.state.kind !== 'ready') return
    setConfirmation({ expected: review.state.saved.version, action, style: choice.style ?? 'token',
      style_option: choice.style_option, affected_finding_ids: findings.map((item) => item.finding_id),
      keep_reason: action === 'keep' ? keepReason : null, same_text_same_entity: action === 'label' && sameEntity })
  }
  return <fieldset className="csv-fields"><legend>Decide the column</legend>
    <p className="field-note">{findings.length} active findings in data cells. Header findings are reviewed individually.</p>
    <label className="field-label" htmlFor={`${id}-action`}>Column decision action</label>
    <GlassSelect id={`${id}-action`} value={action} disabled={Boolean(reason)} onValueChange={(value) => { setAction(value as ReviewAction); setSelected(choiceKey(tokenChoice)); setConfirmation(null) }}>
      <option value="label">Label</option><option value="redact">Redact</option><option value="keep">Keep</option>
    </GlassSelect>
    <label className="field-label" htmlFor={`${id}-style`}>Column decision style</label>
    <GlassSelect id={`${id}-style`} value={choiceKey(choice)} disabled={Boolean(reason)} onValueChange={(value) => { setSelected(value); setConfirmation(null) }}>
      {choices.map((item) => <option key={choiceKey(item)} value={choiceKey(item)}>{styleLabel(item, action)}</option>)}
    </GlassSelect>
    {disclosure && <p className="field-note">{disclosure}</p>}
    {action === 'keep' && <KeepReasonSelect id={`${id}-reason`} value={keepReason} blocked={Boolean(reason)} onChange={(value) => { setKeepReason(value); setConfirmation(null) }} />}
    {action === 'label' && <GlassCheckbox label="Same text means the same entity in this column" checked={sameEntity} disabled={Boolean(reason)}
      description="Otherwise each finding receives its own label. Only opt in after checking the affected cells."
      onCheckedChange={(value) => { setSameEntity(value); setConfirmation(null) }} />}
    {reason && <p className="field-note">{reason}</p>}
    <button type="button" disabled={Boolean(reason)} title={reason} onClick={inspect}>Review column decisions</button>
    {confirmation && <div className="csv-column-confirmation" role="group" aria-label="Confirm column decisions">
      <p>Apply {styleLabel(confirmation, confirmation.action)} to these {confirmation.affected_finding_ids.length} findings in column {column + 1}?</p>
      <ol>{findings.map((item) => <li key={item.finding_id}><strong>{item.span.start + 1}–{item.span.end}</strong> · {review.codePoints.slice(item.span.start, item.span.end).join('')}</li>)}</ol>
      <button type="button" className="button-primary" disabled={Boolean(reason) || review.state.kind !== 'ready' || !sameVersion(confirmation.expected, review.state.saved.version)} title={reason}
        onClick={() => { void review.applyColumnDecision(column, confirmation).then((saved) => { if (saved) setConfirmation(null) }) }}>Apply to column</button>
      <button type="button" onClick={() => setConfirmation(null)} disabled={review.actionPending}>Cancel column decision</button>
    </div>}
  </fieldset>
}

function ColumnPreset({ csv, review }: { csv: CsvInfo; review: ReviewController }) {
  const id = useId()
  const [presets, setPresets] = useState<PresetView[] | null>(null)
  const [chosen, setChosen] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const workspaceId = review.state.kind === 'ready' ? review.state.saved.workspace_id : ''
  useEffect(() => {
    const controller = new AbortController()
    getWorkspacePresets(workspaceId, controller.signal).then((result) => { if (!controller.signal.aborted) setPresets(result) })
      .catch(() => { if (!controller.signal.aborted) setError('Presets could not be loaded.') })
    return () => controller.abort()
  }, [workspaceId, attempt])
  const preset = presets?.find((item) => item.id === chosen)
  const reason = blockedReason(review) ?? (!csv.has_header ? 'Header names are required to match preset columns.' :
    !csv.rules.length ? 'Save a column rule first.' : !preset ? 'Choose an existing workspace preset.' : undefined)
  return <fieldset className="csv-fields"><legend>Reuse column rules</legend>
    <p className="field-note">Replace the chosen preset’s column rules with this document’s saved rules. New CSV imports match by header name.</p>
    {presets?.length ? <><label className="field-label" htmlFor={`${id}-preset`}>Column rules preset</label>
      <GlassSelect id={`${id}-preset`} value={chosen || 'choose'} disabled={review.actionPending} onValueChange={setChosen}>
        <option value="choose" disabled>Choose a preset</option>{presets.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </GlassSelect></> : <p className="field-note">{presets ? 'Create a workspace preset in Settings first.' : 'Loading presets…'}</p>}
    {error && <p role="alert">{error}</p>}
    {error && <button type="button" onClick={() => { setError(null); setAttempt((value) => value + 1) }}>Retry presets</button>}
    <button type="button" disabled={Boolean(reason)} title={reason} onClick={() => {
      if (preset) void review.saveColumnPreset(preset).then((saved) => { if (saved) { setChosen(''); setAttempt((value) => value + 1) } })
    }}>Save column rules to preset</button>
    {reason && <p className="field-note">{reason}</p>}
  </fieldset>
}
