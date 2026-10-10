import { ApiRequestError, getScan } from '../api/client'

export function pollScan(documentId: string, onReady: () => void, onError: (cause: unknown) => void) {
  const controller = new AbortController()
  let timer: ReturnType<typeof setTimeout>
  async function check() {
    let delay = 2000
    try {
      const scan = await getScan(documentId, controller.signal)
      if (controller.signal.aborted) return
      if (scan.status !== 'scanning') { onReady(); return }
    } catch (cause: unknown) {
      if (controller.signal.aborted) return
      onError(cause)
      if (cause instanceof ApiRequestError && [401, 403, 404, 410].includes(cause.status)) return
      delay = 5000
    }
    timer = setTimeout(check, delay)
  }
  timer = setTimeout(check, 2000)
  return () => { controller.abort(); clearTimeout(timer) }
}
