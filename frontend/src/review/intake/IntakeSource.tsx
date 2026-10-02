import { LoadingState } from '../../loading/LoadingState'
import { useRef, useState } from 'react'
import { AlignLeft, FileText, Upload, X } from 'lucide-react'
import type { IntakeController } from './useIntake'
import { InlineNotice } from '../../ui/WorkspaceControls'
import { GlassTextarea } from '../../ui/GlassTextarea'

export function IntakeSource({ intake }: { intake: IntakeController }) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  return (
    <div className="intake-editor-panel workspace-panel">
      <div className="intake-editor-heading">
        <span className="panel-heading-icon">
          <FileText size={20} strokeWidth={1.5} aria-hidden="true" />
        </span>
        <div>
          <h2>Your content</h2>
          <p>A note, a transcript, a document. Start here.</p>
        </div>
        <span className="subtle-badge">Private draft</span>
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
              'Paste your text here…\n\nWe’ll help you spot email addresses and phone numbers. You can mark other details during your review.'
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
            <span>TXT · 1 MiB max · PDF / Word DOCX · 8 MiB max</span>
            <label className="intake-file-picker">
              <input
                ref={inputRef}
                id="source-file"
                type="file"
                accept=".txt,.pdf,.docx,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                aria-label="Choose one TXT, PDF or DOCX file"
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
          {intake.fileNotes.map((note) => <p key={note} className="field-note">{note}</p>)}
          {intake.fileText && (
            <>
              <label className="field-label" htmlFor="file-preview">
                Extracted text preview
              </label>
              <GlassTextarea id="file-preview" readOnly value={intake.fileText} />
            </>
          )}
          <p className="field-note">Check the extracted text. Original formatting and metadata are not exported; the reviewed result downloads as TXT. The filename is not saved as your title.</p>
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
