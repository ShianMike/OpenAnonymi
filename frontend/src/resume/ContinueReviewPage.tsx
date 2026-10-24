import { Navigate, useLocation } from 'react-router-dom'

// Keep existing bookmarks and sign-in return links on the unified Documents page.
export function ContinueReviewPage() {
  const { search, hash } = useLocation()
  return <Navigate replace to={{ pathname: '/documents', search, hash }} />
}
