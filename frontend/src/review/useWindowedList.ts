import { useCallback, useLayoutEffect, useMemo, useRef, useState, type FocusEvent } from 'react'

const GAP = 11
const ESTIMATED_HEIGHT = 156
const OVERSCAN = 3

type Entry<T> = { kind: 'row'; item: T; index: number } | { kind: 'spacer'; key: number; height: number }

function firstAfter(offsets: number[], position: number) {
  let low = 0
  let high = offsets.length - 1
  while (low < high) {
    const middle = Math.floor((low + high) / 2)
    if (offsets[middle + 1] <= position) low = middle + 1
    else high = middle
  }
  return low
}

/** Variable-height rows; selected and focused controls remain mounted while scrolling. */
export function useWindowedList<T extends { finding_id: string }>(items: T[], selectedId: string | null) {
  const enabled = items.length >= 100
  const containerRef = useRef<HTMLElement>(null)
  const listRef = useRef<HTMLOListElement>(null)
  const nodes = useRef(new Map<string, HTMLLIElement>())
  const observer = useRef<ResizeObserver | null>(null)
  const [heights, setHeights] = useState(new Map<string, number>())
  const [viewport, setViewport] = useState({ top: 0, height: 600 })
  const [focusedId, setFocusedId] = useState<string | null>(null)
  const lastSelected = useRef<string | null>(null)

  const offsets = useMemo(() => {
    const result = [0]
    for (const item of items) result.push(result[result.length - 1] + (heights.get(item.finding_id) ?? ESTIMATED_HEIGHT) + GAP)
    return result
  }, [items, heights])

  const updateViewport = useCallback(() => {
    const container = containerRef.current
    const list = listRef.current
    if (!container || !list || !container.clientHeight) return
    const listTop = list.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop - container.clientTop
    const next = { top: Math.max(0, container.scrollTop - listTop), height: container.clientHeight }
    setViewport((current) => Math.abs(current.top - next.top) < 0.5 && current.height === next.height ? current : next)
  }, [])

  useLayoutEffect(() => {
    if (!enabled) return
    const container = containerRef.current
    const list = listRef.current
    if (!container || !list) return
    let frame = 0
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(() => { frame = 0; updateViewport() })
    }
    const resize = new ResizeObserver((entries) => {
      const measured = entries.flatMap((entry) => {
        const row = entry.target as HTMLLIElement
        const id = row.dataset.windowFinding
        const height = entry.borderBoxSize[0]?.blockSize ?? row.getBoundingClientRect().height
        return id && height > 0 ? [[id, height] as const] : []
      })
      if (measured.length) setHeights((current) => {
        const changed = measured.filter(([id, height]) => Math.abs((current.get(id) ?? ESTIMATED_HEIGHT) - height) > 0.5)
        if (!changed.length) return current
        const next = new Map(current)
        for (const [id, height] of changed) next.set(id, height)
        return next
      })
      schedule()
    })
    observer.current = resize
    resize.observe(container)
    resize.observe(list)
    for (const node of nodes.current.values()) resize.observe(node)
    container.addEventListener('scroll', schedule, { passive: true })
    updateViewport()
    return () => {
      cancelAnimationFrame(frame)
      container.removeEventListener('scroll', schedule)
      resize.disconnect()
      observer.current = null
    }
  }, [enabled, updateViewport])

  useLayoutEffect(() => {
    if (!enabled || !selectedId || selectedId === lastSelected.current) {
      lastSelected.current = selectedId
      return
    }
    lastSelected.current = selectedId
    const index = items.findIndex((item) => item.finding_id === selectedId)
    const container = containerRef.current
    const list = listRef.current
    if (index < 0 || !container || !list || !container.clientHeight) return
    const listTop = list.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop - container.clientTop
    const top = listTop + offsets[index]
    const bottom = listTop + offsets[index + 1]
    if (top < container.scrollTop) container.scrollTop = top
    else if (bottom > container.scrollTop + container.clientHeight) container.scrollTop = bottom - container.clientHeight
    updateViewport()
  }, [enabled, items, selectedId, offsets, updateViewport])

  const registerRow = useCallback((id: string, node: HTMLLIElement | null) => {
    const previous = nodes.current.get(id)
    if (previous) observer.current?.unobserve(previous)
    if (node) { nodes.current.set(id, node); observer.current?.observe(node) }
    else nodes.current.delete(id)
  }, [])

  const entries = useMemo(() => {
    if (!enabled) return items.map((item, index): Entry<T> => ({ kind: 'row', item, index }))
    const first = Math.max(0, firstAfter(offsets, viewport.top) - OVERSCAN)
    const last = Math.min(items.length, firstAfter(offsets, viewport.top + viewport.height) + OVERSCAN + 1)
    const visible = new Set(Array.from({ length: last - first }, (_, index) => first + index))
    for (const id of [selectedId, focusedId]) {
      const index = items.findIndex((item) => item.finding_id === id)
      if (index >= 0) visible.add(index)
    }
    const result: Entry<T>[] = []
    let next = 0
    for (const index of Array.from(visible).sort((a, b) => a - b)) {
      if (index > next) result.push({ kind: 'spacer', key: next, height: offsets[index] - offsets[next] })
      result.push({ kind: 'row', item: items[index], index })
      next = index + 1
    }
    if (next < items.length) result.push({ kind: 'spacer', key: next, height: offsets[items.length] - offsets[next] })
    return result
  }, [items, enabled, offsets, viewport, selectedId, focusedId])

  const focusId = (target: EventTarget | null) => target instanceof Element
    ? target.closest<HTMLElement>('[data-window-finding]')?.dataset.windowFinding ?? null : null
  const onFocusCapture = (event: FocusEvent<HTMLOListElement>) => setFocusedId(focusId(event.target))
  const onBlurCapture = (event: FocusEvent<HTMLOListElement>) => setFocusedId(focusId(event.relatedTarget))
  return { enabled, entries, containerRef, listRef, registerRow, onFocusCapture, onBlurCapture }
}
