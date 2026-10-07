import { LoadingState } from '../../loading/LoadingState'
import { useRef, useState } from 'react'
import { AlignLeft, FileText, LockKeyhole, Upload, X } from 'lucide-react'
import type { IntakeController } from './useIntake'
import { InlineNotice } from '../../ui/WorkspaceControls'
import { GlassTextarea } from '../../ui/GlassTextarea'
import { GlassSelect } from '../../ui/GlassSelect'
import type { CsvDelimiter } from '../../api/client'

export function IntakeSource({ intake }: { intake: IntakeController }) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  return (
    <div className="intake-editor-panel">
      <div className="intake-editor-heading">
        <span className="panel-heading-icon">
          <FileText size={20} strokeWidth={1.5} aria-hidden="true" />
        </span>
        <div>
          <h2>Your content</h2>
          <p>Paste a note or bring in a document.</p>
        </div>
        <span className="subtle-badge"><LockKeyhole size={12} aria-hidden="true" /> Private draft</span>
      </div>
      <div className="intake-title-field">
        <label className="field-label" htmlFor="draft-title">
          Review title <span>Optional</span>
        </label>
        <input
          id="draft-title"
          type="text"
          maxLength={200}
          value={intake.title}
          placeholder="e.g. Customer interview · September"
          onChange={(event) => intake.setTitle(event.target.value)}
          disabled={intake.pending}
        />
      </div>
      <fieldset className="intake-mode">
        <legend className="sr-only">Source format</legend>
        <label>
          <input
            type="radio"
            name="source-mode"
            checked={intake.mode === 'paste'}
            onChange={() => intake.setMode('paste')}
            disabled={intake.pending}
          />
          <span>
            <AlignLeft size={16} aria-hidden="true" /> Paste text
          </span>
        </label>
        <label>
          <input
            type="radio"
            name="source-mode"
            checked={intake.mode === 'file'}
            onChange={() => intake.setMode('file')}
            disabled={intake.pending}
          />
          <span>
            <Upload size={16} aria-hidden="true" /> Upload file
          </span>
        </label>
      </fieldset>
      {intake.mode === 'paste' ? (
        <div className="intake-writing-area">
          <label htmlFor="source-text" className="sr-only">
            Text to review
          </label>
          <GlassTextarea
            id="source-text"
            value={intake.source}
            placeholder={
              'Paste the text you want to review…\n\nYour original stays intact. You choose which details to change.'
            }
            onChange={(event) => intake.setSource(event.target.value)}
            required
            disabled={intake.pending}
            aria-describedby="intake-source-limits"
            spellCheck={false}
          />
        </div>
      ) : (
        <div className="intake-file-area">
          <div
            className={`intake-dropzone${dragging ? ' is-dragging' : ''}${intake.file ? ' has-file' : ''}`}
            onDragOver={(event) => {
              event.preventDefault()
              if (!intake.pending) setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault()
              setDragging(false)
              if (!intake.pending) {
                if (inputRef.current) inputRef.current.value = ''
                void intake.chooseFile(event.dataTransfer.files[0] ?? null, event.dataTransfer.files.length)
              }
            }}
          >
            <Upload size={27} strokeWidth={1.3} aria-hidden="true" />
            <strong>{intake.file ? intake.file.name : 'Drop your document here'}</strong>
            <span>TXT / MD / CSV · 1 MiB · PDF / DOCX / Images · 8 MiB</span>
            <label className="intake-file-picker">
              <input
                ref={inputRef}
                id="source-file"
                key={intake.workspaceId}
                type="file"
                accept=".txt,.md,.csv,.pdf,.docx,.png,.jpg,.jpeg,.tif,.tiff,.webp,text/plain,text/markdown,text/csv,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/png,image/jpeg,image/tiff,image/webp"
                aria-label="Choose one document or scan"
                disabled={intake.pending}
                onChange={(event) => void intake.chooseFile(event.currentTarget.files?.[0] ?? null)}
              />
              <span>{intake.file ? 'Choose another file' : 'Choose file'}</span>
            </label>
            {intake.file && (
              <button
                className="quiet-icon intake-file-remove"
                type="button"
                aria-label="Remove selected file"
                disabled={intake.pending}
                onClick={() => {
                  if (inputRef.current) inputRef.current.value = ''
                  void intake.chooseFile(null)
                }}
              >
                <X size={16} aria-hidden="true" />
              </button>
            )}
          </div>
          {intake.fileLoading && (
            <LoadingState label="Reading file text…" compact />
          )}
          {intake.fileError && <InlineNotice error>{intake.fileError}</InlineNotice>}
          {intake.file && /\.csv$/i.test(intake.file.name) && <div className="csv-intake-format">
            <label className="field-label" htmlFor="csv-delimiter">CSV delimiter</label>
            <GlassSelect id="csv-delimiter" value={intake.csvDelimiter} disabled={intake.pending}
              onValueChange={(value) => intake.changeCsvFormat(value as CsvDelimiter | 'auto', intake.csvHeader)}>
              <option value="auto">Detect automatically</option><option value=",">Comma</option><option value=";">Semicolon</option><option value={'\t'}>Tab</option><option value="|">Pipe</option>
            </GlassSelect>
            <label className="field-label" htmlFor="csv-header">First row</label>
            <GlassSelect id="csv-header" value={intake.csvHeader} disabled={intake.pending}
              onValueChange={(value) => intake.changeCsvFormat(intake.csvDelimiter, value as typeof intake.csvHeader)}>
              <option value="auto">Detect column names</option><option value="true">Column names</option><option value="false">Data</option>
            </GlassSelect>
            {intake.csvPreview && <p role="status">Detected: {{ ',': 'comma', ';': 'semicolon', '\t': 'tab', '|': 'pipe' }[intake.csvPreview.delimiter]}-separated; first row {intake.csvPreview.has_header ? 'has column names' : 'is data'}. {intake.csvPreview.columns} columns · {intake.csvPreview.data_rows} data rows.</p>}
            <p className="field-note">Up to 50 columns, 1,000 data rows and 10,000 characters per cell. Suggestions stay inside a cell. Check these settings before saving.</p>
          </div>}
          {intake.fileNotes.map((note) => <p key={note} className="field-note">{note}</p>)}
          {intake.hasFilePreview && (
            <>
              <label className="field-label" htmlFor="file-preview">
                Edit extracted text before saving
              </label>
              <GlassTextarea id="file-preview" value={intake.fileText}
                onChange={(event) => intake.setFileText(event.target.value)} disabled={intake.pending || intake.fileLoading}
                spellCheck={false} aria-describedby="file-preview-help" />
            </>
          )}
          {intake.hasFilePreview && <p id="file-preview-help" className="field-note">The edited text becomes your saved source. Word edits may simplify layout; CSV edits must keep the same column count. Changing CSV reading settings resets the preview.</p>}
          {intake.fileEdited && <p className="field-note" role="status">Your text corrections will be saved. CSV structure is checked again when saving.</p>}
          <details className="intake-file-help">
            <summary>Supported files and import limits</summary>
            <p className="field-note">TXT, Markdown and CSV: up to 1 MiB. PDF, DOCX and images: up to 8 MiB. OCR reads English printed text locally, up to 10 scanned pages and 8 million pixels per page. Check for missing or misread details. Filenames are not saved as titles.</p>
          </details>
        </div>
      )}
      <div
        className={`intake-editor-footer${intake.overLimit ? ' is-over-limit' : ''}`}
        id="intake-source-limits"
      >
        <span>
          <strong>{intake.characters.toLocaleString()}</strong> / 100,000 characters
        </span>
        <span>{intake.bytes.toLocaleString()} bytes · 1 MiB max</span>
      </div>
      {intake.overLimit && (
        <InlineNotice error>
          Shorten the text to 100,000 characters and 1 MiB or less before saving.
        </InlineNotice>
      )}
    </div>
  )
}
