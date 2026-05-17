import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import ErrorBoundary from './components/ErrorBoundary'

const root = document.getElementById('root')
if (root) {
  root.innerHTML = ''
  createRoot(root).render(
    <StrictMode>
      <ErrorBoundary fallback="App crashed — check console (F12)">
        <App />
      </ErrorBoundary>
    </StrictMode>,
  )
}
