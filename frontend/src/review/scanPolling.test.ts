import { afterEach, expect, it, vi } from 'vitest'
import { ApiRequestError, getScan, type ScanView } from '../api/client'
import { pollScan } from './scanPolling'

vi.mock('../api/client', async importOriginal => ({
  ...await importOriginal<typeof import('../api/client')>(), getScan: vi.fn(),
}))
const scanning = { status: 'scanning' } as ScanView
const completed = { status: 'completed' } as ScanView
afterEach(() => { vi.useRealTimers(); vi.resetAllMocks() })

it('waits between requests and refreshes the review once when scanning finishes', async () => {
  vi.useFakeTimers()
  vi.mocked(getScan).mockResolvedValueOnce(scanning).mockResolvedValue(completed)
  const ready = vi.fn()
  const stop = pollScan('document', ready, vi.fn())
  await vi.advanceTimersByTimeAsync(2000)
  expect(getScan).toHaveBeenCalledTimes(1)
  expect(ready).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(2000)
  expect(ready).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(10000)
  expect(getScan).toHaveBeenCalledTimes(2)
  stop()
})

it('aborts an in-flight request and ignores its late result when the review is left or edited', async () => {
  vi.useFakeTimers()
  let resolve!: (value: ScanView) => void
  vi.mocked(getScan).mockImplementation(() => new Promise(done => { resolve = done }))
  const ready = vi.fn()
  const error = vi.fn()
  const stop = pollScan('document', ready, error)
  await vi.advanceTimersByTimeAsync(6000)
  expect(getScan).toHaveBeenCalledTimes(1)
  const signal = vi.mocked(getScan).mock.calls[0][1]!
  stop()
  expect(signal.aborted).toBe(true)
  resolve(completed)
  await vi.advanceTimersByTimeAsync(10000)
  expect(ready).not.toHaveBeenCalled()
  expect(error).not.toHaveBeenCalled()
  expect(getScan).toHaveBeenCalledTimes(1)
})

it('retries a temporary connection error more slowly', async () => {
  vi.useFakeTimers()
  vi.mocked(getScan).mockRejectedValueOnce(new Error('Offline')).mockResolvedValue(completed)
  const ready = vi.fn()
  const error = vi.fn()
  const stop = pollScan('document', ready, error)
  await vi.advanceTimersByTimeAsync(2000)
  expect(error).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(4999)
  expect(getScan).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(1)
  expect(ready).toHaveBeenCalledTimes(1)
  stop()
})

it.each([401, 403, 404, 410])('stops requesting protected content after status %s', async status => {
  vi.useFakeTimers()
  vi.mocked(getScan).mockRejectedValue(new ApiRequestError(status, 'unavailable', 'Unavailable'))
  const error = vi.fn()
  const stop = pollScan('document', vi.fn(), error)
  await vi.advanceTimersByTimeAsync(20000)
  expect(error).toHaveBeenCalledTimes(1)
  expect(getScan).toHaveBeenCalledTimes(1)
  stop()
})
