export function pageWindow(total: number, requestedPage: number, pageSize: number) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const page = Math.max(0, Math.min(requestedPage, pages - 1))
  return { page, pages, start: page * pageSize, end: Math.min((page + 1) * pageSize, total) }
}
