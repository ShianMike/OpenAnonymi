import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import './index.css'
import './appearance/theme.css'
import './appearance/display.css'
import App from './App.tsx'
import { RequestFeedback } from './loading/RequestFeedback'

const router = createBrowserRouter([{ path: '*', element: <App /> }])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
    <RequestFeedback />
  </StrictMode>,
)
