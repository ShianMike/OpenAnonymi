import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import * as AlertDialog from '@radix-ui/react-alert-dialog'
import { ArrowRight, Download, FilePlus2, Files, RefreshCw, Trash2 } from 'lucide-react'
import type { SessionView } from '../api/client'
import { LoadingState } from '../loading/LoadingState'
import { GlassSelect } from '../ui/GlassSelect'
import { PageHeader } from '../ui/PageHeader'
import { InlineNotice, PanelHeading } from '../ui/WorkspaceControls'
import { UnsavedNavigationPrompt } from '../ui/UnsavedNavigationPrompt'
import { deleteBatch, downloadBatch, retryScan, uploadBatchFile, type OutputMode } from './api'
import { fileSelectionError, reasonNames, stateNames } from './presentation'
import { useBatch } from './useBatch'
import './batches.css'
import '../workspace/documents/documents.css'

export function BatchPage({ session, onUnsavedChange }: { session: SessionView; onUnsavedChange?: (dirty: boolean) => void }) {
  const { batchId = '' } = useParams()
  const navigate = useNavigate()
  const { data, error, refresh } = useBatch(batchId)
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [mode, setMode] = useState<OutputMode>('original')
  const [confirmation, setConfirmation] = useState(false)
  const [progress, setProgress] = useState(0)
  const activeUpload = useRef<AbortController | null>(null)
  const alive = useRef(true)
  const downloadUrl = useRef<string | null>(null)
  const downloadTimer = useRef<number | undefined>(undefined)
  const fileInput = useRef<HTMLInputElement>(null)
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
      activeUpload.current?.abort()
      window.clearTimeout(downloadTimer.current)
      if (downloadUrl.current) URL.revokeObjectURL(downloadUrl.current)
    }
  }, [])
  const batch = data?.batch
  const selectionError = batch ? fileSelectionError(files, batch.documents.length, batch.uploaded_bytes) : null
  const reviewLink = (id: string) => `/documents/${encodeURIComponent(id)}/edit?batch=${encodeURIComponent(batchId)}`
  async function upload() {
    if (!batch || busy || files.length === 0 || selectionError) return
    setBusy('upload')
    setActionError(null)
    setNotice(null)
    setProgress(0)
    let accepted = 0
    try {
      for (const file of files) {
        if (!alive.current) break
        const controller = new AbortController()
        activeUpload.current = controller
        await uploadBatchFile(batchId, file, session.csrf_token, controller.signal)
        accepted += 1
        if (!alive.current) break
        setProgress(accepted)
        refresh()
      }
      if (alive.current) setNotice(`${accepted} document${accepted === 1 ? '' : 's'} uploaded. Scans run automatically; open each document to review the findings.`)
    } catch (cause: unknown) {
      if (alive.current) setActionError(`${accepted} uploaded. ${cause instanceof Error ? cause.message : 'Upload failed.'} The remaining files can be retried.`)
    } finally {
      if (alive.current) {
        setFiles((current) => current.slice(accepted))
        if (fileInput.current) fileInput.current.value = ''
        setBusy(null)
        refresh()
      }
    }
  }
  async function retry(documentId: string) {
    if (busy) return
    setBusy(documentId)
    setActionError(null)
    try { await retryScan(batchId, documentId, session.csrf_token); refresh() }
    catch (cause: unknown) { setActionError(cause instanceof Error ? cause.message : 'Scan could not be retried.') }
    finally { setBusy(null) }
  }
  async function download() {
    if (busy || error || !data?.eligibility.included_count) return
    setBusy('download')
    setActionError(null)
    try {
      const blob = await downloadBatch(batchId, mode, session.csrf_token)
      if (!alive.current) return
      if (downloadUrl.current) URL.revokeObjectURL(downloadUrl.current)
      window.clearTimeout(downloadTimer.current)
      const url = URL.createObjectURL(blob)
      downloadUrl.current = url
      const link = document.createElement('a')
      link.href = url
      link.download = `reviewed-batch-${batchId}.zip`
      document.body.append(link)
      link.click()
      link.remove()
      downloadTimer.current = window.setTimeout(() => { URL.revokeObjectURL(url); downloadUrl.current = null }, 20_000)
      setNotice('Reviewed ZIP generated. Its manifest lists the included versions and reasons for exclusions.')
      refresh()
    } catch (cause: unknown) {
      if (alive.current) { setActionError(cause instanceof Error ? cause.message : 'The archive could not be generated.'); refresh() }
    } finally { if (alive.current) setBusy(null) }
  }
  async function remove() {
    if (busy) return
    setBusy('delete')
    setActionError(null)
    try {
      await deleteBatch(batchId, session.csrf_token)
      navigate('/batches', { replace: true })
    } catch (cause: unknown) { setActionError(cause instanceof Error ? cause.message : 'The batch could not be deleted.') }
    finally { setBusy(null) }
  }
  return <section className="batches-page" aria-labelledby="batch-title">
    <PageHeader title={batch?.name || 'Batch review'} titleId="batch-title" description="Review every document, then download the eligible outputs together." action={<Link to="/batches">All batches</Link>} />
    <UnsavedNavigationPrompt when={files.length > 0} focusBackId="batch-files" onDirtyChange={onUnsavedChange} />
    {error && <InlineNotice error>{error} <button type="button" onClick={refresh}>Reload batch</button></InlineNotice>}
    {actionError && <InlineNotice error>{actionError}</InlineNotice>}
    {notice && <InlineNotice>{notice}</InlineNotice>}
    {!batch && !error && <LoadingState label="Loading batch…" shape="document" />}
    {batch && <>
      <div className="batch-summary workspace-panel">
        <PanelHeading icon={Files} title={`${batch.documents.length} of 20 documents`} description={batch.processing ? 'Scans are processing. This page refreshes while it is visible.' : 'Open a document to make decisions and confirm its full reviewed output.'} />
        <ul className="batch-counts" aria-label="Document status counts">{Object.entries(batch.counts).map(([state, count]) => <li key={state}>{stateNames[state as keyof typeof stateNames]} <strong>{count}</strong></li>)}</ul>
        <div className="batch-actions">{batch.next_document_id && <Link className="button button-primary" to={reviewLink(batch.next_document_id)}>Next needing review <ArrowRight size={16} aria-hidden="true" /></Link>}
          <button type="button" onClick={refresh} disabled={!!busy}><RefreshCw size={16} aria-hidden="true" /> Refresh</button>
        </div>
      </div>
      <div className="batch-work-layout">
        <div className="workspace-panel">
          <PanelHeading icon={FilePlus2} title="Add documents" description="TXT and CSV up to 1 MiB; PDF and DOCX up to 8 MiB. Up to 100,000 extracted characters per document and 40 MiB per batch." />
          <p className="field-note">Shared setup: {batch.settings.categories.length} suggestion categories · {batch.settings.phone_region} phone region · English · {batch.settings.retention_days} days. CSV delimiter and header are detected automatically.</p>
          {batch.documents.length < 20 && batch.uploaded_bytes < 40 * 1024 * 1024 ? <>
            <label htmlFor="batch-files">Choose documents</label>
            <input ref={fileInput} id="batch-files" type="file" multiple accept=".txt,.pdf,.docx,.csv" disabled={!!busy || !!error} onChange={(event) => { setFiles(Array.from(event.target.files ?? [])); setActionError(null) }} />
            {files.length > 0 && <ul className="batch-files-selected">{files.map((file, index) => <li key={index}>{file.name}</li>)}</ul>}
            {selectionError && <p role="alert">{selectionError}</p>}
            <button type="button" className="button button-primary" onClick={() => void upload()} disabled={!!busy || !!error || files.length === 0 || !!selectionError}>{busy === 'upload' ? `Uploading ${progress + 1} of ${files.length}…` : 'Upload documents'}</button>
            {files.length > 0 && <button type="button" disabled={!!busy} onClick={() => { setFiles([]); if (fileInput.current) fileInput.current.value = '' }}>Clear selection</button>}
          </> : <p>This batch has reached its upload limit.</p>}
        </div>
        <div className="workspace-panel batch-download">
          <PanelHeading icon={Download} title="Reviewed outputs" />
          {data && <p className="batch-eligibility" role="status">{data.eligibility.included_count} of {data.eligibility.total_count} documents will be included</p>}
          <p className="field-note">Every included document must be confirmed for its current version and have any required reviewer approval.</p>
          <label htmlFor="batch-output-mode">Output format</label>
          <GlassSelect id="batch-output-mode" value={mode} disabled={!!busy} onValueChange={(value) => setMode(value as OutputMode)}>
            <option value="original">Original type · Word, safe CSV, or TXT</option><option value="txt">TXT for every document</option>
          </GlassSelect>
          <button type="button" className="button button-primary" onClick={() => void download()} disabled={!!busy || !!error || !data?.eligibility.included_count} title={!data?.eligibility.included_count ? 'Confirm a document and obtain any required approval first.' : undefined}>{busy === 'download' ? 'Generating ZIP…' : 'Download reviewed ZIP'}</button>
          {!!data?.eligibility.excluded.length && <details><summary>Why documents are excluded</summary><ul>
            {data.eligibility.excluded.map((row) => <li key={row.document_id}>Document {batch.documents.find((item) => item.id === row.document_id)?.position}: {reasonNames[row.reason]}</li>)}
          </ul></details>}
        </div>
      </div>
      <div className="workspace-panel batch-document-list">
        <h2>Documents in this batch</h2>
        {batch.documents.length === 0 ? <p>No documents uploaded yet.</p> : <ol>
          {batch.documents.map((row) => <li key={row.id} className="batch-document">
            <div><strong>{row.title || `Document ${row.position}`}</strong><span className={`batch-state is-${row.state}`}>{stateNames[row.state]}</span>
              {row.state === 'scan_failed' && <p>{row.last_error_code === 'too_many_suggestions' ? 'More than 1,000 suggestions. Open the document to narrow the categories or edit the source before scanning again.' : 'The scan could not finish. Retry it or open the document to adjust settings.'}</p>}
            </div>
            <div className="batch-actions">
              {row.state !== 'expired' && row.state !== 'deleted' && <Link to={reviewLink(row.id)}>Open document <ArrowRight size={15} aria-hidden="true" /></Link>}
              {row.state === 'scan_failed' && <button type="button" disabled={!!busy} onClick={() => void retry(row.id)}>{busy === row.id ? 'Requeuing…' : 'Retry scan'}</button>}
            </div>
          </li>)}
        </ol>}
      </div>
      <div className="batch-delete"><button type="button" disabled={!!busy || !!error || files.length > 0} onClick={() => { setActionError(null); setConfirmation(true) }}><Trash2 size={16} aria-hidden="true" /> Delete batch</button></div>
      <AlertDialog.Root open={confirmation} onOpenChange={(open) => { if (!busy) setConfirmation(open) }}>
        <AlertDialog.Portal><AlertDialog.Overlay className="document-delete-overlay" /><AlertDialog.Content className="document-delete-dialog" onEscapeKeyDown={(event) => { if (busy) event.preventDefault() }}>
          <AlertDialog.Title>Delete this batch?</AlertDialog.Title><AlertDialog.Description>This deletes all {batch.documents.length} documents in the batch. Access ends immediately and stored content removal begins. Downloaded files remain with their recipients.</AlertDialog.Description>
          {actionError && <p role="alert">{actionError}</p>}
          <div className="document-dialog-actions"><AlertDialog.Cancel asChild><button type="button" disabled={!!busy}>Keep batch</button></AlertDialog.Cancel><button type="button" className="document-confirm-delete" disabled={!!busy} onClick={() => void remove()}>{busy === 'delete' ? 'Deleting…' : 'Delete all documents'}</button></div>
        </AlertDialog.Content></AlertDialog.Portal>
      </AlertDialog.Root>
    </>}
  </section>
}
