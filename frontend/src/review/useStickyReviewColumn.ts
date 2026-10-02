import { useCallback } from 'react'

export function useStickyReviewColumn() {
  return useCallback((column: HTMLDivElement | null) => {
    if (!column) return
    // A tall column scrolls with the page until its bottom is visible, then
    // follows the sidebar. A shorter column pins below the app header.
    const measure = () => {
      column.style.setProperty('--review-column-height', `${column.getBoundingClientRect().height}px`)
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(column)
    return () => observer.disconnect()
  }, [])
}
