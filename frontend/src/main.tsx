import React from 'react'
import ReactDOM from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import App from './pages/App'
import AppWrap from './pages/_appwrap'
import OAuthCallback from './pages/OAuthCallback'
import 'antd/dist/reset.css'

const router = createBrowserRouter([
  { path: '/', element: <App /> },
  { path: '/oauth/figma/callback', element: <OAuthCallback /> },
])

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppWrap>
      <RouterProvider router={router} />
    </AppWrap>
  </React.StrictMode>
)
