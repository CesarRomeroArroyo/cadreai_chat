import { lazy, Suspense } from 'react'

import './App.css'

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

  return (
    <main className="app-shell">
      <header className="app-header">
        <a className="brand" href="/">
          <span className="brand-mark" aria-hidden="true">
            C
          </span>
          <span>
            <strong>CADRE AI</strong>
            <small>Support assistant</small>
          </span>
        </a>
        <span className="status-badge">
          <span className="status-dot" aria-hidden="true" />
          Foundation ready
        </span>
      </header>

      <section className="chat-panel" aria-labelledby="chat-title">
        <div className="chat-intro">
          <p className="eyebrow">Verified answers. Clear sources.</p>
          <h1 id="chat-title">How can we help?</h1>
          <p className="intro-copy">
            Ask about Cadre AI services, industries, or ways to get started. Answers
            will be grounded in approved Cadre AI sources.
          </p>
        </div>

        <div className="message-row" aria-label="Assistant message">
          <div className="assistant-avatar" aria-hidden="true">
            C
          </div>
          <div className="message-content">
            <span className="message-author">Cadre AI Assistant</span>
            <div className="message-bubble">
              <p>
                Welcome. Chat connectivity and source-backed answers will be enabled
                in upcoming implementation phases.
              </p>
            </div>
          </div>
        </div>

        <form className="composer" aria-label="Message composer">
          <label htmlFor="message">Message Cadre AI</label>
          <div className="composer-field">
            <textarea
              id="message"
              name="message"
              placeholder="Chat will be available after the RAG service is connected"
              rows={2}
              disabled
            />
            <button type="submit" disabled aria-label="Send message">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="m5 12 14-7-4 14-3-6-7-1Z" />
              </svg>
            </button>
          </div>
          <p className="composer-note">
            This preview does not call OpenAI, OpenRouter, or any external API.
          </p>
        </form>
      </section>
    </main>
  )
}

export default App
