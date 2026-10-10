import { LoadingState } from '../../loading/LoadingState'
import { useRef, useState } from 'react'
import { AlignLeft, ChevronDown, FileText, Files, Image, Info, LockKeyhole, Upload, X } from 'lucide-react'
import type { IntakeController } from './useIntake'
import { InlineNotice } from '../../ui/WorkspaceControls'
import { GlassTextarea } from '../../ui/GlassTextarea'
import { GlassSelect } from '../../ui/GlassSelect'
import { cn } from '../../ui/cn'
import type { CsvDelimiter } from '../../api/client'
import { OriginalScan } from './OriginalScan'

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
          <h2>Your text or file</h2>
          <p>Paste text or add a document to review.</p>
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
        <legend className="sr-only">How would you like to add your text?</legend>
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
        <div key="paste" className="intake-writing-area">
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
        <div key="file" className="intake-file-area">
          <div
            className={cn('intake-dropzone', dragging && 'is-dragging', intake.file && 'has-file')}
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
            {intake.file ? <FileText size={24} strokeWidth={1.5} aria-hidden="true" />
              : <Upload size={27} strokeWidth={1.3} aria-hidden="true" />}
            <div className="intake-file-description">
              <strong>{intake.file ? intake.file.name : 'Drop your document here'}</strong>
              <span>{intake.file
                ? <>{(intake.file.size / 1024).toLocaleString(undefined, { maximumFractionDigits: 0 })} KB
                  {intake.filePages !== null && ` · ${intake.filePages} page${intake.filePages === 1 ? '' : 's'}`}</>
                : 'One file at a time. We’ll extract the text for you.'}</span>
            </div>
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
              <span>{intake.file ? 'Change file' : 'Choose file'}</span>
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
            <label className="field-label" htmlFor="csv-delimiter">How are columns separated?</label>
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
          {intake.hasFilePreview && (
            <div className={cn('intake-file-text', intake.filePagePreviews.length > 0 && 'intake-file-comparison')}>
              {intake.filePagePreviews.length > 0 && <OriginalScan pages={intake.filePagePreviews} totalPages={intake.filePages} />}
              <div className="intake-corrected-text">
                <label className="field-label" htmlFor="file-preview">
                  Text to review <span>{intake.filePagePreviews.length > 0 ? 'All pages · editable' : 'Editable'}</span>
                </label>
                <GlassTextarea id="file-preview" value={intake.fileText}
                  onChange={(event) => intake.setFileText(event.target.value)} disabled={intake.pending || intake.fileLoading}
                  spellCheck={false} aria-describedby="file-preview-help" />
              </div>
            </div>
          )}
          {intake.hasFilePreview && <p id="file-preview-help" className="field-note">{intake.file && /\.csv$/i.test(intake.file.name) ? 'Keep the same number of columns. Changing how columns are read resets this text.' : intake.file && /\.docx$/i.test(intake.file.name) ? 'Editing Word text may simplify its layout.' : 'Check for anything missing or misread.'} We’ll save the text with your corrections.</p>}
          {intake.fileEdited && <p className="field-note" role="status">Your corrections will be saved.</p>}
          {!intake.file && <ul className="intake-file-formats" aria-label="Supported files and size limits">
            <li><FileText size={17} aria-hidden="true" /><strong>Text</strong><span>TXT · Markdown · CSV</span><small>About 1 MB max</small></li>
            <li><Files size={17} aria-hidden="true" /><strong>Documents</strong><span>PDF · Word (DOCX)</span><small>About 8 MB max</small></li>
            <li><Image size={17} aria-hidden="true" /><strong>Images</strong><span>PNG · JPG · TIFF · WebP</span><small>About 8 MB max</small></li>
          </ul>}
          <details className="intake-file-help intake-help">
            <summary><Info size={17} aria-hidden="true" /><span>{intake.file ? 'File notes & tips' : 'Upload tips & limits'}</span><ChevronDown size={16} aria-hidden="true" /></summary>
            {intake.fileNotes.map((note) => <p key={note} className="field-note">{note}</p>)}
            <ul className="intake-help-list">
              <li><Image size={18} aria-hidden="true" /><div><strong>Use a clear scan</strong><p>Printed text in English works best. Compare the scan with its extracted text before saving.</p></div></li>
              <li><FileText size={18} aria-hidden="true" /><div><strong>Check the text first</strong><p>Fix anything missing or misread before you save.</p></div></li>
            </ul>
            <details className="intake-technical-help">
              <summary>File and scan limits <ChevronDown size={14} aria-hidden="true" /></summary>
              <dl>
                <div><dt>Text files</dt><dd>1 MiB (1,048,576 bytes).</dd></div>
                <div><dt>Documents & images</dt><dd>8 MiB (8,388,608 bytes).</dd></div>
                <div><dt>Scanned pages</dt><dd>English printed text only. Up to 10 pages, each up to 8 million pixels.</dd></div>
                <div><dt>Review title</dt><dd>Optional. Add one above to find this review later. We don’t use the filename as the title.</dd></div>
              </dl>
            </details>
          </details>
        </div>
      )}
      <div
        className={cn('intake-editor-footer', intake.overLimit && 'is-over-limit')}
        id="intake-source-limits"
      >
        <span>
          <strong>{intake.characters.toLocaleString()}</strong> / 100,000 characters
        </span>
      </div>
      {intake.overLimit && (
        <InlineNotice error>
          Shorten your text to 100,000 characters or fewer before saving (maximum 1 MiB).
        </InlineNotice>
      )}
    </div>
  )
}
