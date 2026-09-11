import { lazy, Suspense } from 'react'

import ChatPage from './ChatPage'

const KnowledgePage = lazy(() => import('./KnowledgePage'))

function App() {
  const path = window.location.pathname.replace(/\/+$/, '') || '/'
  if (path === '/knowledge') {
    return (
      <Suspense fallback={<main className="app-shell">Loading knowledge console…</main>}>
        <KnowledgePage />
      </Suspense>
    )
  }

  return <ChatPage />
}

export default App
