import {
  type DragEvent,
  type FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react'

import {
  ApiError,
  type IngestionResult,
  type KnowledgeSource,
  knowledgeApi,
} from './knowledgeApi'
import './KnowledgePage.css'

type AuthState = 'checking' | 'anonymous' | 'authenticated'
type AddMode = 'files' | 'urls'
const DATE_FORMATTER = new Intl.DateTimeFormat('en', { dateStyle: 'medium' })

function Brand() {
  return (
    <a className="brand" href="/" aria-label="Cadre AI support assistant">
      <span className="brand-mark" aria-hidden="true">
        C
      </span>
      <span>
        <strong>CADRE AI</strong>
        <small>Knowledge console</small>
      </span>
    </a>
  )
}

function Spinner() {
  return <span className="spinner" aria-hidden="true" />
}

function ErrorMessage({ message }: { message: string }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    ref.current?.focus()
  }, [message])

  return (
    <div className="error-banner" role="alert" tabIndex={-1} ref={ref}>
      <strong>There was a problem</strong>
      <span>{message}</span>
    </div>
  )
}

function formatError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message
  return 'The request could not be completed.'
}

function LoginPanel({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await knowledgeApi.login(password)
      setPassword('')
      onAuthenticated()
    } catch (cause) {
      setError(formatError(cause))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="knowledge-login-shell">
      <header className="knowledge-login-header">
        <Brand />
        <a className="quiet-link" href="/">
          Return to support
        </a>
      </header>
      <section className="login-layout" aria-labelledby="login-title">
        <div className="login-context">
          <p className="eyebrow">Approved sources only</p>
          <h1 id="login-title">Knowledge, under control.</h1>
          <p>
            Maintain source material used by the Cadre AI assistant. Changes are validated
            before a complete index snapshot becomes active.
          </p>
          <ul className="trust-list" aria-label="Knowledge safeguards">
            <li>Official Cadre AI domains</li>
            <li>Bounded, text-extractable files</li>
            <li>Atomic index updates</li>
          </ul>
        </div>
        <form className="login-card" onSubmit={submit} aria-label="Administrator login">
          <div>
            <span className="card-kicker">Administrator access</span>
            <h2>Sign in to continue</h2>
            <p>Use the administrator password configured on this server.</p>
          </div>
          {error && <ErrorMessage message={error} />}
          <label className="field-label" htmlFor="admin-password">
            Password
          </label>
          <input
            className="text-input"
            id="admin-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          <button className="primary-button" type="submit" disabled={submitting}>
            {submitting && <Spinner />}
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
          <p className="security-note">Session expires automatically. Credentials stay server-side.</p>
        </form>
      </section>
    </main>
  )
}

