import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from 'react'

import './App.css'
import {
  ChatApiError,
  type ChatHistoryMessage,
  type ChatSource,
  sendChatMessage,
} from './chatApi'

const MAX_MESSAGE_LENGTH = 2_000
const MAX_HISTORY_MESSAGES = 8
const CITATION_PATTERN = /\s*\[chunk:[0-9a-f]{24}\]/g
const SUGGESTIONS = [
  'What does Cadre AI do?',
  'What is the AI Maturity Index?',
  'How do clients access the portal?',
]

let messageSequence = 0

interface DisplayMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources: ChatSource[]
  abstained?: boolean
  includeInHistory: boolean
}

interface FailedRequest {
  message: string
  history: ChatHistoryMessage[]
}

interface RequestError {
  message: string
  requestId?: string
}

function nextMessageId() {
  messageSequence += 1
  return `message-${messageSequence}`
}

function initialMessages(): DisplayMessage[] {
  return [
    {
      id: nextMessageId(),
      role: 'assistant',
      content:
        'Welcome. Ask about Cadre AI services, industries, assessments, or ways to get started.',
      sources: [],
      includeInHistory: false,
    },
  ]
}

function displayAnswer(content: string) {
  return content.replace(CITATION_PATTERN, '').trim()
}

function SourceCards({ sources }: { sources: ChatSource[] }) {
  if (sources.length === 0) return null
  return (
    <section className="message-sources" aria-label={`${sources.length} verified source${sources.length === 1 ? '' : 's'}`}>
      <span className="sources-label">Verified sources</span>
      <div className="source-card-list">
        {sources.map((source) => {
          const content = (
            <>
              <strong>{source.title}</strong>
              {source.locations.length > 0 ? <span>{source.locations.join(' · ')}</span> : null}
            </>
          )
          return source.url ? (
            <a
              className="source-card"
              href={source.url}
              key={source.source_id}
              target="_blank"
              rel="noreferrer"
            >
              {content}
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M8 16 16 8M10 8h6v6" />
              </svg>
            </a>
          ) : (
            <article className="source-card" key={source.source_id}>
              {content}
            </article>
          )
        })}
      </div>
    </section>
  )
}

function MessageRow({ message }: { message: DisplayMessage }) {
  const assistant = message.role === 'assistant'
  return (
    <article className={`message-row ${assistant ? 'assistant-message' : 'user-message'}`}>
      {assistant ? (
        <div className="assistant-avatar" aria-hidden="true">
          C
        </div>
      ) : null}
      <div className="message-content">
        <span className="message-author">{assistant ? 'Cadre AI Assistant' : 'You'}</span>
        <div className={`message-bubble${message.abstained ? ' abstention-bubble' : ''}`}>
          <p>{assistant ? displayAnswer(message.content) : message.content}</p>
        </div>
        <SourceCards sources={message.sources} />
      </div>
    </article>
  )
}

