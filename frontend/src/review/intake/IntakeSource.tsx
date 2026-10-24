import { useRef, useState } from 'react'
import { Check, ChevronDown, FileUp, FileText, Upload, X } from 'lucide-react'
import { OriginalScan } from './OriginalScan'
import type { IntakeController } from './useIntake'
import { LoadingState } from '../../loading/LoadingState'

export function IntakeSource({ intake }: { intake: IntakeController }) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const restoreFocus = useRef(false)
  const file = intake.mode === 'file' ? intake.file : null
  const fixedLayout = Boolean(file && /\.pdf$/i.test(file.name))
  function addFile(selected: File | null, count = 1) {
    if (!selected || intake.pending) return
    intake.setMode('file'); void intake.chooseFile(selected, count)
  }
  return <div className={`studio-import${dragging ? ' is-dragging' : ''}`} onDragOver={event => {
    if (!event.dataTransfer.types.includes('Files')) return
    event.preventDefault(); if (!intake.pending) setDragging(true)
  }} onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false) }} onDrop={event => {
    if (!event.dataTransfer.files.length) return
    event.preventDefault(); setDragging(false)
    if (inputRef.current) inputRef.current.value = ''
    addFile(event.dataTransfer.files[0] ?? null, event.dataTransfer.files.length)
  }}>
    <label className={`studio-upload${file ? ' has-file' : ''}`}>
      <input ref={inputRef} id="source-file" key={intake.workspaceId} type="file" disabled={intake.pending} aria-label={file ? 'Change source file' : 'Add a file to review'}
        accept=".txt,.md,.pdf,.docx,.png,.jpg,.jpeg,.tif,.tiff,.webp,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/png,image/jpeg,image/tiff,image/webp"
        onChange={event => addFile(event.currentTarget.files?.[0] ?? null)} />
      <span className="studio-upload-icon"><FileUp size={26} strokeWidth={1.3} /></span>
      <span><strong>{file ? 'Choose a different file' : 'Drop your document here'}</strong><small>{file ? 'Replace the current import' : 'PDF, Word, text or an image'}</small></span>
      <span className="studio-upload-button">{file ? 'Change file' : 'Browse files'}</span>
    </label>
    {!file && <div className="studio-source-divider"><span>or paste your text below</span></div>}
    <div className="studio-source-paper">
      <div className="studio-source-title"><label htmlFor="draft-title">Document title <small>Optional</small></label><input id="draft-title" type="text" maxLength={200} placeholder="Untitled document" value={intake.title} disabled={intake.pending} onChange={event => intake.setTitle(event.target.value)} /></div>
      {file ? <div className="studio-imported-file">
        <div className={`studio-file-row${intake.fileError ? ' has-error' : ''}`}><FileText size={19} /><div><strong>{file.name}</strong><small>{file.size < 1024 ? `${file.size} bytes` : `${(file.size / 1024).toLocaleString(undefined, { maximumFractionDigits: 1 })} KiB`}{intake.filePages !== null && ` · ${intake.filePages} ${intake.filePages === 1 ? 'page' : 'pages'}`}</small></div>
          {intake.hasFilePreview && !intake.fileLoading && !intake.fileError && <Check size={16} aria-label="Text extracted" />}
          <button type="button" className="studio-icon" disabled={intake.pending} aria-label="Remove file and return to text" onClick={() => { restoreFocus.current = true; if (inputRef.current) inputRef.current.value = ''; void intake.chooseFile(null); intake.setMode('paste') }}><X size={16} /></button>
        </div>
        {intake.source.trim() && <p className="field-note">Your pasted text is still here. Remove the file to return to it.</p>}
        {intake.fileLoading && <LoadingState className="studio-extracting" label="Extracting your document…" description="You can review the extracted text before saving." compact />}
        {intake.fileError && <p className="studio-error" role="alert">{intake.fileError}</p>}
        {intake.hasFilePreview && <div className={`studio-extracted-text${intake.filePagePreviews.length ? ' with-scan' : ''}`}>
          {intake.filePagePreviews.length > 0 && <OriginalScan key={`${file.name}-${file.lastModified}-${file.size}`} pages={intake.filePagePreviews} totalPages={intake.filePages} pdf={/\.pdf$/i.test(file.name)} />}
          <div><label className="field-label" htmlFor="file-preview">Extracted text <small>{fixedLayout ? 'Read-only · layout preserved' : intake.filePagePreviews.length ? 'All pages · editable' : 'Editable'}</small></label><textarea id="file-preview" readOnly={fixedLayout} value={intake.fileText} onChange={event => intake.setFileText(event.target.value)} disabled={intake.pending || intake.fileLoading} spellCheck={false} aria-describedby="file-preview-help intake-source-limits" aria-invalid={intake.overLimit || undefined} /></div>
        </div>}
        {intake.hasFilePreview && <p id="file-preview-help" className="field-note">{fixedLayout ? 'The original layout stays attached to this review. Apply decisions after importing; upload a revised file to change the source.' : /\.docx$/i.test(file.name) ? 'Editing Word text may simplify its layout.' : 'Check for anything missing or misread. We’ll save the text with your corrections.'}</p>}
        {intake.fileEdited && <p className="field-note" role="status">Your corrections will be saved.</p>}
      </div> : <><label className="sr-only" htmlFor="source-text">Text to review</label><textarea id="source-text" ref={element => { if (element && restoreFocus.current) { restoreFocus.current = false; element.focus() } }} value={intake.source} placeholder="Write or paste the text you want to review…" onChange={event => { intake.setMode('paste'); intake.setSource(event.target.value) }} required disabled={intake.pending} aria-describedby="intake-source-limits intake-import-help" aria-invalid={intake.overLimit || undefined} spellCheck={false} /></>}
      <div className="studio-source-footer"><span>{file ? 'Review extracted text' : 'Plain text or Markdown'}</span><span id="intake-source-limits" className={intake.overLimit ? 'studio-error' : ''}>{intake.characters.toLocaleString()} / 100,000 characters</span></div>
    </div>
    {intake.overLimit && <p className="studio-error" role="alert">Shorten your text to 100,000 characters or fewer before saving (maximum 1 MiB).</p>}
    <details className="studio-import-help"><summary>{file ? 'File notes & tips' : 'Supported files & limits'}<ChevronDown size={13} /></summary>
      <p id="intake-import-help">You can drop one file anywhere in the editor. Text and Markdown: up to 1 MiB. PDF, Word and images: up to 8 MiB.</p>
      {intake.fileNotes.map(note => <p key={note}>{note}</p>)}<p>Scans support printed English text, up to 10 pages and 8 million pixels per page. Compare the scan with its extracted text before saving.</p>
      <p>Titles are optional. We don’t use the filename as the title.</p>
    </details>
    {dragging && <div className="studio-drop-cover" aria-hidden="true"><Upload size={30} /><strong>Drop to import your document</strong></div>}
  </div>
}