function ResultList({ results }: { results: IngestionResult[] }) {
  if (!results.length) return null
  return (
    <section className="result-list" aria-labelledby="result-title" aria-live="polite">
      <h3 id="result-title">Latest operation</h3>
      <ul>
        {results.map((result) => (
          <li
            className={`result-item result-${result.status}`}
            key={`${result.source_id}-${result.name}-${result.status}-${result.detail}`}
          >
            <span className="result-status">{result.status}</span>
            <span>
              <strong>{result.name}</strong>
              <small>{result.detail}</small>
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

interface AddSourcesProps {
  busy: boolean
  onBusyChange: (busy: boolean) => void
  onComplete: (results: IngestionResult[]) => Promise<void>
  onError: (message: string) => void
}

function FileSourceForm({ busy, onBusyChange, onComplete, onError }: AddSourcesProps) {
  const [files, setFiles] = useState<File[]>([])
  const [approved, setApproved] = useState(false)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  function addSelected(selected: File[]) {
    setFiles((current) => {
      const known = new Set(current.map((file) => `${file.name}:${file.size}`))
      return [...current, ...selected.filter((file) => !known.has(`${file.name}:${file.size}`))]
    })
  }

  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragging(false)
    addSelected(Array.from(event.dataTransfer.files))
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!approved || files.length === 0) return
    onBusyChange(true)
    onError('')
    try {
      const response = await knowledgeApi.uploadFiles(files)
      setFiles([])
      if (inputRef.current) inputRef.current.value = ''
      setApproved(false)
      await onComplete(response.results)
    } catch (cause) {
      onError(formatError(cause))
    } finally {
      onBusyChange(false)
    }
  }

  return (
    <form onSubmit={submit}>
      <div
        className={`drop-zone${dragging ? ' dragging' : ''}`}
        onDragEnter={() => setDragging(true)}
        onDragLeave={() => setDragging(false)}
        onDragOver={(event) => event.preventDefault()}
        onDrop={drop}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" />
        </svg>
        <strong>Drop files here</strong>
        <span>Markdown, TXT, or text-extractable PDF</span>
        <label className="secondary-button" htmlFor="knowledge-files">
          Choose files
        </label>
        <input
          className="visually-hidden"
          id="knowledge-files"
          ref={inputRef}
          type="file"
          accept=".md,.txt,.pdf,text/markdown,text/plain,application/pdf"
          multiple
          onChange={(event) => addSelected(Array.from(event.target.files ?? []))}
        />
      </div>
      {files.length > 0 && (
        <ul className="pending-files" aria-label="Selected files">
          {files.map((file) => (
            <li key={`${file.name}-${file.size}-${file.lastModified}`}>
              <span>
                <strong>{file.name}</strong>
                <small>{Math.max(1, Math.ceil(file.size / 1024))} KB</small>
              </span>
              <button
                type="button"
                className="remove-button"
                aria-label={`Remove ${file.name}`}
                onClick={() =>
                  setFiles((current) => current.filter((candidate) => candidate !== file))
                }
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <Approval checked={approved} onChange={setApproved} />
      <button
        className="primary-button"
        type="submit"
        disabled={busy || !approved || files.length === 0}
      >
        {busy && <Spinner />}
        {busy
          ? 'Validating and indexing…'
          : `Add ${files.length || ''} file${files.length === 1 ? '' : 's'}`}
      </button>
    </form>
  )
}

function UrlSourceForm({ busy, onBusyChange, onComplete, onError }: AddSourcesProps) {
  const [urls, setUrls] = useState('')
  const [approved, setApproved] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const entries = [...new Set(urls.split('\n').map((url) => url.trim()).filter(Boolean))]
    if (!approved || entries.length === 0) return
    onBusyChange(true)
    onError('')
    try {
      const response = await knowledgeApi.addUrls(entries)
      setUrls('')
      setApproved(false)
      await onComplete(response.results)
    } catch (cause) {
      onError(formatError(cause))
    } finally {
      onBusyChange(false)
    }
  }

  return (
    <form onSubmit={submit}>
      <label className="field-label" htmlFor="source-urls">
        Official Cadre AI URLs
      </label>
      <textarea
        className="text-input url-input"
        id="source-urls"
        value={urls}
        onChange={(event) => setUrls(event.target.value)}
        placeholder={'https://cadreai.com/services\nhttps://cadreai.com/about'}
        rows={6}
        required
      />
      <p className="field-help">Enter one HTTPS URL per line. Redirects remain domain-restricted.</p>
      <Approval checked={approved} onChange={setApproved} />
      <button
        className="primary-button"
        type="submit"
        disabled={busy || !approved || !urls.trim()}
      >
        {busy && <Spinner />}
        {busy ? 'Downloading and indexing…' : 'Add URLs'}
      </button>
    </form>
  )
}

function AddSources(props: AddSourcesProps) {
  const [mode, setMode] = useState<AddMode>('files')

  return (
    <section className="console-card add-card" aria-labelledby="add-source-title">
      <div className="section-heading">
        <div>
          <span className="card-kicker">Ingestion</span>
          <h2 id="add-source-title">Add approved sources</h2>
        </div>
        <span className="step-chip">01</span>
      </div>
      <div className="mode-switch" role="group" aria-label="Source type">
        <button
          type="button"
          className={mode === 'files' ? 'active' : ''}
          aria-pressed={mode === 'files'}
          onClick={() => setMode('files')}
        >
          Files
        </button>
        <button
          type="button"
          className={mode === 'urls' ? 'active' : ''}
          aria-pressed={mode === 'urls'}
          onClick={() => setMode('urls')}
        >
          Web URLs
        </button>
      </div>
      {mode === 'files' ? <FileSourceForm {...props} /> : <UrlSourceForm {...props} />}
    </section>
  )
}

function Approval({ checked, onChange }: { checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="approval-check">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>
        <strong>I confirm these sources are official and approved.</strong>
        <small>Only verified Cadre AI material may enter the assistant knowledge base.</small>
      </span>
    </label>
  )
}

interface SourceListProps {
  sources: KnowledgeSource[]
  busy: boolean
  onDelete: (sourceId: string) => Promise<void>
}

function SourceList({ sources, busy, onDelete }: SourceListProps) {
  const [confirming, setConfirming] = useState<string | null>(null)

  return (
    <section className="console-card sources-card" aria-labelledby="sources-title">
      <div className="section-heading">
        <div>
          <span className="card-kicker">Active index</span>
          <h2 id="sources-title">Approved sources</h2>
        </div>
        <span className="source-count" aria-label={`${sources.length} sources`}>
          {String(sources.length).padStart(2, '0')}
        </span>
      </div>
      {sources.length === 0 ? (
        <div className="empty-state">
          <strong>No sources indexed yet</strong>
          <p>Add an approved file or URL to create the first active snapshot.</p>
        </div>
      ) : (
        <ul className="source-list">
          {sources.map((source) => (
            <li key={source.source_id}>
              <div className="source-main">
                <div className={`source-icon source-${source.kind}`} aria-hidden="true">
                  {source.kind === 'file' ? 'F' : 'W'}
                </div>
                <div>
                  <div className="source-title-row">
                    <strong>{source.title}</strong>
                    <span>{source.kind}</span>
                  </div>
                  <p>{source.locator}</p>
                  <small>
                    {source.chunk_count} {source.chunk_count === 1 ? 'chunk' : 'chunks'} · Updated{' '}
                    {DATE_FORMATTER.format(new Date(source.retrieved_at))}
                  </small>
                </div>
              </div>
              <div className="source-actions">
                {confirming === source.source_id ? (
                  <div className="delete-confirm" role="group" aria-label={`Confirm deletion of ${source.title}`}>
                    <span>Delete?</span>
                    <button
                      type="button"
                      className="danger-button"
                      disabled={busy}
                      onClick={async () => {
                        await onDelete(source.source_id)
                        setConfirming(null)
                      }}
                    >
                      Yes, delete
                    </button>
                    <button type="button" className="text-button" onClick={() => setConfirming(null)}>
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    className="text-button"
                    disabled={busy}
                    onClick={() => setConfirming(source.source_id)}
                  >
                    Delete
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function KnowledgeConsole({ onSessionExpired }: { onSessionExpired: () => void }) {
  const [sources, setSources] = useState<KnowledgeSource[]>([])
  const [results, setResults] = useState<IngestionResult[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)

  async function refresh() {
    const nextSources = await knowledgeApi.listSources()
    setSources(nextSources)
  }

  const handleError = useCallback(
    (cause: unknown) => {
      if (cause instanceof ApiError && cause.status === 401) onSessionExpired()
      setError(formatError(cause))
    },
    [onSessionExpired],
  )

  useEffect(() => {
    let active = true
    knowledgeApi
      .listSources()
      .then((nextSources) => {
        if (active) setSources(nextSources)
      })
      .catch((cause: unknown) => {
        if (active) handleError(cause)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [handleError])

  async function complete(nextResults: IngestionResult[]) {
    setResults(nextResults)
    await refresh()
  }

  async function remove(sourceId: string) {
    setBusy(true)
    setError('')
    try {
      await knowledgeApi.deleteSource(sourceId)
      await refresh()
    } catch (cause) {
      handleError(cause)
    } finally {
      setBusy(false)
    }
  }

  async function rebuild() {
    setBusy(true)
    setError('')
    setResults([])
    try {
      const response = await knowledgeApi.rebuild()
      setResults([
        {
          source_id: null,
          name: 'Full knowledge index',
          status: 'updated',
          detail: `Rebuilt ${response.chunk_count} ${response.chunk_count === 1 ? 'chunk' : 'chunks'}.`,
          chunk_count: response.chunk_count,
        },
      ])
      await refresh()
    } catch (cause) {
      handleError(cause)
    } finally {
      setBusy(false)
    }
  }

  async function logout() {
    setBusy(true)
    try {
      await knowledgeApi.logout()
      onSessionExpired()
    } catch (cause) {
      handleError(cause)
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="knowledge-shell">
      <header className="console-header">
        <Brand />
        <div className="header-actions">
          <span className="secure-badge">
            <span aria-hidden="true" /> Secure session
          </span>
          <button className="text-button" type="button" disabled={busy} onClick={logout}>
            Sign out
          </button>
        </div>
      </header>

      <section className="console-intro" aria-labelledby="console-title">
        <div>
          <p className="eyebrow">Knowledge operations</p>
          <h1 id="console-title">Source control for grounded answers.</h1>
        </div>
        <div className="snapshot-summary">
          <span>Current snapshot</span>
          <strong>{loading ? 'Loading…' : `${sources.length} approved source${sources.length === 1 ? '' : 's'}`}</strong>
          <small>Changes activate only after validation.</small>
        </div>
      </section>

      {error && <ErrorMessage message={error} />}
      <div className="console-grid" aria-busy={busy || loading}>
        <div>
          <AddSources
            busy={busy}
            onBusyChange={setBusy}
            onComplete={complete}
            onError={setError}
          />
          <ResultList results={results} />
        </div>
        <div>
          <SourceList sources={sources} busy={busy} onDelete={remove} />
          <section className="maintenance-card" aria-labelledby="maintenance-title">
            <div>
              <span className="card-kicker">Maintenance</span>
              <h2 id="maintenance-title">Rebuild index</h2>
              <p>Regenerate embeddings from persisted approved source content.</p>
            </div>
            <button className="secondary-button" type="button" disabled={busy} onClick={rebuild}>
              {busy ? 'Working…' : 'Rebuild'}
            </button>
          </section>
        </div>
      </div>
      <p className="console-footer">Cadre AI · Protected knowledge administration</p>
    </main>
  )
}

export default function KnowledgePage() {
  const [auth, setAuth] = useState<AuthState>('checking')
  const expireSession = useCallback(() => setAuth('anonymous'), [])

  useEffect(() => {
    let active = true
    knowledgeApi
      .session()
      .then(() => {
        if (active) setAuth('authenticated')
      })
      .catch(() => {
        if (active) setAuth('anonymous')
      })
    return () => {
      active = false
    }
  }, [])

  if (auth === 'checking') {
    return (
      <main className="knowledge-loading" aria-live="polite">
        <Brand />
        <div>
          <Spinner />
          <span>Checking secure session…</span>
        </div>
      </main>
    )
  }
  if (auth === 'anonymous') {
    return <LoginPanel onAuthenticated={() => setAuth('authenticated')} />
  }
  return <KnowledgeConsole onSessionExpired={expireSession} />
}