export default function ChatPage() {
  const [messages, setMessages] = useState<DisplayMessage[]>(initialMessages)
  const [draft, setDraft] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [requestError, setRequestError] = useState<RequestError | null>(null)
  const [failedRequest, setFailedRequest] = useState<FailedRequest | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const errorRef = useRef<HTMLDivElement>(null)
  const activeRequest = useRef<AbortController | null>(null)
  const hasConversation = messages.some((message) => message.includeInHistory)

  useEffect(() => {
    if (requestError) errorRef.current?.focus()
  }, [requestError])

  const history = (): ChatHistoryMessage[] =>
    messages
      .filter((message) => message.includeInHistory)
      .slice(-MAX_HISTORY_MESSAGES)
      .map((message) => ({ role: message.role, content: message.content }))

  const focusComposer = () => requestAnimationFrame(() => textareaRef.current?.focus())

  const runRequest = async (
    question: string,
    requestHistory: ChatHistoryMessage[],
    appendUser: boolean,
  ) => {
    const controller = new AbortController()
    activeRequest.current?.abort()
    activeRequest.current = controller
    setIsSending(true)
    setRequestError(null)
    setFailedRequest(null)
    if (appendUser) {
      setMessages((current) => [
        ...current,
        {
          id: nextMessageId(),
          role: 'user',
          content: question,
          sources: [],
          includeInHistory: true,
        },
      ])
    }
    try {
      const result = await sendChatMessage(question, requestHistory, controller.signal)
      if (activeRequest.current !== controller) return
      setMessages((current) => [
        ...current,
        {
          id: nextMessageId(),
          role: 'assistant',
          content: result.answer,
          sources: result.sources,
          abstained: result.abstained,
          includeInHistory: true,
        },
      ])
      focusComposer()
    } catch (error) {
      if (controller.signal.aborted || activeRequest.current !== controller) return
      const apiError = error instanceof ChatApiError ? error : null
      setRequestError({
        message: apiError?.message ?? 'Connection lost. Check your network and try again.',
        requestId: apiError?.requestId,
      })
      setFailedRequest({ message: question, history: requestHistory })
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null
        setIsSending(false)
      }
    }
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const question = draft.trim()
    if (!question || isSending) return
    const requestHistory = history()
    setDraft('')
    void runRequest(question, requestHistory, true)
  }

  const handleComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      event.currentTarget.form?.requestSubmit()
    }
  }

  const resetConversation = () => {
    activeRequest.current?.abort()
    activeRequest.current = null
    setMessages(initialMessages())
    setDraft('')
    setIsSending(false)
    setRequestError(null)
    setFailedRequest(null)
    focusComposer()
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
        <div className="header-actions">
          <span className="status-badge">
            <span className="status-dot" aria-hidden="true" />
            Verified sources
          </span>
          <button
            className="reset-button"
            type="button"
            onClick={resetConversation}
            disabled={!hasConversation && !isSending && requestError === null}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M4 12a8 8 0 1 0 2.3-5.6L4 8.7M4 4v4.7h4.7" />
            </svg>
            <span>New conversation</span>
          </button>
        </div>
      </header>

      <section className={`chat-panel${hasConversation ? ' has-conversation' : ''}`} aria-labelledby="chat-title">
        <div className="chat-intro">
          <p className="eyebrow">Verified answers. Clear sources.</p>
          <h1 id="chat-title">How can we help?</h1>
          <p className="intro-copy">
            Ask about Cadre AI services, industries, or ways to get started. Every answer is checked against approved material.
          </p>
          {!hasConversation ? (
            <div className="suggestion-list" aria-label="Suggested questions">
              {SUGGESTIONS.map((suggestion) => (
                <button
                  type="button"
                  key={suggestion}
                  onClick={() => {
                    setDraft(suggestion)
                    focusComposer()
                  }}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          ) : null}
        </div>

        <section
          className="conversation"
          aria-label="Conversation"
          aria-live="polite"
          aria-busy={isSending}
        >
          {messages.map((message) => (
            <MessageRow message={message} key={message.id} />
          ))}
          {isSending ? (
            <article className="message-row assistant-message loading-message">
              <div className="assistant-avatar" aria-hidden="true">
                C
              </div>
              <div className="message-content">
                <span className="message-author">Cadre AI Assistant</span>
                <div className="message-bubble">
                  <span>Checking approved sources</span>
                  <span className="loading-dots" aria-hidden="true">
                    <i />
                    <i />
                    <i />
                  </span>
                </div>
              </div>
            </article>
          ) : null}
        </section>

        {requestError ? (
          <div ref={errorRef} className="chat-error" role="alert" tabIndex={-1}>
            <div>
              <strong>Message not answered</strong>
              <p>{requestError.message}</p>
              {requestError.requestId ? <small>Request ID: {requestError.requestId}</small> : null}
            </div>
            {failedRequest ? (
              <button
                type="button"
                onClick={() => void runRequest(failedRequest.message, failedRequest.history, false)}
              >
                Try again
              </button>
            ) : null}
          </div>
        ) : null}

        <form className="composer" aria-label="Message composer" onSubmit={handleSubmit}>
          <label htmlFor="message">Message Cadre AI</label>
          <div className="composer-field">
            <textarea
              ref={textareaRef}
              id="message"
              name="message"
              value={draft}
              maxLength={MAX_MESSAGE_LENGTH}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              placeholder="Ask a question about Cadre AI"
              rows={2}
              disabled={isSending}
              aria-describedby="composer-note"
            />
            <button type="submit" disabled={!draft.trim() || isSending} aria-label="Send message">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="m5 12 14-7-4 14-3-6-7-1Z" />
              </svg>
            </button>
          </div>
          <div className="composer-meta" id="composer-note">
            <span>Enter to send · Shift + Enter for a new line</span>
            <span>{draft.length}/{MAX_MESSAGE_LENGTH}</span>
          </div>
          <p className="composer-note">
            Answers are limited to approved sources and may decline unsupported questions.
          </p>
        </form>
      </section>
    </main>
  )
}
